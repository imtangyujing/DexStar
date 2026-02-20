from enum import Enum


class AudioFormat(str, Enum):
    mp3 = 'mp3'
    wav = 'wav'


class JobStatus(str, Enum):
    queued = 'queued'
    downloading = 'downloading'
    converting = 'converting'
    analyzing = 'analyzing'
    uploading = 'uploading'
    completed = 'completed'
    failed = 'failed'
    canceled = 'canceled'


class SourceSite(str, Enum):
    youtube = 'youtube'
    bilibili = 'bilibili'


class ErrorCode(str, Enum):
    unsupported_url = 'UNSUPPORTED_URL'
    source_restricted = 'SOURCE_RESTRICTED'
    download_failed = 'DOWNLOAD_FAILED'
    transcode_failed = 'TRANSCODE_FAILED'
    rate_limited = 'RATE_LIMITED'
    internal_error = 'INTERNAL_ERROR'


class AnalysisStatus(str, Enum):
    pending = 'pending'
    analyzing = 'analyzing'
    completed = 'completed'
    failed = 'failed'


class AnalysisMode(str, Enum):
    standard = 'standard'
    experimental = 'experimental'
