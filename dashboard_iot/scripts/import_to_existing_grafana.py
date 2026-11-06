#!/usr/bin/env python3
"""
import_to_existing_grafana.py
Mengimpor dashboard IoT Heatpress ke instance Grafana yang sudah ada di server homelab.

Fitur:
1. Memeriksa koneksi ke instance Grafana eksisting (misal: http://100.106.63.90:3001 atau http://localhost:3001).
2. Memastikan datasource Prometheus terdaftar di Grafana eksisting.
3. Mengimpor ke-4 dashboard Heatpress (Universal, HPM 55, AF-450, APM-LOGO) via Grafana REST API.
4. Menampilkan link langsung untuk mengakses tiap dashboard.
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def make_request(url: str, method: str = "GET", data: dict = None, auth_header: str = None) -> tuple[int, dict]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if auth_header:
        headers["Authorization"] = auth_header

    req_data = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            res_body = response.read().decode("utf-8")
            return response.status, json.loads(res_body) if res_body else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err_body)
        except Exception:
            return e.code, {"error": err_body}
    except Exception as e:
        return 0, {"error": str(e)}


def ensure_datasource(grafana_url: str, auth_header: str, prometheus_url: str) -> bool:
    print(f"\n[1/3] Memeriksa Datasource Prometheus di Grafana ({prometheus_url})...")
    status, res = make_request(f"{grafana_url}/api/datasources", auth_header=auth_header)
    if status != 200:
        print(f"  [WARN] Gagal mengambil daftar datasources (Status {status}): {res}")
        return False

    ds_list = res if isinstance(res, list) else []
    for ds in ds_list:
        if ds.get("type") == "prometheus" or ds.get("name") == "Prometheus":
            print(f"  [OK] Datasource Prometheus sudah ada (UID: {ds.get('uid')}, Name: {ds.get('name')}).")
            return True

    print("  [+] Membuat datasource Prometheus default...")
    payload = {
        "name": "Prometheus",
        "type": "prometheus",
        "access": "proxy",
        "url": prometheus_url,
        "isDefault": True,
        "jsonData": {
            "httpMethod": "POST",
            "timeInterval": "5s",
        },
    }
    status, res = make_request(f"{grafana_url}/api/datasources", method="POST", data=payload, auth_header=auth_header)
    if status in (200, 201):
        print(f"  [OK] Datasource Prometheus berhasil ditambahkan (UID: {res.get('datasource', {}).get('uid', 'prometheus')}).")
        return True
    else:
        print(f"  [WARN] Gagal membuat datasource Prometheus: {res}")
        return False


def import_dashboards(grafana_url: str, auth_header: str, dashboards_dir: Path, folder_id: int = 0) -> int:
    print(f"\n[2/3] Mengimpor dashboard dari '{dashboards_dir}'...")
    if not dashboards_dir.exists():
        print(f"  [ERROR] Folder '{dashboards_dir}' tidak ditemukan!")
        return 1

    json_files = list(dashboards_dir.glob("*.json"))
    if not json_files:
        print(f"  [ERROR] Tidak ada file .json di '{dashboards_dir}'!")
        return 1

    success_count = 0
    imported_links = []

    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                dash_content = json.load(f)

            # Ensure id is None so Grafana creates/updates by UID
            dash_content["id"] = None

            payload = {
                "dashboard": dash_content,
                "overwrite": True,
                "folderId": folder_id,
            }

            status, res = make_request(f"{grafana_url}/api/dashboards/db", method="POST", data=payload, auth_header=auth_header)
            if status == 200 and res.get("status") == "success":
                slug_or_url = res.get("url", f"/d/{dash_content.get('uid')}")
                full_view_url = f"{grafana_url.rstrip('/')}{slug_or_url}"
                print(f"  [OK] Berhasil impor: {jf.name}")
                print(f"       -> Title: {dash_content.get('title')}")
                print(f"       -> URL  : {full_view_url}")
                imported_links.append((dash_content.get("title"), full_view_url))
                success_count += 1
            else:
                print(f"  [FAIL] Gagal impor {jf.name} (Status {status}): {res.get('message', res)}")
        except Exception as exc:
            print(f"  [ERROR] Kesalahan membaca file {jf.name}: {exc}")

    print(f"\n[3/3] Ringkasan Impor:")
    print(f"  Total Berhasil: {success_count}/{len(json_files)} dashboard.")
    if imported_links:
        print("\n  Dashboard Links di Grafana Eksisting:")
        for title, link in imported_links:
            print(f"  - {title}: {link}")

    return 0 if success_count > 0 else 1


def main():
    parser = argparse.ArgumentParser(description="Impor Dashboard Heatpress ke Instance Grafana Eksisting di Homelab (Sesuai port.md: 192.168.25.101:3001)")
    parser.add_argument("--grafana-url", default=os.getenv("EXISTING_GRAFANA_URL", os.getenv("GRAFANA_URL", "http://192.168.25.101:3001")), help="URL Grafana eksisting (default: http://192.168.25.101:3001)")
    parser.add_argument("--user", default=os.getenv("GF_SECURITY_ADMIN_USER", "admin"), help="Grafana admin username (default: admin)")
    parser.add_argument("--password", default=os.getenv("GF_SECURITY_ADMIN_PASSWORD", "adminpassword"), help="Grafana admin password (default: adminpassword)")
    parser.add_argument("--token", default=os.getenv("GRAFANA_API_KEY", ""), help="Grafana Service Account / API Token (opsional, menggantikan user:password)")
    parser.add_argument("--prometheus-url", default=os.getenv("PROMETHEUS_URL", "http://192.168.25.101:9001"), help="URL Prometheus data source (default: http://192.168.25.101:9001)")
    parser.add_argument("--dashboards-dir", default=str(Path(__file__).parent.parent / "grafana" / "dashboards"), help="Direktori file JSON dashboards")

    args = parser.parse_args()
    grafana_url = args.grafana_url.rstrip("/")

    if args.token:
        auth_header = f"Bearer {args.token}"
    else:
        user_pass = f"{args.user}:{args.password}"
        encoded = base64.b64encode(user_pass.encode("utf-8")).decode("utf-8")
        auth_header = f"Basic {encoded}"

    print("================================================================")
    print("   Heatpress Fleet Dashboard -> Existing Grafana Importer       ")
    print("================================================================")
    print(f"Target Grafana     : {grafana_url}")
    print(f"Prometheus URL     : {args.prometheus_url}")
    print(f"Dashboards Dir     : {args.dashboards_dir}")

    # Check Grafana health
    print("\n[*] Menghubungi Grafana...")
    status, health = make_request(f"{grafana_url}/api/health", auth_header=auth_header)
    if status == 200:
        print(f"  [OK] Grafana terdeteksi aktif! Database: {health.get('database')}, Versi: {health.get('version', 'unknown')}")
    else:
        print(f"  [WARN] Tidak dapat menghubungi endpoint /api/health (Status {status}): {health}")
        print("  Silakan periksa apakah Grafana menyala dan dapat diakses dari jaringan ini.")

    ensure_datasource(grafana_url, auth_header, args.prometheus_url)
    exit_code = import_dashboards(grafana_url, auth_header, Path(args.dashboards_dir))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

