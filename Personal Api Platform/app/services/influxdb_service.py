"""
influxdb_service.py — InfluxDB v2 Service for IoT Telemetry & Metrics
Connects to InfluxDB v2 (:8086) using native Line Protocol over HTTP.
Provides zero-dependency writing and querying of time-series telemetry data.
"""

from datetime import datetime, timezone
import os
import re
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request
import json

from app.core.config import get_settings
from app.core.logging import logger


class InfluxDbService:
    """Manages InfluxDB v2 interactions for IoT Telemetry and Time-Series Data."""

    def __init__(self):
        settings = get_settings()
        self.url = (
            os.getenv("INFLUXDB_URL")
            or getattr(settings, "INFLUXDB_URL", "http://influxdb:8086")
        ).rstrip("/")
        self.token = (
            os.getenv("INFLUXDB_TOKEN")
            or getattr(settings, "INFLUXDB_TOKEN", "homelab-influxdb-master-auth-token-2026")
        )
        self.org = (
            os.getenv("INFLUXDB_ORG")
            or getattr(settings, "INFLUXDB_ORG", "homelab")
        )
        self.bucket = (
            os.getenv("INFLUXDB_BUCKET")
            or getattr(settings, "INFLUXDB_BUCKET", "eternal_telemetry")
        )

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Token {self.token}",
            "Content-Type": "text/plain; charset=utf-8",
            "Accept": "application/json",
        }

    def check_health(self) -> Dict[str, Any]:
        """Check if InfluxDB server is reachable and healthy."""
        test_urls = [
            f"{self.url}/health",
            f"http://127.0.0.1:8086/health",
            f"http://192.168.25.101:8086/health",
        ]
        for u in test_urls:
            try:
                req = urllib.request.Request(u, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    data = json.loads(resp.read().decode())
                    return {
                        "status": "healthy" if resp.status == 200 else "degraded",
                        "url": u,
                        "data": data,
                        "org": self.org,
                        "bucket": self.bucket,
                    }
            except Exception:
                continue

        return {
            "status": "offline",
            "url": self.url,
            "org": self.org,
            "bucket": self.bucket,
            "error": "Could not connect to InfluxDB at port 8086",
        }

    def write_line_protocol(self, lines: List[str] | str) -> bool:
        """Write raw Influx Line Protocol string(s) directly to InfluxDB bucket."""
        if isinstance(lines, list):
            payload = "\n".join(lines).encode("utf-8")
        else:
            payload = lines.encode("utf-8")

        params = urllib.parse.urlencode({
            "org": self.org,
            "bucket": self.bucket,
            "precision": "s"
        })
        target_urls = [
            f"{self.url}/api/v2/write?{params}",
            f"http://127.0.0.1:8086/api/v2/write?{params}",
            f"http://192.168.25.101:8086/api/v2/write?{params}",
        ]

        last_err = None
        for write_url in target_urls:
            try:
                req = urllib.request.Request(
                    write_url,
                    data=payload,
                    headers=self._get_headers(),
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    if resp.status in (200, 204):
                        return True
            except Exception as e:
                last_err = e
                continue

        logger.warning(f"[InfluxDB] Failed to write line protocol: {last_err}")
        return False

    def write_telemetry(
        self,
        device_serial: str = "ETL-ESP32-001",
        device_name: str = "Eternal",
        model: str = "Eternal-ESP32",
        temperature: float = 0.0,
        humidity: float = 0.0,
        heat_index: float = 0.0,
        rssi: int = -55,
        is_locked: int = 1,
        remaining_sec: int = 0,
        uptime_sec: int = 0,
        free_heap: int = 0,
        extra_tags: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        Record a structured IoT Telemetry metric point into InfluxDB.
        Measurement: `iot_telemetry`
        """
        tags = {
            "device": self._sanitize_tag(device_name),
            "serial": self._sanitize_tag(device_serial),
            "model": self._sanitize_tag(model),
            "lock_status": "LOCKED" if is_locked else "UNLOCKED",
        }
        if extra_tags:
            for k, v in extra_tags.items():
                if v:
                    tags[self._sanitize_tag(k)] = self._sanitize_tag(str(v))

        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))

        fields = [
            f"temperature={float(temperature):.2f}",
            f"humidity={float(humidity):.2f}",
            f"heat_index={float(heat_index):.2f}",
            f"rssi={int(rssi)}i",
            f"is_locked={int(is_locked)}i",
            f"remaining_sec={int(remaining_sec)}i",
            f"uptime_sec={int(uptime_sec)}i",
            f"free_heap={int(free_heap)}i",
        ]
        field_str = ",".join(fields)
        now_sec = int(datetime.now(timezone.utc).timestamp())

        line = f"iot_telemetry,{tag_str} {field_str} {now_sec}"
        return self.write_line_protocol(line)

    def write_nfc_event(
        self,
        uid: str,
        user_name: str = "-",
        username: str = "-",
        role: str = "Operator",
        action: str = "TAP_ON",
        device_serial: str = "ETL-ESP32-001",
        duration_sec: int = 7200,
        status: str = "granted",
    ) -> bool:
        """
        Record an NFC card tap event into InfluxDB.
        Measurement: `nfc_events`
        """
        tags = {
            "uid": self._sanitize_tag(uid),
            "serial": self._sanitize_tag(device_serial),
            "role": self._sanitize_tag(role),
            "action": self._sanitize_tag(action),
            "status": self._sanitize_tag(status),
        }
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        
        escaped_name = user_name.replace('"', '\\"')
        escaped_user = username.replace('"', '\\"')
        fields = [
            f'user_name="{escaped_name}"',
            f'username="{escaped_user}"',
            f"duration_sec={int(duration_sec)}i",
            f"tap_count=1i",
        ]
        field_str = ",".join(fields)
        now_sec = int(datetime.now(timezone.utc).timestamp())

        line = f"nfc_events,{tag_str} {field_str} {now_sec}"
        return self.write_line_protocol(line)

    def query_flux(self, flux: str) -> List[Dict[str, Any]]:
        """Execute a Flux query and return parsed results."""
        params = urllib.parse.urlencode({"org": self.org})
        url = f"{self.url}/api/v2/query?{params}"
        headers = {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/vnd.flux",
            "Accept": "application/csv",
        }

        try:
            req = urllib.request.Request(url, data=flux.encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                csv_data = resp.read().decode("utf-8")
                return self._parse_flux_csv(csv_data)
        except Exception as e:
            logger.warning(f"[InfluxDB] Flux query error: {e}")
            return []

    def get_latest_telemetry(self, device_serial: str = "ETL-ESP32-001") -> Optional[Dict[str, Any]]:
        """Fetch the latest telemetry readings for a device."""
        flux = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -1h)
          |> filter(fn: (r) => r["_measurement"] == "iot_telemetry")
          |> filter(fn: (r) => r["serial"] == "{device_serial}")
          |> last()
        '''
        rows = self.query_flux(flux)
        if not rows:
            return None

        result: Dict[str, Any] = {"serial": device_serial}
        for r in rows:
            field = r.get("_field")
            val = r.get("_value")
            time_val = r.get("_time")
            if field and val is not None:
                try:
                    result[field] = float(val) if "." in str(val) else int(val)
                except Exception:
                    result[field] = val
            if time_val:
                result["last_seen"] = time_val

        return result

    @staticmethod
    def _sanitize_tag(val: str) -> str:
        s = str(val).strip().replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")
        return s or "unknown"

    @staticmethod
    def _parse_flux_csv(csv_text: str) -> List[Dict[str, Any]]:
        lines = [l.strip() for l in csv_text.strip().split("\n") if l.strip()]
        if len(lines) < 2:
            return []

        header = None
        results = []
        for line in lines:
            if line.startswith("#"):
                continue
            cols = [c.strip() for c in line.split(",")]
            if header is None:
                header = cols
                continue
            if len(cols) == len(header):
                row = {header[i]: cols[i] for i in range(len(cols)) if header[i]}
                results.append(row)
        return results


# Global singleton instance
influx_service = InfluxDbService()

