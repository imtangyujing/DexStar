from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from libs.common.enums import AnalysisMode, AnalysisStatus, AudioFormat, JobStatus, SourceSite


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class CreateJobRequest(BaseModel):
    url: str
    analysis_mode: AnalysisMode = AnalysisMode.standard


class CreateJobResponse(BaseModel):
    job_id: str
    status: JobStatus


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: int
    source: SourceSite
    format: AudioFormat
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    download_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    has_cover: bool = False
    cover_status: str = 'pending'
    cover_error_message: Optional[str] = None
    analysis_status: AnalysisStatus = AnalysisStatus.pending
    bpm: Optional[float] = None
    musical_key: Optional[str] = None
    type_beat_name: Optional[str] = None
    final_filename: Optional[str] = None
    analysis_error_code: Optional[str] = None
    analysis_error_message: Optional[str] = None
    analysis_mode: AnalysisMode = AnalysisMode.standard


class JobsListResponse(BaseModel):
    items: list[JobResponse]
    total: int


class CancelJobResponse(BaseModel):
    job_id: str
    status: JobStatus
