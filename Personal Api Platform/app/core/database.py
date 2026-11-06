"""SQLAlchemy database engine, session factory, and DeclarativeBase."""

from collections.abc import Generator
import socket
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Base class for all PAP SQLAlchemy ORM models."""


def _can_reach_tcp(host: str | None, port: int | None, timeout: float = 1.0) -> bool:
    if not host or not port:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _create_sqlite_engine(url: str):
    connect_args: dict[str, Any] = {"check_same_thread": False}
    if ":memory:" in url:
        eng = create_engine(
            url,
            connect_args=connect_args,
            poolclass=StaticPool,
            future=True,
        )
    else:
        eng = create_engine(
            url,
            connect_args=connect_args,
            future=True,
        )

    @event.listens_for(eng, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return eng


def build_engine(database_url: str | None = None):
    settings = get_settings()
    url = database_url or settings.PAP_DATABASE_URL

    if url.startswith("sqlite"):
        return _create_sqlite_engine(url)

    settings.validate_core_database_target()

    if database_url is None and settings.APP_ENV != "production":
        parsed = urlparse(url)
        if "REPLACE_ME" in url or not _can_reach_tcp(parsed.hostname, parsed.port or 5432):
            return _create_sqlite_engine("sqlite:///./pap_core.db")

    return create_engine(
        url,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.DB_CONNECT_TIMEOUT},
        future=True,
    )


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

