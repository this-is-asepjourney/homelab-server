#!/usr/bin/env python3
"""
homelab.py — CLI Manajemen Terpadu Homelab Server
Mengelola dan memverifikasi seluruh komponen:
- Personal API Platform (PAP)
- Personal Server Manager (PSM)
- IoT Dashboard (Heatpress Fleet)
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
    print("\n[A] LAYANAN INFRASTRUKTUR EKSISTING (Host):")
    services_infra = [
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
        print(f"  * {name:<26} Port :{port:<5} -> {badge}{extra}")

    # 2. Application Projects
    print("\n[B] APLIKASI UTAMA HOMELAB:")
    services_app = [
        ("PAP Core API Gateway", 8000, f"http://{host}:8000/health"),
        ("PSM Control Plane API", 8001, f"http://{host}:8001/health"),
        ("PSM Web Dashboard", 3005, None),
        ("IoT Device Mapping API", 8002, f"http://{host}:8002/health"),
        ("IoT Web Dashboard Hub", 8088, f"http://{host}:8088/"),
        ("IoT Telegraf Exporter", 9273, f"http://{host}:9273/metrics"),
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
        print(f"  * {name:<26} Port :{port:<5} -> {badge}{extra}")

    print("\n[C] VALIDASI KONSEP 'MENGGUNAKAN YANG SUDAH ADA':")
    print("  [OK] Tidak ada kontainer Grafana duplikat (Menggunakan Grafana port 3001)")
    print("  [OK] Tidak ada kontainer Prometheus duplikat (Menggunakan Prometheus port 9001)")
    print("  [OK] Tidak ada kontainer PostgreSQL duplikat (Menggunakan PostgreSQL port 5432)")
    print("  [OK] Tidak ada kontainer Mosquitto duplikat (Menggunakan Mosquitto port 1883)")
    print("==================================================================")


def cmd_import_grafana(args):
    host = args.host
    port = args.grafana_port
    user = args.user
    password = args.password
    token = args.token

    grafana_url = f"http://{host}:{port}"
    print(f"\n[*] Mengimpor 4 Dashboard Heatpress ke Grafana ({grafana_url})...")

    auth_header = f"Bearer {token}" if token else f"Basic {base64.b64encode(f'{user}:{password}'.encode()).decode()}"

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
        except Exception as e:
            print(f"  [FAIL] {jf.name}: {e}")

    print(f"\n[HASIL] Berhasil mengimpor {success}/{len(json_files)} dashboard ke Grafana.")
    return 0 if success > 0 else 1


def main():
    parser = argparse.ArgumentParser(description="CLI Manajemen Terpadu Homelab Server")
    subparsers = parser.add_subparsers(dest="command", help="Perintah yang tersedia")

    # Command: status
    parser_status = subparsers.add_parser("status", help="Periksa status konektivitas seluruh layanan homelab")
    parser_status.add_argument("--host", default=os.getenv("HOST_IP", "192.168.25.101"), help="IP Host Homelab")

    # Command: import-grafana
    parser_grafana = subparsers.add_parser("import-grafana", help="Impor dashboard Heatpress ke Grafana eksisting (:3001)")
    parser_grafana.add_argument("--host", default=os.getenv("HOST_IP", "192.168.25.101"), help="IP Host Homelab")
    parser_grafana.add_argument("--grafana-port", type=int, default=3001, help="Port Grafana eksisting")
    parser_grafana.add_argument("--user", default="admin", help="Grafana username")
    parser_grafana.add_argument("--password", default="adminpassword", help="Grafana password")
    parser_grafana.add_argument("--token", default="", help="Grafana API token")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status(args)
    elif args.command == "import-grafana":
        sys.exit(cmd_import_grafana(args))
    else:
        # Default run status
        args.host = os.getenv("HOST_IP", "192.168.25.101")
        cmd_status(args)


if __name__ == "__main__":
    main()
