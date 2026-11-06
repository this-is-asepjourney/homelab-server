"""Pydantic schemas for server metrics and Prometheus query responses."""

from typing import Any, Optional

from pydantic import BaseModel


class ServerMetricsRead(BaseModel):
    hostname: str
    platform: str
    cpu_count: int
    disk_total_gb: float
    disk_free_gb: float
    container_limits: dict[str, Any]


class PrometheusQueryResponse(BaseModel):
    resultType: str
    result: list[Any]
    query: Optional[str] = None

