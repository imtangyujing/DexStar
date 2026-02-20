import secrets
from json import dumps

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from apps.api.app.services.auth_service import WechatAuthService
from libs.common.config import get_settings
from libs.common.db import User, get_db
from libs.common.security import create_access_token

router = APIRouter(prefix='/auth', tags=['auth'])


def _get_or_create_user(db: Session, identity: str, email: str, display_name: str) -> User:
    user = db.query(User).filter(User.google_sub == identity).first()
    if user:
        return user
    safe_email = email or f'{identity.replace(":", "_")}@grab.local'
    user = User(google_sub=identity, email=safe_email, display_name=display_name or 'User')
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post('/google/callback')
def google_callback_disabled() -> dict:
    raise HTTPException(status_code=410, detail='Google login is temporarily disabled')


@router.get('/wechat/login-url')
def wechat_login_url() -> dict:
    settings = get_settings()
    service = WechatAuthService()
    state = secrets.token_urlsafe(16)
    if settings.wechat_auth_bypass:
        return {
            'login_url': f'/api/v1/auth/wechat/callback?code=dev-{state}&state={state}',
            'state': state,
            'mode': 'bypass',
        }
    if not settings.wechat_app_id or not settings.wechat_app_secret:
        raise HTTPException(status_code=400, detail='缺少微信登录配置：WECHAT_APP_ID 或 WECHAT_APP_SECRET')
    return {'login_url': service.build_qr_login_url(state=state), 'state': state}


@router.get('/wechat/callback', response_class=HTMLResponse)
def wechat_callback(
    code: str = Query(..., min_length=1),
    state: str = Query(default=''),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    service = WechatAuthService()
    try:
        info = service.exchange_code(code)
    except Exception as exc:
        raise HTTPException(status_code=401, detail='Wechat login failed') from exc

    user = _get_or_create_user(
        db=db,
        identity=f"wechat:{info['openid']}",
        email='',
        display_name=info.get('nickname', 'Wechat User'),
    )
    token = create_access_token(user.id)
    payload = dumps({'type': 'grab_wechat_login', 'access_token': token, 'state': state})
    html = f"""
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>微信登录成功</title>
    <style>
      body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        display: grid;
        place-items: center;
        min-height: 100vh;
        margin: 0;
        background: #f6f7f8;
        color: #111827;
      }}
      .card {{
        padding: 18px 20px;
        border: 1px solid #d1d5db;
        border-radius: 10px;
        background: #ffffff;
      }}
    </style>
  </head>
  <body>
    <div class="card">登录成功，正在返回 GRAB...</div>
    <script>
      (function () {{
        var payload = {payload};
        try {{
          localStorage.setItem('grab_access_token', payload.access_token);
        }} catch (e) {{}}
        try {{
          if (window.parent && window.parent !== window) {{
            window.parent.postMessage(payload, window.location.origin);
          }}
        }} catch (e) {{}}
        try {{
          if (window.opener && !window.opener.closed) {{
            window.opener.postMessage(payload, window.location.origin);
            window.close();
            return;
          }}
        }} catch (e) {{}}
        setTimeout(function () {{
          window.location.href = '/';
        }}, 500);
      }})();
    </script>
  </body>
</html>
"""
    return HTMLResponse(content=html)
