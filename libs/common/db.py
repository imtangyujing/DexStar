from __future__ import annotations

from collections.abc import Generator
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, func, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from libs.common.config import get_settings


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    jobs: Mapped[list['DownloadJob']] = relationship(back_populates='user')


class DownloadJob(Base):
    __tablename__ = 'download_jobs'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    source_url: Mapped[str] = mapped_column(Text())
    source_site: Mapped[str] = mapped_column(String(32), index=True)
    format: Mapped[str] = mapped_column(String(8))
    quality: Mapped[str] = mapped_column(String(32), default='best')
    status: Mapped[str] = mapped_column(String(32), default='queued', index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    storage_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    download_url: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates='jobs')
    ai_insight: Mapped[Optional['JobAIInsight']] = relationship(
        back_populates='job',
        uselist=False,
        cascade='all, delete-orphan',
    )


class JobAIInsight(Base):
    __tablename__ = 'job_ai_insights'

    job_id: Mapped[str] = mapped_column(ForeignKey('download_jobs.id', ondelete='CASCADE'), primary_key=True)
    has_cover: Mapped[bool] = mapped_column(Boolean, default=False)
    cover_status: Mapped[str] = mapped_column(String(32), default='pending')
    cover_error_message: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    analysis_status: Mapped[str] = mapped_column(String(32), default='pending')
    analysis_mode: Mapped[str] = mapped_column(String(32), default='standard')
    bpm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    musical_key: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    type_beat_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    final_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    model_provider: Mapped[str] = mapped_column(String(32), default='openai')
    model_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    analysis_error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    analysis_error_message: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    job: Mapped[DownloadJob] = relationship(back_populates='ai_insight')


class RateLimitEvent(Base):
    __tablename__ = 'rate_limit_events'

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    action: Mapped[str] = mapped_column(String(64), default='create_job')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


settings = get_settings()
engine_kwargs = {'pool_pre_ping': True}
if settings.database_url.startswith('sqlite'):
    engine_kwargs['connect_args'] = {'check_same_thread': False}
engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_job_ai_insights_columns()


def _ensure_job_ai_insights_columns() -> None:
    inspector = inspect(engine)
    if 'job_ai_insights' not in inspector.get_table_names():
        return
    existing = {item['name'] for item in inspector.get_columns('job_ai_insights')}
    statements: list[str] = []
    definitions = {
        'has_cover': "BOOLEAN DEFAULT FALSE",
        'cover_status': "VARCHAR(32) DEFAULT 'pending'",
        'cover_error_message': "TEXT",
        'analysis_status': "VARCHAR(32) DEFAULT 'pending'",
        'analysis_mode': "VARCHAR(32) DEFAULT 'standard'",
        'bpm': "FLOAT",
        'musical_key': "VARCHAR(16)",
        'type_beat_name': "VARCHAR(128)",
        'final_filename': "VARCHAR(255)",
        'model_provider': "VARCHAR(32) DEFAULT 'openai'",
        'model_name': "VARCHAR(128)",
        'analysis_error_code': "VARCHAR(64)",
        'analysis_error_message': "TEXT",
    }
    for col, ddl in definitions.items():
        if col in existing:
            continue
        statements.append(f"ALTER TABLE job_ai_insights ADD COLUMN {col} {ddl}")
    if not statements:
        return
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
