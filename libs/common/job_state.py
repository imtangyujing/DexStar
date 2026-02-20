from libs.common.enums import JobStatus

ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.queued: {JobStatus.downloading, JobStatus.canceled, JobStatus.failed},
    JobStatus.downloading: {JobStatus.converting, JobStatus.failed, JobStatus.canceled},
    JobStatus.converting: {JobStatus.analyzing, JobStatus.uploading, JobStatus.failed, JobStatus.canceled},
    JobStatus.analyzing: {JobStatus.uploading, JobStatus.failed, JobStatus.canceled},
    JobStatus.uploading: {JobStatus.completed, JobStatus.failed, JobStatus.canceled},
    JobStatus.completed: set(),
    JobStatus.failed: set(),
    JobStatus.canceled: set(),
}


def can_transition(current: JobStatus, target: JobStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]
