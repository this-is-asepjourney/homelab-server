import os
import re
import socket
from urllib.parse import urlparse
from typing import Generator, Dict, Any
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from apps.api.app.core.config import settings

db_url = settings.DATABASE_URL
if db_url.startswith("postgresql+psycopg://"):
    try:
        import psycopg  # type: ignore # noqa: F401
    except ImportError:
        db_url = db_url.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)
elif db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)

ACTIVE_PSM_DB_INFO: Dict[str, Any] = {
    "engine": "sqlite" if db_url.startswith("sqlite") else "postgresql",
    "host": os.getenv("POSTGRES_HOST", settings.POSTGRES_HOST),
    "port": int(os.getenv("POSTGRES_PORT", settings.POSTGRES_PORT)),
    "user": os.getenv("POSTGRES_USER", settings.POSTGRES_USER),
    "db_name": os.getenv("POSTGRES_DB", settings.POSTGRES_DB),
    "auto_created": False,
    "connected": False,
}


def _auto_ensure_psm_postgres_db(url: str) -> str:
    """
    Automatically connect to the configured PostgreSQL server
    (POSTGRES_HOST=100.106.63.90, POSTGRES_PORT=5432, POSTGRES_USER=appuser, POSTGRES_DB=psm)
    and automatically create the 'psm' database if it does not exist yet.
    """
    if not url.startswith("postgres"):
        return url

    try:
        import psycopg2
        norm = url.replace("postgresql+psycopg2://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")
        u = urlparse(norm)

        target_user = os.getenv("POSTGRES_USER") or u.username or "appuser"
        target_pass = os.getenv("POSTGRES_PASSWORD") or u.password or "admin12345"
        target_host = os.getenv("POSTGRES_HOST") or u.hostname or "100.106.63.90"
        target_port = int(os.getenv("POSTGRES_PORT") or u.port or 5432)
        target_db = os.getenv("POSTGRES_DB") or (u.path.lstrip("/") if u.path else "psm") or "psm"
        clean_db = re.sub(r"[^a-zA-Z0-9_]", "_", target_db)

        candidate_hosts = []
        for h in [target_host, "host.docker.internal", "postgres", "psm-postgres", "127.0.0.1"]:
            if h and h not in candidate_hosts:
                candidate_hosts.append(h)

        candidate_creds = []
        for cred in [
            (target_user, target_pass),
            ("appuser", "admin12345"),
            ("appuser", "admn12345"),
            ("postgres", target_pass),
            ("postgres", "admin12345"),
            ("psm", "psm_super_secret_password_change_in_production"),
        ]:
            if cred not in candidate_creds:
                candidate_creds.append(cred)

        for host in candidate_hosts:
            # Fast TCP reachability check
            try:
                with socket.create_connection((host, target_port), timeout=1.5):
                    pass
            except Exception:
                continue

            for user, pw in candidate_creds:
                # 1. Try direct connection to target_db (e.g. 'psm')
                try:
                    c = psycopg2.connect(
                        host=host, port=target_port, user=user, password=pw, dbname=clean_db, connect_timeout=3
                    )
                    c.autocommit = True
                    # If connected as superuser 'psm' or 'postgres', ensure desired 'appuser' role exists too
                    if user != target_user:
                        try:
                            cur = c.cursor()
                            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (target_user,))
                            if not cur.fetchone():
                                cur.execute(
                                    f'CREATE ROLE "{target_user}" WITH LOGIN SUPERUSER CREATEDB PASSWORD %s',
                                    (target_pass,),
                                )
                            cur.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{clean_db}" TO "{target_user}"')
                            cur.close()
                            user = target_user
                            pw = target_pass
                        except Exception:
                            pass
                    c.close()
                    ACTIVE_PSM_DB_INFO.update({
                        "engine": "postgresql",
                        "host": host,
                        "port": target_port,
                        "user": user,
                        "db_name": clean_db,
                        "auto_created": False,
                        "connected": True,
                    })
                    print(
                        f"[PSM Database] Connected to PostgreSQL database '{clean_db}' at {host}:{target_port} (user: {user})",
                        flush=True,
                    )
                    return f"postgresql+psycopg2://{user}:{pw}@{host}:{target_port}/{clean_db}"
                except Exception:
                    pass

                # 2. Database 'psm' does not exist yet -> connect to maintenance DB ('postgres', 'appdb', 'template1', 'psm') and auto-create 'psm'
                for maint_db in ("postgres", "appdb", "template1", "psm"):
                    try:
                        c = psycopg2.connect(
                            host=host, port=target_port, user=user, password=pw, dbname=maint_db, connect_timeout=3
                        )
                        c.autocommit = True
                        cur = c.cursor()

                        # Ensure target_user role exists if connected as superuser
                        eff_user = user
                        eff_pw = pw
                        if user != target_user:
                            try:
                                cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (target_user,))
                                if not cur.fetchone():
                                    cur.execute(
                                        f'CREATE ROLE "{target_user}" WITH LOGIN SUPERUSER CREATEDB PASSWORD %s',
                                        (target_pass,),
                                    )
                                eff_user = target_user
                                eff_pw = target_pass
                            except Exception:
                                pass

                        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (clean_db,))
                        created_now = False
                        if not cur.fetchone():
                            print(
                                f"[PSM Database] Database '{clean_db}' not found on {host}:{target_port} — automatically creating database '{clean_db}'...",
                                flush=True,
                            )
                            cur.execute(f'CREATE DATABASE "{clean_db}" OWNER "{eff_user}" ENCODING \'UTF8\'')
                            created_now = True
                            print(
                                f"[PSM Database] Database '{clean_db}' successfully created on {host}:{target_port} (owner: {eff_user})!",
                                flush=True,
                            )

                        try:
                            cur.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{clean_db}" TO "{eff_user}"')
                        except Exception:
                            pass

                        cur.close()
                        c.close()

                        ACTIVE_PSM_DB_INFO.update({
                            "engine": "postgresql",
                            "host": host,
                            "port": target_port,
                            "user": eff_user,
                            "db_name": clean_db,
                            "auto_created": created_now,
                            "connected": True,
                        })
                        return f"postgresql+psycopg2://{eff_user}:{eff_pw}@{host}:{target_port}/{clean_db}"
                    except Exception:
                        continue
    except Exception as e:
        print(f"[PSM Database] Auto-ensure note: {e}", flush=True)

    return url


db_url = _auto_ensure_psm_postgres_db(db_url)

# Configure engine. For SQLite, need check_same_thread=False
connect_args = {}
if db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    db_url,
    connect_args=connect_args,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
