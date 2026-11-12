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
from datetime import datetime, timezone
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
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.connected = False
        self.messages_count = 0
        self.last_message_at = None
        self.last_topic = None
        self.devices_last_seen: Dict[str, float] = {}

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
        self.stop_event.clear()
        self.worker_thread = threading.Thread(target=self._run_loop, daemon=True, name="MqttInfluxWorker")
        self.worker_thread.start()
        logger.info(f"[MQTT->InfluxDB] Background consumer worker started on {self.host}:{self.port}")

    def stop(self):
        self.is_running = False
        self.stop_event.set()
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass
            try:
                self.client.loop_stop()
            except Exception:
                pass

    def _run_loop(self):
        """Thread worker loop with automatic reconnection."""
        while self.is_running and not self.stop_event.is_set():
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
                client.loop_start()

                while self.is_running and not self.stop_event.is_set():
                    self.stop_event.wait(timeout=1.0)

                try:
                    client.loop_stop()
                    client.disconnect()
                except Exception:
                    pass
            except Exception as e:
                if not self.is_running or self.stop_event.is_set():
                    break
                logger.warning(f"[MQTT->InfluxDB] Connection error: {e}. Retrying in 10s...")
                self.stop_event.wait(timeout=10)

    def _on_connect(self, client, userdata, flags, rc, *args):
        if rc == 0:
            self.connected = True
            logger.info(f"[MQTT->InfluxDB] Connected to broker {self.host}:{self.port}!")
            for topic, qos in self.topics:
                client.subscribe(topic, qos)
                logger.info(f"[MQTT->InfluxDB] Subscribed to topic: {topic}")
        else:
            self.connected = False
            logger.warning(f"[MQTT->InfluxDB] Connect failed with code {rc}")

    def _on_disconnect(self, client, userdata, *args):
        self.connected = False
        logger.warning("[MQTT->InfluxDB] Disconnected from Mosquitto broker")

    def _on_message(self, client, userdata, msg):
        """Process incoming telemetry message and write to InfluxDB."""
        try:
            self.messages_count += 1
            self.last_message_at = datetime.now(timezone.utc).isoformat()
            self.last_topic = msg.topic
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

    def get_status(self) -> Dict[str, Any]:
        """Returns the consumer health status and telemetry counters."""
        return {
            "running": self.is_running,
            "connected": self.connected,
            "broker": f"{self.host}:{self.port}",
            "messages_count": self.messages_count,
            "last_message_at": self.last_message_at,
            "last_topic": self.last_topic,
            "devices_last_seen": self.devices_last_seen,
        }

    def _process_payload(self, topic: str, data: Dict[str, Any]):
        # Extract common fields
        device_serial = (
            data.get("serial")
            or data.get("MCID")
            or data.get("device_serial")
            or data.get("mcid")
            or "ETL-ESP32-001"
        )
        self.devices_last_seen[str(device_serial)] = time.time()
        device_name = data.get("device") or data.get("nama") or "Eternal"
        model = data.get("model") or data.get("IOT_MODEL") or "Eternal-ESP32"

        # 1. NFC RFID Tap Events (hanya dari topik /Eternal/rfid; pesan "registered" = sinkron whitelist, bukan tap)
        is_rfid_topic = topic.lower().rstrip("/").endswith("/rfid") or data.get("event") == "nfc_tap"
        if is_rfid_topic and data.get("status") != "registered" and data.get("action") != "REGISTER_USER":
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

                # Catatan: log MySQL nfc_access_logs ditulis oleh ESP32 langsung via POST /api/nfc/access
                # (NfcService.record_tap_event) sehingga tidak diduplikasi dari MQTT.

                # Broadcast live event to Architecture Map
                try:
                    from app.modules.traffic.broadcaster import traffic_broadcaster
                    traffic_broadcaster.record_and_broadcast(
                        method="NFC_TAP",
                        path=topic,
                        status=200 if status == "granted" else 403,
                        duration_ms=1.8,
                        client_ip="192.168.25.104",
                        source="esp32",
                        target="core",
                        sub_target="mysql",
                        tag="NFC_AUTH",
                        color="#34d399" if status == "granted" else "#ef4444",
                        detail=f"ESP32 -> Core -> InfluxDB & MySQL eternal_db [UID: {uid} | {user_name} ({role}) -> {status.upper()}]"
                    )
                except Exception:
                    pass

        # 2. Temperature, Humidity & Telemetry Readings (hanya field yang ada di payload)
        f = influx_service.parse_telemetry_payload(data)
        temp_val, hum_val, heat_val = f["temperature"], f["humidity"], f["heat_index"]
        rssi_val, is_locked = f["rssi"], f["is_locked"]
        rem_sec, uptime, heap = f["remaining_sec"], f["uptime_sec"], f["free_heap"]

        # Heat index diturunkan dari suhu bila firmware belum mengirimnya
        if heat_val is None and temp_val is not None and temp_val > 0:
            heat_val = temp_val

        has_data = any(v is not None for v in f.values())
        if has_data:
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
                rssi=rssi_val,
                is_locked=is_locked,
                remaining_sec=rem_sec,
                uptime_sec=uptime,
                free_heap=heap,
                extra_tags=extra_tags
            )
            if ok:
                logger.debug(f"[MQTT->InfluxDB] Wrote telemetry for {device_serial} ({temp_val}°C, {hum_val}%)")

            # Also sync latest snapshot & telemetry row to MySQL eternal_db for Grafana & Web Dashboards
            self._sync_mysql_telemetry(
                device_serial=str(device_serial),
                device_name=str(device_name),
                temp=temp_val,
                hum=hum_val,
                heat_idx=heat_val,
                rssi=rssi_val,
                is_locked=is_locked,
                rem_sec=rem_sec,
                ip=data.get("ip"),
                mac=data.get("mac"),
                ssid=data.get("ap") or data.get("ssid"),
                firmware=data.get("VER"),
            )

            # Broadcast live telemetry stream to Architecture Map
            try:
                from app.modules.traffic.broadcaster import traffic_broadcaster
                traffic_broadcaster.record_and_broadcast(
                    method="MQTT",
                    path=topic,
                    status=200,
                    duration_ms=1.2,
                    client_ip=str(data.get("ip") or "192.168.25.104"),
                    source="esp32",
                    target="mqtt",
                    sub_target="influxdb",
                    tag="TELEMETRY",
                    color="#06b6d4",
                    detail=f"ESP32 -> Mosquitto {topic} -> InfluxDB :8086 & MySQL :3306 [Suhu: {temp_val}°C, Hum: {hum_val}%]"
                )
            except Exception:
                pass

    def _sync_mysql_telemetry(
        self,
        device_serial: str,
        device_name: str,
        temp=None,
        hum=None,
        heat_idx=None,
        rssi=None,
        is_locked=None,
        rem_sec=None,
        ip=None,
        mac=None,
        ssid=None,
        firmware=None,
    ):
        """Keep MySQL eternal_db snapshot & logs in sync (hanya kolom yang datanya ada di payload)."""
        try:
            from app.modules.iot.nfc_service import get_eternal_mysql_conn
            conn = get_eternal_mysql_conn()
            try:
                with conn.cursor() as cur:
                    # 1. Update latest snapshot in iot_devices (kolom dinamis, tanpa menimpa dengan nilai palsu)
                    cols = {"device_name": device_name}
                    if temp is not None:
                        cols["temperature_c"] = temp
                    if hum is not None:
                        cols["humidity_pct"] = hum
                    if heat_idx is not None:
                        cols["heat_index_c"] = heat_idx
                    if rssi is not None:
                        cols["wifi_rssi"] = rssi
                        cols["rssi"] = rssi
                    if ip:
                        cols["ip_address"] = str(ip)
                    if mac:
                        cols["mac_address"] = str(mac)
                    if ssid:
                        cols["ssid"] = str(ssid)
                    if firmware:
                        cols["firmware_version"] = str(firmware)

                    names = ["device_serial", "model", "status", "last_seen_at"] + list(cols.keys())
                    placeholders = ["%s", "'Eternal-ESP32'", "'online'", "NOW()"] + ["%s"] * len(cols)
                    updates = ["status = 'online'", "last_seen_at = NOW()"] + [f"{k} = VALUES({k})" for k in cols]
                    cur.execute(
                        f"INSERT INTO iot_devices ({', '.join(names)}) VALUES ({', '.join(placeholders)}) "
                        f"ON DUPLICATE KEY UPDATE {', '.join(updates)};",
                        [device_serial] + list(cols.values()),
                    )

                    # 2. Append time-series point to iot_telemetry_logs (hanya bila ada pembacaan sensor)
                    if temp is not None and hum is not None and (temp > 0 or hum > 0):
                        cur.execute("""
                            INSERT INTO iot_telemetry_logs (device_serial, temperature_c, humidity_pct, heat_index_c, wifi_rssi, recorded_at)
                            VALUES (%s, %s, %s, %s, %s, NOW());
                        """, (device_serial, temp, hum, heat_idx if heat_idx is not None else temp, rssi or 0))

                    # 3. Update device_locks hanya jika status kunci ada di payload
                    if is_locked is not None:
                        lock_str = "LOCKED" if is_locked == 1 else "UNLOCKED"
                        cur.execute("""
                            UPDATE device_locks
                            SET is_locked = %s,
                                lock_status = %s,
                                unlock_duration_sec = COALESCE(%s, unlock_duration_sec),
                                updated_at = NOW()
                            WHERE device_serial = %s;
                        """, (is_locked, lock_str, rem_sec, device_serial))
            finally:
                conn.close()
        except Exception as e:
            logger.debug(f"[MQTT->MySQL Sync] Note: {e}")


# Global singleton instance
mqtt_influx_consumer = MqttInfluxConsumer()

