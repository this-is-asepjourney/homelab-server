"""
Personal API Platform (PAP) — Decoupled Background Worker Daemon
================================================================
Eliminates Single Point of Failure (SPOF) from the Central API Gateway:
- Consumes realtime MQTT telemetry from Mosquitto (:1883) and writes to InfluxDB (:8086)
- Keeps MySQL eternal_db telemetry and lock state in sync
- Runs automated periodic full-stack backup scheduler with instant integrity verification
- Enforces backup retention policy (auto-prune old archives)
- Monitors Fleet IoT health (Dead Man's Snitch)
- Reports live heartbeats to the Central API Gateway (pap-api)
"""

import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import urllib.request
import json

from app.core.config import get_settings
from app.modules.backups.service import BackupService
from app.services.mqtt_influx_consumer import mqtt_influx_consumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [pap.worker] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pap.worker")

stop_event = threading.Event()


def _get_process_rss_mb() -> float:
    """Returns the resident memory set in megabytes safely across platforms."""
    try:
        # Linux /proc/self/status check
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    return round(float(parts[1]) / 1024.0, 1)
    except Exception:
        pass
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(rss / (1024.0 if sys.platform != "darwin" else 1024.0 * 1024.0), 1)
    except Exception:
        return 0.0


class PapWorker:
    """Master background worker orchestrator."""

    def __init__(self):
        self.settings = get_settings()
        self.worker_id = os.getenv("WORKER_ID", "pap-worker-01")
        self.gateway_url = os.getenv("PAP_API_URL", "http://pap-api:8000").rstrip("/")
        self.start_time = time.time()

        # Auto-backup configuration
        self.enable_auto_backup = os.getenv("ENABLE_AUTO_BACKUP", "true").lower() in ("true", "1", "yes")
        self.backup_interval_sec = int(os.getenv("BACKUP_INTERVAL_HOURS", "24")) * 3600
        self.backup_retention_days = int(os.getenv("BACKUP_RETENTION_DAYS", "7"))
        self.last_backup_time: Optional[float] = None
        self.last_backup_status: Optional[str] = None

        # IoT Fleet watchdog tracking
        self.device_last_seen: Dict[str, float] = {}
        self.device_offline_states: Dict[str, bool] = {}
        self.last_nfc_sync_time: float = 0.0
        self.last_maintenance_time: float = 0.0

    def start(self):
        logger.info("==================================================")
        logger.info(f"Starting {self.worker_id} (PAP Decoupled Worker Engine)")
        logger.info(f"Connected Gateway: {self.gateway_url}")
        logger.info(f"Auto-Backup Enabled: {self.enable_auto_backup} (every {self.backup_interval_sec // 3600}h, retention {self.backup_retention_days}d)")
        logger.info("IoT Fleet Watchdog: Active (90s dead-man timeout)")
        logger.info("NFC Whitelist Relay: Active (every 5m sync to MQTT)")
        logger.info("Database Retention Maintenance: Active (every 6h prune >14d)")
        logger.info("==================================================")

        # 1. Start MQTT -> InfluxDB Consumer
        try:
            mqtt_influx_consumer.start()
            logger.info("MQTT Influx consumer thread started successfully.")
        except Exception as e:
            logger.error(f"Failed to start MQTT consumer: {e}")

        # 2. Main loop running scheduled jobs & heartbeats
        last_heartbeat_time = 0.0
        last_watchdog_time = 0.0

        while not stop_event.is_set():
            now = time.time()

            # Heartbeat check (every 15s)
            if now - last_heartbeat_time >= 15.0:
                self._send_heartbeat()
                last_heartbeat_time = now

            # Automated Backup check (every 60s check)
            if self.enable_auto_backup:
                self._check_backup_schedule(now)

            # Fleet Watchdog check (every 30s)
            if now - last_watchdog_time >= 30.0:
                self._check_fleet_watchdog()
                last_watchdog_time = now

            # NFC Whitelist sync to MQTT (every 300s / 5m)
            if now - self.last_nfc_sync_time >= 300.0:
                self._sync_nfc_whitelist_to_mqtt()
                self.last_nfc_sync_time = now

            # Database maintenance & log pruning (every 6 hours)
            if now - self.last_maintenance_time >= 21600.0:
                self._run_database_maintenance()
                self.last_maintenance_time = now

            stop_event.wait(timeout=1.0)

        self._shutdown()

    def _check_backup_schedule(self, now: float):
        """Triggers scheduled full-stack backup if interval elapsed or daily slot reached."""
        should_run = False
        if self.last_backup_time is None:
            # Check existing backups on disk
            try:
                existing = BackupService.list_backups()
                if existing:
                    latest_created = existing[0].get("created_at")
                    if latest_created:
                        if latest_created.endswith("Z"):
                            latest_created = latest_created[:-1] + "+00:00"
                        dt = datetime.fromisoformat(latest_created)
                        self.last_backup_time = dt.timestamp()
                else:
                    # No backups exist yet; wait 30s after startup then trigger initial backup
                    if now - self.start_time >= 30.0:
                        should_run = True
            except Exception as e:
                logger.debug(f"Error checking existing backups: {e}")

        if not should_run and self.last_backup_time is not None:
            if now - self.last_backup_time >= self.backup_interval_sec:
                should_run = True

        if should_run:
            self._execute_scheduled_backup()

    def _execute_scheduled_backup(self):
        """Executes full-stack backup, verifies archive integrity, and applies retention pruning."""
        logger.info("[AutoBackup] Starting scheduled full-stack disaster recovery backup...")
        try:
            manifest = BackupService.create_backup(
                scope="all",
                note=f"Automated Scheduled Backup by {self.worker_id}"
            )
            archive_name = manifest["archive"]["filename"]
            logger.info(f"[AutoBackup] Archive created: {archive_name} ({manifest['archive']['size_human']})")

            # Verify integrity
            verification = BackupService.verify_backup(archive_name)
            score = verification.get("integrity_score_percent", 0.0)
            status = verification.get("status", "UNKNOWN")
            logger.info(f"[AutoBackup] Verification Report: {status} (Integrity Score: {score}%)")

            # Prune old backups
            prune_report = BackupService.prune_backups(
                keep_days=self.backup_retention_days,
                keep_min=3
            )
            if prune_report["pruned"] > 0:
                logger.info(f"[AutoBackup] Pruned {prune_report['pruned']} old backup archives (Remaining: {prune_report['remaining']})")

            self.last_backup_time = time.time()
            self.last_backup_status = f"{status} ({score}%)"

            # Post live event to Gateway
            self._post_traffic_event(
                method="SNAPSHOT",
                path="/api/v1/backups/auto",
                status=200,
                source="worker",
                target="core",
                sub_target="postgres",
                tag="AUTO_BACKUP",
                color="#10b981",
                detail=f"Auto-Backup Completed: {archive_name} [{score}% Valid, {prune_report['remaining']} stored]"
            )
        except Exception as e:
            logger.error(f"[AutoBackup] Scheduled backup failed: {e}")
            self.last_backup_status = f"FAILED: {e}"

    def _check_fleet_watchdog(self):
        """Monitors fleet machine activity for silence (Dead Man's Snitch)."""
        mqtt_status = mqtt_influx_consumer.get_status()
        devices = mqtt_status.get("devices_last_seen", {})
        now = time.time()

        # If no messages seen in session yet, also check MySQL devices
        if not devices:
            try:
                from app.modules.iot.nfc_service import get_eternal_mysql_conn
                conn = get_eternal_mysql_conn()
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT device_serial, status, UNIX_TIMESTAMP(last_seen_at) FROM iot_devices;")
                        rows = cur.fetchall() or []
                        for r in rows:
                            s = r.get("device_serial")
                            ts = r.get("UNIX_TIMESTAMP(last_seen_at)")
                            if s and ts:
                                devices[s] = float(ts)
                finally:
                    conn.close()
            except Exception:
                pass

        for serial, last_seen in list(devices.items()):
            idle_sec = now - last_seen
            is_idle = idle_sec > 90.0  # 90 seconds without packet

            was_offline = self.device_offline_states.get(serial, False)
            if is_idle and not was_offline:
                self.device_offline_states[serial] = True
                logger.warning(f"[Fleet Watchdog] Machine {serial} silent for {int(idle_sec)}s. Marking OFFLINE.")
                self._update_device_status_in_db(serial, "offline")
                self._post_traffic_event(
                    method="WATCHDOG",
                    path=f"/iot/devices/{serial}/status",
                    status=504,
                    source="worker",
                    target="core",
                    sub_target="mysql",
                    tag="FLEET_OFFLINE",
                    color="#ef4444",
                    detail=f"Watchdog alert: {serial} is silent ({int(idle_sec)}s without telemetry)"
                )
            elif not is_idle and was_offline:
                self.device_offline_states[serial] = False
                logger.info(f"[Fleet Watchdog] Machine {serial} active again ({int(idle_sec)}s). Marking ONLINE.")
                self._update_device_status_in_db(serial, "online")
                self._post_traffic_event(
                    method="WATCHDOG",
                    path=f"/iot/devices/{serial}/status",
                    status=200,
                    source="worker",
                    target="core",
                    sub_target="mysql",
                    tag="FLEET_ONLINE",
                    color="#10b981",
                    detail=f"Watchdog recovery: {serial} resumed telemetry"
                )

    def _update_device_status_in_db(self, serial: str, status: str):
        try:
            from app.modules.iot.nfc_service import get_eternal_mysql_conn
            conn = get_eternal_mysql_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE iot_devices SET status = %s WHERE device_serial = %s;",
                        (status, serial)
                    )
            finally:
                conn.close()
        except Exception as e:
            logger.debug(f"[Worker DB Update] Error updating {serial} to {status}: {e}")

    def _sync_nfc_whitelist_to_mqtt(self):
        """Periodically broadcasts verified NFC UID whitelist to MQTT broker for offline resiliency."""
        try:
            from app.modules.iot.nfc_service import NfcService
            users = NfcService.list_users()
            active_uids = [u.get("uid") for u in users if u.get("is_active", 1) and u.get("uid")]
            if active_uids and mqtt_influx_consumer.client and mqtt_influx_consumer.connected:
                payload = {
                    "event": "users_sync",
                    "count": len(active_uids),
                    "uids": active_uids,
                    "timestamp": int(time.time()),
                    "synced_by": self.worker_id,
                }
                mqtt_influx_consumer.client.publish(
                    "Eternal/users/sync",
                    json.dumps(payload),
                    qos=1,
                    retain=True
                )
                logger.info(f"[Worker NFC Sync] Synced {len(active_uids)} active NFC cards to MQTT 'Eternal/users/sync'")
        except Exception as e:
            logger.debug(f"[Worker NFC Sync] Note: {e}")

    def _run_database_maintenance(self):
        """Prunes old telemetry logs in MySQL older than 14 days (InfluxDB handles long-term TSDB)."""
        try:
            from app.modules.iot.nfc_service import get_eternal_mysql_conn
            conn = get_eternal_mysql_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM iot_telemetry_logs WHERE recorded_at < NOW() - INTERVAL 14 DAY;")
                    deleted = cur.rowcount
                    if deleted > 0:
                        logger.info(f"[Worker Maintenance] Pruned {deleted} old raw rows from iot_telemetry_logs (>14d)")
            finally:
                conn.close()
        except Exception as e:
            logger.debug(f"[Worker Maintenance] Note: {e}")

    def _check_databases_health(self) -> Dict[str, str]:
        """Runs fast connectivity checks across Postgres, MySQL, and InfluxDB."""
        results = {}
        # 1. MySQL
        try:
            from app.modules.iot.nfc_service import get_eternal_mysql_conn
            c = get_eternal_mysql_conn()
            c.close()
            results["mysql"] = "healthy"
        except Exception as e:
            results["mysql"] = f"unhealthy: {e}"

        # 2. InfluxDB
        try:
            from app.services.influxdb_service import influx_service
            results["influxdb"] = "healthy" if influx_service.is_healthy() else "degraded"
        except Exception:
            results["influxdb"] = "unreachable"

        # 3. PostgreSQL
        try:
            import psycopg2
            pg_conn = psycopg2.connect(
                host=os.getenv("POSTGRES_HOST", "192.168.25.101"),
                port=int(os.getenv("POSTGRES_PORT", 5432)),
                dbname=os.getenv("POSTGRES_DB", "psm"),
                user=os.getenv("POSTGRES_USER", "appuser"),
                password=os.getenv("POSTGRES_PASSWORD", "admin12345"),
                connect_timeout=3
            )
            pg_conn.close()
            results["postgres"] = "healthy"
        except Exception:
            results["postgres"] = "unreachable"

        return results

    def _send_heartbeat(self):
        """Sends periodic operational status to central gateway."""
        try:
            mqtt_status = mqtt_influx_consumer.get_status()
            devices_monitored = max(len(mqtt_status.get("devices_last_seen", {})), 1)
            devices_offline_count = sum(1 for v in self.device_offline_states.values() if v)
            devices_online = max(devices_monitored - devices_offline_count, 0)

            db_health = self._check_databases_health()

            payload = {
                "worker_id": self.worker_id,
                "uptime_sec": int(time.time() - self.start_time),
                "mqtt_connected": mqtt_status.get("connected", False),
                "mqtt_messages_processed": mqtt_status.get("messages_count", 0),
                "last_mqtt_topic": mqtt_status.get("last_topic"),
                "last_mqtt_at": mqtt_status.get("last_message_at"),
                "auto_backup_enabled": self.enable_auto_backup,
                "last_backup_at": datetime.fromtimestamp(self.last_backup_time, timezone.utc).isoformat() if self.last_backup_time else None,
                "active_monitors": 4,
                "memory_rss_mb": _get_process_rss_mb(),
                "devices_online": devices_online,
                "devices_monitored": devices_monitored,
                "databases_health": db_health,
                "last_maintenance_at": datetime.fromtimestamp(self.last_maintenance_time, timezone.utc).isoformat() if self.last_maintenance_time else None,
            }

            url = f"{self.gateway_url}/api/v1/system/worker-heartbeat"
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                pass
        except Exception as e:
            logger.debug(f"Heartbeat dispatch note: {e}")

    def _post_traffic_event(self, method: str, path: str, status: int, source: str, target: str, sub_target: str, tag: str, color: str, detail: str):
        """Posts a live event to the gateway architecture map."""
        try:
            event = {
                "method": method,
                "path": path,
                "status": status,
                "duration_ms": 2.5,
                "client_ip": "127.0.0.1",
                "source": source,
                "target": target,
                "sub_target": sub_target,
                "tag": tag,
                "color": color,
                "detail": detail,
            }
            url = f"{self.gateway_url}/api/v1/traffic/event"
            req = urllib.request.Request(
                url,
                data=json.dumps(event).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                pass
        except Exception:
            pass

    def _shutdown(self):
        logger.info("Graceful shutdown in progress...")
        try:
            mqtt_influx_consumer.stop()
            logger.info("MQTT Influx consumer stopped.")
        except Exception as e:
            logger.error(f"Error stopping MQTT consumer: {e}")
        logger.info(f"{self.worker_id} shutdown complete.")


def handle_signal(sig, frame):
    logger.info(f"Signal {sig} received, stopping worker...")
    stop_event.set()


def main():
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    worker = PapWorker()
    worker.start()


if __name__ == "__main__":
    main()

