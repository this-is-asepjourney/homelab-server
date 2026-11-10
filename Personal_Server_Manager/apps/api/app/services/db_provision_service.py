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
    """Convert any project name into a safe, lowercase database identifier."""
    if not raw_name:
        return "psm_app_db"
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", raw_name.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        return "psm_app_db"
    if cleaned[0].isdigit():
        cleaned = f"db_{cleaned}"
    return cleaned[:63]


# ══════════════════════════════════════════════════════════════════════════════
# 1. POSTGRESQL ENGINE
# ══════════════════════════════════════════════════════════════════════════════

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
    configured_host = os.getenv("POSTGRES_HOST") or parsed_host or settings.POSTGRES_HOST or "192.168.25.101"
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
    for h in [cfg["configured_host"], "192.168.25.101", "host.docker.internal", "postgres", "psm-postgres", "127.0.0.1"]:
        if h and h not in candidate_hosts:
            candidate_hosts.append(h)

    candidate_creds: List[Tuple[str, str]] = [
        (cfg["user"], cfg["password"]),
        ("appuser", "admin12345"),
        ("postgres", cfg["password"]),
        ("postgres", "admin12345"),
        ("psm", "psm_super_secret_password_change_in_production"),
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
        try:
            with socket.create_connection((host, cfg["port"]), timeout=0.6):
                pass
        except Exception:
            continue

        for user, password in unique_creds:
            for dbname in candidate_dbs:
                try:
                    conn = _try_pg_connect(host, cfg["port"], user, password, dbname, timeout=2)
                    conn.close()
                    return {
                        "host": host,
                        "port": cfg["port"],
                        "user": user,
                        "password": password,
                        "maintenance_db": dbname,
                    }
                except Exception:
                    continue
    return None


def ensure_postgres_database(db_name: str) -> Dict[str, Any]:
    """Ensure a PostgreSQL database exists, creating it if missing, and inspect tables/size."""
    clean_name = sanitize_db_name(db_name)
    pg_conn_info = find_working_postgres_connection()
    if not pg_conn_info:
        return {
            "db_type": "postgres",
            "db_name": clean_name,
            "host": os.getenv("POSTGRES_HOST", "192.168.25.101"),
            "external_host": os.getenv("HOST_IP", "192.168.25.101"),
            "port": 5432,
            "user": os.getenv("POSTGRES_USER", "appuser"),
            "password": os.getenv("POSTGRES_PASSWORD", "admin12345"),
            "created": False,
            "connected": False,
            "tables": [],
            "tables_count": 0,
            "size_bytes": 0,
            "error": "PostgreSQL host unreachable",
        }

    host = pg_conn_info["host"]
    port = pg_conn_info["port"]
    user = pg_conn_info["user"]
    password = pg_conn_info["password"]
    maintenance_db = pg_conn_info["maintenance_db"]

    try:
        conn = _try_pg_connect(host, port, user, password, maintenance_db, timeout=4)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (clean_name,))
        exists = cur.fetchone() is not None
        created = False
        if not exists:
            cur.execute(f'CREATE DATABASE "{clean_name}" ENCODING \'UTF8\'')
            created = True
        cur.close()
        conn.close()

        # Connect to specific database to inspect tables and storage size
        tables: List[str] = []
        size_bytes = 0
        try:
            db_conn = _try_pg_connect(host, port, user, password, clean_name, timeout=3)
            db_cur = db_conn.cursor()
            db_cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename ASC"
            )
            tables = [row[0] for row in db_cur.fetchall()]
            db_cur.execute("SELECT pg_database_size(%s)", (clean_name,))
            size_row = db_cur.fetchone()
            if size_row and size_row[0]:
                size_bytes = int(size_row[0])
            db_cur.close()
            db_conn.close()
        except Exception:
            pass

        external_host = os.getenv("HOST_IP", "192.168.25.101")
        return {
            "db_type": "postgres",
            "db_name": clean_name,
            "host": host,
            "external_host": external_host,
            "port": port,
            "user": user,
            "password": password,
            "created": created,
            "connected": True,
            "tables": tables,
            "tables_count": len(tables),
            "size_bytes": size_bytes,
        }
    except Exception as e:
        return {
            "db_type": "postgres",
            "db_name": clean_name,
            "host": host,
            "external_host": os.getenv("HOST_IP", "192.168.25.101"),
            "port": port,
            "user": user,
            "password": password,
            "created": False,
            "connected": False,
            "tables": [],
            "tables_count": 0,
            "size_bytes": 0,
            "error": str(e),
        }


def build_postgres_env_vars(db_info: Dict[str, Any]) -> Dict[str, str]:
    host = db_info.get("host") or "192.168.25.101"
    port = str(db_info.get("port") or 5432)
    db_name = db_info.get("db_name") or "psm_app_db"
    user = db_info.get("user") or "appuser"
    password = db_info.get("password") or "admin12345"
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
        "DB_CONNECTION": "pgsql",
        "DB_HOST": host,
        "DB_PORT": port,
        "DB_DATABASE": db_name,
        "DB_NAME": db_name,
        "DB_USERNAME": user,
        "DB_USER": user,
        "DB_PASSWORD": password,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2. MYSQL / MARIADB ENGINE (FLEXIBLE DATABASE)
# ══════════════════════════════════════════════════════════════════════════════

def find_working_mysql_connection() -> Optional[Dict[str, Any]]:
    """Probe MySQL host and credentials with root & appuser candidates."""
    import pymysql

    host = os.getenv("MYSQL_HOST") or os.getenv("STOCK_DB_HOST", "192.168.25.101")
    port = int(os.getenv("MYSQL_PORT") or os.getenv("STOCK_DB_PORT", 3306))
    candidates = [
        (host, port),
        ("192.168.25.101", 3306),
        ("host.docker.internal", 3306),
        ("127.0.0.1", 3306),
    ]
    creds = [
        ("root", os.getenv("MYSQL_ROOT_PASSWORD", "adminroot12345")),
        (os.getenv("MYSQL_USER", "appuser"), os.getenv("MYSQL_PASSWORD", "admin12345")),
        ("root", "adminroot12345"),
        ("root", "admin12345"),
        ("root", "root"),
        ("appuser", "admin12345"),
    ]

    for h, p in candidates:
        try:
            with socket.create_connection((h, p), timeout=0.6):
                pass
        except Exception:
            continue

        for u, pw in creds:
            try:
                conn = pymysql.connect(host=h, port=p, user=u, password=pw, connect_timeout=2)
                conn.close()
                return {"host": h, "port": p, "user": u, "password": pw}
            except Exception:
                continue
    return None


def ensure_mysql_database(db_name: str, target_user: Optional[str] = None) -> Dict[str, Any]:
    """Ensure a project-specific MySQL database exists, creating it if missing and granting privileges to project user, and inspect tables/size."""
    import pymysql

    clean_name = sanitize_db_name(db_name)
    conn_info = find_working_mysql_connection()
    app_user = target_user or os.getenv("MYSQL_USER", "appuser")
    app_pass = os.getenv("MYSQL_PASSWORD", "admin12345")
    external_host = os.getenv("HOST_IP", "192.168.25.101")

    if not conn_info:
        return {
            "db_type": "mysql",
            "db_name": clean_name,
            "host": os.getenv("MYSQL_HOST") or os.getenv("STOCK_DB_HOST", "192.168.25.101"),
            "external_host": external_host,
            "port": 3306,
            "user": app_user,
            "password": app_pass,
            "created": False,
            "connected": False,
            "tables": [],
            "tables_count": 0,
            "size_bytes": 0,
            "error": "MySQL host unreachable",
        }

    host = conn_info["host"]
    port = conn_info["port"]
    user = conn_info["user"]
    password = conn_info["password"]

    try:
        conn = pymysql.connect(host=host, port=port, user=user, password=password, connect_timeout=3)
        cur = conn.cursor()
        cur.execute("SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s", (clean_name,))
        exists = cur.fetchone() is not None
        created = False
        if not exists:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{clean_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            created = True

        # Ensure dedicated project user (appuser) has full rights on this database
        try:
            cur.execute(f"CREATE USER IF NOT EXISTS '{app_user}'@'%' IDENTIFIED BY '{app_pass}';")
            cur.execute(f"GRANT ALL PRIVILEGES ON `{clean_name}`.* TO '{app_user}'@'%';")
            cur.execute("FLUSH PRIVILEGES;")
        except Exception:
            pass

        # Inspect tables and storage size in this database
        tables: List[str] = []
        size_bytes = 0
        try:
            cur.execute(
                "SELECT TABLE_NAME, (DATA_LENGTH + INDEX_LENGTH) "
                "FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE' "
                "ORDER BY TABLE_NAME ASC",
                (clean_name,)
            )
            rows = cur.fetchall()
            for r in rows:
                tables.append(r[0])
                if r[1]:
                    size_bytes += int(r[1])
        except Exception:
            pass

        conn.commit()
        cur.close()
        conn.close()

        return {
            "db_type": "mysql",
            "db_name": clean_name,
            "host": host,
            "external_host": external_host,
            "port": port,
            "user": app_user,
            "password": app_pass,
            "created": created,
            "connected": True,
            "tables": tables,
            "tables_count": len(tables),
            "size_bytes": size_bytes,
        }
    except Exception as e:
        return {
            "db_type": "mysql",
            "db_name": clean_name,
            "host": host,
            "external_host": external_host,
            "port": port,
            "user": app_user,
            "password": app_pass,
            "created": False,
            "connected": False,
            "tables": [],
            "tables_count": 0,
            "size_bytes": 0,
            "error": str(e),
        }


def build_mysql_env_vars(db_info: Dict[str, Any]) -> Dict[str, str]:
    host = db_info.get("host") or "192.168.25.101"
    port = str(db_info.get("port") or 3306)
    db_name = db_info.get("db_name") or "appdb"
    user = db_info.get("user") or os.getenv("MYSQL_USER", "appuser")
    password = db_info.get("password") or os.getenv("MYSQL_PASSWORD", "admin12345")
    conn_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{db_name}"
    standard_url = f"mysql://{user}:{password}@{host}:{port}/{db_name}"

    return {
        "DATABASE_URL": conn_url,
        "MYSQL_URL": standard_url,
        "SQLALCHEMY_DATABASE_URI": conn_url,
        "MYSQL_HOST": host,
        "MYSQL_PORT": port,
        "MYSQL_DATABASE": db_name,
        "MYSQL_USER": user,
        "MYSQL_PASSWORD": password,
        "DB_CONNECTION": "mysql",
        "DB_HOST": host,
        "DB_PORT": port,
        "DB_DATABASE": db_name,
        "DB_NAME": db_name,
        "DB_USERNAME": user,
        "DB_USER": user,
        "DB_PASSWORD": password,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 3. SQLITE ENGINE (FLEXIBLE EMBEDDED FILE DATABASE)
# ══════════════════════════════════════════════════════════════════════════════

def build_sqlite_env_vars(db_name: str) -> Tuple[Dict[str, Any], Dict[str, str]]:
    clean_name = sanitize_db_name(db_name)
    sqlite_file = f"/data/{clean_name}.db"
    conn_url = f"sqlite:////{sqlite_file}"

    tables: List[str] = []
    size_bytes = 0
    for pth in [sqlite_file, f"./data/{clean_name}.db", f"Personal_Server_Manager/data/{clean_name}.db"]:
        if os.path.exists(pth):
            try:
                size_bytes = os.path.getsize(pth)
                import sqlite3
                sconn = sqlite3.connect(pth)
                scur = sconn.cursor()
                scur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name ASC")
                tables = [r[0] for r in scur.fetchall()]
                sconn.close()
                break
            except Exception:
                pass

    db_info = {
        "db_type": "sqlite",
        "db_name": clean_name,
        "file_path": sqlite_file,
        "host": "localhost",
        "external_host": "localhost",
        "port": 0,
        "user": "N/A",
        "created": True,
        "connected": True,
        "tables": tables,
        "tables_count": len(tables),
        "size_bytes": size_bytes,
    }
    env_vars = {
        "DATABASE_URL": conn_url,
        "SQLITE_DATABASE": sqlite_file,
        "SQLITE_DB_PATH": sqlite_file,
        "DB_CONNECTION": "sqlite",
        "DB_DATABASE": sqlite_file,
    }
    return db_info, env_vars


# ══════════════════════════════════════════════════════════════════════════════
# 4. UNIFIED MULTI-DATABASE PROVISIONER & SYNC
# ══════════════════════════════════════════════════════════════════════════════

def resolve_project_db_name(project: Project, env_map: Optional[Dict[str, str]] = None) -> str:
    """Resolve database name specifically for this project (isolated per project, preventing shared appdb)."""
    if project.db_name and project.db_name.strip().lower() != "appdb":
        return sanitize_db_name(project.db_name)

    if env_map:
        for k in ["POSTGRES_DB", "MYSQL_DATABASE", "DB_DATABASE", "DB_NAME"]:
            val = env_map.get(k)
            if val and val.strip().lower() != "appdb":
                return sanitize_db_name(val)

    return sanitize_db_name(project.name)


def provision_and_sync_project_db(
    db: Session,
    project: Project,
    custom_db_name: Optional[str] = None,
    db_type: Optional[str] = None,
    override_existing_env: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """
    Unified provisioner supporting:
      - 'postgres': PostgreSQL database on :5432
      - 'mysql': MySQL database on :3306
      - 'sqlite': Local embedded SQLite file
      - 'none': Stateless / No database required
    """
    existing_env: Dict[str, str] = {}
    for var in project.environment_variables:
        try:
            existing_env[var.key] = decrypt_secret(var.encrypted_value)
        except Exception:
            pass

    target_type = (db_type or project.db_type or "postgres").lower().strip()
    target_db_name = sanitize_db_name(custom_db_name) if custom_db_name else resolve_project_db_name(project, existing_env)

    # 1. Stateless / None
    if target_type in ("none", "stateless", "false"):
        return {"db_type": "none", "db_name": None, "created": False, "status": "stateless"}, existing_env

    # 2. SQLite
    if target_type == "sqlite":
        db_info, generated_env = build_sqlite_env_vars(target_db_name)
    # 3. MySQL
    elif target_type in ("mysql", "mariadb"):
        db_info = ensure_mysql_database(target_db_name)
        generated_env = build_mysql_env_vars(db_info)
    # 4. PostgreSQL (Default)
    else:
        db_info = ensure_postgres_database(target_db_name)
        generated_env = build_postgres_env_vars(db_info)

    # Merge into existing environment
    for k, v in generated_env.items():
        if override_existing_env or (k not in existing_env) or not existing_env.get(k):
            existing_env[k] = v

    # Persist in database
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
    project.db_type = target_type
    project.db_name = target_db_name
    db.commit()

    return db_info, existing_env


def list_all_postgres_databases() -> List[Dict[str, Any]]:
    """Return a list of all non-template databases on the PostgreSQL server."""
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
                "type": "postgres",
            })
        cur.close()
        conn.close()
    except Exception:
        pass
    return results


def list_all_mysql_databases() -> List[Dict[str, Any]]:
    """Return a list of all databases on MySQL server."""
    import pymysql

    conn_info = find_working_mysql_connection()
    if not conn_info:
        return []

    results: List[Dict[str, Any]] = []
    try:
        conn = pymysql.connect(
            host=conn_info["host"],
            port=conn_info["port"],
            user=conn_info["user"],
            password=conn_info["password"],
            connect_timeout=3,
        )
        cur = conn.cursor()
        cur.execute("SHOW DATABASES;")
        for (name,) in cur.fetchall():
            if name not in ("information_schema", "performance_schema", "mysql", "sys"):
                results.append({
                    "db_name": name,
                    "host": conn_info["host"],
                    "port": conn_info["port"],
                    "type": "mysql",
                })
        cur.close()
        conn.close()
    except Exception:
        pass
    return results
