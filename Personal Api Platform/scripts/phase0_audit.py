"""Phase 0 — Homelab server and connectivity audit script."""

import os
import platform
import shutil
import socket
import sys

from app.core.config import get_settings


def check_tcp(host: str, port: int, timeout: float = 2.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"TCP {host}:{port} reachable"
    except Exception as exc:
        return False, f"TCP {host}:{port} unreachable ({type(exc).__name__})"


def run_audit() -> int:
    settings = get_settings()
    disk = shutil.disk_usage(".")

    print("=== Personal API Platform (PAP) — Phase 0 Audit ===")
    print(f"OS / Platform     : {platform.platform()}")
    print(f"Python Version    : {platform.python_version()}")
    print(f"CPU Cores         : {os.cpu_count() or 1}")
    print(f"Free Disk Space   : {round(disk.free / (1024**3), 2)} GB")
    print(f"Intended Binding  : {settings.HOST_IP}:{settings.PORT}")

    try:
        settings.validate_core_database_target()
        print("[OK] Core database target is not 'psm'")
    except Exception as exc:
        print(f"[FAIL] {exc}")
        return 1

    if settings.STOCK_DB_USER.strip().lower() == "root":
        print("[WARN] STOCK_DB_USER is set to 'root'; create 'pap_stock_reader' before production!")
    else:
        print(f"[OK] MySQL integration user is least-privilege ({settings.STOCK_DB_USER})")

    endpoints = [
        ("PostgreSQL", settings.PSM_DATABASE_HOST, settings.PSM_DATABASE_PORT),
        ("MySQL", settings.STOCK_DB_HOST, settings.STOCK_DB_PORT),
        ("Mosquitto MQTT", settings.MQTT_HOST, settings.MQTT_PORT),
    ]
    for label, host, port in endpoints:
        ok, msg = check_tcp(host, port)
        status_str = "OK" if ok else "INFO"
        print(f"[{status_str}] {label}: {msg}")

    return 0


if __name__ == "__main__":
    sys.exit(run_audit())

