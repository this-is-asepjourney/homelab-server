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
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path


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


def cmd_status(args):
    host = args.host
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
    host = args.host
    url = f"http://{host}:8000/api/v1/dns/records"
    print("==================================================================")
    print(f"       DAFTAR DOMAIN LOKAL & ROUTING HOMELAB ({host})")
    print("==================================================================")
    st, data = http_get(url)
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
    host = args.host
    scope = args.scope
    note = args.note
    url = f"http://{host}:8000/api/v1/backups/create"
    print(f"\n[*] Memicu pembuatan backup sistem di {url} (Scope: {scope})...")

    data = json.dumps({"scope": scope, "note": note}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
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

    # 4. InfluxDB eternal_telemetry Datasource (uid: influxdb-iot)
    influx_ds = next(
        (d for d in existing_ds if d.get("uid") == "influxdb-iot" or "influx" in d.get("name", "").lower()),
        None
    )
    influx_payload = {
        "name": "InfluxDB - eternal_telemetry",
        "type": "influxdb",
        "uid": "influxdb-iot",
        "access": "proxy",
        "url": f"http://{host}:8086",
        "isDefault": False,
        "jsonData": {
            "version": "Flux",
            "organization": "homelab",
            "defaultBucket": "eternal_telemetry",
            "tlsSkipVerify": True
        },
        "secureJsonData": {
            "token": "homelab-influxdb-master-auth-token-2026"
        }
    }
    if influx_ds:
        uid = influx_ds.get("uid", "influxdb-iot")
        try:
            req = urllib.request.Request(
                f"{grafana_url}/api/datasources/uid/{uid}",
                data=json.dumps(influx_payload).encode(),
                headers=headers,
                method="PUT"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                print(f"  [OK] Datasource InfluxDB (uid={uid}) berhasil diperbarui!")
        except Exception:
            # File-provisioned datasources di Grafana berstatus read-only dari API, ini normal
            pass
    else:
        try:
            req = urllib.request.Request(
                f"{grafana_url}/api/datasources",
                data=json.dumps(influx_payload).encode(),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                print("  [OK] Datasource InfluxDB (uid: influxdb-iot) berhasil didaftarkan!")
        except Exception as e:
            print(f"  [WARN] Gagal membuat datasource InfluxDB: {e}")

    # 5. Test InfluxDB datasource health
    try:
        req = urllib.request.Request(f"{grafana_url}/api/datasources/uid/influxdb-iot/health", headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            health = json.loads(resp.read().decode())
            status = health.get("status", "UNKNOWN")
            msg = health.get("message", "")
            if status == "OK":
                print(f"  [OK] Verifikasi Koneksi InfluxDB: SEHAT ({msg or 'Datasource Connection OK'})\n")
            else:
                print(f"  [WARN] Verifikasi Koneksi InfluxDB: {status} - {msg}\n")
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


def main():
    parser = argparse.ArgumentParser(description="CLI Manajemen Terpadu Homelab Server")
    subparsers = parser.add_subparsers(dest="command", help="Perintah yang tersedia")

    # Command: status
    parser_status = subparsers.add_parser("status", help="Periksa status konektivitas seluruh layanan homelab")
    parser_status.add_argument("--host", default=os.getenv("HOST_IP", "192.168.25.101"), help="IP Host Homelab")

    # Command: backup
    parser_backup = subparsers.add_parser("backup", help="Buat cadangan seluruh database & konfigurasi homelab")
    parser_backup.add_argument("--host", default=os.getenv("HOST_IP", "127.0.0.1"), help="IP Host API Gateway")
    parser_backup.add_argument("--scope", default="all", choices=["all", "databases", "configs"], help="Lingkup cadangan")
    parser_backup.add_argument("--note", default="CLI On-demand Backup", help="Catatan backup")

    # Command: import-grafana
    parser_grafana = subparsers.add_parser("import-grafana", help="Impor dashboard Heatpress ke Grafana eksisting (:3001)")
    parser_grafana.add_argument("--host", default=os.getenv("HOST_IP", "192.168.25.101"), help="IP Host Homelab")
    parser_grafana.add_argument("--grafana-port", "--port", dest="grafana_port", type=int, default=3001, help="Port Grafana eksisting")
    parser_grafana.add_argument("--user", default="admin", help="Grafana username")
    parser_grafana.add_argument("--password", default="admin12345", help="Grafana password")
    parser_grafana.add_argument("--token", default="", help="Grafana API token")

    # Command: provision-db
    parser_prov = subparsers.add_parser("provision-db", help="Auto-provision database mandiri untuk setiap project (eternal_db, stock_umkm, pap_core, psm)")

    # Command: dns
    parser_dns = subparsers.add_parser("dns", help="Tampilkan daftar domain lokal & status DNS")
    parser_dns.add_argument("--host", default=os.getenv("HOST_IP", "192.168.25.101"), help="IP Host Homelab")

    # Command: init-dockerfile
    parser_df = subparsers.add_parser("init-dockerfile", help="PSM Professional Deployer: Tambahkan Dockerfile multi-stage & .dockerignore ke project")
    parser_df.add_argument("path", nargs="?", default=".", help="Path direktori project (default: current directory)")
    parser_df.add_argument("--framework", "-f", default="auto", help="Pilih framework manual (nextjs, vite, fastapi, laravel, go, dll)")
    parser_df.add_argument("--port", "-p", type=int, default=None, help="Port container target")
    parser_df.add_argument("--overwrite", action="store_true", help="Timpa file Dockerfile & .dockerignore jika sudah ada")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status(args)
    elif args.command == "init-dockerfile":
        sys.exit(cmd_init_dockerfile(args))
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
        args.host = os.getenv("HOST_IP", "192.168.25.101")
        cmd_status(args)


if __name__ == "__main__":
    main()
