import os
import shutil
import zipfile
import subprocess
import re
import time
from typing import Callable, Optional, Dict, Any, List, Tuple
from apps.agent.app.deployment.dockerfile_generator import (
    ensure_dockerfile_and_ignore,
    generate_dockerignore,
    detect_project_stack,
    generate_dockerfile,
)


def should_log_build_line(line: str) -> bool:
    if not line:
        return False
    # Skip high-frequency BuildKit transfer/progress ticks that flood and bloat the database
    if re.search(r"^\s*#\d+\s+(?:transferring|extracting|preparing)\b", line, re.I):
        return False
    if re.search(r"^\s*#\d+\s+\[.*\]\s+\d+\.\d+s\s*$", line):
        return False
    return True


class DeploymentEngine:
    @staticmethod
    def sanitize_db_name(raw_name: str) -> str:
        """Convert any project name into a valid PostgreSQL database identifier."""
        if not raw_name:
            return "psm_app_db"
        cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", raw_name.strip().lower())
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        if not cleaned:
            return "psm_app_db"
        if cleaned[0].isdigit():
            cleaned = f"db_{cleaned}"
        return cleaned[:63]

    @staticmethod
    def safe_extract_zip(zip_path: str, target_dir: str) -> bool:
        """Safely extract ZIP archive preventing Zip Slip vulnerabilities."""
        os.makedirs(target_dir, exist_ok=True)
        resolved_target = os.path.abspath(target_dir)

        with zipfile.ZipFile(zip_path, "r") as archive:
            for member in archive.infolist():
                member_path = os.path.abspath(os.path.join(target_dir, member.filename))
                if not member_path.startswith(resolved_target + os.sep) and member_path != resolved_target:
                    raise ValueError(f"Zip slip vulnerability detected in member: {member.filename}")
                archive.extract(member, target_dir)
        return True

    @staticmethod
    def write_env_file(workspace_dir: str, env_vars: Optional[Dict[str, str]] = None) -> None:
        """
        Write decrypted environment variables to .env in workspace.
        If .env.example exists in workspace_dir, preserves non-conflicting framework defaults
        (such as APP_NAME, APP_KEY, LOG_CHANNEL) and overrides database & custom keys.
        """
        if not env_vars:
            return

        merged: Dict[str, str] = {}
        env_example_path = os.path.join(workspace_dir, ".env.example")
        if os.path.exists(env_example_path):
            try:
                with open(env_example_path, "r", encoding="utf-8", errors="ignore") as f:
                    for raw_line in f:
                        line = raw_line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            merged[k.strip()] = v.strip()
            except Exception:
                pass

        for k, v in env_vars.items():
            clean_k = str(k).strip()
            clean_v = str(v).replace("\n", "\\n")
            merged[clean_k] = clean_v

        env_path = os.path.join(workspace_dir, ".env")
        lines = [f"{k}={v}" for k, v in merged.items()]
        with open(env_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")

    @staticmethod
    def _auto_wire_silo_storage(
        project_name: str,
        merged_env: Dict[str, str],
        env_example_hint: Dict[str, str],
        log_callback: Callable[[str, str], None],
    ) -> None:
        """
        Automatically configures Silo (MinIO) S3 object storage for projects that use S3 or cloud storage.
        Ensures bucket exists in MinIO with download permissions.
        """
        has_s3_hint = (
            merged_env.get("FILESYSTEM_DISK") == "s3"
            or env_example_hint.get("FILESYSTEM_DISK") == "s3"
            or "AWS_BUCKET" in merged_env
            or "AWS_BUCKET" in env_example_hint
            or "AWS_ACCESS_KEY_ID" in env_example_hint
            or "AWS_ENDPOINT" in env_example_hint
        )
        if not has_s3_hint:
            return

        clean_bucket = re.sub(r"[^a-z0-9-]", "-", project_name.lower().strip()).strip("-")
        minio_host = os.getenv("HOST_IP", "192.168.25.101")
        minio_port = os.getenv("MINIO_PORT", "9000")
        target_bucket = env_example_hint.get("AWS_BUCKET") or merged_env.get("AWS_BUCKET") or clean_bucket
        if not target_bucket:
            target_bucket = clean_bucket

        silo_vars = {
            "FILESYSTEM_DISK": "s3",
            "AWS_ACCESS_KEY_ID": os.getenv("MINIO_ROOT_USER", "admin"),
            "AWS_SECRET_ACCESS_KEY": os.getenv("MINIO_ROOT_PASSWORD", "admin12345"),
            "AWS_DEFAULT_REGION": "us-east-1",
            "AWS_BUCKET": target_bucket,
            "AWS_ENDPOINT": env_example_hint.get("AWS_ENDPOINT") or merged_env.get("AWS_ENDPOINT") or f"http://{minio_host}:{minio_port}",
            "AWS_URL": env_example_hint.get("AWS_URL") or merged_env.get("AWS_URL") or f"http://{minio_host}:{minio_port}/{target_bucket}",
            "AWS_USE_PATH_STYLE_ENDPOINT": "true",
        }
        for k, v in silo_vars.items():
            if k not in merged_env or not merged_env.get(k):
                merged_env[k] = v

        # Attempt to auto-create bucket in MinIO / Silo
        try:
            import docker
            client = docker.from_env()
            for mc_cand in ["homelab_minio_init", "homelab_minio", "minio"]:
                try:
                    mcont = client.containers.get(mc_cand)
                    if mcont.status == "running":
                        cmd = f"mc mb myminio/{target_bucket} --ignore-existing && mc anonymous set download myminio/{target_bucket}"
                        mcont.exec_run(["sh", "-c", cmd])
                        break
                except Exception:
                    pass
        except Exception:
            pass

        log_callback("info", f"[Storage] Auto-wired Silo / MinIO S3 bucket '{target_bucket}' ({minio_host}:{minio_port}).")

    @staticmethod
    def ensure_project_db(
        project_name: str,
        env_vars: Optional[Dict[str, str]],
        db_config: Optional[Dict[str, Any]],
        log_callback: Callable[[str, str], None],
        workspace_dir: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        Unified multi-database provisioner & auto-connect helper for deployed projects.
        Supports:
          - 'mysql' / 'mariadb': Verifies / creates MySQL DB and sets MySQL connection credentials
          - 'sqlite': Configures embedded SQLite file
          - 'none' / 'stateless': Skips database injection
          - 'postgres': Configures PostgreSQL DB
        """
        merged_env = dict(env_vars or {})
        cfg = dict(db_config or {})

        # Inspect workspace .env.example to detect project's native database preference
        env_example_hint: Dict[str, str] = {}
        if workspace_dir:
            ex_path = os.path.join(workspace_dir, ".env.example")
            if os.path.exists(ex_path):
                try:
                    with open(ex_path, "r", encoding="utf-8", errors="ignore") as f:
                        for raw_line in f:
                            line = raw_line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                k, v = line.split("=", 1)
                                env_example_hint[k.strip()] = v.strip()
                except Exception:
                    pass

        # Determine target db_type
        # If user explicitly configured db_type (e.g. postgres, mysql, sqlite, none) via UI/API,
        # that choice MUST be respected with absolute priority and NEVER overridden by framework templates or .env.example.
        explicit_db_type = (cfg.get("db_type") or "").strip().lower()
        if explicit_db_type in ("postgres", "postgresql", "pgsql"):
            db_type = "postgres"
        elif explicit_db_type in ("mysql", "mariadb"):
            db_type = "mysql"
        elif explicit_db_type == "sqlite":
            db_type = "sqlite"
        elif explicit_db_type in ("none", "stateless", "false"):
            db_type = "none"
        else:
            # Fallback ONLY when explicit_db_type was not set or empty
            if "DB_CONNECTION" in merged_env and merged_env["DB_CONNECTION"]:
                db_conn = merged_env["DB_CONNECTION"].lower().strip()
                db_type = "postgres" if db_conn in ("pgsql", "postgres", "postgresql") else ("mysql" if db_conn in ("mysql", "mariadb") else db_conn)
            elif "DB_CONNECTION" in env_example_hint and env_example_hint["DB_CONNECTION"]:
                db_conn = env_example_hint["DB_CONNECTION"].lower().strip()
                db_type = "postgres" if db_conn in ("pgsql", "postgres", "postgresql") else ("mysql" if db_conn in ("mysql", "mariadb") else db_conn)
            elif "MYSQL_DATABASE" in env_example_hint and "POSTGRES_DB" not in env_example_hint:
                db_type = "mysql"
            else:
                db_type = "postgres"

        # 1. Stateless / None
        if db_type in ("none", "stateless", "false"):
            log_callback("info", "[Database] Mode stateless — project berjalan tanpa database.")
            DeploymentEngine._auto_wire_silo_storage(project_name, merged_env, env_example_hint, log_callback)
            return merged_env

        # 2. SQLite
        if db_type == "sqlite":
            clean_db = DeploymentEngine.sanitize_db_name(cfg.get("db_name") or project_name)
            sqlite_file = f"/data/{clean_db}.db"
            merged_env["DB_CONNECTION"] = "sqlite"
            merged_env["DB_DATABASE"] = sqlite_file
            merged_env["DATABASE_URL"] = f"sqlite:////{sqlite_file}"
            log_callback("info", f"[SQLite] Konfigurasi database SQLite embedded disiapkan ({sqlite_file}).")
            DeploymentEngine._auto_wire_silo_storage(project_name, merged_env, env_example_hint, log_callback)
            return merged_env

        # 3. MySQL / MariaDB
        if db_type in ("mysql", "mariadb"):
            target_db = DeploymentEngine.sanitize_db_name(
                cfg.get("db_name")
                or merged_env.get("MYSQL_DATABASE")
                or merged_env.get("DB_DATABASE")
                or env_example_hint.get("DB_DATABASE")
                or env_example_hint.get("MYSQL_DATABASE")
                or project_name
            )
            my_user = cfg.get("user") or os.getenv("MYSQL_USER") or merged_env.get("DB_USERNAME") or env_example_hint.get("DB_USERNAME") or "appuser"
            my_pass = cfg.get("password") or os.getenv("MYSQL_PASSWORD") or merged_env.get("DB_PASSWORD") or env_example_hint.get("DB_PASSWORD") or "admin12345"
            my_port = str(cfg.get("port") or os.getenv("MYSQL_PORT") or 3306)
            my_host = cfg.get("host") or os.getenv("MYSQL_HOST") or os.getenv("HOST_IP") or "192.168.25.101"

            # Auto-create MySQL database if not exists
            db_verified = False
            try:
                import pymysql
                m_conn = pymysql.connect(
                    host=my_host,
                    port=int(my_port),
                    user="root",
                    password=os.getenv("MYSQL_ROOT_PASSWORD", "adminroot12345"),
                    connect_timeout=3
                )
                m_cur = m_conn.cursor()
                m_cur.execute(f"CREATE DATABASE IF NOT EXISTS `{target_db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
                try:
                    m_cur.execute(f"CREATE USER IF NOT EXISTS '{my_user}'@'%' IDENTIFIED BY '{my_pass}';")
                    m_cur.execute(f"GRANT ALL PRIVILEGES ON `{target_db}`.* TO '{my_user}'@'%';")
                    m_cur.execute("FLUSH PRIVILEGES;")
                except Exception:
                    pass
                m_conn.commit()
                m_cur.close()
                m_conn.close()
                db_verified = True
                log_callback("info", f"[MySQL] Database '{target_db}' diverifikasi via PyMySQL ({my_host}:{my_port}).")
            except Exception:
                pass

            # Fallback via Docker container exec
            if not db_verified:
                try:
                    import docker
                    client = docker.from_env()
                    for c_candidate in ["homelab-mysql", "homelab_mysql", "mysql"]:
                        try:
                            mysql_cont = client.containers.get(c_candidate)
                            if mysql_cont.status == "running":
                                root_pw = os.getenv("MYSQL_ROOT_PASSWORD", "adminroot12345")
                                sql = f"CREATE DATABASE IF NOT EXISTS `{target_db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; CREATE USER IF NOT EXISTS '{my_user}'@'%' IDENTIFIED BY '{my_pass}'; GRANT ALL PRIVILEGES ON `{target_db}`.* TO '{my_user}'@'%'; FLUSH PRIVILEGES;"
                                cmd = f'mysql -uroot -p"{root_pw}" -e "{sql}"'
                                c_res = mysql_cont.exec_run(["sh", "-c", cmd])
                                if c_res.exit_code == 0:
                                    db_verified = True
                                    log_callback("info", f"[MySQL] Database '{target_db}' aktif & diverifikasi via container '{c_candidate}'.")
                                break
                        except Exception:
                            pass
                except Exception:
                    pass

            conn_url = f"mysql+pymysql://{my_user}:{my_pass}@{my_host}:{my_port}/{target_db}"
            std_url = f"mysql://{my_user}:{my_pass}@{my_host}:{my_port}/{target_db}"

            my_vars = {
                "DATABASE_URL": conn_url,
                "MYSQL_URL": std_url,
                "SQLALCHEMY_DATABASE_URI": conn_url,
                "DB_CONNECTION": "mysql",
                "DB_HOST": my_host,
                "DB_PORT": my_port,
                "DB_DATABASE": target_db,
                "DB_NAME": target_db,
                "DB_USERNAME": my_user,
                "DB_USER": my_user,
                "DB_PASSWORD": my_pass,
                "MYSQL_HOST": my_host,
                "MYSQL_PORT": my_port,
                "MYSQL_DATABASE": target_db,
                "MYSQL_USER": my_user,
                "MYSQL_PASSWORD": my_pass,
            }
            for k, v in my_vars.items():
                if k not in merged_env or not merged_env.get(k):
                    merged_env[k] = v

            log_callback("info", f"[MySQL] Auto-connected project ke MySQL database '{target_db}'.")
            DeploymentEngine._auto_wire_silo_storage(project_name, merged_env, env_example_hint, log_callback)
            return merged_env

        # 4. PostgreSQL (Default)
        pg_res = DeploymentEngine.ensure_project_postgres_db(project_name, merged_env, db_config, log_callback)
        DeploymentEngine._auto_wire_silo_storage(project_name, pg_res, env_example_hint, log_callback)
        return pg_res

    @staticmethod
    def ensure_project_postgres_db(
        project_name: str,
        env_vars: Optional[Dict[str, str]],
        db_config: Optional[Dict[str, Any]],
        log_callback: Callable[[str, str], None],
    ) -> Dict[str, str]:
        """
        Ensure the PostgreSQL database for the deployed project exists on the PostgreSQL server
        (auto-creating it if missing) and return merged environment variables for auto-connection.
        Works via psycopg2 direct socket AND via 'psm-postgres' Docker container exec fallback.
        """
        merged_env = dict(env_vars or {})
        cfg = dict(db_config or {})

        # 1. Determine target database name
        target_db = (
            cfg.get("db_name")
            or merged_env.get("POSTGRES_DB")
            or merged_env.get("DB_DATABASE")
            or merged_env.get("DB_NAME")
        )
        if not target_db or target_db in ("psm", "laravel", "app", "test"):
            target_db = DeploymentEngine.sanitize_db_name(project_name)
        else:
            target_db = DeploymentEngine.sanitize_db_name(target_db)

        pg_user = (
            cfg.get("user")
            or os.getenv("POSTGRES_USER")
            or merged_env.get("POSTGRES_USER")
            or "psm"
        )
        pg_pass = (
            cfg.get("password")
            or os.getenv("POSTGRES_PASSWORD")
            or merged_env.get("POSTGRES_PASSWORD")
            or "psm_super_secret_password_change_in_production"
        )
        pg_port = int(cfg.get("port") or os.getenv("POSTGRES_PORT") or 5432)
        configured_host = cfg.get("host") or os.getenv("POSTGRES_HOST") or os.getenv("HOST_IP") or "192.168.25.101"

        db_verified = False
        db_created = False
        resolved_container_host = configured_host if configured_host not in ("127.0.0.1", "localhost") else os.getenv("HOST_IP", "192.168.25.101")

        # 2. Method A: Direct PostgreSQL connection via psycopg2
        try:
            import psycopg2
            candidate_hosts = []
            for h in [configured_host, os.getenv("HOST_IP", "192.168.25.101"), "homelab-postgres", "host.docker.internal", "127.0.0.1"]:
                if h and h not in candidate_hosts:
                    candidate_hosts.append(h)

            candidate_creds = [
                (pg_user, pg_pass),
                ("psm", "psm_super_secret_password_change_in_production"),
                ("appuser", "admin12345"),
            ]

            import socket
            for host in candidate_hosts:
                if db_verified:
                    break
                try:
                    with socket.create_connection((host, pg_port), timeout=0.6):
                        pass
                except Exception:
                    continue
                for user, pw in candidate_creds:
                    if db_verified:
                        break
                    for maint_db in ("postgres", "psm", "template1"):
                        try:
                            conn = psycopg2.connect(
                                host=host,
                                port=pg_port,
                                user=user,
                                password=pw,
                                dbname=maint_db,
                                connect_timeout=3,
                            )
                            conn.autocommit = True
                            cur = conn.cursor()

                            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
                            exists = cur.fetchone() is not None
                            if not exists:
                                log_callback(
                                    "info",
                                    f"[PostgreSQL] Database '{target_db}' tidak ditemukan — membuat database baru secara otomatis...",
                                )
                                cur.execute(f'CREATE DATABASE "{target_db}" OWNER "{user}" ENCODING \'UTF8\'')
                                db_created = True
                            cur.close()
                            conn.close()

                            pg_user = user
                            pg_pass = pw
                            resolved_container_host = (
                                os.getenv("HOST_IP", "192.168.25.101")
                                if host in ("127.0.0.1", "localhost")
                                else host
                            )
                            db_verified = True
                            break
                        except Exception:
                            continue
        except Exception:
            pass

        # 3. Method B: Fallback via Docker container (exec psql inside container)
        if not db_verified:
            try:
                import docker
                client = docker.from_env()
                for pg_c_name in ["homelab-postgres", "homelab_postgres", "psm-postgres", "postgres"]:
                    try:
                        pg_cont = client.containers.get(pg_c_name)
                        if pg_cont.status == "running":
                            chk_cmd = f"psql -U {pg_user} -d postgres -tAc \"SELECT 1 FROM pg_database WHERE datname='{target_db}'\""
                            exit_code, output = pg_cont.exec_run(["sh", "-c", chk_cmd])
                            out_str = output.decode("utf-8", errors="ignore").strip() if output else ""
                            if exit_code == 0 and "1" in out_str:
                                db_verified = True
                                resolved_container_host = os.getenv("HOST_IP", "192.168.25.101")
                            else:
                                log_callback(
                                    "info",
                                    f"[PostgreSQL] Membuat database '{target_db}' di dalam container {pg_c_name}...",
                                )
                                create_cmd = f'psql -U {pg_user} -d postgres -c \'CREATE DATABASE "{target_db}";\''
                                c_code, _ = pg_cont.exec_run(["sh", "-c", create_cmd])
                                if c_code == 0:
                                    db_verified = True
                                    db_created = True
                                    resolved_container_host = os.getenv("HOST_IP", "192.168.25.101")
                            break
                    except Exception:
                        pass
            except Exception:
                pass

        if db_verified:
            if db_created:
                log_callback(
                    "info",
                    f"[PostgreSQL] Database '{target_db}' berhasil dibuat dan terhubung otomatis ({resolved_container_host}:{pg_port}).",
                )
            else:
                log_callback(
                    "info",
                    f"[PostgreSQL] Database '{target_db}' terdeteksi aktif. Auto-connecting ke {resolved_container_host}:{pg_port}...",
                )
        else:
            log_callback(
                "info",
                f"[PostgreSQL] Menyiapkan variabel koneksi otomatis untuk database '{target_db}' ({resolved_container_host}:{pg_port}).",
            )

        conn_url = f"postgresql://{pg_user}:{pg_pass}@{resolved_container_host}:{pg_port}/{target_db}"
        sqlalchemy_url = f"postgresql+psycopg2://{pg_user}:{pg_pass}@{resolved_container_host}:{pg_port}/{target_db}"

        pg_vars = {
            "DATABASE_URL": conn_url,
            "POSTGRES_URL": conn_url,
            "SQLALCHEMY_DATABASE_URI": sqlalchemy_url,
            "POSTGRES_HOST": resolved_container_host,
            "POSTGRES_PORT": str(pg_port),
            "POSTGRES_DB": target_db,
            "POSTGRES_USER": pg_user,
            "POSTGRES_PASSWORD": pg_pass,
            "DB_CONNECTION": "pgsql",
            "DB_HOST": resolved_container_host,
            "DB_PORT": str(pg_port),
            "DB_DATABASE": target_db,
            "DB_NAME": target_db,
            "DB_USERNAME": pg_user,
            "DB_USER": pg_user,
            "DB_PASSWORD": pg_pass,
        }

        # Purge any conflicting MySQL variables when database is configured as PostgreSQL
        for my_k in ["MYSQL_URL", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_HOST", "MYSQL_PORT"]:
            merged_env.pop(my_k, None)

        for k, v in pg_vars.items():
            merged_env[k] = v

        return merged_env

    @staticmethod
    def prepare_dockerfile_for_postgres(
        workspace_dir: str,
        dockerfile_path: str,
        log_callback: Callable[[str, str], None],
    ) -> None:
        """Alias for backward-compatibility with tests."""
        DeploymentEngine.prepare_dockerfile_environment(
            workspace_dir=workspace_dir,
            dockerfile_path=dockerfile_path,
            log_callback=log_callback,
            db_type="postgres",
        )

    @staticmethod
    def prepare_dockerfile_environment(
        workspace_dir: str,
        dockerfile_path: str,
        log_callback: Callable[[str, str], None],
        db_type: str = "auto",
    ) -> None:
        """
        1. Normalize line endings (CRLF -> LF) on .sh scripts in workspace_dir.
        2. Ensure required database drivers are present in PHP Dockerfiles based on active db_type.
        """
        # 1. Normalize shell script line endings
        try:
            for root, _, files in os.walk(workspace_dir):
                for fname in files:
                    if fname.endswith(".sh"):
                        fpath = os.path.join(root, fname)
                        if os.path.isfile(fpath):
                            with open(fpath, "rb") as f:
                                raw = f.read()
                            if b"\r\n" in raw:
                                with open(fpath, "wb") as f:
                                    f.write(raw.replace(b"\r\n", b"\n"))
        except Exception:
            pass

        # 2. Check Dockerfile for PHP database drivers
        full_df_path = os.path.join(workspace_dir, dockerfile_path)
        if not os.path.exists(full_df_path):
            return

        try:
            with open(full_df_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if "docker-php-ext-install" in content:
                # If PostgreSQL is selected and pdo_pgsql is missing
                if db_type == "postgres" and "pdo_pgsql" not in content:
                    log_callback(
                        "info",
                        "[Docker-Build] Menginjeksi driver 'pdo_pgsql' ke Dockerfile PHP untuk koneksi PostgreSQL...",
                    )
                    pg_layer = (
                        "\n# Auto-injected by Personal Server Manager for PostgreSQL connectivity\n"
                        "RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev postgresql-client \\\n"
                        "    && docker-php-ext-install pdo_pgsql pgsql \\\n"
                        "    && rm -rf /var/lib/apt/lists/*\n"
                    )
                    if "ENTRYPOINT" in content:
                        idx = content.rfind("ENTRYPOINT")
                        content = content[:idx] + pg_layer + "\n" + content[idx:]
                    elif "EXPOSE" in content:
                        idx = content.rfind("EXPOSE")
                        content = content[:idx] + pg_layer + "\n" + content[idx:]
                    else:
                        content = content + "\n" + pg_layer

                    with open(full_df_path, "w", encoding="utf-8", newline="\n") as f:
                        f.write(content)

                # If MySQL is selected and pdo_mysql is missing
                elif db_type in ("mysql", "mariadb") and "pdo_mysql" not in content:
                    log_callback(
                        "info",
                        "[Docker-Build] Menginjeksi driver 'pdo_mysql' ke Dockerfile PHP untuk koneksi MySQL...",
                    )
                    my_layer = (
                        "\n# Auto-injected by Personal Server Manager for MySQL connectivity\n"
                        "RUN apt-get update && apt-get install -y --no-install-recommends default-mysql-client \\\n"
                        "    && docker-php-ext-install pdo_mysql mysqli \\\n"
                        "    && rm -rf /var/lib/apt/lists/*\n"
                    )
                    if "ENTRYPOINT" in content:
                        idx = content.rfind("ENTRYPOINT")
                        content = content[:idx] + my_layer + "\n" + content[idx:]
                    elif "EXPOSE" in content:
                        idx = content.rfind("EXPOSE")
                        content = content[:idx] + my_layer + "\n" + content[idx:]
                    else:
                        content = content + "\n" + my_layer

                    with open(full_df_path, "w", encoding="utf-8", newline="\n") as f:
                        f.write(content)
        except Exception as e:
            log_callback("warning", f"[Docker-Build] Dockerfile inspection note: {e}")

    @staticmethod
    def run_post_deploy_db_migrations(
        workspace_dir: str,
        container_name: str,
        log_callback: Callable[[str, str], None],
    ) -> None:
        """
        Automatically run database schema migrations, optimizations, and symlinks inside the newly launched container.
        """
        sanitized_name = re.sub(r"[^a-zA-Z0-9_.-]", "-", container_name.lower())
        artisan_path = os.path.join(workspace_dir, "artisan")
        manage_py_path = os.path.join(workspace_dir, "manage.py")
        prisma_path = os.path.join(workspace_dir, "prisma")

        # Give the container process 3s to initialize
        time.sleep(3)

        # 1. Laravel Project
        if os.path.exists(artisan_path):
            log_callback("info", "[Post-Deploy] Mendeteksi framework Laravel — Menjalankan migrasi, storage link, dan optimasi cache...")
            try:
                import docker
                client = docker.from_env()
                cont = client.containers.get(sanitized_name)

                # Migration
                code, out = cont.exec_run(["php", "artisan", "migrate", "--force"])
                if out:
                    for line in out.decode("utf-8", errors="ignore").splitlines():
                        if line.strip():
                            log_callback("info", f"[Migrate] {line.strip()}")
                if code == 0:
                    log_callback("info", "[Post-Deploy] Migrasi tabel database Laravel berhasil!")
                else:
                    log_callback("warning", f"[Post-Deploy] Artisan migrate exit code: {code}")

                # Storage Symlink
                s_code, s_out = cont.exec_run(["php", "artisan", "storage:link"])
                if s_out:
                    for line in s_out.decode("utf-8", errors="ignore").splitlines():
                        if line.strip():
                            log_callback("info", f"[StorageLink] {line.strip()}")

                # Optimization Cache
                cont.exec_run(["php", "artisan", "optimize:clear"])
                cont.exec_run(["php", "artisan", "optimize"])

                # Storage Permissions
                cont.exec_run(["sh", "-c", "chown -R www-data:www-data storage bootstrap/cache 2>/dev/null || chmod -R 775 storage bootstrap/cache 2>/dev/null"])
                log_callback("info", "[Post-Deploy] Konfigurasi runtime Laravel selesai dengan sukses!")
                return
            except Exception as e:
                log_callback("warning", f"[Post-Deploy] Laravel post-deploy error: {e}")

        # 2. Django Project
        elif os.path.exists(manage_py_path):
            log_callback("info", "[Post-Deploy] Mendeteksi framework Django — Menjalankan 'python manage.py migrate'...")
            try:
                import docker
                client = docker.from_env()
                cont = client.containers.get(sanitized_name)
                code, out = cont.exec_run(["python", "manage.py", "migrate", "--noinput"])
                if out:
                    for line in out.decode("utf-8", errors="ignore").splitlines():
                        if line.strip():
                            log_callback("info", f"[Migrate] {line.strip()}")
                cont.exec_run(["python", "manage.py", "collectstatic", "--noinput"])
                return
            except Exception as e:
                log_callback("warning", f"[Post-Deploy] Django post-deploy error: {e}")

        # 3. Node.js / Prisma
        elif os.path.exists(prisma_path):
            log_callback("info", "[Post-Deploy] Mendeteksi schema Prisma — Menjalankan 'npx prisma migrate deploy'...")
            try:
                import docker
                client = docker.from_env()
                cont = client.containers.get(sanitized_name)
                code, out = cont.exec_run(["npx", "prisma", "migrate", "deploy"])
                if out:
                    for line in out.decode("utf-8", errors="ignore").splitlines():
                        if line.strip():
                            log_callback("info", f"[Migrate] {line.strip()}")
                return
            except Exception as e:
                log_callback("warning", f"[Post-Deploy] Prisma post-deploy error: {e}")

    @staticmethod
    def clone_or_pull_git(
        repo_url: str,
        branch: str,
        target_dir: str,
        log_callback: Callable[[str, str], None],
        commit_hash: Optional[str] = None
    ) -> bool:
        """Clone or pull git repository with clean workspace reset."""
        os.makedirs(target_dir, exist_ok=True)
        git_dir = os.path.join(target_dir, ".git")

        # Auto-normalize GitHub / GitLab branch URLs (e.g. https://github.com/owner/repo/tree/branch_name)
        if repo_url and "/tree/" in repo_url:
            parts = repo_url.split("/tree/", 1)
            clean_base = parts[0].rstrip("/")
            extracted_branch = parts[1].strip("/").split("/")[0]
            log_callback("info", f"[Git] Normalisasi URL browser Git: '{repo_url}' -> base: '{clean_base}', branch: '{extracted_branch}'")
            repo_url = clean_base
            if not repo_url.endswith(".git") and "github.com" in repo_url:
                repo_url += ".git"
            if extracted_branch and (not branch or branch in ("main", "master")):
                branch = extracted_branch
        elif repo_url and not repo_url.endswith(".git") and "github.com" in repo_url:
            repo_url = repo_url.rstrip("/") + ".git"

        if os.path.exists(git_dir):
            log_callback("info", f"[Git] Fetching latest changes from branch '{branch}'...")
            subprocess.run(["git", "-C", target_dir, "fetch", "origin", branch], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            cmd = ["git", "-C", target_dir, "reset", "--hard", f"origin/{branch}"]
        else:
            if os.path.exists(target_dir) and os.listdir(target_dir):
                shutil.rmtree(target_dir, ignore_errors=True)
                os.makedirs(target_dir, exist_ok=True)
            log_callback("info", f"[Git] Cloning repository {repo_url} (branch: {branch})...")
            cmd = ["git", "clone", "--depth", "1", "--branch", branch, repo_url, target_dir]

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            clean = line.strip()
            if clean:
                log_callback("info", clean)
        proc.wait()

        if proc.returncode != 0:
            return False

        if commit_hash and commit_hash != "HEAD":
            log_callback("info", f"[Git] Checking out commit {commit_hash}...")
            c_proc = subprocess.run(
                ["git", "-C", target_dir, "checkout", commit_hash],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            for line in c_proc.stdout.strip().split("\n"):
                if line.strip():
                    log_callback("info", line.strip())

        return True

    @staticmethod
    def _get_compose_cmd() -> Optional[List[str]]:
        """Detect available Docker Compose executable (V2 plugin or standalone)."""
        docker_bin = shutil.which("docker") or "/usr/bin/docker"
        if os.path.exists(docker_bin) or shutil.which("docker"):
            try:
                res = subprocess.run([docker_bin, "compose", "version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=4)
                if res.returncode == 0:
                    return [docker_bin, "compose"]
            except Exception:
                pass

        dc_bin = shutil.which("docker-compose") or "/usr/local/bin/docker-compose"
        if os.path.exists(dc_bin) or shutil.which("docker-compose"):
            return [dc_bin]

        return None

    @staticmethod
    def build_and_deploy_compose(
        workspace_dir: str,
        compose_file: str,
        log_callback: Callable[[str, str], None]
    ) -> bool:
        """Execute docker compose up -d --build."""
        compose_path = os.path.join(workspace_dir, compose_file)
        if not os.path.exists(compose_path):
            log_callback("error", f"[Compose] Compose specification not found at {compose_path}")
            return False

        compose_cmd = DeploymentEngine._get_compose_cmd()
        if not compose_cmd:
            log_callback("error", "[Compose] Neither 'docker compose' (V2 plugin) nor 'docker-compose' was found in PATH.")
            return False

        cmd = [*compose_cmd, "-f", compose_file, "up", "-d", "--build", "--remove-orphans"]
        log_callback("info", f"[Compose] Launching stack: {' '.join(cmd)}")
        try:
            proc = subprocess.Popen(cmd, cwd=workspace_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in proc.stdout:
                clean = line.strip()
                if clean and should_log_build_line(clean):
                    log_callback("info", clean)
            proc.wait()
            if proc.returncode != 0:
                log_callback("error", f"[Compose] Stack deployment failed with exit code {proc.returncode}")
                return False

            log_callback("info", "[Compose] Stack deployed successfully!")
            return True
        except Exception as e:
            log_callback("error", f"[Compose] Process execution error: {e}")
            return False

    @staticmethod
    def parse_port_mappings(
        explicit_mappings: Optional[str],
        full_df_path: str,
        workspace_dir: str,
        log_callback: Callable[[str, str], None]
    ) -> Tuple[List[str], Dict[str, int], int]:
        """
        Parses port configuration with multi-layer intelligence:
        1. Inspects Dockerfile EXPOSE instructions or server config (Apache/Nginx/framework)
           to determine the true port the application listens on.
        2. If explicit_mappings is given (e.g. '3101:3000'), detects if container port (3000)
           was a default placeholder that conflicts with what the Dockerfile actually exposes (e.g. 8080 or 80),
           and intelligently aligns the container port.
        3. Sets accurate Host -> Container mappings for Docker CLI and SDK.
        """
        cli_args: List[str] = []
        sdk_ports: Dict[str, int] = {}

        # 1. Inspect Dockerfile for EXPOSE ports
        detected_exposed_ports: List[int] = []
        if full_df_path and os.path.exists(full_df_path):
            try:
                with open(full_df_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    for m in re.finditer(r"EXPOSE\s+([0-9\s]+)", content, re.IGNORECASE):
                        for port_item in m.group(1).split():
                            if port_item.strip().isdigit():
                                detected_exposed_ports.append(int(port_item.strip()))
            except Exception:
                pass

        # 2. Inspect workspace configuration files (Apache ports.conf, nginx.conf)
        if not detected_exposed_ports and workspace_dir:
            for pth in ["ports.conf", "etc/apache2/ports.conf", "nginx.conf", "default.conf", "docker/nginx.conf"]:
                full_p = os.path.join(workspace_dir, pth)
                if os.path.exists(full_p):
                    try:
                        with open(full_p, "r", encoding="utf-8", errors="ignore") as f:
                            for pm in re.findall(r"Listen\s+(\d+)", f.read(), re.IGNORECASE):
                                detected_exposed_ports.append(int(pm))
                    except Exception:
                        pass

        # Framework default fallback guess
        framework_default_port = 3000
        if workspace_dir:
            if os.path.exists(os.path.join(workspace_dir, "composer.json")) or os.path.exists(os.path.join(workspace_dir, "artisan")):
                framework_default_port = 8080 if 8080 in detected_exposed_ports else (80 if 80 in detected_exposed_ports else 8000)
            elif os.path.exists(os.path.join(workspace_dir, "requirements.txt")) or any(os.path.exists(os.path.join(workspace_dir, f)) for f in ("main.py", "app.py", "manage.py")):
                framework_default_port = 8000
            elif os.path.exists(os.path.join(workspace_dir, "index.html")) and not os.path.exists(os.path.join(workspace_dir, "package.json")):
                framework_default_port = 80

        primary_target_cp = detected_exposed_ports[0] if detected_exposed_ports else framework_default_port
        primary_container_port = primary_target_cp
        parsed_any = False

        # 3. Process explicit mappings with intelligent alignment
        if explicit_mappings and str(explicit_mappings).strip():
            raw_entries = [p.strip() for p in str(explicit_mappings).split(",") if p.strip()]
            for entry in raw_entries:
                parts = entry.split(":")
                try:
                    if len(parts) == 1:
                        hp = int(parts[0])
                        cp = primary_target_cp
                    elif len(parts) >= 2:
                        hp = int(parts[0])
                        cp = int(parts[1])

                        # INTELLIGENT ALIGNMENT:
                        # If container port was submitted as 3000 (standard UI default) but Dockerfile
                        # explicitly exposes a different primary port (e.g. 8080 or 80):
                        if cp == 3000 and detected_exposed_ports and (3000 not in detected_exposed_ports):
                            log_callback(
                                "info",
                                f"[Docker-Port] Penyesuaian cerdas: Dockerfile mengekspos port {primary_target_cp} (bukan 3000). Memetakan Host {hp} -> Container {primary_target_cp}."
                            )
                            cp = primary_target_cp
                        elif detected_exposed_ports and (cp not in detected_exposed_ports) and len(detected_exposed_ports) == 1:
                            log_callback(
                                "info",
                                f"[Docker-Port] Menyelaraskan port container dari {cp} ke {detected_exposed_ports[0]} sesuai EXPOSE Dockerfile."
                            )
                            cp = detected_exposed_ports[0]
                    else:
                        continue

                    cli_args.extend(["-p", f"{hp}:{cp}"])
                    sdk_ports[f"{cp}/tcp"] = hp
                    if not parsed_any:
                        primary_container_port = cp
                    parsed_any = True
                    log_callback("info", f"[Docker-Port] Port Mapping: Host {hp} -> Container {cp}")
                except ValueError:
                    continue

        # 4. Check .env for PORT or HOST_PORT
        if not parsed_any:
            env_dict = DeploymentEngine._load_env_dict(workspace_dir)
            p_val = env_dict.get("HOST_PORT") or env_dict.get("PORT")
            if p_val:
                try:
                    if ":" in p_val:
                        hp_str, cp_str = p_val.split(":", 1)
                        hp, cp = int(hp_str), int(cp_str)
                    else:
                        hp = int(p_val)
                        cp = primary_target_cp
                    cli_args.extend(["-p", f"{hp}:{cp}"])
                    sdk_ports[f"{cp}/tcp"] = hp
                    primary_container_port = cp
                    parsed_any = True
                    log_callback("info", f"[Docker-Port] Port dari .env: Host {hp} -> Container {cp}")
                except ValueError:
                    pass

        # 5. Check Dockerfile EXPOSE
        if not parsed_any and detected_exposed_ports:
            for p in detected_exposed_ports:
                cli_args.extend(["-p", f"{p}:{p}"])
                sdk_ports[f"{p}/tcp"] = p
            primary_container_port = detected_exposed_ports[0]
            parsed_any = True
            log_callback("info", f"[Docker-Port] Terdeteksi EXPOSE {primary_container_port} pada Dockerfile: Host {primary_container_port} -> Container {primary_container_port}")

        # 6. Fallback default
        if not parsed_any:
            cli_args.extend(["-p", f"{primary_target_cp}:{primary_target_cp}"])
            sdk_ports[f"{primary_target_cp}/tcp"] = primary_target_cp
            primary_container_port = primary_target_cp
            log_callback("info", f"[Docker-Port] Port default otomatis: Mapping Host {primary_container_port} -> Container {primary_container_port}")

        return cli_args, sdk_ports, primary_container_port

    @staticmethod
    def ensure_dockerfile_or_generate(
        workspace_dir: str,
        dockerfile_path: str,
        compose_path: str,
        container_port: int,
        log_callback: Callable[[str, str], None],
        fallback_framework: str = "auto",
    ) -> str:
        """
        Ensure workspace has a buildable Dockerfile or Docker Compose file.
        If missing, detect project type and auto-generate an optimized, production-ready
        multi-stage Dockerfile and .dockerignore like modern PaaS platforms (Railway, Coolify, Render).
        """
        full_compose = os.path.join(workspace_dir, compose_path)
        if os.path.exists(full_compose):
            return compose_path

        resolved_df, created_df, created_di = ensure_dockerfile_and_ignore(
            workspace_dir=workspace_dir,
            dockerfile_path=dockerfile_path,
            fallback_framework=fallback_framework,
            container_port=container_port,
            log_callback=log_callback,
        )
        return resolved_df

    @staticmethod
    def _extract_port_args(full_df_path: str, workspace_dir: str, log_callback: Callable[[str, str], None]) -> List[str]:
        cli_args, _, _ = DeploymentEngine.parse_port_mappings(None, full_df_path, workspace_dir, log_callback)
        return cli_args

    @staticmethod
    def _extract_ports_dict(full_df_path: str, workspace_dir: str, log_callback: Callable[[str, str], None]) -> Dict[str, int]:
        _, sdk_ports, _ = DeploymentEngine.parse_port_mappings(None, full_df_path, workspace_dir, log_callback)
        return sdk_ports

    @staticmethod
    def _load_env_dict(workspace_dir: str) -> Dict[str, str]:
        env_dict: Dict[str, str] = {}
        env_file_path = os.path.join(workspace_dir, ".env")
        if os.path.exists(env_file_path):
            try:
                with open(env_file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            env_dict[k.strip()] = v.strip()
            except Exception:
                pass
        return env_dict

    @staticmethod
    def _resolve_psm_network_name() -> Optional[str]:
        """Find the Docker network where homelab databases and services reside so deployed containers can auto-connect."""
        try:
            import docker
            client = docker.from_env()
            for container_name in ("homelab-postgres", "homelab-mysql", "psm-postgres", "homelab_minio", "pap-api", "psm-agent", "homelab_router"):
                try:
                    c = client.containers.get(container_name)
                    nets = list((c.attrs.get("NetworkSettings", {}).get("Networks") or {}).keys())
                    custom_nets = [n for n in nets if n not in ("bridge", "host", "none")]
                    if "psm-network" in custom_nets:
                        return "psm-network"
                    if "homelab-network" in custom_nets:
                        return "homelab-network"
                    if custom_nets:
                        return custom_nets[0]
                except Exception:
                    continue
            for net in client.networks.list():
                if net.name in ("psm-network", "homelab-network"):
                    return net.name
        except Exception:
            pass
        return "psm-network"

    @staticmethod
    def build_and_run_dockerfile(
        workspace_dir: str,
        dockerfile_path: str,
        image_tag: str,
        container_name: str,
        log_callback: Callable[[str, str], None],
        port_mappings: Optional[str] = None,
        db_type: str = "auto",
    ) -> bool:
        """Build image using Dockerfile and launch container directly.
        Automatically attaches container to the homelab network (psm-network)
        and runs post-deploy database migrations if applicable.
        """
        full_df_path = os.path.join(workspace_dir, dockerfile_path)
        if not os.path.exists(full_df_path):
            log_callback("error", f"[Docker] Dockerfile not found at {full_df_path}")
            return False

        # Resolve db_type for Dockerfile PHP/framework driver injection
        resolved_db_type = db_type
        if resolved_db_type == "auto":
            env_map = DeploymentEngine._load_env_dict(workspace_dir)
            db_conn = env_map.get("DB_CONNECTION", "").lower()
            if db_conn in ("pgsql", "postgres", "postgresql") or "postgres" in env_map.get("DATABASE_URL", "").lower():
                resolved_db_type = "postgres"
            elif db_conn in ("mysql", "mariadb") or "mysql" in env_map.get("DATABASE_URL", "").lower():
                resolved_db_type = "mysql"

        # Ensure required database drivers and normalize script line endings
        DeploymentEngine.prepare_dockerfile_environment(workspace_dir, dockerfile_path, log_callback, db_type=resolved_db_type)

        sanitized_tag = re.sub(r"[^a-z0-9_.:-]", "-", image_tag.lower())
        sanitized_name = re.sub(r"[^a-zA-Z0-9_.-]", "-", container_name.lower())
        target_network = DeploymentEngine._resolve_psm_network_name()

        # Parse ports & ensure PORT env
        port_args, ports_mapping, primary_port = DeploymentEngine.parse_port_mappings(
            explicit_mappings=port_mappings,
            full_df_path=full_df_path,
            workspace_dir=workspace_dir,
            log_callback=log_callback
        )
        env_dict = DeploymentEngine._load_env_dict(workspace_dir)
        if "PORT" not in env_dict:
            env_dict["PORT"] = str(primary_port)
            DeploymentEngine.write_env_file(workspace_dir, env_dict)

        # 1. Check if Docker CLI is available
        docker_bin = shutil.which("docker") or "/usr/bin/docker"
        cli_available = False
        if os.path.exists(docker_bin) or shutil.which("docker"):
            try:
                chk = subprocess.run([docker_bin, "info"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=4)
                cli_available = (chk.returncode == 0)
            except Exception:
                cli_available = False

        if cli_available:
            log_callback("info", f"[Docker-CLI] Building image '{sanitized_tag}' from {dockerfile_path}...")
            build_cmd = [docker_bin, "build", "-t", sanitized_tag, "-f", dockerfile_path, "."]
            try:
                build_proc = subprocess.Popen(build_cmd, cwd=workspace_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in build_proc.stdout:
                    clean = line.strip()
                    if clean and should_log_build_line(clean):
                        log_callback("info", clean)
                build_proc.wait()
                if build_proc.returncode != 0:
                    log_callback("error", f"[Docker-CLI] Build failed with exit code {build_proc.returncode}")
                    return False
            except Exception as e:
                log_callback("error", f"[Docker-CLI] Build execution error: {e}")
                return False

            log_callback("info", f"[Docker-CLI] Image '{sanitized_tag}' built successfully.")

            # Stop & remove existing container
            log_callback("info", f"[Docker-CLI] Removing existing container '{sanitized_name}'...")
            subprocess.run([docker_bin, "stop", sanitized_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run([docker_bin, "rm", "-f", sanitized_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Ports, Network & Run (with lean resource boundaries for homelab stability)
            run_cmd = [
                docker_bin, "run", "-d",
                "--restart", "unless-stopped",
                "--name", sanitized_name,
                "--memory=768m",
                "--cpus=1.0",
                "--add-host=host.docker.internal:host-gateway",
            ]
            if target_network:
                run_cmd.extend(["--network", target_network])
                log_callback("info", f"[PostgreSQL] Attaching container '{sanitized_name}' to database network '{target_network}'")

            env_file_path = os.path.join(workspace_dir, ".env")
            if os.path.exists(env_file_path):
                run_cmd.extend(["--env-file", ".env"])
            run_cmd.extend(port_args)
            run_cmd.append(sanitized_tag)

            log_callback("info", f"[Docker-CLI] Running container: {' '.join(run_cmd)}")
            try:
                run_proc = subprocess.Popen(run_cmd, cwd=workspace_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                for line in run_proc.stdout:
                    clean = line.strip()
                    if clean:
                        log_callback("info", clean)
                run_proc.wait()
                if run_proc.returncode != 0:
                    log_callback("error", f"[Docker-CLI] Container launch failed with exit code {run_proc.returncode}")
                    return False

                log_callback("info", f"[Docker-CLI] Container '{sanitized_name}' is now running successfully!")
                DeploymentEngine.run_post_deploy_db_migrations(workspace_dir, sanitized_name, log_callback)
                return True
            except Exception as e:
                log_callback("error", f"[Docker-CLI] Launch execution error: {e}")
                return False

        # 2. FALLBACK: Use Python Docker SDK directly through /var/run/docker.sock
        log_callback("info", "[Docker-SDK] Utilizing Docker daemon socket connection...")
        try:
            import docker
            client = docker.from_env()
            client.ping()

            log_callback("info", f"[Docker-SDK] Building image '{sanitized_tag}' from {dockerfile_path}...")
            build_logs = client.api.build(
                path=workspace_dir,
                dockerfile=dockerfile_path,
                tag=sanitized_tag,
                rm=True,
                decode=True
            )
            for chunk in build_logs:
                if "stream" in chunk:
                    for line in chunk["stream"].splitlines():
                        clean = line.strip()
                        if clean:
                            log_callback("info", clean)
                elif "error" in chunk:
                    log_callback("error", chunk["error"].strip())
                    return False

            log_callback("info", f"[Docker-SDK] Image '{sanitized_tag}' built successfully.")

            # Stop & remove existing container
            try:
                existing = client.containers.get(sanitized_name)
                log_callback("info", f"[Docker-SDK] Removing existing container '{sanitized_name}'...")
                existing.stop(timeout=5)
                existing.remove(force=True)
            except Exception:
                pass

            # Environment variables
            env_dict = DeploymentEngine._load_env_dict(workspace_dir)

            if target_network:
                log_callback("info", f"[PostgreSQL] Attaching container '{sanitized_name}' to database network '{target_network}'")

            log_callback("info", f"[Docker-SDK] Launching container '{sanitized_name}'...")
            run_kwargs: Dict[str, Any] = {
                "image": sanitized_tag,
                "name": sanitized_name,
                "detach": True,
                "restart_policy": {"Name": "unless-stopped"},
                "ports": ports_mapping if ports_mapping else None,
                "environment": env_dict if env_dict else None,
                "extra_hosts": {"host.docker.internal": "host-gateway"},
            }
            if target_network:
                run_kwargs["network"] = target_network

            c = client.containers.run(**run_kwargs)
            log_callback("info", f"[Docker-SDK] Container '{sanitized_name}' ({c.short_id}) launched and operational!")
            DeploymentEngine.run_post_deploy_db_migrations(workspace_dir, sanitized_name, log_callback)
            return True
        except Exception as sdk_err:
            log_callback("error", f"[Docker-SDK] Failure via Docker daemon socket: {sdk_err}")
            return False
