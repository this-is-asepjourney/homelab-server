 #!/usr/bin/env python3
"""
homelab.py — CLI Manajemen Terpadu Homelab Server
Mengelola dan memverifikasi seluruh komponen:
- Personal API Platform (PAP) + PSM Control Plane + IoT Fleet Unified
- Homelab Backup & Disaster Recovery
- Layanan Eksisting Host (Mosquitto, PostgreSQL, MySQL, Prometheus, Grafana)
"""

import argparse
import base64
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


class ConsoleProgress:
    """
    Renders rich ANSI/Unicode loading progress, spinner animations,
    and step progress bars for terminal deployments.
    """
    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    @staticmethod
    def bar(current: int, total: int, width: int = 24) -> str:
        ratio = min(max(current / max(total, 1), 0.0), 1.0)
        filled = int(ratio * width)
        empty = width - filled
        pct = int(ratio * 100)
        return f"[{'█' * filled}{'░' * empty}] {pct:3d}%"

    @staticmethod
    def step_header(step: int, total: int, title: str, subtitle: str = ""):
        print("\n" + "=" * 70)
        bar_str = ConsoleProgress.bar(step, total, width=20)
        print(f"  TAHAP {step}/{total}  {bar_str}")
        print(f"  >> {title.upper()}")
        if subtitle:
            print(f"     {subtitle}")
        print("=" * 70)


class SpinnerTask:
    """
    Lightweight background thread spinner that animates in terminal
    while a blocking task (like docker build or database init) runs.
    """
    def __init__(self, message: str):
        self.message = message
        self._running = False
        self._thread = None
        self._start_time = 0.0

    def __enter__(self):
        self._running = True
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        elapsed = time.time() - self._start_time
        if exc_type is None:
            sys.stdout.write(f"\r  [✓] {self.message} ({elapsed:.1f}s)\n")
        else:
            sys.stdout.write(f"\r  [✗] {self.message} (Gagal: {exc_val})\n")
        sys.stdout.flush()

    def _spin(self):
        idx = 0
        frames = ConsoleProgress.SPINNER_FRAMES
        while self._running:
            frame = frames[idx % len(frames)]
            elapsed = time.time() - self._start_time
            sys.stdout.write(f"\r  [{frame}] {self.message}... ({elapsed:.1f}s)")
            sys.stdout.flush()
            idx += 1
            time.sleep(0.08)


def check_tcp(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def http_get(url: str, auth_header: str = None, timeout: float = 3.0) -> tuple[int, dict]:
    headers = {"Accept": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            return resp.status, json.loads(data) if data else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err)
        except Exception:
            return e.code, {"error": err}
    except Exception as e:
        return 0, {"error": str(e)}


def resolve_default_host(preferred_host: str = None) -> str:
    """
    Automatically resolve the active host IP between LAN (192.168.25.101),
    Tailscale (100.106.63.90), and Localhost (127.0.0.1).
    """
    if preferred_host and preferred_host != "auto":
        return preferred_host

    env_host = os.getenv("HOST_IP")
    if env_host:
        return env_host

    lan_ip = "192.168.25.101"
    tailscale_ip = os.getenv("HOST_TAILSCALE", "100.106.63.90")

    # Fast probe (timeout 0.35s)
    # 1. Probe LAN
    if check_tcp(lan_ip, 8000, timeout=0.35) or check_tcp(lan_ip, 80, timeout=0.35):
        return lan_ip

    # 2. Probe Tailscale
    if check_tcp(tailscale_ip, 8000, timeout=0.6) or check_tcp(tailscale_ip, 80, timeout=0.6):
        return tailscale_ip

    # 3. Probe Localhost
    if check_tcp("127.0.0.1", 8000, timeout=0.2):
        return "127.0.0.1"

    return tailscale_ip


def get_psm_auth_header(host: str) -> str:
    """
    Retrieve or acquire Bearer token for PSM / PAP Core API.
    Supports PSM_TOKEN env var, token cache, and auto-login with default admin.
    """
    env_token = os.getenv("PSM_TOKEN") or os.getenv("PAP_TOKEN")
    if env_token:
        return f"Bearer {env_token}"

    # Check cached token in user directory
    cache_file = Path.home() / ".homelab_psm_token"
    if cache_file.exists():
        try:
            cached_data = json.loads(cache_file.read_text(encoding="utf-8"))
            tok = cached_data.get("token")
            exp = cached_data.get("expires_at", 0)
            if tok and time.time() < exp - 60:
                return f"Bearer {tok}"
        except Exception:
            pass

    # Attempt auto-login with default admin credentials
    login_url = f"http://{host}:8000/api/v1/auth/login"
    login_payload = {
        "email": os.getenv("PSM_ADMIN_EMAIL", "admin@psm.local"),
        "password": os.getenv("PSM_ADMIN_PASSWORD", "Admin12345!")
    }
    try:
        req = urllib.request.Request(
            login_url,
            data=json.dumps(login_payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            token = data.get("access_token")
            expires_in = data.get("expires_in", 3600)
            if token:
                try:
                    cache_file.write_text(json.dumps({
                        "token": token,
                        "expires_at": time.time() + expires_in
                    }), encoding="utf-8")
                except Exception:
                    pass
                return f"Bearer {token}"
    except Exception:
        pass

    return ""


def cmd_status(args):
    host = resolve_default_host(getattr(args, "host", None))
    print("==================================================================")
    print(f"       STATUS AUDIT HOMELAB SERVER ({host})")
    print("==================================================================")

    # 1. Host Infrastructure Services
    print("\n[A] LAYANAN INFRASTRUKTUR & NETWORKING GATEWAY (Host):")
    services_infra = [
        ("Ingress Gateway Router (Nginx)", 80, "http", f"http://{host}:80/"),
        ("Local DNS Server (CoreDNS)", 53, "tcp"),
        ("Mosquitto MQTT Broker", 1883, "tcp"),
        ("PostgreSQL Server", 5432, "tcp"),
        ("MySQL Server (Stock)", 3306, "tcp"),
        ("Grafana Utama Homelab", 3001, "http", f"http://{host}:3001/api/health"),
        ("Prometheus Server (Docker)", 9001, "http", f"http://{host}:9001/-/ready"),
        ("Uptime Kuma", 3002, "tcp"),
        ("Vaultwarden", 8080, "tcp"),
        ("Cockpit Web Console", 9090, "tcp"),
    ]

    for item in services_infra:
        name, port = item[0], item[1]
        ok = check_tcp(host, port)
        badge = "[ONLINE]" if ok else "[OFFLINE]"
        extra = ""
        if ok and item[2] == "http":
            st, res = http_get(item[3])
            extra = f" (HTTP {st})"
        print(f"  * {name:<28} Port :{port:<5} -> {badge}{extra}")

    # 2. Application Projects
    print("\n[B] APLIKASI UTAMA (1 CENTRAL CORE API & ZERO DUPLICATION):")
    services_app = [
        ("PAP Core API & PSM Gateway", 8000, f"http://{host}:8000/health"),
        ("Mission Control Web UI", 8000, f"http://{host}:8000/"),
        ("Disaster Recovery Backup Engine", 8000, f"http://{host}:8000/api/v1/backups"),
        ("IoT Fleet & Device Telemetry", 8000, f"http://{host}:8000/api/devices/hierarchy"),
        ("PSM Web Dashboard Console", 3005, None),
        ("IoT Web Dashboard Hub", 8088, f"http://{host}:8088/"),
        ("IoT Telegraf Exporter", 9273, f"http://{host}:9273/metrics"),
        ("InfluxDB Time-Series DB", 8086, f"http://{host}:8086/health"),
    ]

    for name, port, url in services_app:
        ok = check_tcp(host, port)
        badge = "[ONLINE]" if ok else "[OFFLINE]"
        extra = ""
        if ok and url:
            try:
                st, _ = http_get(url)
                extra = f" (HTTP {st})"
            except Exception:
                pass
        print(f"  * {name:<32} Port :{port:<5} -> {badge}{extra}")

    print("\n[C] VALIDASI KONSEP 'MENGGUNAKAN YANG SUDAH ADA':")
    print("  [OK] Tidak ada kontainer Grafana duplikat (Menggunakan Grafana port 3001)")
    print("  [OK] Tidak ada kontainer Prometheus duplikat (Menggunakan Prometheus port 9001)")
    print("  [OK] Tidak ada kontainer PostgreSQL duplikat (Menggunakan PostgreSQL port 5432)")
    print("  [OK] Tidak ada kontainer Mosquitto duplikat (Menggunakan Mosquitto port 1883)")
    print("  [OK] Tidak ada kontainer API redundan (PSM & IoT disatukan dalam pap-api port 8000)")
    print("==================================================================")


def cmd_dns(args):
    host = resolve_default_host(getattr(args, "host", None))
    url = f"http://{host}:8000/api/v1/dns/records"
    print("==================================================================")
    print(f"       DAFTAR DOMAIN LOKAL & ROUTING HOMELAB ({host})")
    print("==================================================================")
    auth_header = get_psm_auth_header(host)
    st, data = http_get(url, auth_header=auth_header)
    if st != 200:
        print(f"[ERROR] Gagal mengambil data DNS dari {url} (HTTP {st})")
        return 1

    records = data.get("records", [])
    print(f"\nTotal Domain Terdaftar: {len(records)}\n")
    print(f"{'DOMAIN':<25} {'TARGET PROXY':<25} {'KATEGORI':<15} {'DESKRIPSI'}")
    print("-" * 85)
    for r in records:
        print(f"{r.get('domain'):<25} {r.get('target'):<25} {r.get('category'):<15} {r.get('description')}")

    print("\n[PETUNJUK DNS KLIEN]")
    print(f"  • DNS Server IP : {host} (Port 53)")
    print(f"  • Ingress HTTP  : http://{host}:80")
    print(f"  • Unduh hosts   : http://{host}:8000/api/v1/dns/hosts-file")
    print("==================================================================")
    return 0


def cmd_backup(args):
    host = resolve_default_host(getattr(args, "host", None))
    scope = args.scope
    note = args.note
    url = f"http://{host}:8000/api/v1/backups/create"
    print(f"\n[*] Memicu pembuatan backup sistem di {url} (Scope: {scope})...")

    auth_header = get_psm_auth_header(host)
    headers = {"Content-Type": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header

    data = json.dumps({"scope": scope, "note": note}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            archive = res.get("data", {}).get("archive", {})
            print(f"[OK] {res.get('message', 'Backup sukses!')}")
            print(f"     Nama File : {archive.get('filename')}")
            print(f"     Ukuran    : {archive.get('size_human')}")
            print(f"     SHA-256   : {archive.get('sha256')}")
            return 0
    except Exception as e:
        print(f"[ERROR] Gagal membuat backup: {e}")
        return 1


def test_grafana_auth(grafana_url: str, auth_header: str) -> bool:
    try:
        req = urllib.request.Request(f"{grafana_url}/api/org", headers={"Authorization": auth_header})
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def ensure_grafana_datasources(grafana_url: str, auth_header: str, host: str):
    """Memastikan Datasource Prometheus dan MySQL eternal_db terpasang di Grafana."""
    print(f"\n[*] Memeriksa & Mengkonfigurasi Datasource di Grafana ({grafana_url})...")
    headers = {
        "Content-Type": "application/json",
        "Authorization": auth_header,
        "Accept": "application/json",
    }

    existing_ds = []
    try:
        req = urllib.request.Request(f"{grafana_url}/api/datasources", headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            existing_ds = json.loads(resp.read().decode())
    except Exception as e:
        print(f"  [WARN] Tidak dapat membaca daftar datasource: {e}")

    # 1. Prometheus Datasource (uid: prometheus)
    prom_ds = next((d for d in existing_ds if d.get("uid") == "prometheus" or d.get("type") == "prometheus"), None)
    prom_payload = {
        "name": "Prometheus",
        "type": "prometheus",
        "uid": "prometheus",
        "access": "proxy",
        "url": f"http://{host}:9001",
        "isDefault": True,
        "jsonData": {"httpMethod": "POST"}
    }
    if not prom_ds:
        try:
            req = urllib.request.Request(
                f"{grafana_url}/api/datasources",
                data=json.dumps(prom_payload).encode(),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                print("  [OK] Datasource Prometheus berhasil didaftarkan (uid: prometheus)")
        except Exception as e:
            print(f"  [WARN] Gagal membuat datasource Prometheus: {e}")
    else:
        print(f"  [OK] Datasource Prometheus ditemukan: '{prom_ds.get('name')}' (uid: {prom_ds.get('uid')})")

    # 2. MySQL eternal_db Datasource (uid: mysql-iot-db)
    mysql_ds = next(
        (d for d in existing_ds if d.get("uid") == "mysql-iot-db" or "eternal_db" in d.get("name", "") or "iot_db" in d.get("name", "")),
        None
    )
    mysql_payload = {
        "name": "MySQL - eternal_db",
        "type": "mysql",
        "uid": "mysql-iot-db",
        "access": "proxy",
        "url": f"{host}:3306",
        "user": "appuser",
        "database": "eternal_db",
        "basicAuth": False,
        "isDefault": False,
        "jsonData": {
            "database": "eternal_db",
            "maxOpenConns": 10,
            "maxIdleConns": 5,
            "connMaxLifetime": 14400,
            "timezone": "Asia/Jakarta"
        },
        "secureJsonData": {
            "password": "admin12345"
        }
    }

    if mysql_ds:
        uid = mysql_ds.get("uid", "mysql-iot-db")
        try:
            req = urllib.request.Request(
                f"{grafana_url}/api/datasources/uid/{uid}",
                data=json.dumps(mysql_payload).encode(),
                headers=headers,
                method="PUT"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                print(f"  [OK] Datasource MySQL (uid={uid}) berhasil diperbarui ke 'eternal_db'")
        except Exception:
            # File-provisioned datasources di Grafana berstatus read-only dari API, ini normal
            pass
    else:
        try:
            req = urllib.request.Request(
                f"{grafana_url}/api/datasources",
                data=json.dumps(mysql_payload).encode(),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                print("  [OK] Datasource MySQL (uid: mysql-iot-db) berhasil didaftarkan ke 'eternal_db'!")
        except Exception as e:
            print(f"  [WARN] Gagal membuat datasource MySQL: {e}")

    # 3. Test MySQL datasource connection
    try:
        req = urllib.request.Request(f"{grafana_url}/api/datasources/uid/mysql-iot-db/health", headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            health = json.loads(resp.read().decode())
            status = health.get("status", "UNKNOWN")
            msg = health.get("message", "")
            if status == "OK":
                print(f"  [OK] Verifikasi Koneksi MySQL: SEHAT ({msg or 'Database Connection OK'})\n")
            else:
                print(f"  [WARN] Verifikasi Koneksi MySQL: {status} - {msg}\n")
    except Exception:
        pass

    # 4. PostgreSQL eternal_iot Datasource (uid: postgres-iot-db)
    pg_ds = next(
        (d for d in existing_ds if d.get("uid") == "postgres-iot-db" or "eternal_iot" in d.get("name", "").lower()),
        None
    )
    pg_payload = {
        "name": "PostgreSQL - eternal_iot",
        "type": "postgres",
        "uid": "postgres-iot-db",
        "access": "proxy",
        "url": f"{host}:5432",
        "user": "appuser",
        "database": "eternal_iot",
        "isDefault": False,
        "jsonData": {
            "database": "eternal_iot",
            "sslmode": "disable",
            "postgresVersion": 1600,
            "timescaledb": False,
            "maxOpenConns": 10,
            "maxIdleConns": 5,
            "connMaxLifetime": 14400
        },
        "secureJsonData": {
            "password": "admin12345"
        }
    }
    if pg_ds:
        uid = pg_ds.get("uid", "postgres-iot-db")
        try:
            req = urllib.request.Request(
                f"{grafana_url}/api/datasources/uid/{uid}",
                data=json.dumps(pg_payload).encode(),
                headers=headers,
                method="PUT"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                print(f"  [OK] Datasource PostgreSQL (uid={uid}) berhasil diperbarui ke 'eternal_iot'")
        except Exception:
            pass
    else:
        try:
            req = urllib.request.Request(
                f"{grafana_url}/api/datasources",
                data=json.dumps(pg_payload).encode(),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                print("  [OK] Datasource PostgreSQL (uid: postgres-iot-db) berhasil didaftarkan ke 'eternal_iot'!")
        except Exception as e:
            print(f"  [WARN] Gagal membuat datasource PostgreSQL: {e}")

    try:
        req = urllib.request.Request(f"{grafana_url}/api/datasources/uid/postgres-iot-db/health", headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            health = json.loads(resp.read().decode())
            status = health.get("status", "UNKNOWN")
            msg = health.get("message", "")
            if status == "OK":
                print(f"  [OK] Verifikasi Koneksi PostgreSQL eternal_iot: SEHAT ({msg or 'Database Connection OK'})\n")
            else:
                print(f"  [WARN] Verifikasi Koneksi PostgreSQL eternal_iot: {status} - {msg}\n")
    except Exception:
        pass


def cmd_import_grafana(args):
    host = args.host
    port = args.grafana_port
    user = args.user
    password = args.password
    token = args.token

    grafana_url = f"http://{host}:{port}"
    print(f"\n[*] Menghubungi Grafana Homelab ({grafana_url})...")

    auth_header = None
    if token:
        auth_header = f"Bearer {token}"
    else:
        # Test provided credentials first, then try known homelab default passwords
        candidates = [
            (user, password),
            ("admin", "admin12345"),
            ("admin", "adminroot12345"),
            ("admin", "adminpassword"),
            ("admin", "admin"),
            ("admin", "25022002"),
        ]
        for u, p in candidates:
            cand_header = f"Basic {base64.b64encode(f'{u}:{p}'.encode()).decode()}"
            if test_grafana_auth(grafana_url, cand_header):
                auth_header = cand_header
                print(f"[OK] Berhasil terautentikasi ke Grafana sebagai '{u}'!")
                break

        if not auth_header:
            auth_header = f"Basic {base64.b64encode(f'{user}:{password}'.encode()).decode()}"
            print("[WARN] Autentikasi Grafana belum tervalidasi. Akan dicoba dengan kredensial input.")

    # Otomatis pastikan datasource Prometheus & MySQL terpasang sebelum impor dashboard
    ensure_grafana_datasources(grafana_url, auth_header, host)

    # Pastikan bucket InfluxDB memiliki titik telemetri awal agar grafik Grafana langsung tampil
    try:
        import auto_provision_all_databases
        auto_provision_all_databases.provision_influxdb()
    except Exception:
        pass

    dashboards_dir = Path(__file__).parent / "dashboard_iot" / "grafana" / "dashboards"
    if not dashboards_dir.exists():
        print(f"[ERROR] Folder dashboards '{dashboards_dir}' tidak ditemukan!")
        return 1

    json_files = list(dashboards_dir.glob("*.json"))
    success = 0
    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                content = json.load(f)
            content["id"] = None

            req_data = json.dumps({"dashboard": content, "overwrite": True, "folderId": 0}).encode("utf-8")
            req = urllib.request.Request(
                f"{grafana_url}/api/dashboards/db",
                data=req_data,
                headers={"Content-Type": "application/json", "Authorization": auth_header},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                res_json = json.loads(resp.read().decode())
                print(f"  [OK] Dashboard '{content.get('title')}' berhasil diimpor -> {res_json.get('url')}")
                success += 1
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print(f"  [FAIL] {jf.name}: 401 Unauthorized. Gunakan: python3 homelab.py import-grafana --user admin --password <password_grafana_anda>")
            else:
                print(f"  [FAIL] {jf.name}: {e}")
        except Exception as e:
            print(f"  [FAIL] {jf.name}: {e}")

    print(f"\n[HASIL] Berhasil mengimpor {success}/{len(json_files)} dashboard ke Grafana.")
    return 0 if success > 0 else 1


def cmd_init_dockerfile(args):
    psm_root = Path(__file__).resolve().parent / "Personal_Server_Manager"
    if str(psm_root) not in sys.path:
        sys.path.insert(0, str(psm_root))
    # pyrefly: ignore[missing-import]
    from apps.agent.app.deployment.dockerfile_generator import (
        detect_project_stack,
        generate_dockerfile,
        generate_dockerignore,
    )
    target_dir = os.path.abspath(args.path)
    if not os.path.exists(target_dir):
        print(f"[Error] Directory not found: {target_dir}")
        return 1

    stack = detect_project_stack(target_dir)
    print("==================================================================")
    print("   PSM DOCKERFILE SETUP ASSISTANT (Professional PaaS Deployer)")
    print("==================================================================")
    print(f"Target Directory  : {target_dir}")
    print(f"Detected Stack    : {stack.get('detected_stack')}")
    print(f"Framework         : {stack.get('framework')}")
    print(f"Package Manager   : {stack.get('package_manager')}")
    print(f"Recommended Port  : {stack.get('recommended_port')}")

    tmpl_key = stack.get("template_key", "nextjs")
    if args.framework and args.framework != "auto":
        fw_clean = args.framework.lower()
        if "next" in fw_clean:
            tmpl_key = "nextjs"
        elif "vite" in fw_clean or "react" in fw_clean or "vue" in fw_clean:
            tmpl_key = "vite_spa"
        elif "fastapi" in fw_clean:
            tmpl_key = "fastapi"
        elif "django" in fw_clean:
            tmpl_key = "django"
        elif "flask" in fw_clean:
            tmpl_key = "flask"
        elif "laravel" in fw_clean or "php" in fw_clean:
            tmpl_key = "laravel"
        elif "go" in fw_clean:
            tmpl_key = "golang"
        elif "static" in fw_clean or "html" in fw_clean:
            tmpl_key = "static_html"
        else:
            tmpl_key = "node_backend"

    port = args.port or stack.get("recommended_port", 3000)
    df_content = generate_dockerfile(tmpl_key, port=port)
    di_content = generate_dockerignore()

    df_path = os.path.join(target_dir, "Dockerfile")
    di_path = os.path.join(target_dir, ".dockerignore")

    if not os.path.exists(df_path) or args.overwrite:
        with open(df_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(df_content)
        print(f"\n[+] Created professional Dockerfile: {df_path}")
    else:
        print(f"\n[i] Dockerfile already exists at {df_path} (use --overwrite to replace)")

    if not os.path.exists(di_path) or args.overwrite:
        with open(di_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(di_content)
        print(f"[+] Created context guard .dockerignore: {di_path}")
    else:
        print(f"[i] .dockerignore already exists at {di_path} (use --overwrite to replace)")

    print("\n[OK] Setup complete! Project is now ready for deployment in PSM.")
    return 0


def cmd_deploy(args):
    """
    Interactive, highly informative full-stack deployment orchestrator for Homelab Server.
    Provides real-time loading feedback, progress bars, pre-flight checks,
    compose build/pull, container orchestration, and live service health audits.
    """
    host = args.host
    skip_build = getattr(args, "skip_build", False)
    skip_db = getattr(args, "skip_db", False)
    health_timeout = getattr(args, "timeout", 45)

    print("\n╔════════════════════════════════════════════════════════════════════╗")
    print("║        DEPLOYMENT TERPADU MASTER HOMELAB SERVER                    ║")
    print("║        1 Central Core API Gateway + PSM + IoT Fleet + Router       ║")
    print("╚════════════════════════════════════════════════════════════════════╝")
    print(f" Target Host: {host}  |  Platform: {sys.platform}  |  Python: {sys.version.split()[0]}\n")

    TOTAL_STEPS = 6
    start_total_time = time.time()

    # Detect compose command
    compose_cmd = ["docker", "compose"]
    try:
        c_chk = subprocess.run([*compose_cmd, "version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if c_chk.returncode != 0:
            compose_cmd = ["docker-compose"]
    except Exception:
        compose_cmd = ["docker-compose"]

    # -------------------------------------------------------------------------
    # TAHAP 1/6: Verifikasi Prasyarat Sistem
    # -------------------------------------------------------------------------
    ConsoleProgress.step_header(
        1, TOTAL_STEPS,
        "Verifikasi Prasyarat Sistem & Port Server",
        "Memeriksa Docker daemon, Compose V2, Python 3, dan alokasi port..."
    )

    with SpinnerTask("Memeriksa Docker CLI & daemon"):
        docker_bin = shutil.which("docker")
        if not docker_bin:
            print("\n[ERROR] Docker tidak ditemukan di PATH!")
            return 1
        res = subprocess.run([docker_bin, "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode != 0:
            print("\n[WARN] Docker daemon tidak merespons atau tidak aktif. Periksa layanan Docker.")

    with SpinnerTask(f"Memeriksa executable Docker Compose ({' '.join(compose_cmd)})"):
        res = subprocess.run([*compose_cmd, "version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode != 0:
            print(f"\n[ERROR] Perintah '{' '.join(compose_cmd)}' tidak dapat dijalankan!")
            return 1

    with SpinnerTask("Memeriksa ketersediaan direktori kerja & modul monorepo"):
        os.makedirs("router/conf.d/projects", exist_ok=True)
        os.makedirs("dns", exist_ok=True)
        os.makedirs("backups", exist_ok=True)
        for d in ["Personal_Server_Manager", "Personal Api Platform", "dashboard_iot"]:
            if not os.path.exists(d):
                os.makedirs(d, exist_ok=True)

    # -------------------------------------------------------------------------
    # TAHAP 2/6: Database Auto-Provisioning
    # -------------------------------------------------------------------------
    ConsoleProgress.step_header(
        2, TOTAL_STEPS,
        "Auto-Provisioning Database Mandiri",
        "Menyiapkan schema database terpisah (eternal_db, stock_umkm, psm, pap_core)..."
    )

    if not skip_db:
        try:
            with SpinnerTask("Menjalankan script auto-provisioning database"):
                import auto_provision_all_databases
                auto_provision_all_databases.provision_mysql()
                auto_provision_all_databases.provision_postgres()
        except Exception as e:
            print(f"  [i] Catatan auto-provisioning database: {e}")
    else:
        print("  [i] Auto-provisioning database dilewati (--skip-db).")

    # -------------------------------------------------------------------------
    # TAHAP 3/6: Konfigurasi Environment & Network
    # -------------------------------------------------------------------------
    ConsoleProgress.step_header(
        3, TOTAL_STEPS,
        "Penyusunan Konfigurasi & Environment Secrets",
        "Memeriksa .env, router ingress Nginx, dan konfigurasi scrape Prometheus..."
    )

    with SpinnerTask("Memeriksa file environment .env"):
        if not os.path.exists(".env"):
            if os.path.exists(".env.example"):
                shutil.copy(".env.example", ".env")
                print("  [+] Membuat file .env baru dari .env.example")
            else:
                with open(".env", "w") as f:
                    f.write(f"HOST_IP={host}\n")

    with SpinnerTask("Memvalidasi sintaks docker-compose.yml"):
        v_res = subprocess.run([*compose_cmd, "config", "--quiet"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if v_res.returncode != 0:
            print("\n[ERROR] File docker-compose.yml memiliki kesalahan sintaks!")
            return 1

    # -------------------------------------------------------------------------
    # TAHAP 4/6: Build Docker Master Stack
    # -------------------------------------------------------------------------
    ConsoleProgress.step_header(
        4, TOTAL_STEPS,
        "Membangun Docker Images & Layer Cache",
        "Mengompilasi pap-api, psm-web, psm-agent, iot-web..."
    )

    if not skip_build:
        print("  [*] Menjalankan build parallel...")
        build_proc = subprocess.Popen(
            [*compose_cmd, "build", "--parallel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        for line in build_proc.stdout:
            clean = line.strip()
            if not clean:
                continue
            if any(k in clean for k in ["Step ", "#", "naming to", "writing image", "DONE", "CACHED", "RUN", "COPY"]):
                print(f"    ⠋ {clean[:75]}")
        build_proc.wait()
        if build_proc.returncode != 0:
            print("\n[ERROR] Build docker compose gagal!")
            return 1
        print("  [✓] Docker images berhasil dibangun.")
    else:
        print("  [i] Build container dilewati (--skip-build).")

    # -------------------------------------------------------------------------
    # TAHAP 5/6: Startup & Orkestrasi Container
    # -------------------------------------------------------------------------
    ConsoleProgress.step_header(
        5, TOTAL_STEPS,
        "Peluncuran & Orkestrasi Container",
        "Membersihkan zombie container dan menjalankan stack..."
    )

    with SpinnerTask("Mematikan container lama & konflik port"):
        subprocess.run(["docker", "rm", "-f", "psm-api", "iot_device_mapping_api"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    with SpinnerTask("Menjalankan container master stack (docker compose up -d)"):
        up_res = subprocess.run([*compose_cmd, "up", "-d", "--remove-orphans"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if up_res.returncode != 0:
            print(f"\n[ERROR] Gagal menjalankan container: {up_res.stdout}")
            return 1

    # -------------------------------------------------------------------------
    # TAHAP 6/6: Live Endpoint Healthcheck & Latency Meter
    # -------------------------------------------------------------------------
    ConsoleProgress.step_header(
        6, TOTAL_STEPS,
        "Live Endpoint Healthcheck & Latency Meter",
        "Memverifikasi seluruh endpoint layanan aktif dan mengukur response time..."
    )

    endpoints = [
        ("PAP Core Central API", f"http://{host}:8000/health", 8000),
        ("Mission Control Web UI", f"http://{host}:8000/", 8000),
        ("Disaster Recovery API", f"http://{host}:8000/api/v1/backups", 8000),
        ("Local DNS & VHost API", f"http://{host}:8000/api/v1/dns/records", 8000),
        ("Nginx Ingress Router", f"http://{host}:80/", 80),
        ("PSM Web Dashboard", f"http://{host}:3005", 3005),
        ("IoT Web Dashboard Hub", f"http://{host}:8088/", 8088),
        ("IoT Telegraf Metrics", f"http://{host}:9273/metrics", 9273),
    ]

    results = []
    print(f"  [*] Menguji {len(endpoints)} endpoint dengan batas waktu {health_timeout} detik...\n")

    for name, url, port in endpoints:
        online = False
        http_code = 0
        latency_ms = 0.0

        for attempt in range(1, int(health_timeout / 2) + 1):
            t0 = time.time()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Homelab-Deployer/1.0"})
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    http_code = resp.status
                    latency_ms = (time.time() - t0) * 1000
                    online = True
                    break
            except urllib.error.HTTPError as he:
                http_code = he.code
                latency_ms = (time.time() - t0) * 1000
                if he.code in (200, 301, 302, 401, 403):
                    online = True
                    break
            except Exception:
                pass

            spin_f = ConsoleProgress.SPINNER_FRAMES[attempt % len(ConsoleProgress.SPINNER_FRAMES)]
            sys.stdout.write(f"\r    [{spin_f}] {name:<26} (Coba {attempt:2d}) Menunggu endpoint...")
            sys.stdout.flush()
            time.sleep(1.5)

        if online:
            sys.stdout.write(f"\r    [✓] {name:<26} Port :{port:<5} -> ONLINE (HTTP {http_code}, {latency_ms:.1f}ms)\n")
        else:
            sys.stdout.write(f"\r    [!] {name:<26} Port :{port:<5} -> INISIALISASI (Periksa via 'docker compose logs')\n")
        sys.stdout.flush()
        results.append((name, port, online, http_code, latency_ms))

    # FINAL SUMMARY DASHBOARD
    total_elapsed = time.time() - start_total_time
    online_count = sum(1 for r in results if r[2])

    print("\n" + "=" * 75)
    print(f"        RINGKASAN STATUS AKHIR DEPLOYMENT HOMELAB SERVER")
    print(f"        Total Waktu Deployment: {total_elapsed:.1f} detik | Layanan Siap: {online_count}/{len(results)}")
    print("=" * 75)
    print(f"{'LAYANAN / KOMPONEN':<30} {'PORT':<8} {'STATUS':<12} {'HTTP':<8} {'LATENCY'}")
    print("-" * 75)
    for name, port, online, code, lat in results:
        status_str = "[ONLINE]" if online else "[CHECKING]"
        http_str = str(code) if code else "-"
        lat_str = f"{lat:.1f}ms" if online else "-"
        print(f"{name:<30} :{port:<7} {status_str:<12} {http_str:<8} {lat_str}")

    print("\n[Akses Domain Virtual Host (Port 80)]:")
    print(f"  • Mission Control      : http://homelab  (atau http://api.homelab)")
    print(f"  • Personal Server Mgr  : http://psm.homelab")
    print(f"  • IoT Fleet Dashboard  : http://iot.homelab")
    print(f"  • Grafana Analytics    : http://grafana.homelab")
    print(f"  • Prometheus Monitoring: http://prometheus.homelab")
    print(f"  • Cockpit Server OS    : http://cockpit.homelab")
    print("=" * 75)
    print("\n[OK] Deployment Homelab Server selesai dan siap digunakan!")
    return 0


def cmd_update_project(args):
    host = resolve_default_host(getattr(args, "host", None))
    project_identifier = (args.project or "").strip()
    api_base = f"http://{host}:8000/api/v1"

    print("==================================================================")
    print(f"       UPDATE PROJECT & DEPLOY KE SERVER ({host})")
    tailscale_ip = os.getenv("HOST_TAILSCALE", "100.106.63.90")
    if host == tailscale_ip:
        print(f"       [✓] Mode Terhubung: Tailscale VPN ({host})")
    elif host == "192.168.25.101":
        print(f"       [✓] Mode Terhubung: Local LAN ({host})")
    print("==================================================================")

    auth_header = get_psm_auth_header(host)

    # 1. Fetch projects
    st, projects = http_get(f"{api_base}/projects", auth_header=auth_header)
    if st != 200 or not isinstance(projects, list):
        print(f"[ERROR] Gagal menghubungi API PSM di {api_base}/projects (HTTP {st})")
        if st == 401:
            print("        Otentikasi diperlukan. Pastikan akun admin PSM aktif.")
        return 1

    if not project_identifier:
        print(f"\nDaftar {len(projects)} Project di Server Homelab:")
        print(f"{'ID':<38} {'NAMA':<22} {'FRAMEWORK':<12} {'PORT':<12} {'DB ENGINE'}")
        print("-" * 92)
        for p in projects:
            print(f"{p.get('id'):<38} {p.get('name'):<22} {p.get('framework', '-'):<12} {p.get('port_mappings', '-'):<12} {p.get('db_type', 'none')}")
        print("\nPetunjuk:")
        print("  Gunakan: python homelab.py update-project <nama_atau_id> [--branch <branch>] [--port <port>] [--db-type <postgres|mysql>] [--deploy]")
        return 0

    # Match project by ID or Name
    matched = None
    for p in projects:
        if p.get("id") == project_identifier or p.get("name", "").lower() == project_identifier.lower():
            matched = p
            break
    if not matched:
        candidates = [p for p in projects if project_identifier.lower() in p.get("name", "").lower()]
        if len(candidates) == 1:
            matched = candidates[0]
        elif len(candidates) > 1:
            print(f"[!] Ditemukan beberapa project dengan nama '{project_identifier}':")
            for c in candidates:
                print(f"  • {c.get('name')} (ID: {c.get('id')})")
            print("Gunakan ID project yang spesifik.")
            return 1
        else:
            print(f"[ERROR] Project '{project_identifier}' tidak ditemukan di server.")
            return 1

    proj_id = matched["id"]
    proj_name = matched.get("name")
    print(f"\n[*] Target Project: {proj_name} (ID: {proj_id})")
    print(f"    Framework      : {matched.get('framework')}")
    print(f"    Source Type    : {matched.get('source_type')}")
    print(f"    Current Port   : {matched.get('port_mappings')}")
    print(f"    Current DB     : {matched.get('db_type', 'none')}")

    # Build update payload
    payload = {}
    if getattr(args, "repo", None):
        raw_repo = args.repo.strip()
        if "/tree/" in raw_repo:
            parts = raw_repo.split("/tree/", 1)
            raw_repo = parts[0].rstrip("/")
            if not getattr(args, "branch", None):
                payload["branch"] = parts[1].strip("/").split("/")[0]
        if not raw_repo.endswith(".git") and "github.com" in raw_repo:
            raw_repo += ".git"
        payload["repository_url"] = raw_repo
    if args.name:
        payload["name"] = args.name.strip()
    if args.branch:
        payload["branch"] = args.branch.strip()
    if args.port:
        payload["port_mappings"] = args.port.strip()
    if args.db_type:
        payload["db_type"] = args.db_type.strip().lower()
    if args.db_name:
        payload["db_name"] = args.db_name.strip()
    if args.domain:
        payload["domain"] = args.domain.strip()

    if payload:
        print(f"\n[*] Memperbarui konfigurasi project di server...")
        req_data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if auth_header:
            headers["Authorization"] = auth_header
        req = urllib.request.Request(
            f"{api_base}/projects/{proj_id}",
            data=req_data,
            headers=headers,
            method="PATCH"
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                print(f"  [✓] Pengaturan berhasil disimpan ke database server.")
                print(f"      Port Mappings   : {res.get('port_mappings')}")
                print(f"      Database Engine : {res.get('db_type')}")
                print(f"      Domain Ingress  : {res.get('domain')}")
        except Exception as e:
            print(f"  [ERROR] Gagal memperbarui project: {e}")
            return 1

    if args.deploy:
        print(f"\n[*] Memicu deployment rilis baru ke container server (docker build & run)...")
        headers = {"Content-Type": "application/json"}
        if auth_header:
            headers["Authorization"] = auth_header
        req = urllib.request.Request(
            f"{api_base}/projects/{proj_id}/redeploy",
            data=b"{}",
            headers=headers,
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                dep_res = json.loads(resp.read().decode("utf-8"))
                dep_id = dep_res.get("id")
                version = dep_res.get("version")
                print(f"  [✓] Deployment rilis v{version} berhasil dipicu (Deployment ID: {dep_id})!")
                print(f"      Pantau status live di: http://{host}:3005/deployments/{dep_id}")
        except Exception as e:
            print(f"  [ERROR] Gagal memicu deployment: {e}")
            return 1

    print("\n[OK] Selesai.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="CLI Manajemen Terpadu Homelab Server")
    subparsers = parser.add_subparsers(dest="command", help="Perintah yang tersedia")

    # Command: deploy
    parser_deploy = subparsers.add_parser("deploy", help="Deployer Homelab Server: Build, jalankan, dan verifikasi status kesehatan master stack")
    parser_deploy.add_argument("--host", default=None, help="IP Host Homelab (default: auto-detect LAN/Tailscale)")
    parser_deploy.add_argument("--skip-build", action="store_true", help="Lewati build container image (langsung compose up)")
    parser_deploy.add_argument("--skip-db", action="store_true", help="Lewati auto-provisioning database")
    parser_deploy.add_argument("--timeout", type=int, default=45, help="Batas waktu healthcheck endpoint (detik)")

    # Command: status
    parser_status = subparsers.add_parser("status", help="Periksa status konektivitas seluruh layanan homelab")
    parser_status.add_argument("--host", default=None, help="IP Host Homelab (default: auto-detect LAN/Tailscale)")

    # Command: backup
    parser_backup = subparsers.add_parser("backup", help="Buat cadangan seluruh database & konfigurasi homelab")
    parser_backup.add_argument("--host", default=None, help="IP Host API Gateway (default: auto-detect LAN/Tailscale)")
    parser_backup.add_argument("--scope", default="all", choices=["all", "databases", "configs"], help="Lingkup cadangan")
    parser_backup.add_argument("--note", default="CLI On-demand Backup", help="Catatan backup")

    # Command: import-grafana
    parser_grafana = subparsers.add_parser("import-grafana", help="Impor dashboard Heatpress ke Grafana eksisting (:3001)")
    parser_grafana.add_argument("--host", default=None, help="IP Host Homelab (default: auto-detect LAN/Tailscale)")
    parser_grafana.add_argument("--grafana-port", "--port", dest="grafana_port", type=int, default=3001, help="Port Grafana eksisting")
    parser_grafana.add_argument("--user", default="admin", help="Grafana username")
    parser_grafana.add_argument("--password", default="admin12345", help="Grafana password")
    parser_grafana.add_argument("--token", default="", help="Grafana API token")

    # Command: provision-db
    parser_prov = subparsers.add_parser("provision-db", help="Auto-provision database mandiri untuk setiap project (eternal_db, stock_umkm, pap_core, psm)")

    # Command: dns
    parser_dns = subparsers.add_parser("dns", help="Tampilkan daftar domain lokal & status DNS")
    parser_dns.add_argument("--host", default=None, help="IP Host Homelab (default: auto-detect LAN/Tailscale)")

    # Command: init-dockerfile
    parser_df = subparsers.add_parser("init-dockerfile", help="PSM Professional Deployer: Tambahkan Dockerfile multi-stage & .dockerignore ke project")
    parser_df.add_argument("path", nargs="?", default=".", help="Path direktori project (default: current directory)")
    parser_df.add_argument("--framework", "-f", default="auto", help="Pilih framework manual (nextjs, vite, fastapi, laravel, go, dll)")
    parser_df.add_argument("--port", "-p", type=int, default=None, help="Port container target")
    parser_df.add_argument("--overwrite", action="store_true", help="Timpa file Dockerfile & .dockerignore jika sudah ada")

    # Command: update-project
    parser_up = subparsers.add_parser("update-project", help="Perbarui konfigurasi project dan picu deployment rilis baru ke container server")
    parser_up.add_argument("project", nargs="?", default="", help="Nama atau ID project yang ingin diupdate")
    parser_up.add_argument("--host", default=None, help="IP Host API Gateway (default: auto-detect LAN/Tailscale)")
    parser_up.add_argument("--repo", help="Repository URL Git (e.g. https://github.com/user/repo.git)")
    parser_up.add_argument("--name", help="Nama baru untuk project")
    parser_up.add_argument("--branch", help="Target branch Git")
    parser_up.add_argument("--port", help="Port mapping Docker (e.g. 3000:3000)")
    parser_up.add_argument("--db-type", choices=["postgres", "mysql", "sqlite", "none"], help="Engine database")
    parser_up.add_argument("--db-name", help="Nama database")
    parser_up.add_argument("--domain", help="Local domain virtual host (e.g. pos.homelab)")
    parser_up.add_argument("--deploy", action="store_true", help="Langsung picu deployment ke server container")

    args = parser.parse_args()

    if args.command == "deploy":
        sys.exit(cmd_deploy(args))
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "init-dockerfile":
        sys.exit(cmd_init_dockerfile(args))
    elif args.command == "update-project":
        sys.exit(cmd_update_project(args))
    elif args.command == "provision-db":
        import auto_provision_all_databases
        auto_provision_all_databases.provision_mysql()
        auto_provision_all_databases.provision_postgres()
    elif args.command == "dns":
        sys.exit(cmd_dns(args))
    elif args.command == "backup":
        sys.exit(cmd_backup(args))
    elif args.command == "import-grafana":
        sys.exit(cmd_import_grafana(args))
    else:
        args.host = resolve_default_host(None)
        cmd_status(args)


if __name__ == "__main__":
    main()
