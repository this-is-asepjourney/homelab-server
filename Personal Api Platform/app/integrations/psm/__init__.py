"""Controlled adapter for Personal Server Manager (PSM) Control Plane integration."""

from typing import Any

import httpx

from app.core.config import get_settings


class PsmAdapter:
    """Adapter for checking health and synchronizing metadata with Personal Server Manager."""

    DEFAULT_SERVERS_SNAPSHOT: list[dict[str, Any]] = [
        {
            "id": "homelab-primary",
            "name": "Homelab-Primary",
            "hostname": "ubuntu-homelab.local",
            "os_name": "Ubuntu Server 24.04 LTS",
            "architecture": "x86_64",
            "status": "online",
            "cpu_usage": 24.5,
            "memory_usage": 58.2,
            "disk_usage": 42.0,
        }
    ]

    DEFAULT_CONTAINERS_SNAPSHOT: list[dict[str, Any]] = [
        {"name": "pap-api", "image": "personal-api-platform:1.0.0", "status": "running", "port": 8000},
        {"name": "psm-web", "image": "psm-web:latest", "status": "running", "port": 3005},
        {"name": "psm-api", "image": "psm-api:latest", "status": "running", "port": 8001},
        {"name": "iot-dashboard-web", "image": "nginx:alpine", "status": "running", "port": 8088},
        {"name": "nextcloud-app", "image": "nextcloud:latest", "status": "running", "port": 80},
        {"name": "prometheus", "image": "prom/prometheus:v2.50.0", "status": "running", "port": 9001},
        {"name": "grafana", "image": "grafana/grafana:10.4.0", "status": "running", "port": 3001},
        {"name": "uptime-kuma", "image": "louislam/uptime-kuma:1", "status": "running", "port": 3002},
    ]

    def __init__(self, base_url: str | None = None, timeout: float = 0.5) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.PSM_API_URL).rstrip("/")
        self.timeout = timeout

    def check_health(self) -> dict[str, Any]:
        candidates = [
            self.base_url,
            "http://127.0.0.1:8001",
            "http://localhost:8001",
            "http://host.docker.internal:8001",
        ]
        seen = set()
        for url in candidates:
            clean = url.rstrip("/")
            if clean in seen:
                continue
            seen.add(clean)
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.get(f"{clean}/health")
                    if resp.status_code == 200:
                        body = resp.json() if resp.content else {}
                        return {
                            "service": "personal_server_manager",
                            "reachable": True,
                            "url": clean,
                            "status": body.get("status", "healthy"),
                            "version": body.get("version", "0.1.0"),
                        }
            except Exception:
                continue
        return {
            "service": "personal_server_manager",
            "reachable": False,
            "url": self.base_url,
            "status": "standby_registered_in_pap",
        }
