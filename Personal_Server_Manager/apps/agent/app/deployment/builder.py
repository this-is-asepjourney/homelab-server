import os
import shutil
import zipfile
import subprocess
import re
import time
from typing import Callable, Optional, Dict, Any, List, Tuple


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
        configured_host = cfg.get("host") or os.getenv("POSTGRES_HOST") or "psm-postgres"

        db_verified = False
        db_created = False
        resolved_container_host = "psm-postgres"

        # 2. Method A: Direct PostgreSQL connection via psycopg2
        try:
            import psycopg2
            candidate_hosts = []
            for h in [configured_host, "postgres", "psm-postgres", "host.docker.internal", "127.0.0.1"]:
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
                                "psm-postgres"
                                if host in ("postgres", "psm-postgres", "127.0.0.1", "localhost")
                                else host
                            )
                            db_verified = True
                            break
                        except Exception:
                            continue
        except Exception:
            pass

        # 3. Method B: Fallback via Docker container 'psm-postgres' (exec psql inside container)
        if not db_verified:
            try:
                import docker
                client = docker.from_env()
                pg_cont = client.containers.get("psm-postgres")
                if pg_cont.status == "running":
                    chk_cmd = f"psql -U {pg_user} -d postgres -tAc \"SELECT 1 FROM pg_database WHERE datname='{target_db}'\""
                    exit_code, output = pg_cont.exec_run(["sh", "-c", chk_cmd])
                    out_str = output.decode("utf-8", errors="ignore").strip() if output else ""
                    if exit_code == 0 and "1" in out_str:
                        db_verified = True
                        resolved_container_host = "psm-postgres"
                    else:
                        log_callback(
                            "info",
                            f"[PostgreSQL] Membuat database '{target_db}' di dalam container psm-postgres...",
                        )
                        create_cmd = f'psql -U {pg_user} -d postgres -c \'CREATE DATABASE "{target_db}";\''
                        c_code, _ = pg_cont.exec_run(["sh", "-c", create_cmd])
                        if c_code == 0:
                            db_verified = True
                            db_created = True
                            resolved_container_host = "psm-postgres"
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

        # Override MySQL defaults or missing keys with PostgreSQL auto-connect credentials
        was_mysql = merged_env.get("DB_CONNECTION", "").lower() == "mysql"
        for k, v in pg_vars.items():
            if was_mysql or k not in merged_env or not merged_env.get(k) or k in ("DB_CONNECTION", "DB_HOST", "DB_PORT", "DB_DATABASE", "DB_USERNAME", "DB_PASSWORD", "DATABASE_URL"):
                merged_env[k] = v

        return merged_env

    @staticmethod
    def prepare_dockerfile_for_postgres(
        workspace_dir: str,
        dockerfile_path: str,
        log_callback: Callable[[str, str], None],
    ) -> None:
        """
        1. Normalize line endings (CRLF -> LF) on .sh scripts in workspace_dir.
        2. If Dockerfile is a PHP image missing pdo_pgsql, auto-inject libpq-dev and pdo_pgsql
           so PHP/Laravel projects can connect to PostgreSQL out-of-the-box.
        """
        # 1. Normalize shell script line endings
        try:
            for fname in os.listdir(workspace_dir):
                if fname.endswith(".sh"):
                    fpath = os.path.join(workspace_dir, fname)
                    if os.path.isfile(fpath):
                        with open(fpath, "rb") as f:
                            raw = f.read()
                        if b"\r\n" in raw:
                            with open(fpath, "wb") as f:
                                f.write(raw.replace(b"\r\n", b"\n"))
        except Exception:
            pass

        # 2. Check Dockerfile for PHP without pdo_pgsql
        full_df_path = os.path.join(workspace_dir, dockerfile_path)
        if not os.path.exists(full_df_path):
            return

        try:
            with open(full_df_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if "docker-php-ext-install" in content and "pdo_pgsql" not in content:
                log_callback(
                    "info",
                    "[PostgreSQL] Mendeteksi Dockerfile PHP tanpa driver 'pdo_pgsql' — menginjeksi libpq-dev & pdo_pgsql secara otomatis...",
                )
                # Inject libpq-dev and pdo_pgsql right after existing docker-php-ext-install or before ENTRYPOINT/CMD
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
        except Exception as e:
            log_callback("warning", f"[PostgreSQL] Dockerfile inspection note: {e}")

    @staticmethod
    def run_post_deploy_db_migrations(
        workspace_dir: str,
        container_name: str,
        log_callback: Callable[[str, str], None],
    ) -> None:
        """
        Automatically run database schema migrations inside the newly launched container
        when standard framework migration tools (e.g., Laravel artisan) are detected.
        """
        sanitized_name = re.sub(r"[^a-zA-Z0-9_.-]", "-", container_name.lower())
        artisan_path = os.path.join(workspace_dir, "artisan")

        if os.path.exists(artisan_path):
            log_callback("info", f"[PostgreSQL] Mendeteksi project Laravel — menjalankan 'php artisan migrate --force' pada database...")
            time.sleep(2)
            docker_bin = shutil.which("docker") or "/usr/bin/docker"
            if os.path.exists(docker_bin) or shutil.which("docker"):
                try:
                    proc = subprocess.run(
                        [docker_bin, "exec", sanitized_name, "php", "artisan", "migrate", "--force"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        timeout=60,
                    )
                    for line in (proc.stdout or "").splitlines():
                        if line.strip():
                            log_callback("info", f"[Migrate] {line.strip()}")
                    if proc.returncode == 0:
                        log_callback("info", "[PostgreSQL] Migrasi tabel database Laravel selesai dengan sukses!")
                    return
                except Exception:
                    pass

            # SDK fallback for exec
            try:
                import docker
                client = docker.from_env()
                cont = client.containers.get(sanitized_name)
                exit_code, output = cont.exec_run(["php", "artisan", "migrate", "--force"])
                if output:
                    for line in output.decode("utf-8", errors="ignore").splitlines():
                        if line.strip():
                            log_callback("info", f"[Migrate] {line.strip()}")
                if exit_code == 0:
                    log_callback("info", "[PostgreSQL] Migrasi tabel database selesai dengan sukses!")
            except Exception as e:
                log_callback("warning", f"[PostgreSQL] Post-deploy migration note: {e}")

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
                if clean:
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
        Parses port configuration with priority:
        1. Explicit port_mappings string (e.g. '8080:3000', '8080:80, 8443:443', '3000')
        2. Environment variables (HOST_PORT, PORT)
        3. EXPOSE instruction in Dockerfile
        4. Default 3000:3000
        """
        cli_args: List[str] = []
        sdk_ports: Dict[str, int] = {}
        primary_container_port = 3000
        parsed_any = False

        # 1. Explicit port mappings
        if explicit_mappings and str(explicit_mappings).strip():
            raw_entries = [p.strip() for p in str(explicit_mappings).split(",") if p.strip()]
            for entry in raw_entries:
                parts = entry.split(":")
                try:
                    if len(parts) == 1:
                        hp = int(parts[0])
                        cp = hp
                    elif len(parts) == 2:
                        hp = int(parts[0])
                        cp = int(parts[1])
                    elif len(parts) >= 3:
                        hp = int(parts[-2])
                        cp = int(parts[-1])
                    else:
                        continue

                    cli_args.extend(["-p", f"{hp}:{cp}"])
                    sdk_ports[f"{cp}/tcp"] = hp
                    if not parsed_any:
                        primary_container_port = cp
                    parsed_any = True
                    log_callback("info", f"[Docker] Port Mapping: Host {hp} -> Container {cp}")
                except ValueError:
                    continue

        # 2. Check .env for PORT or HOST_PORT
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
                        cp = hp
                    cli_args.extend(["-p", f"{hp}:{cp}"])
                    sdk_ports[f"{cp}/tcp"] = hp
                    primary_container_port = cp
                    parsed_any = True
                    log_callback("info", f"[Docker] Port dari konfigurasi .env: Host {hp} -> Container {cp}")
                except ValueError:
                    pass

        # 3. Check Dockerfile EXPOSE
        if not parsed_any and os.path.exists(full_df_path):
            try:
                with open(full_df_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    matches = re.findall(r"EXPOSE\s+(\d+)", content, re.IGNORECASE)
                    for port in matches:
                        p = int(port)
                        cli_args.extend(["-p", f"{p}:{p}"])
                        sdk_ports[f"{p}/tcp"] = p
                        if not parsed_any:
                            primary_container_port = p
                        parsed_any = True
                        log_callback("info", f"[Docker] Terdeteksi EXPOSE {p} pada Dockerfile: Host {p} -> Container {p}")
            except Exception:
                pass

        # 4. Fallback default
        if not parsed_any:
            cli_args.extend(["-p", "3000:3000"])
            sdk_ports["3000/tcp"] = 3000
            primary_container_port = 3000
            log_callback("info", "[Docker] Port default: Mapping Host 3000 -> Container 3000")

        return cli_args, sdk_ports, primary_container_port

    @staticmethod
    def ensure_dockerfile_or_generate(
        workspace_dir: str,
        dockerfile_path: str,
        compose_path: str,
        container_port: int,
        log_callback: Callable[[str, str], None],
    ) -> str:
        """
        Ensure workspace has a buildable Dockerfile or Docker Compose file.
        If missing, detect project type and auto-generate an optimized Dockerfile.
        """
        full_compose = os.path.join(workspace_dir, compose_path)
        if os.path.exists(full_compose):
            return compose_path

        full_df = os.path.join(workspace_dir, dockerfile_path)
        if os.path.exists(full_df):
            return dockerfile_path

        root_df = os.path.join(workspace_dir, "Dockerfile")
        if os.path.exists(root_df):
            return "Dockerfile"

        # Detect tech stack
        detected_fw = "Generic Web App"
        generated_content = ""

        pkg_json = os.path.join(workspace_dir, "package.json")
        req_txt = os.path.join(workspace_dir, "requirements.txt")
        py_files = [f for f in ("main.py", "app.py", "manage.py") if os.path.exists(os.path.join(workspace_dir, f))]
        composer_json = os.path.join(workspace_dir, "composer.json")
        index_html = os.path.join(workspace_dir, "index.html")

        if os.path.exists(pkg_json):
            is_next = False
            try:
                with open(pkg_json, "r", encoding="utf-8", errors="ignore") as f:
                    raw_pkg = f.read().lower()
                    if '"next"' in raw_pkg:
                        is_next = True
            except Exception:
                pass

            if is_next:
                detected_fw = "Next.js"
                generated_content = (
                    "FROM node:20-alpine\n"
                    "WORKDIR /app\n"
                    "COPY package*.json ./\n"
                    "RUN npm install --legacy-peer-deps\n"
                    "COPY . .\n"
                    f"ENV PORT={container_port}\n"
                    "ENV NODE_ENV=production\n"
                    "RUN npm run build || true\n"
                    f"EXPOSE {container_port}\n"
                    "CMD [\"npm\", \"start\"]\n"
                )
            else:
                detected_fw = "Node.js"
                generated_content = (
                    "FROM node:20-alpine\n"
                    "WORKDIR /app\n"
                    "COPY package*.json ./\n"
                    "RUN npm install --legacy-peer-deps\n"
                    "COPY . .\n"
                    f"ENV PORT={container_port}\n"
                    f"EXPOSE {container_port}\n"
                    "CMD [\"npm\", \"start\"]\n"
                )
        elif os.path.exists(req_txt) or py_files:
            detected_fw = "Python"
            cmd_line = f"python -m uvicorn main:app --host 0.0.0.0 --port {container_port}" if "main.py" in py_files else (f"python app.py" if "app.py" in py_files else f"python -m http.server {container_port}")
            generated_content = (
                "FROM python:3.11-slim\n"
                "WORKDIR /app\n"
                "RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev gcc build-essential curl && rm -rf /var/lib/apt/lists/*\n"
                "COPY requirements.txt* ./\n"
                "RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi\n"
                "COPY . .\n"
                f"ENV PORT={container_port}\n"
                f"EXPOSE {container_port}\n"
                f"CMD [\"sh\", \"-c\", \"{cmd_line}\"]\n"
            )
        elif os.path.exists(composer_json) or os.path.exists(os.path.join(workspace_dir, "artisan")):
            detected_fw = "PHP / Laravel"
            generated_content = (
                "FROM php:8.2-cli-alpine\n"
                "WORKDIR /var/www/html\n"
                "RUN apk add --no-cache libpq-dev postgresql-client\n"
                "RUN docker-php-ext-install pdo pdo_pgsql\n"
                "COPY . .\n"
                f"ENV PORT={container_port}\n"
                f"EXPOSE {container_port}\n"
                f"CMD [\"php\", \"-S\", \"0.0.0.0:{container_port}\", \"-t\", \"public\"]\n"
            )
        elif os.path.exists(index_html):
            detected_fw = "Static HTML / Web"
            generated_content = (
                "FROM nginx:alpine\n"
                "COPY . /usr/share/nginx/html\n"
                "EXPOSE 80\n"
                "CMD [\"nginx\", \"-g\", \"daemon off;\"]\n"
            )
        else:
            detected_fw = "Standard Web Container"
            generated_content = (
                "FROM python:3.11-alpine\n"
                "WORKDIR /app\n"
                "COPY . .\n"
                f"ENV PORT={container_port}\n"
                f"EXPOSE {container_port}\n"
                f"CMD [\"python\", \"-m\", \"http.server\", \"{container_port}\"]\n"
            )

        target_file = os.path.join(workspace_dir, "Dockerfile")
        with open(target_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(generated_content)

        log_callback("info", f"[Docker] Dockerfile tidak ditemukan di project — Otomatis membuat Dockerfile optimal untuk stack '{detected_fw}' (Port: {container_port}).")
        return "Dockerfile"

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
        """Find the Docker network where psm-postgres resides so deployed containers can auto-connect."""
        try:
            import docker
            client = docker.from_env()
            try:
                pg = client.containers.get("psm-postgres")
                nets = list((pg.attrs.get("NetworkSettings", {}).get("Networks") or {}).keys())
                if nets:
                    return nets[0]
            except Exception:
                pass
            for net in client.networks.list():
                if net.name == "psm-network" or net.name.endswith("_psm-network"):
                    return net.name
        except Exception:
            pass
        return None

    @staticmethod
    def build_and_run_dockerfile(
        workspace_dir: str,
        dockerfile_path: str,
        image_tag: str,
        container_name: str,
        log_callback: Callable[[str, str], None],
        port_mappings: Optional[str] = None
    ) -> bool:
        """Build image using Dockerfile and launch container directly.
        Automatically attaches container to the PostgreSQL Docker network (psm-network)
        and runs post-deploy database migrations if applicable.
        """
        full_df_path = os.path.join(workspace_dir, dockerfile_path)
        if not os.path.exists(full_df_path):
            log_callback("error", f"[Docker] Dockerfile not found at {full_df_path}")
            return False

        # Ensure PHP/Laravel Dockerfiles have pdo_pgsql and normalized LF scripts
        DeploymentEngine.prepare_dockerfile_for_postgres(workspace_dir, dockerfile_path, log_callback)

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
                    if clean:
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

            # Ports, Network & Run
            run_cmd = [
                docker_bin, "run", "-d",
                "--restart", "unless-stopped",
                "--name", sanitized_name,
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
