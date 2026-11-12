"""
nfc_service.py — NFC Identity, Roles, Whitelist & Access Logs Management
Dedicated IoT Project Database: PostgreSQL `eternal_iot` (:5432).

Pipeline Arsitektur:
  Device IoT (ESP32) -> Mosquitto MQTT (:1883) -> Worker API PAP Core -> PostgreSQL (:5432) -> Dashboard Grafana
"""

from datetime import datetime, timezone
import json
import os
from typing import Any, Dict, List, Optional
import urllib.request


def get_eternal_pg_conn():
    """Connect to PostgreSQL `eternal_iot` dedicated IoT database."""
    host = os.getenv("POSTGRES_HOST", "192.168.25.101")
    port = int(os.getenv("POSTGRES_PORT", 5432))
    user = os.getenv("POSTGRES_USER", "appuser")
    password = os.getenv("POSTGRES_PASSWORD", "admin12345")
    db_name = os.getenv("IOT_POSTGRES_DB", "eternal_iot")

    try:
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=db_name,
            autocommit=True,
            row_factory=dict_row
        )
    except ImportError:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=db_name
        )
        conn.autocommit = True
        return conn


# Backward-compatibility alias
def get_eternal_mysql_conn():
    return get_eternal_pg_conn()


def _ensure_tables(conn):
    """Ensure PostgreSQL schema for eternal_iot exists."""
    ddl = """
    CREATE TABLE IF NOT EXISTS nfc_users (
        id SERIAL PRIMARY KEY,
        uid VARCHAR(32) NOT NULL UNIQUE,
        nama VARCHAR(100) NOT NULL,
        username VARCHAR(64) NOT NULL,
        role VARCHAR(32) DEFAULT 'Operator',
        pin VARCHAR(16) DEFAULT '',
        is_active SMALLINT DEFAULT 1,
        device_serial VARCHAR(32) DEFAULT 'ETL-ESP32-001',
        total_taps INT DEFAULT 0,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        last_login_at TIMESTAMP WITH TIME ZONE DEFAULT NULL
    );

    CREATE TABLE IF NOT EXISTS nfc_access_logs (
        id SERIAL PRIMARY KEY,
        uid VARCHAR(32) NOT NULL,
        nama VARCHAR(100) DEFAULT '-',
        username VARCHAR(64) DEFAULT '-',
        role VARCHAR(32) DEFAULT 'Operator',
        action_type VARCHAR(64) NOT NULL,
        lock_duration_sec INT DEFAULT 7200,
        device_serial VARCHAR(32) DEFAULT 'ETL-ESP32-001',
        device_ip VARCHAR(64) DEFAULT '0.0.0.0',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS device_locks (
        device_serial VARCHAR(32) PRIMARY KEY,
        device_name VARCHAR(64) DEFAULT 'Eternal',
        is_locked SMALLINT DEFAULT 1,
        lock_status VARCHAR(16) DEFAULT 'LOCKED',
        unlocked_by_uid VARCHAR(32) DEFAULT NULL,
        unlocked_by_name VARCHAR(100) DEFAULT NULL,
        unlocked_by_username VARCHAR(64) DEFAULT NULL,
        unlocked_by_role VARCHAR(32) DEFAULT NULL,
        unlock_duration_sec INT DEFAULT 7200,
        unlocked_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
        unlock_expires_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
        last_toggle_action VARCHAR(64) DEFAULT 'LOCK_OFF',
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS iot_devices (
        id SERIAL PRIMARY KEY,
        device_serial VARCHAR(32) NOT NULL UNIQUE,
        device_name VARCHAR(64) NOT NULL,
        mac_address VARCHAR(32) DEFAULT NULL,
        model VARCHAR(32) DEFAULT 'Eternal-ESP32',
        ip_address VARCHAR(64) DEFAULT '0.0.0.0',
        ssid VARCHAR(64) DEFAULT NULL,
        rssi INT DEFAULT 0,
        wifi_rssi INT DEFAULT 0,
        temperature_c REAL DEFAULT 0,
        humidity_pct REAL DEFAULT 0,
        heat_index_c REAL DEFAULT 0,
        firmware_version VARCHAR(32) DEFAULT '3.1.0',
        mqtt_broker VARCHAR(64) DEFAULT '192.168.25.101',
        status VARCHAR(16) DEFAULT 'online',
        uptime_sec BIGINT DEFAULT 0,
        free_heap BIGINT DEFAULT 0,
        air_quality VARCHAR(32) DEFAULT NULL,
        last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS iot_telemetry_logs (
        id BIGSERIAL PRIMARY KEY,
        device_serial VARCHAR(32) NOT NULL,
        temperature_c REAL DEFAULT 0,
        humidity_pct REAL DEFAULT 0,
        heat_index_c REAL DEFAULT 0,
        wifi_rssi INT DEFAULT 0,
        is_locked SMALLINT DEFAULT 1,
        remaining_sec INT DEFAULT 0,
        uptime_sec BIGINT DEFAULT 0,
        free_heap BIGINT DEFAULT 0,
        recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_nfc_users_uid ON nfc_users(uid);
    CREATE INDEX IF NOT EXISTS idx_nfc_access_logs_time ON nfc_access_logs(created_at);
    CREATE INDEX IF NOT EXISTS idx_iot_telemetry_logs_time ON iot_telemetry_logs(recorded_at);
    CREATE INDEX IF NOT EXISTS idx_iot_telemetry_logs_serial ON iot_telemetry_logs(device_serial, recorded_at);
    """
    try:
        with conn.cursor() as cur:
            cur.execute(ddl)
    except Exception:
        pass


def _get_cursor(conn):
    try:
        import psycopg2.extras
        if hasattr(conn, "cursor") and not hasattr(conn, "row_factory"):
            return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    except Exception:
        pass
    return conn.cursor()


class NfcService:
    @staticmethod
    def list_users() -> List[Dict[str, Any]]:
        conn = get_eternal_pg_conn()
        try:
            _ensure_tables(conn)
            with _get_cursor(conn) as cur:
                cur.execute("""
                    SELECT id, uid, nama, username, role, pin, is_active, device_serial,
                           total_taps,
                           TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at,
                           TO_CHAR(last_login_at, 'YYYY-MM-DD HH24:MI:SS') AS last_login_at
                    FROM nfc_users
                    ORDER BY id ASC;
                """)
                return cur.fetchall() or []
        finally:
            conn.close()

    @staticmethod
    def get_user_by_uid(uid: str) -> Optional[Dict[str, Any]]:
        clean_uid = uid.strip().upper().replace(" ", "").replace(":", "")
        conn = get_eternal_pg_conn()
        try:
            _ensure_tables(conn)
            with _get_cursor(conn) as cur:
                cur.execute("""
                    SELECT id, uid, nama, username, role, pin, is_active, device_serial,
                           total_taps,
                           TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at,
                           TO_CHAR(last_login_at, 'YYYY-MM-DD HH24:MI:SS') AS last_login_at
                    FROM nfc_users
                    WHERE UPPER(uid) = %s
                    LIMIT 1;
                """, (clean_uid,))
                return cur.fetchone()
        finally:
            conn.close()

    @staticmethod
    def save_user(data: Dict[str, Any], push_to_hardware: bool = True) -> Dict[str, Any]:
        raw_uid = data.get("uid", "").strip().upper().replace(" ", "").replace(":", "")
        if not raw_uid:
            raise ValueError("UID NFC wajib diisi")

        nama = data.get("nama", "").strip() or "Pengguna NFC"
        username = data.get("username", "").strip() or f"user_{raw_uid[-4:].lower()}"
        role = data.get("role", "Operator").strip()
        pin = data.get("pin", "").strip()
        is_active = 1 if data.get("is_active", True) in (1, True, "1", "true") else 0
        device_serial = data.get("device_serial", "ETL-ESP32-001")

        conn = get_eternal_pg_conn()
        try:
            _ensure_tables(conn)
            with _get_cursor(conn) as cur:
                cur.execute("""
                    INSERT INTO nfc_users (uid, nama, username, role, pin, is_active, device_serial, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (uid) DO UPDATE
                    SET nama = EXCLUDED.nama,
                        username = EXCLUDED.username,
                        role = EXCLUDED.role,
                        pin = EXCLUDED.pin,
                        is_active = EXCLUDED.is_active,
                        device_serial = EXCLUDED.device_serial;
                """, (raw_uid, nama, username, role, pin, is_active, device_serial))

            saved_user = NfcService.get_user_by_uid(raw_uid) or {"uid": raw_uid, "status": "saved"}

            # Auto-push ke ESP32 hardware hanya jika bukan event yang berasal dari alat itu sendiri
            if push_to_hardware:
                NfcService.push_to_device(saved_user)
            return saved_user
        finally:
            conn.close()

    @staticmethod
    def push_to_device(user: Dict[str, Any]):
        """Kirim profil user NFC langsung ke memori RAM/NVS ESP32 agar langsung aktif tanpa restart alat."""
        target_ips = ["192.168.25.104"]
        for ip in target_ips:
            try:
                payload = json.dumps({
                    "uid": user.get("uid"),
                    "nama": user.get("nama"),
                    "username": user.get("username"),
                    "role": user.get("role", "Operator"),
                    "pin": user.get("pin", ""),
                    "source": "server"
                }).encode("utf-8")
                req = urllib.request.Request(
                    f"http://{ip}/api/nfc/register_user",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Source": "server-sync"
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=1.5):
                    pass
            except Exception:
                pass

    @staticmethod
    def delete_user(uid: str) -> bool:
        clean_uid = uid.strip().upper().replace(" ", "").replace(":", "")
        conn = get_eternal_pg_conn()
        try:
            _ensure_tables(conn)
            with _get_cursor(conn) as cur:
                cur.execute("DELETE FROM nfc_users WHERE UPPER(uid) = %s;", (clean_uid,))
                affected = cur.rowcount

            # Hapus juga dari hardware ESP32
            try:
                payload = json.dumps({"uid": clean_uid}).encode("utf-8")
                req = urllib.request.Request(
                    "http://192.168.25.104/api/rfid/delete",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=1.5):
                    pass
            except Exception:
                pass

            return affected > 0
        finally:
            conn.close()

    @staticmethod
    def list_access_logs(limit: int = 50) -> List[Dict[str, Any]]:
        conn = get_eternal_pg_conn()
        try:
            _ensure_tables(conn)
            with _get_cursor(conn) as cur:
                cur.execute("""
                    SELECT id, uid, nama, username, role, action_type, lock_duration_sec,
                           device_serial, device_ip,
                           TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at
                    FROM nfc_access_logs
                    ORDER BY id DESC
                    LIMIT %s;
                """, (limit,))
                return cur.fetchall() or []
        finally:
            conn.close()

    @staticmethod
    def get_latest_tap() -> Optional[Dict[str, Any]]:
        conn = get_eternal_pg_conn()
        try:
            _ensure_tables(conn)
            with _get_cursor(conn) as cur:
                cur.execute("""
                    SELECT id, uid, nama, username, role, action_type, lock_duration_sec,
                           device_serial, device_ip,
                           TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at
                    FROM nfc_access_logs
                    ORDER BY id DESC
                    LIMIT 1;
                """)
                return cur.fetchone()
        finally:
            conn.close()

    @staticmethod
    def record_tap_event(payload: Dict[str, Any]) -> Dict[str, Any]:
        raw_uid = payload.get("uid", "").strip().upper().replace(" ", "").replace(":", "")
        if not raw_uid:
            raise ValueError("UID kartu wajib ada.")

        user = NfcService.get_user_by_uid(raw_uid)
        nama = payload.get("nama") or (user["nama"] if user else "Tamu / Belum Terdaftar")
        username = payload.get("username") or (user["username"] if user else f"nfc_{raw_uid[-4:].lower()}")
        role = payload.get("role") or (user["role"] if user else "GUEST")
        action = str(
            payload.get("action_type") or payload.get("action") or payload.get("event") or "TAP_ON"
        )
        action_up = action.upper()
        device_serial = payload.get("device_serial", "ETL-ESP32-001")
        device_ip = payload.get("device_ip") or payload.get("ip") or "0.0.0.0"
        if payload.get("lock_duration_sec") is not None:
            lock_sec = int(payload["lock_duration_sec"])
        elif payload.get("remaining_sec") is not None:
            lock_sec = int(payload["remaining_sec"])
        else:
            lock_sec = 7200
        is_denied = "DENIED" in action_up
        is_unlocking = "UNLOCK" in action_up or action_up.endswith("_ON") or action_up == "TAP_ON"

        conn = get_eternal_pg_conn()
        try:
            _ensure_tables(conn)
            with _get_cursor(conn) as cur:
                # 1. Simpan ke nfc_access_logs PostgreSQL
                cur.execute("""
                    INSERT INTO nfc_access_logs (uid, nama, username, role, action_type, lock_duration_sec, device_serial, device_ip, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW());
                """, (raw_uid, nama, username, role, action, lock_sec, device_serial, device_ip))

                # 2. Update counter & login time di nfc_users PostgreSQL
                if user:
                    cur.execute("""
                        UPDATE nfc_users 
                        SET total_taps = total_taps + 1,
                            last_login_at = NOW()
                        WHERE UPPER(uid) = %s;
                    """, (raw_uid,))

                # 3. Update status kunci di device_locks PostgreSQL (penolakan kartu tidak merubah kunci)
                if not is_denied:
                    lock_val = 0 if is_unlocking else 1
                    lock_str = "UNLOCKED" if is_unlocking else "LOCKED"
                    cur.execute("""
                        INSERT INTO device_locks 
                            (device_serial, is_locked, lock_status, unlocked_by_uid, unlocked_by_name,
                             unlocked_by_username, unlocked_by_role, unlock_duration_sec,
                             unlock_expires_at, last_toggle_action, updated_at)
                        VALUES 
                            (%s, %s, %s, %s, %s, %s, %s, %s, NOW() + (interval '1 second' * %s), %s, NOW())
                        ON CONFLICT (device_serial) DO UPDATE
                        SET is_locked = EXCLUDED.is_locked,
                            lock_status = EXCLUDED.lock_status,
                            unlocked_by_uid = EXCLUDED.unlocked_by_uid,
                            unlocked_by_name = EXCLUDED.unlocked_by_name,
                            unlocked_by_username = EXCLUDED.unlocked_by_username,
                            unlocked_by_role = EXCLUDED.unlocked_by_role,
                            unlock_duration_sec = EXCLUDED.unlock_duration_sec,
                            unlock_expires_at = EXCLUDED.unlock_expires_at,
                            last_toggle_action = EXCLUDED.last_toggle_action,
                            updated_at = NOW();
                    """, (
                        device_serial,
                        lock_val,
                        lock_str,
                        raw_uid,
                        nama,
                        username,
                        role,
                        lock_sec,
                        lock_sec if is_unlocking else 0,
                        action,
                    ))

            return {
                "status": "success",
                "uid": raw_uid,
                "nama": nama,
                "role": role,
                "action": action,
                "is_locked": not is_unlocking,
                "database": "postgresql"
            }
        finally:
            conn.close()
