"""Service for server resource telemetry and controlled Prometheus HTTP API queries."""

import os
import platform
import shutil
import socket
from typing import Any, Optional

from app.integrations.prometheus import PrometheusAdapter


class MetricsService:
    def __init__(self) -> None:
        self.prometheus = PrometheusAdapter()

    def get_server_metrics(self) -> dict[str, Any]:
        disk = shutil.disk_usage(".")
        return {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "cpu_count": os.cpu_count() or 1,
            "disk_total_gb": round(disk.total / (1024**3), 2),
            "disk_used_gb": round(disk.used / (1024**3), 2),
            "disk_free_gb": round(disk.free / (1024**3), 2),
            "container_limits": {
                "mem_limit": "256m",
                "cpus": 0.5,
            },
        }

    def query_instant(self, query: str, time_param: Optional[str] = None) -> dict[str, Any]:
        return self.prometheus.instant_query(query=query, time_param=time_param)

    def query_range(
        self, query: str, start: str, end: str, step: str = "60s"
    ) -> dict[str, Any]:
        return self.prometheus.range_query(query=query, start=start, end=end, step=step)

    def get_targets(self) -> dict[str, Any]:
        return self.prometheus.get_targets()

