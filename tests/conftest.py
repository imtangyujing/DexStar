import os

import pytest
from fastapi.testclient import TestClient

from libs.common.config import get_settings


@pytest.fixture(scope='session', autouse=True)
def _env_setup():
    os.environ['GOOGLE_AUTH_BYPASS'] = 'true'
    get_settings.cache_clear()


@pytest.fixture()
def client():
    from apps.api.app.main import app
    from libs.common.db import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
