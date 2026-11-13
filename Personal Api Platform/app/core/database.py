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


def _auto_ensure_pap_postgres_db(url: str) -> str:
    """
    Ensure the target PostgreSQL database (e.g. 'pap_core') exists on the host.
    If it does not exist, connect via a maintenance database (psm, postgres, template1)
    and create it automatically.
    """
    if not url.startswith("postgres"):
        return url

    try:
        import re
        norm = url.replace("postgresql+psycopg://", "postgresql://").replace("postgresql+psycopg2://", "postgresql://")
        u = urlparse(norm)
        target_user = u.username or "appuser"
        target_pass = u.password or "admin12345"
        target_host = u.hostname or "192.168.25.101"
        target_port = int(u.port or 5432)
        target_db = (u.path.lstrip("/") if u.path else "pap_core") or "pap_core"
        clean_db = re.sub(r"[^a-zA-Z0-9_]", "_", target_db)

        if not _can_reach_tcp(target_host, target_port, timeout=1.5):
            return url

        # 1. Try psycopg (v3)
        try:
            import psycopg
            try:
                with psycopg.connect(
                    host=target_host,
                    port=target_port,
                    user=target_user,
                    password=target_pass,
                    dbname=clean_db,
                    connect_timeout=3,
                ):
                    return url
            except Exception:
                pass

            for maint_db in ("psm", "postgres", "template1"):
                try:
                    with psycopg.connect(
                        host=target_host,
                        port=target_port,
                        user=target_user,
                        password=target_pass,
                        dbname=maint_db,
                        connect_timeout=3,
                        autocommit=True,
                    ) as conn:
                        with conn.cursor() as cur:
                            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (clean_db,))
                            if not cur.fetchone():
                                print(
                                    f"[PAP Core] Creating missing PostgreSQL database '{clean_db}'...",
                                    flush=True,
                                )
                                cur.execute(f'CREATE DATABASE "{clean_db}" OWNER "{target_user}" ENCODING \'UTF8\'')
                    return url
                except Exception:
                    continue
        except ImportError:
            try:
                import psycopg2
                try:
                    c = psycopg2.connect(
                        host=target_host,
                        port=target_port,
                        user=target_user,
                        password=target_pass,
                        dbname=clean_db,
                        connect_timeout=3,
                    )
                    c.close()
                    return url
                except Exception:
                    pass

                for maint_db in ("psm", "postgres", "template1"):
                    try:
                        c = psycopg2.connect(
                            host=target_host,
                            port=target_port,
                            user=target_user,
                            password=target_pass,
                            dbname=maint_db,
                            connect_timeout=3,
                        )
                        c.autocommit = True
                        cur = c.cursor()
                        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (clean_db,))
                        if not cur.fetchone():
                            print(
                                f"[PAP Core] Creating missing PostgreSQL database '{clean_db}'...",
                                flush=True,
                            )
                            cur.execute(f'CREATE DATABASE "{clean_db}" OWNER "{target_user}" ENCODING \'UTF8\'')
                        cur.close()
                        c.close()
                        return url
                    except Exception:
                        continue
            except Exception:
                pass
    except Exception as e:
        print(f"[PAP Core] Database auto-provision notice: {e}", flush=True)

    return url


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

    try:
        url = _auto_ensure_pap_postgres_db(url)
        eng = create_engine(
            url,
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_pre_ping=True,
            connect_args={"connect_timeout": settings.DB_CONNECT_TIMEOUT},
            future=True,
        )
        if database_url is None and settings.APP_ENV != "production":
            from sqlalchemy import text
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
        return eng
    except Exception as e:
        print(f"[PAP Core] PostgreSQL fallback to SQLite: {e}", flush=True)
        return _create_sqlite_engine("sqlite:///./pap_core.db")


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

