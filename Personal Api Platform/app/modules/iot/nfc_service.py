"""
nfc_service.py — NFC Identity, Roles, Whitelist & Access Logs Management
Connects directly to MySQL 8.4 database `eternal_db` (:3306).
Provides methods for HeatpressHub web dashboard to manage NFC users, roles, and tap logs.
"""

from datetime import datetime, timezone
import os
from typing import Any, Dict, List, Optional
import pymysql


def get_eternal_mysql_conn():
    """Connect to MySQL `eternal_db` with appuser and root fallback."""
    host = os.getenv("MYSQL_HOST") or os.getenv("STOCK_DB_HOST", "192.168.25.101")
    port = int(os.getenv("MYSQL_PORT") or os.getenv("STOCK_DB_PORT", 3306))
    app_user = os.getenv("MYSQL_USER", "appuser")
    app_pass = os.getenv("MYSQL_PASSWORD", "admin12345")
    root_pass = os.getenv("MYSQL_ROOT_PASSWORD", "adminroot12345")
    db_name = "eternal_db"

    candidates = [
        (app_user, app_pass),
        ("root", root_pass),
        ("root", "adminroot12345"),
        ("root", "admin12345"),
    ]

    last_err = None
    for u, p in candidates:
        try:
            conn = pymysql.connect(
                host=host,
                port=port,
                user=u,
                password=p,
                database=db_name,
                connect_timeout=3,
                autocommit=True,
                cursorclass=pymysql.cursors.DictCursor,
            )
            return conn
        except Exception as e:
            last_err = e
            # Try connecting without db to create it if missing
            try:
                raw_conn = pymysql.connect(
                    host=host,
                    port=port,
                    user=u,
                    password=p,
                    connect_timeout=2,
                    autocommit=True,
                )
                with raw_conn.cursor() as cur:
                    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
                    cur.execute(f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{app_user}'@'%';")
                    cur.execute("FLUSH PRIVILEGES;")
                raw_conn.close()
                # Retry connection to db
                conn = pymysql.connect(
                    host=host,
                    port=port,
                    user=u,
                    password=p,
                    database=db_name,
                    connect_timeout=3,
                    autocommit=True,
                    cursorclass=pymysql.cursors.DictCursor,
                )
                _ensure_tables(conn)
                return conn
            except Exception:
                continue

    raise RuntimeError(f"Could not connect to MySQL 'eternal_db': {last_err}")


def _ensure_tables(conn):
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS `nfc_users` (
            `id` INT AUTO_INCREMENT PRIMARY KEY,
            `uid` VARCHAR(32) NOT NULL UNIQUE,
            `nama` VARCHAR(100) NOT NULL,
            `username` VARCHAR(64) NOT NULL,
            `role` VARCHAR(32) DEFAULT 'Operator',
            `pin` VARCHAR(16) DEFAULT '',
            `is_active` TINYINT(1) DEFAULT 1,
            `device_serial` VARCHAR(32) DEFAULT 'ETL-ESP32-001',
            `total_taps` INT DEFAULT 0,
            `created_at` VARCHAR(64) DEFAULT NULL,
            `last_login_at` VARCHAR(64) DEFAULT NULL,
            INDEX `idx_nfc_users_username` (`username`),
            INDEX `idx_nfc_users_active` (`is_active`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS `nfc_access_logs` (
            `id` INT AUTO_INCREMENT PRIMARY KEY,
            `uid` VARCHAR(32) NOT NULL,
            `nama` VARCHAR(100) DEFAULT '-',
            `username` VARCHAR(64) DEFAULT '-',
            `role` VARCHAR(32) DEFAULT 'Operator',
            `action_type` VARCHAR(32) NOT NULL,
            `lock_duration_sec` INT DEFAULT 7200,
            `device_serial` VARCHAR(32) DEFAULT 'ETL-ESP32-001',
            `device_ip` VARCHAR(32) DEFAULT '0.0.0.0',
            `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX `idx_access_logs_uid` (`uid`),
            INDEX `idx_access_logs_created` (`created_at`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS `device_locks` (
            `device_serial` VARCHAR(32) PRIMARY KEY,
            `device_name` VARCHAR(64) DEFAULT 'Eternal',
            `is_locked` TINYINT(1) DEFAULT 1,
            `lock_status` VARCHAR(16) DEFAULT 'LOCKED',
            `unlocked_by_uid` VARCHAR(32) DEFAULT NULL,
            `unlocked_by_name` VARCHAR(100) DEFAULT NULL,
            `unlocked_by_username` VARCHAR(64) DEFAULT NULL,
            `unlocked_by_role` VARCHAR(32) DEFAULT NULL,
            `unlock_duration_sec` INT DEFAULT 7200,
            `unlocked_at` VARCHAR(64) DEFAULT NULL,
            `unlock_expires_at` DATETIME DEFAULT NULL,
            `last_toggle_action` VARCHAR(32) DEFAULT 'LOCK_OFF',
            `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)


class NfcService:
    @staticmethod
    def list_users() -> List[Dict[str, Any]]:
        conn = get_eternal_mysql_conn()
        try:
            _ensure_tables(conn)
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, uid, nama, username, role, pin, is_active, device_serial,
                           total_taps, created_at, last_login_at
                    FROM nfc_users
                    ORDER BY id ASC;
                """)
                return cur.fetchall() or []
        finally:
            conn.close()

    @staticmethod
    def get_user_by_uid(uid: str) -> Optional[Dict[str, Any]]:
        clean_uid = uid.strip().upper().replace(" ", "").replace(":", "")
        conn = get_eternal_mysql_conn()
        try:
            _ensure_tables(conn)
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM nfc_users WHERE UPPER(uid) = %s LIMIT 1;", (clean_uid,))
                return cur.fetchone()
        finally:
            conn.close()

    @staticmethod
    def save_user(data: Dict[str, Any]) -> Dict[str, Any]:
        raw_uid = data.get("uid", "").strip().upper().replace(" ", "").replace(":", "")
        if not raw_uid:
            raise ValueError("UID NFC wajib diisi")

        nama = data.get("nama", "").strip() or "Pengguna NFC"
        username = data.get("username", "").strip() or f"user_{raw_uid[-4:].lower()}"
        role = data.get("role", "Operator").strip()
        pin = data.get("pin", "").strip()
        is_active = 1 if data.get("is_active", True) in (1, True, "1", "true") else 0
        device_serial = data.get("device_serial", "ETL-ESP32-001")
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        conn = get_eternal_mysql_conn()
        try:
            _ensure_tables(conn)
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO nfc_users (uid, nama, username, role, pin, is_active, device_serial, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        nama = VALUES(nama),
                        username = VALUES(username),
                        role = VALUES(role),
                        pin = VALUES(pin),
                        is_active = VALUES(is_active),
                        device_serial = VALUES(device_serial);
                """, (raw_uid, nama, username, role, pin, is_active, device_serial, now_str))
            saved_user = NfcService.get_user_by_uid(raw_uid) or {"uid": raw_uid, "status": "saved"}

            # Auto-push ke ESP32 hardware (192.168.25.104) agar langsung aktif tanpa restart alat
            NfcService.push_to_device(saved_user)
            return saved_user
        finally:
            conn.close()

    @staticmethod
    def push_to_device(user: Dict[str, Any]):
        """Kirim profil user NFC langsung ke memori RAM/NVS ESP32 agar langsung GRANTED."""
        import json
        import urllib.request
        target_ips = ["192.168.25.104"]
        for ip in target_ips:
            try:
                payload = json.dumps({
                    "uid": user.get("uid"),
                    "nama": user.get("nama"),
                    "username": user.get("username"),
                    "role": user.get("role", "Operator"),
                    "pin": user.get("pin", "")
                }).encode("utf-8")
                req = urllib.request.Request(
                    f"http://{ip}/api/nfc/register_user",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=1.5):
                    pass
            except Exception:
                pass

    @staticmethod
    def delete_user(uid: str) -> bool:
        clean_uid = uid.strip().upper().replace(" ", "").replace(":", "")
        conn = get_eternal_mysql_conn()
        try:
            _ensure_tables(conn)
            with conn.cursor() as cur:
                affected = cur.execute("DELETE FROM nfc_users WHERE UPPER(uid) = %s;", (clean_uid,))
            
            # Hapus juga dari hardware ESP32
            import json
            import urllib.request
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
        conn = get_eternal_mysql_conn()
        try:
            _ensure_tables(conn)
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, uid, nama, username, role, action_type, lock_duration_sec,
                           device_serial, device_ip,
                           DATE_FORMAT(created_at, '%%Y-%%m-%%d %%H:%%i:%%s') AS created_at
                    FROM nfc_access_logs
                    ORDER BY id DESC
                    LIMIT %s;
                """, (limit,))
                return cur.fetchall() or []
        finally:
            conn.close()

    @staticmethod
    def get_latest_tap() -> Optional[Dict[str, Any]]:
        conn = get_eternal_mysql_conn()
        try:
            _ensure_tables(conn)
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, uid, nama, username, role, action_type, lock_duration_sec,
                           device_serial, device_ip,
                           DATE_FORMAT(created_at, '%%Y-%%m-%%d %%H:%%i:%%s') AS created_at
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
        action = payload.get("action_type") or payload.get("action") or "TAP_ON"
        device_serial = payload.get("device_serial", "ETL-ESP32-001")
        device_ip = payload.get("device_ip", "0.0.0.0")
        lock_sec = int(payload.get("lock_duration_sec", 7200))

        conn = get_eternal_mysql_conn()
        try:
            _ensure_tables(conn)
            with conn.cursor() as cur:
                # 1. Log event
                cur.execute("""
                    INSERT INTO nfc_access_logs (uid, nama, username, role, action_type, lock_duration_sec, device_serial, device_ip)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """, (raw_uid, nama, username, role, action, lock_sec, device_serial, device_ip))

                # 2. Update user stats if registered
                if user:
                    cur.execute("""
                        UPDATE nfc_users 
                        SET total_taps = total_taps + 1,
                            last_login_at = NOW()
                        WHERE UPPER(uid) = %s;
                    """, (raw_uid,))

                # 3. Update device lock status (Toggle ON/OFF)
                is_unlocking = "ON" in action.upper() or "UNLOCK" in action.upper()
                cur.execute("""
                    INSERT INTO device_locks 
                        (device_serial, is_locked, lock_status, unlocked_by_uid, unlocked_by_name,
                         unlocked_by_username, unlocked_by_role, unlock_duration_sec, unlock_expires_at, last_toggle_action)
                    VALUES 
                        (%s, %s, %s, %s, %s, %s, %s, %s, DATE_ADD(NOW(), INTERVAL %s SECOND), %s)
                    ON DUPLICATE KEY UPDATE
                        is_locked = VALUES(is_locked),
                        lock_status = VALUES(lock_status),
                        unlocked_by_uid = VALUES(unlocked_by_uid),
                        unlocked_by_name = VALUES(unlocked_by_name),
                        unlocked_by_username = VALUES(unlocked_by_username),
                        unlocked_by_role = VALUES(unlocked_by_role),
                        unlock_duration_sec = VALUES(unlock_duration_sec),
                        unlock_expires_at = VALUES(unlock_expires_at),
                        last_toggle_action = VALUES(last_toggle_action);
                """, (
                    device_serial,
                    0 if is_unlocking else 1,
                    "UNLOCKED" if is_unlocking else "LOCKED",
                    raw_uid,
                    nama,
                    username,
                    role,
                    lock_sec,
                    lock_sec if is_unlocking else 0,
                    action,
                ))

            # Auto-record NFC event to InfluxDB time-series database
            try:
                from app.services.influxdb_service import influx_service
                influx_service.write_nfc_event(
                    uid=raw_uid,
                    user_name=nama,
                    username=username,
                    role=role,
                    action=action,
                    device_serial=device_serial,
                    duration_sec=lock_sec,
                    status="granted" if user else "denied"
                )
            except Exception:
                pass

            return {
                "status": "success",
                "uid": raw_uid,
                "nama": nama,
                "role": role,
                "action": action,
                "is_locked": not is_unlocking,
            }
        finally:
            conn.close()

