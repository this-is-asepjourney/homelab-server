"""
mqtt_influx_consumer.py — Realtime MQTT to InfluxDB IoT Pipeline
Implements the architecture:
  ESP32 -> Mosquitto MQTT (:1883) -> Central API Gateway (:8000) -> InfluxDB (:8086) -> Grafana (:3001)

Runs as a resilient background worker inside PAP Core API Gateway.
"""

import json
import os
import threading
import time
from typing import Any, Dict

from app.core.config import get_settings
from app.core.logging import logger
from app.services.influxdb_service import influx_service


class MqttInfluxConsumer:
    """Consumes incoming ESP32 IoT telemetry from Mosquitto and stores to InfluxDB."""

    def __init__(self):
        settings = get_settings()
        self.host = os.getenv("MQTT_HOST", getattr(settings, "MQTT_HOST", "192.168.25.101"))
        self.port = int(os.getenv("MQTT_PORT", getattr(settings, "MQTT_PORT", 1883)))
        self.username = os.getenv("MQTT_USERNAME", getattr(settings, "MQTT_USERNAME", "useriot"))
        self.password = os.getenv("MQTT_PASSWORD", getattr(settings, "MQTT_PASSWORD", "25022002"))
        self.client_id = f"pap-influx-consumer-{int(time.time())}"
        self.client = None
        self.is_running = False
        self.worker_thread = None

        self.topics = [
            ("/SysCtrl", 0),
            ("SysCtrl", 0),
            ("Eternal/SysCtrl", 0),
            ("/Eternal/telemetry", 0),
            ("Eternal/telemetry", 0),
            ("/Eternal/rfid", 0),
            ("/Eternal/lock", 0),
            ("/Eternal/#", 0),
            ("Eternal/#", 0),
            ("+/SysCtrl", 0),
            ("pap/iot/+/telemetry", 0),
        ]

    def start(self):
        """Start the background consumer thread."""
        if self.is_running:
            return
        self.is_running = True
        self.worker_thread = threading.Thread(target=self._run_loop, daemon=True, name="MqttInfluxWorker")
        self.worker_thread.start()
        logger.info(f"[MQTT->InfluxDB] Background consumer worker started on {self.host}:{self.port}")

    def stop(self):
        self.is_running = False
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass

    def _run_loop(self):
        """Thread worker loop with automatic reconnection."""
        while self.is_running:
            try:
                import paho.mqtt.client as mqtt

                # Compatibility for paho-mqtt 2.x and 1.x
                try:
                    client = mqtt.Client(
                        mqtt.CallbackAPIVersion.VERSION2,
                        client_id=self.client_id
                    )
                except Exception:
                    client = mqtt.Client(client_id=self.client_id)

                self.client = client
                if self.username:
                    client.username_pw_set(self.username, self.password)

                client.on_connect = self._on_connect
                client.on_message = self._on_message
                client.on_disconnect = self._on_disconnect

                logger.info(f"[MQTT->InfluxDB] Connecting to Mosquitto {self.host}:{self.port}...")
                client.connect(self.host, self.port, keepalive=60)
                client.loop_forever(retry_first_connection=True)
            except Exception as e:
                logger.warning(f"[MQTT->InfluxDB] Connection error: {e}. Retrying in 10s...")
                time.sleep(10)

    def _on_connect(self, client, userdata, flags, rc, *args):
        if rc == 0:
            logger.info(f"[MQTT->InfluxDB] Connected to broker {self.host}:{self.port}!")
            for topic, qos in self.topics:
                client.subscribe(topic, qos)
                logger.info(f"[MQTT->InfluxDB] Subscribed to topic: {topic}")
        else:
            logger.warning(f"[MQTT->InfluxDB] Connect failed with code {rc}")

    def _on_disconnect(self, client, userdata, *args):
        logger.warning("[MQTT->InfluxDB] Disconnected from Mosquitto broker")

    def _on_message(self, client, userdata, msg):
        """Process incoming telemetry message and write to InfluxDB."""
        try:
            topic = msg.topic
            raw_payload = msg.payload.decode("utf-8", errors="replace").strip()
            if not raw_payload:
                return

            data = None
            try:
                data = json.loads(raw_payload)
            except Exception:
                # If plain text or numeric
                return

            if not isinstance(data, dict):
                return

            self._process_payload(topic, data)
        except Exception as e:
            logger.debug(f"[MQTT->InfluxDB] Error handling message on {msg.topic}: {e}")

    def _process_payload(self, topic: str, data: Dict[str, Any]):
        # Extract common fields
        device_serial = (
            data.get("serial")
            or data.get("MCID")
            or data.get("device_serial")
            or data.get("mcid")
            or "ETL-ESP32-001"
        )
        device_name = data.get("device") or data.get("nama") or "Eternal"
        model = data.get("model") or data.get("IOT_MODEL") or "Eternal-ESP32"

        # 1. NFC RFID Tap Events
        if "rfid" in topic.lower() or "uid" in data or data.get("event") == "nfc_tap":
            uid = data.get("uid")
            if uid:
                user_name = data.get("nama") or data.get("user") or "Tamu"
                username = data.get("username") or "-"
                role = data.get("role") or "Operator"
                action = data.get("action") or data.get("action_type") or "TAP_ON"
                status = data.get("status") or "granted"
                duration = int(data.get("remaining_sec") or data.get("lock_duration_sec") or 7200)

                influx_service.write_nfc_event(
                    uid=uid,
                    user_name=user_name,
                    username=username,
                    role=role,
                    action=action,
                    device_serial=device_serial,
                    duration_sec=duration,
                    status=status
                )
                logger.info(f"[MQTT->InfluxDB] Recorded NFC event for {user_name} ({uid}) -> InfluxDB")

        # 2. Temperature, Humidity & Telemetry Readings
        suhu = data.get("suhu") or data.get("temperature") or data.get("temp")
        hum = data.get("humidity") or data.get("hum") or data.get("kelembapan")
        heat_idx = data.get("heat_index") or data.get("heatIndex") or 0.0
        rssi = data.get("rssi") or data.get("wifi_rssi") or -55
        is_locked_val = data.get("is_locked")
        if is_locked_val is None:
            lock_str = str(data.get("lock_status", "")).upper()
            is_locked = 0 if "UNLOCK" in lock_str or "OPEN" in lock_str else 1
        else:
            is_locked = 1 if is_locked_val in (1, True, "1", "true") else 0

        rem_sec = int(data.get("remaining_sec") or 0)
        uptime = int(data.get("uptime_sec") or data.get("uptime") or 0)
        heap = int(data.get("free_heap") or data.get("heap") or 0)

        # If temperature or humidity exists, store telemetry point
        if suhu is not None or hum is not None or "is_locked" in data or "lock_status" in data:
            temp_val = float(suhu) if suhu is not None else 0.0
            hum_val = float(hum) if hum is not None else 0.0
            heat_val = float(heat_idx) if heat_idx else (temp_val if temp_val > 0 else 0.0)

            extra_tags = {}
            if "ip" in data:
                extra_tags["ip"] = str(data["ip"])
            if "mac" in data:
                extra_tags["mac"] = str(data["mac"])

            ok = influx_service.write_telemetry(
                device_serial=str(device_serial),
                device_name=str(device_name),
                model=str(model),
                temperature=temp_val,
                humidity=hum_val,
                heat_index=heat_val,
                rssi=int(rssi),
                is_locked=is_locked,
                remaining_sec=rem_sec,
                uptime_sec=uptime,
                free_heap=heap,
                extra_tags=extra_tags
            )
            if ok:
                logger.debug(f"[MQTT->InfluxDB] Wrote telemetry for {device_serial} ({temp_val}°C, {hum_val}%)")


# Global singleton instance
mqtt_influx_consumer = MqttInfluxConsumer()
