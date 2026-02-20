from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'GRAB API'
    env: str = 'dev'
    jwt_secret: str = 'dev-secret'
    jwt_algorithm: str = 'HS256'
    jwt_exp_minutes: int = 60 * 24 * 7
    auth_disabled: bool = True

    database_url: str = 'sqlite:///./grab.db'
    redis_url: str = 'redis://localhost:6379/0'
    celery_broker_url: str = 'redis://localhost:6379/1'
    celery_result_backend: str = 'redis://localhost:6379/2'

    wechat_app_id: str = ''
    wechat_app_secret: str = ''
    wechat_redirect_uri: str = 'http://localhost:8000/api/v1/auth/wechat/callback'
    wechat_auth_bypass: bool = True

    storage_endpoint: str = 'http://localhost:9000'
    storage_public_endpoint: str = ''
    storage_region: str = 'us-east-1'
    storage_access_key: str = 'minioadmin'
    storage_secret_key: str = 'minioadmin'
    storage_bucket: str = 'grab-audio'
    storage_secure: bool = False
    download_url_ttl_seconds: int = 3600
    object_retention_hours: int = 24

    rate_limit_per_hour: int = 20
    temp_dir: str = '/tmp/grab'
    enable_ai_analysis: bool = True
    enable_ai_naming_fallback: bool = False
    enable_bpm_key_analysis: bool = True
    analysis_bpm_backend: str = 'auto'
    analysis_key_backend: str = 'auto'
    tempo_cnn_graph_path: str = '/opt/grab/models/deeptemp-k16-3.pb'
    keyfinder_cli_bin: str = 'keyfinder-cli'
    keyfinder_timeout_seconds: int = 30
    openai_api_key: str = ''
    openai_base_url: str = 'https://api.openai.com'
    openai_model: str = 'gpt-4.1-mini'
    ai_timeout_seconds: int = 20
    ai_max_retries: int = 2
    copyright_advice_text: str = (
        '尊重音乐版权。本工具仅供个人学习使用，如涉及商业用途，请联系创作者授权。'
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
