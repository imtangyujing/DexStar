from celery import Celery

from libs.common.config import get_settings

settings = get_settings()
celery_app = Celery('grab-worker', broker=settings.celery_broker_url, backend=settings.celery_result_backend)
celery_app.autodiscover_tasks(['apps.worker'])
