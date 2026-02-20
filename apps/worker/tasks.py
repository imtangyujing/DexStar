import shutil
from datetime import datetime, timezone
from pathlib import Path

from celery.utils.log import get_task_logger

from apps.worker.analysis import AudioAnalysisError, analyze_bpm_and_key
from apps.worker.celery_app import celery_app
from apps.worker.media import (
    DownloadError,
    download_source,
    embed_cover_art,
    transcode_audio,
    write_mp3_source_metadata,
)
from apps.worker.naming_ai import (
    build_final_filename,
    extract_type_beat_name_from_title,
    generate_type_beat_name,
    normalize_musical_key,
)
from libs.common.config import get_settings
from libs.common.db import DownloadJob, JobAIInsight, SessionLocal
from libs.common.enums import AnalysisMode, AnalysisStatus, AudioFormat, ErrorCode, JobStatus
from libs.common.job_state import can_transition
from libs.common.storage import ObjectStorage

logger = get_task_logger(__name__)
settings = get_settings()


@celery_app.task(name='apps.worker.tasks.process_download_job', bind=True)
def process_download_job(self, job_id: str) -> None:
    db = SessionLocal()
    storage = ObjectStorage()
    workdir = Path(settings.temp_dir) / job_id
    try:
        storage.ensure_bucket()
        job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
        if not job:
            logger.error('job not found: %s', job_id)
            return
        insight = _get_or_create_insight(db, job.id)
        insight.model_provider = 'rule'
        insight.model_name = 'title_rule'

        if job.status == JobStatus.canceled.value:
            return

        if not can_transition(JobStatus(job.status), JobStatus.downloading):
            return
        job.status = JobStatus.downloading.value
        job.progress = 10
        db.commit()

        artifacts = download_source(job.source_url, str(workdir))
        source_file = artifacts.source_file
        if artifacts.cover_file:
            insight.cover_status = 'pending'
            insight.has_cover = False
            insight.cover_error_message = None
        else:
            insight.cover_status = 'not_found'
            insight.has_cover = False
            insight.cover_error_message = None
        db.commit()

        if not can_transition(JobStatus(job.status), JobStatus.converting):
            return
        job.status = JobStatus.converting.value
        job.progress = 50
        db.commit()

        output_file = transcode_audio(source_file, AudioFormat(job.format), str(workdir))

        upload_filename = f'audio.{job.format}'
        if settings.enable_ai_analysis and job.format == AudioFormat.mp3.value:
            if can_transition(JobStatus(job.status), JobStatus.analyzing):
                job.status = JobStatus.analyzing.value
                job.progress = 65
            insight.analysis_status = AnalysisStatus.analyzing.value
            insight.analysis_error_code = None
            insight.analysis_error_message = None
            db.commit()
            upload_filename = _run_analysis(job, insight, output_file, artifacts.source_title, artifacts.uploader)
            db.commit()
        else:
            insight.analysis_status = AnalysisStatus.pending.value
            insight.bpm = None
            insight.musical_key = None
            insight.type_beat_name = None
            insight.final_filename = upload_filename
            insight.analysis_error_code = None
            insight.analysis_error_message = None
            db.commit()

        if artifacts.cover_file and job.format == AudioFormat.mp3.value:
            try:
                output_file = embed_cover_art(output_file, artifacts.cover_file, str(workdir))
                insight.has_cover = True
                insight.cover_status = 'embedded'
                insight.cover_error_message = None
                logger.info('cover embedded', extra={'job_id': job_id, 'cover_status': 'embedded'})
            except Exception as exc:  # best effort
                insight.has_cover = False
                insight.cover_status = 'failed'
                insight.cover_error_message = str(exc)[:800]
                logger.warning('cover embed failed', extra={'job_id': job_id, 'cover_status': 'failed'})
            db.commit()

        if job.format == AudioFormat.mp3.value:
            try:
                output_file = write_mp3_source_metadata(
                    output_file,
                    source_url=job.source_url,
                    artist=artifacts.uploader,
                    advice=settings.copyright_advice_text,
                )
            except Exception as exc:  # best effort
                logger.warning('metadata write failed', extra={'job_id': job_id, 'error': str(exc)[:200]})

        if not can_transition(JobStatus(job.status), JobStatus.uploading):
            return
        job.status = JobStatus.uploading.value
        job.progress = 80
        db.commit()

        key = f"{job.user_id}/{job.id}/{upload_filename}"
        content_type = 'audio/mpeg' if job.format == 'mp3' else 'audio/wav'
        storage.upload_file(output_file, key=key, content_type=content_type)
        signed_url, expires_at = storage.sign_download_url(key)

        job.storage_key = key
        job.download_url = signed_url
        job.expires_at = expires_at
        job.status = JobStatus.completed.value
        job.progress = 100
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
    except DownloadError as exc:
        code = exc.code.value if isinstance(exc.code, ErrorCode) else ErrorCode.download_failed.value
        _mark_failed(db, job_id, code, str(exc))
    except Exception as exc:  # pragma: no cover
        _mark_failed(db, job_id, ErrorCode.internal_error.value, str(exc))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        db.close()


def _mark_failed(db, job_id: str, code: str, message: str) -> None:
    job = db.query(DownloadJob).filter(DownloadJob.id == job_id).first()
    if not job:
        return
    job.status = JobStatus.failed.value
    job.error_code = code
    job.error_message = message[:800]
    job.finished_at = datetime.now(timezone.utc)
    db.commit()


def _get_or_create_insight(db, job_id: str) -> JobAIInsight:
    insight = db.query(JobAIInsight).filter(JobAIInsight.job_id == job_id).first()
    if insight:
        return insight
    insight = JobAIInsight(
        job_id=job_id,
        has_cover=False,
        cover_status='pending',
        cover_error_message=None,
        analysis_status=AnalysisStatus.pending.value,
        analysis_mode=AnalysisMode.standard.value,
        bpm=None,
        musical_key=None,
        type_beat_name=None,
        final_filename=None,
        model_provider='openai',
        model_name=settings.openai_model,
        analysis_error_code=None,
        analysis_error_message=None,
    )
    db.add(insight)
    db.commit()
    db.refresh(insight)
    return insight


def _run_analysis(
    job: DownloadJob,
    insight: JobAIInsight,
    output_file: str,
    source_title: str,
    uploader: str,
) -> str:
    analysis_mode = (insight.analysis_mode or AnalysisMode.standard.value).lower()
    bpm_backend = 'essentia'
    key_backend = 'none'
    if analysis_mode == AnalysisMode.experimental.value:
        bpm_backend = 'tempo_cnn_vote'

    bpm_value = 0.0
    key_value = None
    error_code = None
    error_message = None
    model_name = 'title_rule'

    if settings.enable_bpm_key_analysis:
        try:
            audio_result = analyze_bpm_and_key(
                output_file,
                bpm_backend_override=bpm_backend,
                key_backend_override=key_backend,
            )
            bpm_value = audio_result.bpm
            key_value = None if key_backend == 'none' else normalize_musical_key(audio_result.musical_key)
        except Exception as exc:
            code = getattr(exc, 'code', None)
            if isinstance(exc, AudioAnalysisError):
                code = exc.code
            error_code = code or 'ANALYSIS_FAILED'
            error_message = str(exc)[:800]
            logger.warning(
                'audio analysis failed; continue with naming fallback',
                extra={'job_id': job.id, 'error_code': error_code},
            )

    rounded_bpm = int(round(bpm_value)) if bpm_value > 0 else None
    type_name = extract_type_beat_name_from_title(source_title)
    if not type_name and settings.enable_ai_naming_fallback:
        try:
            type_name, model_name = generate_type_beat_name(
                source_title=source_title,
                uploader=uploader,
                bpm=rounded_bpm or 0,
                musical_key=key_value or '',
                source_site=job.source_site,
            )
            insight.model_provider = 'openai'
        except Exception as exc:  # pragma: no cover
            if not error_code:
                error_code = getattr(exc, 'code', None) or 'AI_NAME_FAILED'
                error_message = str(exc)[:800]
            logger.warning('ai naming failed; continue with unknown name', extra={'job_id': job.id})

    if not type_name:
        if not error_code:
            error_code = 'TITLE_NAME_NOT_FOUND'
            error_message = 'title naming rule not matched'
        type_name = 'Unknown'

    final_filename = build_final_filename(type_name, rounded_bpm, key_value)
    insight.analysis_status = AnalysisStatus.completed.value
    insight.bpm = bpm_value if bpm_value > 0 else None
    insight.musical_key = key_value
    insight.type_beat_name = type_name
    insight.final_filename = final_filename
    insight.model_name = model_name
    insight.analysis_error_code = error_code
    insight.analysis_error_message = error_message
    logger.info(
        'analysis completed',
        extra={
            'job_id': job.id,
            'analysis_status': insight.analysis_status,
            'model': model_name,
            'fallback_used': type_name == 'Unknown',
        },
    )
    return final_filename
