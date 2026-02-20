from libs.common.enums import JobStatus
from libs.common.job_state import can_transition


def test_valid_transitions():
    assert can_transition(JobStatus.queued, JobStatus.downloading)
    assert can_transition(JobStatus.downloading, JobStatus.converting)
    assert can_transition(JobStatus.converting, JobStatus.analyzing)
    assert can_transition(JobStatus.analyzing, JobStatus.uploading)
    assert can_transition(JobStatus.converting, JobStatus.uploading)
    assert can_transition(JobStatus.uploading, JobStatus.completed)


def test_invalid_transitions():
    assert not can_transition(JobStatus.completed, JobStatus.downloading)
    assert not can_transition(JobStatus.failed, JobStatus.completed)
    assert not can_transition(JobStatus.canceled, JobStatus.uploading)
