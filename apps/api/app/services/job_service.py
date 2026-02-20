from datetime import datetime, timezone

from celery import Celery
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from libs.common.config import get_settings
from libs.common.db import DownloadJob, JobAIInsight, RateLimitEvent, User
from libs.common.enums import AnalysisStatus, AudioFormat, ErrorCode, JobStatus
from libs.common.job_state import can_transition
from libs.common.rate_limit import RateLimitedError, RateLimiter
from libs.common.schemas import CreateJobRequest
from libs.common.storage import ObjectStorage
from libs.common.url_utils import UnsupportedUrlError, detect_source_site

settings = get_settings()
celery_app = Celery('grab', broker=settings.celery_broker_url, backend=settings.celery_result_backend)


class JobService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.rate_limiter = RateLimiter()

    def create_job(self, user: User, payload: CreateJobRequest) -> DownloadJob:
        try:
            source = detect_source_site(payload.url)
        except UnsupportedUrlError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={'code': ErrorCode.unsupported_url, 'message': str(exc)},
            ) from exc

        try:
            self.rate_limiter.check_and_increment(user.id)
        except RateLimitedError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={'code': ErrorCode.rate_limited, 'message': str(exc)},
            ) from exc

        job = DownloadJob(
            user_id=user.id,
            source_url=payload.url,
            source_site=source.value,
            format=AudioFormat.mp3.value,
            quality='best',
            status=JobStatus.queued.value,
            progress=0,
        )
        self.db.add(job)
        self.db.add(RateLimitEvent(user_id=user.id, action='create_job'))
        self.db.commit()
        self.db.refresh(job)
        self.db.add(
            JobAIInsight(
                job_id=job.id,
                has_cover=False,
                cover_status='pending',
                cover_error_message=None,
                analysis_status=AnalysisStatus.pending.value,
                analysis_mode=payload.analysis_mode.value,
                bpm=None,
                musical_key=None,
                type_beat_name=None,
                final_filename=None,
                model_provider='openai',
                model_name=None,
                analysis_error_code=None,
                analysis_error_message=None,
            )
        )
        self.db.commit()

        task = celery_app.send_task('apps.worker.tasks.process_download_job', args=[job.id])
        job.celery_task_id = task.id
        self.db.commit()
        self.db.refresh(job)
        return job

    def list_jobs(self, user_id: str, limit: int = 20, offset: int = 0) -> tuple[list[DownloadJob], int]:
        q = self.db.query(DownloadJob).filter(DownloadJob.user_id == user_id)
        total = q.count()
        items = q.order_by(DownloadJob.created_at.desc()).offset(offset).limit(limit).all()
        return items, total

    def get_job(self, user_id: str, job_id: str) -> DownloadJob:
        job = self.db.query(DownloadJob).filter(DownloadJob.id == job_id, DownloadJob.user_id == user_id).first()
        if not job:
            raise HTTPException(status_code=404, detail='Job not found')
        if job.status == JobStatus.completed.value and job.storage_key:
            signed_url, expires_at = ObjectStorage().sign_download_url(job.storage_key)
            job.download_url = signed_url
            job.expires_at = expires_at
            self.db.commit()
            self.db.refresh(job)
        elif job.status == JobStatus.completed.value and job.expires_at and job.expires_at < datetime.now(timezone.utc):
            job.download_url = None
            self.db.commit()
            self.db.refresh(job)
        return job

    def cancel_job(self, user_id: str, job_id: str) -> DownloadJob:
        job = self.get_job(user_id, job_id)
        if job.status in {JobStatus.completed.value, JobStatus.failed.value, JobStatus.canceled.value}:
            return job
        if not can_transition(JobStatus(job.status), JobStatus.canceled):
            return job
        if job.celery_task_id:
            celery_app.control.revoke(job.celery_task_id, terminate=True)
        job.status = JobStatus.canceled.value
        job.finished_at = datetime.now(timezone.utc)
        job.progress = 0
        self.db.commit()
        self.db.refresh(job)
        return job
