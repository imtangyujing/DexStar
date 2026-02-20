from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from apps.api.app.core.deps import get_current_user
from apps.api.app.services.job_service import JobService
from libs.common.db import User, get_db
from libs.common.schemas import CancelJobResponse, CreateJobRequest, CreateJobResponse, JobResponse, JobsListResponse

router = APIRouter(prefix='/jobs', tags=['jobs'])


def to_job_response(job) -> JobResponse:
    insight = getattr(job, 'ai_insight', None)
    return JobResponse(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        source=job.source_site,
        format=job.format,
        error_code=job.error_code,
        error_message=job.error_message,
        download_url=job.download_url,
        expires_at=job.expires_at,
        has_cover=insight.has_cover if insight else False,
        cover_status=insight.cover_status if insight else 'pending',
        cover_error_message=insight.cover_error_message if insight else None,
        analysis_status=insight.analysis_status if insight else 'pending',
        bpm=insight.bpm if insight else None,
        musical_key=insight.musical_key if insight else None,
        type_beat_name=insight.type_beat_name if insight else None,
        final_filename=insight.final_filename if insight else None,
        analysis_error_code=insight.analysis_error_code if insight else None,
        analysis_error_message=insight.analysis_error_message if insight else None,
        analysis_mode=(insight.analysis_mode if insight and insight.analysis_mode else 'standard'),
    )


@router.post('', response_model=CreateJobResponse)
def create_job(
    payload: CreateJobRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreateJobResponse:
    job = JobService(db).create_job(user, payload)
    return CreateJobResponse(job_id=job.id, status=job.status)


@router.get('/{job_id}', response_model=JobResponse)
def get_job(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> JobResponse:
    job = JobService(db).get_job(user.id, job_id)
    return to_job_response(job)


@router.get('', response_model=JobsListResponse)
def list_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobsListResponse:
    items, total = JobService(db).list_jobs(user.id, limit=limit, offset=offset)
    return JobsListResponse(items=[to_job_response(item) for item in items], total=total)


@router.post('/{job_id}/cancel', response_model=CancelJobResponse)
def cancel_job(job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> CancelJobResponse:
    job = JobService(db).cancel_job(user.id, job_id)
    return CancelJobResponse(job_id=job.id, status=job.status)
