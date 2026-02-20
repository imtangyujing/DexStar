from urllib.parse import quote

import httpx

from libs.common.config import get_settings


class WechatAuthService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def build_qr_login_url(self, state: str) -> str:
        redirect = quote(self.settings.wechat_redirect_uri, safe='')
        return (
            'https://open.weixin.qq.com/connect/qrconnect'
            f'?appid={self.settings.wechat_app_id}'
            f'&redirect_uri={redirect}'
            '&response_type=code'
            '&scope=snsapi_login'
            f'&state={state}'
            '#wechat_redirect'
        )

    def exchange_code(self, code: str) -> dict:
        if self.settings.wechat_auth_bypass:
            return {
                'openid': f'dev-openid-{code[:12]}',
                'nickname': 'Dev Wechat User',
            }
        token_resp = httpx.get(
            'https://api.weixin.qq.com/sns/oauth2/access_token',
            params={
                'appid': self.settings.wechat_app_id,
                'secret': self.settings.wechat_app_secret,
                'code': code,
                'grant_type': 'authorization_code',
            },
            timeout=10.0,
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()
        if token_data.get('errcode'):
            raise ValueError(token_data.get('errmsg') or 'wechat access_token failed')

        user_resp = httpx.get(
            'https://api.weixin.qq.com/sns/userinfo',
            params={
                'access_token': token_data['access_token'],
                'openid': token_data['openid'],
            },
            timeout=10.0,
        )
        user_resp.raise_for_status()
        user_data = user_resp.json()
        if user_data.get('errcode'):
            raise ValueError(user_data.get('errmsg') or 'wechat userinfo failed')
        return {
            'openid': user_data['openid'],
            'nickname': user_data.get('nickname', 'Wechat User'),
        }
