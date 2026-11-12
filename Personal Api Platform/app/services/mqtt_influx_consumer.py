"""
mqtt_influx_consumer.py — Realtime MQTT to PostgreSQL IoT Pipeline Worker
Dedicated IoT Project Architecture:
  Device IoT (ESP32) -> Mosquitto MQTT (:1883) -> Worker API PAP Core -> PostgreSQL eternal_iot (:5432) -> Dashboard Grafana

Runs as a background worker inside PAP Core (pap-worker / pap-api).
"""

from datetime import datetime, timezone
import json
import os
import threading
import time
from typing import Any, Dict, Optional

from app.core.config import get_settings
from app.core.logging import logger
from app.modules.iot.nfc_service import get_eternal_pg_conn, NfcService


class MqttPgConsumer:
    """Consumes incoming ESP32 IoT telemetry from Mosquitto and stores to PostgreSQL `eternal_iot`."""

    def __init__(self):
        settings = get_settings()
        self.host = os.getenv("MQTT_HOST", getattr(settings, "MQTT_HOST", "192.168.25.101"))
        self.port = int(os.getenv("MQTT_PORT", getattr(settings, "MQTT_PORT", 1883)))
        self.username = os.getenv("MQTT_USERNAME", getattr(settings, "MQTT_USERNAME", "useriot"))
        self.password = os.getenv("MQTT_PASSWORD", getattr(settings, "MQTT_PASSWORD", "25022002"))
        self.client_id = f"pap-pg-consumer-{int(time.time())}"
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
        self.worker_thread = threading.Thread(target=self._run_loop, daemon=True, name="MqttPgWorker")
        self.worker_thread.start()
        logger.info(f"[MQTT->PostgreSQL] IoT consumer worker started on {self.host}:{self.port} -> db: eternal_iot")

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

                logger.info(f"[MQTT->PostgreSQL] Connecting to Mosquitto {self.host}:{self.port}...")
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
                logger.warning(f"[MQTT->PostgreSQL] Connection error: {e}. Retrying in 10s...")
                self.stop_event.wait(timeout=10)

    def _on_connect(self, client, userdata, flags, rc, *args):
        if rc == 0:
            self.connected = True
            logger.info(f"[MQTT->PostgreSQL] Connected to broker {self.host}:{self.port}!")
            for topic, qos in self.topics:
                client.subscribe(topic, qos)
                logger.info(f"[MQTT->PostgreSQL] Subscribed to topic: {topic}")
        else:
            self.connected = False
            logger.warning(f"[MQTT->PostgreSQL] Connect failed with code {rc}")

    def _on_disconnect(self, client, userdata, *args):
        self.connected = False
        logger.warning("[MQTT->PostgreSQL] Disconnected from Mosquitto broker")

    def _on_message(self, client, userdata, msg):
        """Process incoming telemetry message and write to PostgreSQL `eternal_iot`."""
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
                return

            if not isinstance(data, dict):
                return

            self._process_payload(topic, data)
        except Exception as e:
            logger.debug(f"[MQTT->PostgreSQL] Error handling message on {msg.topic}: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Returns the consumer health status and telemetry counters."""
        return {
            "running": self.is_running,
            "connected": self.connected,
            "broker": f"{self.host}:{self.port}",
            "database": "postgresql://eternal_iot",
            "messages_count": self.messages_count,
            "last_message_at": self.last_message_at,
            "last_topic": self.last_topic,
            "devices_last_seen": self.devices_last_seen,
        }

    def _process_payload(self, topic: str, data: Dict[str, Any]):
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

        # 1. Handle NFC RFID Tap Events
        is_rfid_topic = topic.lower().rstrip("/").endswith("/rfid") or data.get("event") == "nfc_tap"
        if is_rfid_topic and data.get("status") != "registered" and data.get("action") != "REGISTER_USER":
            uid = data.get("uid")
            if uid:
                user_name = data.get("nama") or data.get("user") or "Tamu"
                username = data.get("username") or "-"
                role = data.get("role") or "Operator"
                action = data.get("action") or data.get("action_type") or data.get("event") or "TAP_ON"
                duration = int(data.get("remaining_sec") or data.get("lock_duration_sec") or 7200)

                try:
                    NfcService.record_tap_event({
                        "uid": uid,
                        "nama": user_name,
                        "username": username,
                        "role": role,
                        "action_type": action,
                        "lock_duration_sec": duration,
                        "device_serial": str(device_serial),
                        "device_ip": str(data.get("ip") or "192.168.25.104")
                    })
                    logger.info(f"[MQTT->PostgreSQL] Recorded NFC event for {user_name} ({uid}) -> PostgreSQL")
                except Exception as e:
                    logger.debug(f"[MQTT->PostgreSQL NFC Tap] Error: {e}")

                # Broadcast live event to Architecture Map UI
                try:
                    from app.modules.traffic.broadcaster import traffic_broadcaster
                    traffic_broadcaster.record_and_broadcast(
                        method="NFC_TAP",
                        path=topic,
                        status=200 if data.get("status") != "denied" else 403,
                        duration_ms=1.8,
                        client_ip="192.168.25.104",
                        source="esp32",
                        target="core",
                        sub_target="postgresql",
                        tag="NFC_AUTH",
                        color="#34d399" if data.get("status") != "denied" else "#ef4444",
                        detail=f"ESP32 -> Core -> PostgreSQL eternal_iot [UID: {uid} | {user_name} ({role})]"
                    )
                except Exception:
                    pass

        # 2. Handle Telemetry & Lock State
        f = self._parse_telemetry(data)
        has_data = any(v is not None for v in f.values())
        if has_data:
            self._sync_pg_telemetry(
                device_serial=str(device_serial),
                device_name=str(device_name),
                model=str(model),
                temp=f["temperature"],
                hum=f["humidity"],
                heat_idx=f["heat_index"],
                rssi=f["rssi"],
                is_locked=f["is_locked"],
                rem_sec=f["remaining_sec"],
                uptime=f["uptime_sec"],
                heap=f["free_heap"],
                ip=data.get("ip") or data.get("MCIP"),
                mac=data.get("mac") or data.get("MAC"),
                ssid=data.get("ap") or data.get("ssid"),
                firmware=data.get("VER"),
            )

            # Broadcast live telemetry stream to Architecture Map UI
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
                    sub_target="postgresql",
                    tag="TELEMETRY",
                    color="#06b6d4",
                    detail=f"ESP32 -> Mosquitto {topic} -> PostgreSQL eternal_iot"
                )
            except Exception:
                pass

    @staticmethod
    def _parse_telemetry(payload: Dict[str, Any]) -> Dict[str, Any]:
        def _num(*keys, cast=float):
            for k in keys:
                v = payload.get(k)
                if v is not None and v != "":
                    try:
                        return cast(v)
                    except (TypeError, ValueError):
                        return None
            return None

        is_locked_val = payload.get("is_locked")
        if is_locked_val is not None:
            is_locked = 1 if is_locked_val in (1, True, "1", "true") else 0
        elif payload.get("lock_status") is not None:
            lock_str = str(payload.get("lock_status", "")).upper()
            is_locked = 0 if ("UNLOCK" in lock_str or "OPEN" in lock_str) else 1
        else:
            is_locked = None

        temp = _num("suhu", "temperature", "temp")
        hum = _num("humidity", "hum", "kelembapan")
        heat_idx = _num("heat_index", "heatIndex")
        if heat_idx is None and temp is not None and temp > 0:
            heat_idx = temp

        return {
            "temperature": temp,
            "humidity": hum,
            "heat_index": heat_idx,
            "rssi": _num("rssi", "wifi_rssi", cast=int),
            "is_locked": is_locked,
            "remaining_sec": _num("remaining_sec", cast=int),
            "uptime_sec": _num("uptime_sec", "uptime", cast=int),
            "free_heap": _num("free_heap", "heap", cast=int),
        }

    def _sync_pg_telemetry(
        self,
        device_serial: str,
        device_name: str,
        model: str = "Eternal-ESP32",
        temp=None,
        hum=None,
        heat_idx=None,
        rssi=None,
        is_locked=None,
        rem_sec=None,
        uptime=None,
        heap=None,
        ip=None,
        mac=None,
        ssid=None,
        firmware=None,
    ):
        """Keep PostgreSQL `eternal_iot` snapshot & logs in sync with incoming MQTT telemetry."""
        conn = None
        try:
            conn = get_eternal_pg_conn()
            with conn.cursor() as cur:
                # 1. Update latest snapshot in iot_devices
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
                if uptime is not None:
                    cols["uptime_sec"] = uptime
                if heap is not None:
                    cols["free_heap"] = heap
                if ip:
                    cols["ip_address"] = str(ip)
                if mac:
                    cols["mac_address"] = str(mac)
                if ssid:
                    cols["ssid"] = str(ssid)
                if firmware:
                    cols["firmware_version"] = str(firmware)

                names = ["device_serial", "model", "status", "last_seen_at", "updated_at"] + list(cols.keys())
                placeholders = ["%s", "%s", "'online'", "NOW()", "NOW()"] + ["%s"] * len(cols)
                updates = ["status = 'online'", "last_seen_at = NOW()", "updated_at = NOW()"] + [f"{k} = EXCLUDED.{k}" for k in cols]

                sql_device = f"""
                    INSERT INTO iot_devices ({', '.join(names)})
                    VALUES ({', '.join(placeholders)})
                    ON CONFLICT (device_serial) DO UPDATE
                    SET {', '.join(updates)};
                """
                cur.execute(sql_device, [device_serial, model] + list(cols.values()))

                # 2. Append time-series point to iot_telemetry_logs
                if temp is not None or hum is not None or is_locked is not None:
                    cur.execute("""
                        INSERT INTO iot_telemetry_logs
                            (device_serial, temperature_c, humidity_pct, heat_index_c, wifi_rssi,
                             is_locked, remaining_sec, uptime_sec, free_heap, recorded_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW());
                    """, (
                        device_serial,
                        temp or 0.0,
                        hum or 0.0,
                        heat_idx or 0.0,
                        rssi or 0,
                        is_locked if is_locked is not None else 1,
                        rem_sec or 0,
                        uptime or 0,
                        heap or 0,
                    ))

                # 3. Update device_locks if is_locked is present
                if is_locked is not None:
                    lock_str = "LOCKED" if is_locked == 1 else "UNLOCKED"
                    cur.execute("""
                        INSERT INTO device_locks
                            (device_serial, device_name, is_locked, lock_status, unlock_duration_sec, updated_at)
                        VALUES (%s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (device_serial) DO UPDATE
                        SET is_locked = EXCLUDED.is_locked,
                            lock_status = EXCLUDED.lock_status,
                            unlock_duration_sec = COALESCE(EXCLUDED.unlock_duration_sec, device_locks.unlock_duration_sec),
                            updated_at = NOW();
                    """, (device_serial, device_name, is_locked, lock_str, rem_sec or 7200))
        except Exception as e:
            logger.debug(f"[MQTT->PostgreSQL Sync] Error: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass


# Global singleton instance
mqtt_influx_consumer = MqttPgConsumer()
