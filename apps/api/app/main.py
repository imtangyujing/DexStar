from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apps.api.app.api.v1.auth import router as auth_router
from apps.api.app.api.v1.jobs import router as jobs_router
from libs.common.db import init_db
from libs.common.logging import configure_logging

configure_logging()
app = FastAPI(title='GRAB API', version='0.1.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(auth_router, prefix='/api/v1')
app.include_router(jobs_router, prefix='/api/v1')

static_dir = Path(__file__).resolve().parent / 'static'
app.mount('/static', StaticFiles(directory=static_dir), name='static')


@app.on_event('startup')
def on_startup() -> None:
    init_db()


@app.get('/')
def index() -> FileResponse:
    return FileResponse(static_dir / 'index.html')


@app.get('/healthz')
def healthz() -> dict:
    return {'status': 'ok'}
