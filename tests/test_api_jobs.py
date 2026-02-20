from libs.common.db import SessionLocal, User
from libs.common.rate_limit import RateLimitedError
from libs.common.security import create_access_token


def _create_user_and_token():
    db = SessionLocal()
    user = User(google_sub='sub-1', email='u@test.dev', display_name='U')
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id)
    db.close()
    return user, token


def test_google_callback_disabled(client):
    res = client.post('/api/v1/auth/google/callback', json={'id_token': 'dev-token'})
    assert res.status_code == 410


def test_wechat_login_url_bypass_mode(client, monkeypatch):
    monkeypatch.setattr('apps.api.app.api.v1.auth.get_settings', lambda: type('S', (), {
        'wechat_auth_bypass': True,
        'wechat_app_id': '',
        'wechat_app_secret': '',
    })())
    res = client.get('/api/v1/auth/wechat/login-url')
    assert res.status_code == 200
    body = res.json()
    assert body['mode'] == 'bypass'
    assert '/api/v1/auth/wechat/callback?code=dev-' in body['login_url']


def test_wechat_login_url(client, monkeypatch):
    monkeypatch.setattr('apps.api.app.api.v1.auth.get_settings', lambda: type('S', (), {
        'wechat_auth_bypass': False,
        'wechat_app_id': 'x',
        'wechat_app_secret': 'y',
    })())
    monkeypatch.setattr(
        'apps.api.app.services.auth_service.WechatAuthService.build_qr_login_url',
        lambda _self, state: f'https://wx.test/login?state={state}',
    )
    res = client.get('/api/v1/auth/wechat/login-url')
    assert res.status_code == 200
    body = res.json()
    assert body['login_url'].startswith('https://wx.test/login')
    assert body['state']


def test_wechat_callback_redirect(client, monkeypatch):
    monkeypatch.setattr(
        'apps.api.app.services.auth_service.WechatAuthService.exchange_code',
        lambda _self, _code: {'openid': 'openid-1', 'nickname': 'Jay'},
    )
    res = client.get('/api/v1/auth/wechat/callback?code=abc&state=s1')
    assert res.status_code == 200
    assert 'grab_wechat_login' in res.text
    assert 'access_token' in res.text


def test_create_and_get_job(client, monkeypatch):
    _, token = _create_user_and_token()

    class FakeLimiter:
        def check_and_increment(self, _user_id):
            return None

    class FakeTaskResult:
        id = 'task-1'

    def fake_send_task(*_args, **_kwargs):
        return FakeTaskResult()

    monkeypatch.setattr('apps.api.app.services.job_service.RateLimiter', FakeLimiter)
    monkeypatch.setattr('apps.api.app.services.job_service.celery_app.send_task', fake_send_task)

    headers = {'Authorization': f'Bearer {token}'}
    create_res = client.post(
        '/api/v1/jobs',
        json={'url': 'https://www.youtube.com/watch?v=abc'},
        headers=headers,
    )
    assert create_res.status_code == 200
    body = create_res.json()
    assert body['status'] == 'queued'

    job_id = body['job_id']
    get_res = client.get(f'/api/v1/jobs/{job_id}', headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()['job_id'] == job_id
    assert get_res.json()['format'] == 'mp3'
    assert get_res.json()['has_cover'] is False
    assert get_res.json()['cover_status'] == 'pending'
    assert get_res.json()['analysis_status'] == 'pending'
    assert get_res.json()['final_filename'] is None
    assert get_res.json()['analysis_mode'] == 'standard'


def test_create_job_with_experimental_mode(client, monkeypatch):
    _, token = _create_user_and_token()

    class FakeLimiter:
        def check_and_increment(self, _user_id):
            return None

    class FakeTaskResult:
        id = 'task-3'

    def fake_send_task(*_args, **_kwargs):
        return FakeTaskResult()

    monkeypatch.setattr('apps.api.app.services.job_service.RateLimiter', FakeLimiter)
    monkeypatch.setattr('apps.api.app.services.job_service.celery_app.send_task', fake_send_task)

    headers = {'Authorization': f'Bearer {token}'}
    create_res = client.post(
        '/api/v1/jobs',
        json={'url': 'https://www.youtube.com/watch?v=abc', 'analysis_mode': 'experimental'},
        headers=headers,
    )
    assert create_res.status_code == 200
    job_id = create_res.json()['job_id']

    get_res = client.get(f'/api/v1/jobs/{job_id}', headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()['analysis_mode'] == 'experimental'


def test_rate_limit_error(client, monkeypatch):
    _, token = _create_user_and_token()

    class FakeLimiter:
        def check_and_increment(self, _user_id):
            raise RateLimitedError('rate limit exceeded')

    monkeypatch.setattr('apps.api.app.services.job_service.RateLimiter', FakeLimiter)

    headers = {'Authorization': f'Bearer {token}'}
    create_res = client.post(
        '/api/v1/jobs',
        json={'url': 'https://www.youtube.com/watch?v=abc'},
        headers=headers,
    )
    assert create_res.status_code == 429


def test_create_job_without_auth_when_auth_disabled(client, monkeypatch):
    class FakeLimiter:
        def check_and_increment(self, _user_id):
            return None

    class FakeTaskResult:
        id = 'task-2'

    def fake_send_task(*_args, **_kwargs):
        return FakeTaskResult()

    monkeypatch.setattr('apps.api.app.services.job_service.RateLimiter', FakeLimiter)
    monkeypatch.setattr('apps.api.app.services.job_service.celery_app.send_task', fake_send_task)

    create_res = client.post(
        '/api/v1/jobs',
        json={'url': 'https://www.youtube.com/watch?v=abc'},
    )
    assert create_res.status_code == 200
    body = create_res.json()
    assert body['status'] == 'queued'
