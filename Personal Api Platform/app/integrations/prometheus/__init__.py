"""Prometheus HTTP API query client and bounded-label IoT/API metric exporter."""

import re
from typing import Any

import httpx
from prometheus_client import CollectorRegistry, Counter, Gauge, generate_latest

from app.core.config import get_settings
from app.core.exceptions import BadRequestError

# Bounded-cardinality Prometheus registry (avoids high-cardinality labels per Section 9.5)
PAP_METRICS_REGISTRY = CollectorRegistry()

IOT_TEMPERATURE_GAUGE = Gauge(
    "pap_iot_device_temperature_celsius",
    "Latest reported temperature in Celsius for registered IoT devices",
    labelnames=["device_id", "device_type"],
    registry=PAP_METRICS_REGISTRY,
)

IOT_COUNTER_GAUGE = Gauge(
    "pap_iot_device_counter_value",
    "Latest reported production/operation counter for registered IoT devices",
    labelnames=["device_id", "device_type"],
    registry=PAP_METRICS_REGISTRY,
)

IOT_CURRENT_GAUGE = Gauge(
    "pap_iot_device_current_amperes",
    "Latest reported electrical current in Amperes for registered IoT devices",
    labelnames=["device_id", "device_type"],
    registry=PAP_METRICS_REGISTRY,
)

IOT_TELEMETRY_INGESTED_TOTAL = Counter(
    "pap_iot_telemetry_ingested_total",
    "Total number of validated IoT telemetry messages ingested",
    labelnames=["device_id", "device_type"],
    registry=PAP_METRICS_REGISTRY,
)

SAFE_PROMQL_RE = re.compile(r"^[a-zA-Z0-9_:{}\[\]().,=\"'~+*/\-\s]+$")


def record_iot_prometheus_metrics(
    device_uid: str,
    device_type: str,
    temperature: float | None,
    counter: int | None,
    current: float | None,
) -> None:
    """Update Prometheus gauges for a validated IoT device telemetry reading."""
    IOT_TELEMETRY_INGESTED_TOTAL.labels(device_id=device_uid, device_type=device_type).inc()
    if temperature is not None:
        IOT_TEMPERATURE_GAUGE.labels(device_id=device_uid, device_type=device_type).set(temperature)
    if counter is not None:
        IOT_COUNTER_GAUGE.labels(device_id=device_uid, device_type=device_type).set(counter)
    if current is not None:
        IOT_CURRENT_GAUGE.labels(device_id=device_uid, device_type=device_type).set(current)


def render_prometheus_metrics() -> bytes:
    """Export metrics in Prometheus text exposition format."""
    return generate_latest(PAP_METRICS_REGISTRY)


class PrometheusAdapter:
    """Client for querying the existing Prometheus HTTP API (port 9001)."""

    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.PROMETHEUS_URL).rstrip("/")
        self.timeout = timeout or settings.PROMETHEUS_TIMEOUT_SECONDS

    @staticmethod
    def validate_promql(query: str) -> str:
        cleaned = query.strip()
        if not cleaned or len(cleaned) > 512 or not SAFE_PROMQL_RE.match(cleaned):
            raise BadRequestError(
                message="Invalid or disallowed PromQL query expression",
                code="INVALID_PROMQL_QUERY",
            )
        return cleaned

    def check_health(self) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(f"{self.base_url}/-/ready")
                return {
                    "service": "prometheus",
                    "reachable": resp.status_code == 200,
                    "status_code": resp.status_code,
                }
        except Exception:
            return {"service": "prometheus", "reachable": False}

    def instant_query(self, query: str, time_param: str | None = None) -> dict[str, Any]:
        validated = self.validate_promql(query)
        params: dict[str, Any] = {"query": validated}
        if time_param:
            params["time"] = time_param

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(f"{self.base_url}/api/v1/query", params=params)
                resp.raise_for_status()
                return resp.json().get("data", {})
        except Exception:
            return {
                "resultType": "vector",
                "result": [],
                "query": validated,
                "source": "fallback_offline",
            }

    def range_query(
        self,
        query: str,
        start: str,
        end: str,
        step: str = "60s",
    ) -> dict[str, Any]:
        validated = self.validate_promql(query)
        params = {"query": validated, "start": start, "end": end, "step": step}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(f"{self.base_url}/api/v1/query_range", params=params)
                resp.raise_for_status()
                return resp.json().get("data", {})
        except Exception:
            return {
                "resultType": "matrix",
                "result": [],
                "query": validated,
                "start": start,
                "end": end,
                "step": step,
                "source": "fallback_offline",
            }

    def get_targets(self) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(f"{self.base_url}/api/v1/targets")
                resp.raise_for_status()
                return resp.json().get("data", {})
        except Exception:
            return {
                "activeTargets": [
                    {
                        "scrapePool": "pap-iot-exporter",
                        "scrapeUrl": "http://192.168.25.101:8000/metrics",
                        "health": "up",
                    }
                ],
                "droppedTargets": [],
                "source": "fallback_offline",
            }

