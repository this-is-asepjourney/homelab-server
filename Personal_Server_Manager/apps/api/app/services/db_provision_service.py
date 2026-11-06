import os
import re
import socket
from urllib.parse import urlparse
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy.orm import Session
from apps.api.app.core.config import settings
from apps.api.app.core.security import encrypt_secret, decrypt_secret
from apps.api.app.models.entities import Project, EnvironmentVariable


def sanitize_db_name(raw_name: str) -> str:
    """Convert any project name into a safe, lowercase PostgreSQL database identifier."""
    if not raw_name:
        return "psm_app_db"
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", raw_name.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        return "psm_app_db"
    if cleaned[0].isdigit():
        cleaned = f"db_{cleaned}"
    return cleaned[:63]


def parse_database_url_Config() -> Dict[str, Any]:
    """Extract PostgreSQL connection parameters from environment and settings.DATABASE_URL."""
    db_url = settings.DATABASE_URL or ""
    parsed_user = None
    parsed_pass = None
    parsed_host = None
    parsed_port = None
    parsed_db = None

    if db_url.startswith("postgres"):
        try:
            normalized = db_url.replace("postgresql+psycopg2://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")
            u = urlparse(normalized)
            parsed_user = u.username
            parsed_pass = u.password
            parsed_host = u.hostname
            parsed_port = u.port
            parsed_db = u.path.lstrip("/") if u.path else None
        except Exception:
            pass

    user = os.getenv("POSTGRES_USER") or parsed_user or settings.POSTGRES_USER or "appuser"
    password = os.getenv("POSTGRES_PASSWORD") or parsed_pass or settings.POSTGRES_PASSWORD or "admin12345"
    configured_host = os.getenv("POSTGRES_HOST") or parsed_host or settings.POSTGRES_HOST or "100.106.63.90"
    port = int(os.getenv("POSTGRES_PORT") or parsed_port or 5432)
    default_db = os.getenv("POSTGRES_DB") or parsed_db or "psm"

    return {
        "user": user,
        "password": password,
        "configured_host": configured_host,
        "port": port,
        "default_db": default_db,
    }


def _try_pg_connect(host: str, port: int, user: str, password: str, dbname: str, timeout: int = 3):
    import psycopg2
    return psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=dbname,
        connect_timeout=timeout,
    )


def find_working_postgres_connection() -> Optional[Dict[str, Any]]:
    """Probe candidate PostgreSQL hosts and credentials to find the active server."""
    cfg = parse_database_url_Config()
    candidate_hosts = []
    for h in [cfg["configured_host"], "postgres", "psm-postgres", "host.docker.internal", "127.0.0.1"]:
        if h and h not in candidate_hosts:
            candidate_hosts.append(h)

    candidate_creds: List[Tuple[str, str]] = [
        (cfg["user"], cfg["password"]),
        ("psm", "psm_super_secret_password_change_in_production"),
        ("appuser", "admin12345"),
        ("postgres", cfg["password"]),
    ]
    unique_creds: List[Tuple[str, str]] = []
    for c in candidate_creds:
        if c not in unique_creds:
            unique_creds.append(c)

    candidate_dbs = []
    for d in [cfg["default_db"], "postgres", "template1", "psm"]:
        if d and d not in candidate_dbs:
            candidate_dbs.append(d)

    for host in candidate_hosts:
        # Fast TCP port reachability pre-check before trying credential combinations
        try:
            with socket.create_connection((host, cfg["port"]), timeout=0.6):
                pass
        except Exception:
            continue

        for user, password in unique_creds:
            for maint_db in candidate_dbs:
                try:
                    conn = _try_pg_connect(host, cfg["port"], user, password, maint_db, timeout=2)
                    conn.close()
                    return {
                        "host": host,
                        "port": cfg["port"],
                        "user": user,
                        "password": password,
                        "maintenance_db": maint_db,
                        "desired_user": cfg["user"],
                        "desired_password": cfg["password"],
                        "external_host": cfg["configured_host"] if cfg["configured_host"] not in ("postgres", "psm-postgres") else host,
                    }
                except Exception:
                    continue
    return None


def ensure_postgres_database(
    target_db_name: str,
    desired_user: Optional[str] = None,
    desired_password: Optional[str] = None,
) -> Dict[str, Any]:
    """Connect to PostgreSQL, create the target role/database if missing, and return database telemetry."""
    clean_db = sanitize_db_name(target_db_name)
    pg_conn_info = find_working_postgres_connection()
    cfg = parse_database_url_Config()

    if not pg_conn_info:
        # Fallback metadata when running unit tests without a live PostgreSQL instance (e.g. SQLite mode)
        eff_user = desired_user or cfg["user"]
        eff_pass = desired_password or cfg["password"]
        eff_host = cfg["configured_host"] or "psm-postgres"
        eff_port = cfg["port"]
        return {
            "connected": False,
            "engine": "postgresql (offline/standby)",
            "exists": False,
            "created": False,
            "db_name": clean_db,
            "host": "psm-postgres",
            "external_host": eff_host,
            "port": eff_port,
            "user": eff_user,
            "password": eff_pass,
            "size_bytes": 0,
            "tables_count": 0,
            "tables": [],
            "connection_url_internal": f"postgresql://{eff_user}:{eff_pass}@psm-postgres:{eff_port}/{clean_db}",
            "connection_url_external": f"postgresql://{eff_user}:{eff_pass}@{eff_host}:{eff_port}/{clean_db}",
            "message": f"Configured to auto-create database '{clean_db}' on deployment.",
        }

    host = pg_conn_info["host"]
    port = pg_conn_info["port"]
    admin_user = pg_conn_info["user"]
    admin_pass = pg_conn_info["password"]
    maint_db = pg_conn_info["maintenance_db"]

    app_user = desired_user or pg_conn_info["desired_user"] or admin_user
    app_pass = desired_password or pg_conn_info["desired_password"] or admin_pass

    created = False
    exists = False
    size_bytes = 0
    tables: List[str] = []

    try:
        conn = _try_pg_connect(host, port, admin_user, admin_pass, maint_db, timeout=5)
        conn.autocommit = True
        cur = conn.cursor()

        # 1. Ensure desired user role exists if different from connected admin_user
        clean_user = re.sub(r"[^a-zA-Z0-9_]", "", app_user) or admin_user
        if clean_user != admin_user:
            try:
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (clean_user,))
                if not cur.fetchone():
                    cur.execute(
                        f'CREATE ROLE "{clean_user}" WITH LOGIN SUPERUSER CREATEDB PASSWORD %s',
                        (app_pass,),
                    )
            except Exception:
                clean_user = admin_user
                app_pass = admin_pass
        else:
            clean_user = admin_user
            app_pass = admin_pass

        # 2. Check if target database exists; if not, create it automatically
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (clean_db,))
        row = cur.fetchone()
        if not row:
            cur.execute(f'CREATE DATABASE "{clean_db}" OWNER "{clean_user}" ENCODING \'UTF8\'')
            created = True
            exists = True
        else:
            exists = True

        # Grant privileges
        try:
            cur.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{clean_db}" TO "{clean_user}"')
        except Exception:
            pass

        # 3. Get database disk size
        try:
            cur.execute("SELECT pg_database_size(%s)", (clean_db,))
            sz_row = cur.fetchone()
            if sz_row and sz_row[0] is not None:
                size_bytes = int(sz_row[0])
        except Exception:
            pass

        cur.close()
        conn.close()

        # 4. Connect to the target database itself to inspect public tables
        try:
            db_conn = _try_pg_connect(host, port, clean_user, app_pass, clean_db, timeout=4)
            db_cur = db_conn.cursor()
            db_cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name ASC"
            )
            tables = [r[0] for r in db_cur.fetchall()]
            db_cur.close()
            db_conn.close()
        except Exception:
            pass

        # Determine best container host for deployed apps
        # Containers attached to 'psm-network' can always reach 'psm-postgres' (or external host if not internal)
        container_host = "psm-postgres" if host in ("postgres", "psm-postgres", "127.0.0.1", "localhost") else host
        external_host = pg_conn_info.get("external_host") or host

        return {
            "connected": True,
            "engine": "postgresql",
            "exists": exists,
            "created": created,
            "db_name": clean_db,
            "host": container_host,
            "external_host": external_host,
            "port": port,
            "user": clean_user,
            "password": app_pass,
            "size_bytes": size_bytes,
            "tables_count": len(tables),
            "tables": tables,
            "connection_url_internal": f"postgresql://{clean_user}:{app_pass}@{container_host}:{port}/{clean_db}",
            "connection_url_external": f"postgresql://{clean_user}:{app_pass}@{external_host}:{port}/{clean_db}",
            "message": (
                f"Database '{clean_db}' was automatically created on PostgreSQL ({container_host}:{port})."
                if created
                else f"Database '{clean_db}' is active and ready on PostgreSQL ({container_host}:{port})."
            ),
        }
    except Exception as e:
        return {
            "connected": False,
            "engine": "postgresql",
            "exists": False,
            "created": False,
            "db_name": clean_db,
            "host": host,
            "external_host": pg_conn_info.get("external_host", host),
            "port": port,
            "user": app_user,
            "password": app_pass,
            "size_bytes": 0,
            "tables_count": 0,
            "tables": [],
            "connection_url_internal": f"postgresql://{app_user}:{app_pass}@psm-postgres:{port}/{clean_db}",
            "connection_url_external": f"postgresql://{app_user}:{app_pass}@{host}:{port}/{clean_db}",
            "message": f"PostgreSQL check error: {e}",
        }


def resolve_project_db_name(project: Project, existing_env: Optional[Dict[str, str]] = None) -> str:
    """Resolve the database name for a project from its environment variables or project name."""
    env_map = existing_env or {}
    if not env_map and project.environment_variables:
        for var in project.environment_variables:
            try:
                env_map[var.key] = decrypt_secret(var.encrypted_value)
            except Exception:
                pass

    for key in ("POSTGRES_DB", "DB_DATABASE", "DB_NAME"):
        val = env_map.get(key, "").strip()
        if val and val not in ("psm", "laravel", "app", "test"):
            return sanitize_db_name(val)

    # Check if DATABASE_URL has a specific db name
    db_url = env_map.get("DATABASE_URL", "").strip()
    if db_url.startswith("postgres"):
        try:
            u = urlparse(db_url)
            path_db = u.path.lstrip("/")
            if path_db and path_db != "psm":
                return sanitize_db_name(path_db)
        except Exception:
            pass

    return sanitize_db_name(project.name)


def build_postgres_env_vars(db_info: Dict[str, Any]) -> Dict[str, str]:
    """Generate comprehensive PostgreSQL environment variables compatible with Laravel, Node, Python, Go, etc."""
    host = db_info.get("host") or "psm-postgres"
    port = str(db_info.get("port") or 5432)
    db_name = db_info.get("db_name") or "psm_app_db"
    user = db_info.get("user") or "psm"
    password = db_info.get("password") or ""
    conn_url = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
    sqlalchemy_url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db_name}"

    return {
        "DATABASE_URL": conn_url,
        "POSTGRES_URL": conn_url,
        "SQLALCHEMY_DATABASE_URI": sqlalchemy_url,
        "POSTGRES_HOST": host,
        "POSTGRES_PORT": port,
        "POSTGRES_DB": db_name,
        "POSTGRES_USER": user,
        "POSTGRES_PASSWORD": password,
        # Laravel / PHP / Standard DB_* variables
        "DB_CONNECTION": "pgsql",
        "DB_HOST": host,
        "DB_PORT": port,
        "DB_DATABASE": db_name,
        "DB_NAME": db_name,
        "DB_USERNAME": user,
        "DB_USER": user,
        "DB_PASSWORD": password,
    }


def provision_and_sync_project_db(
    db: Session,
    project: Project,
    custom_db_name: Optional[str] = None,
    override_existing_env: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """
    Ensure the PostgreSQL database for `project` exists (creating it if missing),
    and sync the PostgreSQL connection variables into the project's encrypted environment variables.
    Returns (db_info, merged_decrypted_env_vars).
    """
    existing_env: Dict[str, str] = {}
    for var in project.environment_variables:
        try:
            existing_env[var.key] = decrypt_secret(var.encrypted_value)
        except Exception:
            pass

    target_db_name = sanitize_db_name(custom_db_name) if custom_db_name else resolve_project_db_name(project, existing_env)
    db_info = ensure_postgres_database(target_db_name)
    pg_env = build_postgres_env_vars(db_info)

    # Merge into existing_env:
    # Always set PG keys if not present, or if override_existing_env is True, or if previous DB_CONNECTION was mysql
    was_mysql = existing_env.get("DB_CONNECTION", "").lower() == "mysql"
    for k, v in pg_env.items():
        if override_existing_env or was_mysql or (k not in existing_env) or not existing_env.get(k):
            existing_env[k] = v

    # Persist back into EnvironmentVariable table
    existing_records = {
        v.key: v for v in db.query(EnvironmentVariable).filter(EnvironmentVariable.project_id == project.id).all()
    }
    for k, val in existing_env.items():
        enc = encrypt_secret(str(val))
        if k in existing_records:
            existing_records[k].encrypted_value = enc
        else:
            db.add(
                EnvironmentVariable(
                    project_id=project.id,
                    key=k,
                    encrypted_value=enc,
                )
            )
    db.commit()

    return db_info, existing_env


def list_all_postgres_databases() -> List[Dict[str, Any]]:
    """Return a list of all non-template databases on the PostgreSQL server with their sizes."""
    pg_conn_info = find_working_postgres_connection()
    if not pg_conn_info:
        return []

    results: List[Dict[str, Any]] = []
    try:
        conn = _try_pg_connect(
            pg_conn_info["host"],
            pg_conn_info["port"],
            pg_conn_info["user"],
            pg_conn_info["password"],
            pg_conn_info["maintenance_db"],
            timeout=4,
        )
        cur = conn.cursor()
        cur.execute(
            "SELECT datname, pg_database_size(datname) "
            "FROM pg_database WHERE datistemplate = false ORDER BY datname ASC"
        )
        for name, sz in cur.fetchall():
            results.append({
                "db_name": name,
                "size_bytes": int(sz or 0),
                "host": pg_conn_info["host"],
                "port": pg_conn_info["port"],
            })
        cur.close()
        conn.close()
    except Exception:
        pass
    return results

