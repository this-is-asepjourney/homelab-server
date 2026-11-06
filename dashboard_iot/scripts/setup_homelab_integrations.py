#!/usr/bin/env python3
"""
setup_homelab_integrations.py
Skrip terpadu untuk menyelaraskan dashboard_iot dengan aplikasi yang sudah terinstall di Homelab:
1. Memverifikasi konektivitas ke Mosquitto (:1883), Prometheus (:9001), dan Grafana (:3001).
2. Memeriksa apakah Prometheus eksisting sudah men-scrape Telegraf (:9273).
3. Mengimpor ke-4 dashboard Heatpress ke Grafana eksisting (:3001) via API.
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


def check_port(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def http_json_request(url: str, method: str = "GET", data: dict = None, auth_header: str = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
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


def main():
    parser = argparse.ArgumentParser(description="Penyelarasan IoT Dashboard dengan Layanan Eksisting Homelab")
    parser.add_argument("--host", default="192.168.25.101", help="IP Server Homelab (default: 192.168.25.101)")
    parser.add_argument("--grafana-port", type=int, default=3001, help="Port Grafana eksisting (default: 3001)")
    parser.add_argument("--prometheus-port", type=int, default=9001, help="Port Prometheus eksisting (default: 9001)")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="Port Mosquitto eksisting (default: 1883)")
    parser.add_argument("--telegraf-port", type=int, default=9273, help="Port Telegraf exporter (default: 9273)")
    parser.add_argument("--user", default=os.getenv("GF_SECURITY_ADMIN_USER", "admin"), help="Grafana user")
    parser.add_argument("--password", default=os.getenv("GF_SECURITY_ADMIN_PASSWORD", "adminpassword"), help="Grafana pass")
    parser.add_argument("--token", default=os.getenv("GRAFANA_API_KEY", ""), help="Grafana API token")

    args = parser.parse_args()

    print("==================================================================")
    print("   Penyelarasan Layanan Homelab Eksisting (Tanpa Duplikasi)       ")
    print("==================================================================")

    # 1. Audit Layanan
    print("\n[1/3] Memeriksa Layanan Eksisting di Homelab:")
    mqtt_ok = check_port(args.host, args.mqtt_port)
    prom_ok = check_port(args.host, args.prometheus_port)
    graf_ok = check_port(args.host, args.grafana_port)
    teleg_ok = check_port(args.host, args.telegraf_port)

    print(f"  - Mosquitto MQTT  ({args.host}:{args.mqtt_port})   : {'[ONLINE]' if mqtt_ok else '[OFFLINE]'}")
    print(f"  - Prometheus Snap ({args.host}:{args.prometheus_port})   : {'[ONLINE]' if prom_ok else '[OFFLINE]'}")
    print(f"  - Grafana Utama   ({args.host}:{args.grafana_port})   : {'[ONLINE]' if graf_ok else '[OFFLINE]'}")
    print(f"  - Telegraf Exporter ({args.host}:{args.telegraf_port}) : {'[ONLINE]' if teleg_ok else '[BELUM JALAN (Jalankan docker compose)]'}")

    # 2. Prometheus Target Check
    print(f"\n[2/3] Memeriksa Konfigurasi Scrape di Prometheus ({args.host}:{args.prometheus_port}):")
    prom_url = f"http://{args.host}:{args.prometheus_port}"
    status, res = http_json_request(f"{prom_url}/api/v1/targets")
    has_telegraf = False
    if status == 200:
        targets = res.get("data", {}).get("activeTargets", [])
        for t in targets:
            job = t.get("labels", {}).get("job", "")
            s_url = t.get("scrapeUrl", "")
            if "telegraf" in job.lower() or "9273" in s_url:
                has_telegraf = True
                print(f"  [OK] Job Telegraf terdeteksi di Prometheus: {job} ({s_url}) - Status: {t.get('health')}")
                break

    if not has_telegraf:
        print("  [INFO] Job 'iot_telegraf' belum terdaftar di Prometheus.")
        print("  Agar Prometheus eksisting dapat mengumpulkan metrik dari Telegraf, tambahkan konfigurasi berikut")
        print("  ke file /var/snap/prometheus/current/prometheus.yml (atau /etc/prometheus/prometheus.yml):")
        print("\n" + "-" * 60)
        print("scrape_configs:")
        print("  - job_name: 'iot_telegraf'")
        print("    scrape_interval: 5s")
        print("    static_configs:")
        print(f"      - targets: ['127.0.0.1:{args.telegraf_port}']")
        print("-" * 60)
        print("  Setelah disimpan, reload Prometheus dengan:")
        print("    sudo snap restart prometheus  # atau curl -X POST http://localhost:9001/-/reload\n")

    # 3. Grafana Dashboards Import
    print(f"\n[3/3] Impor Dashboard ke Grafana Eksisting ({args.host}:{args.grafana_port}):")
    grafana_url = f"http://{args.host}:{args.grafana_port}"
    auth_header = f"Bearer {args.token}" if args.token else f"Basic {base64.b64encode(f'{args.user}:{args.password}'.encode()).decode()}"

    status, health = http_json_request(f"{grafana_url}/api/health", auth_header=auth_header)
    if status == 200:
        print(f"  [OK] Grafana aktif! Versi: {health.get('version', 'unknown')}")
        dashboards_dir = Path(__file__).parent.parent / "grafana" / "dashboards"
        json_files = list(dashboards_dir.glob("*.json"))

        for jf in json_files:
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    content = json.load(f)
                content["id"] = None
                p_status, p_res = http_json_request(
                    f"{grafana_url}/api/dashboards/db",
                    method="POST",
                    data={"dashboard": content, "overwrite": True, "folderId": 0},
                    auth_header=auth_header,
                )
                if p_status == 200:
                    print(f"  [OK] Dashboard '{content.get('title')}' berhasil diimpor.")
                else:
                    print(f"  [FAIL] Gagal impor {jf.name}: {p_res}")
            except Exception as e:
                print(f"  [ERROR] {jf.name}: {e}")
    else:
        print(f"  [INFO] Grafana di {grafana_url} tidak dapat diakses langsung dari jaringan ini ({status}: {health.get('error', health)}).")
        print(f"  Pastikan Anda berada di jaringan LAN {args.host} atau jalankan impor dari server homelab.")

    print("\n[SELESAI] Stack IoT siap dijalankan dengan:")
    print("  cd dashboard_iot")
    print("  docker compose up -d")
    print("  (Hanya akan menjalankan iot_telegraf, iot_device_mapping_api, dan iot_dashboard_web tanpa membuat container ganda)")


if __name__ == "__main__":
    main()
