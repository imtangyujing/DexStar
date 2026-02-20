from libs.common.schemas import CreateJobRequest


def test_create_job_request_url_only():
    payload = CreateJobRequest(url='https://www.youtube.com/watch?v=abc')
    assert payload.url.startswith('https://')
