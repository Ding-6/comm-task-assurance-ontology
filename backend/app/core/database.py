"""SQLAlchemy 引擎、会话与基类。"""
from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """ORM 基类。"""


def _build_engine() -> Engine:
    """构造 SQLAlchemy 引擎。"""
    settings = get_settings()
    return create_engine(
        settings.sqlalchemy_database_uri,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_recycle=settings.pool_recycle,
        pool_pre_ping=True,
        future=True,
    )


engine: Engine = _build_engine()
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=True,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：提供一个数据库会话。"""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
