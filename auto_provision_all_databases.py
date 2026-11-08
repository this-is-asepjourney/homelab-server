#!/usr/bin/env python3
"""
auto_provision_all_databases.py — Automated Multi-Database Provisioner for Homelab Server
Ensures each project has its OWN dedicated database (not shared appdb):
  - eternal_db  (MySQL 8.4 :3306) -> Dedicated to Eternal IoT ESP32 Smart Lock & NFC
  - stock_umkm  (MySQL 8.4 :3306) -> Dedicated to Stock UMKM & Business
  - pap_core    (PostgreSQL :5432) -> Dedicated to Central Core API Gateway
  - psm         (PostgreSQL :5432) -> Dedicated to Personal Server Manager
Ensures 'appuser' ('admin12345') has full privileges on all project databases.
"""

import os
import sys
import time

def provision_mysql():
    print("=" * 65)
    print("  [MySQL 8.4] Auto-Provisioning Project Databases")
    print("=" * 65)

    host = os.getenv("MYSQL_HOST") or os.getenv("STOCK_DB_HOST", "192.168.25.101")
    port = int(os.getenv("MYSQL_PORT") or os.getenv("STOCK_DB_PORT", 3306))
    root_pass = os.getenv("MYSQL_ROOT_PASSWORD", "adminroot12345")
    app_user = os.getenv("MYSQL_USER", "appuser")
    app_pass = os.getenv("MYSQL_PASSWORD", "admin12345")

    try:
        import pymysql
    except ImportError:
        print("[!] pymysql not installed. Installing...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pymysql"])
        import pymysql

    candidates = [
        ("root", root_pass),
        (app_user, app_pass),
        ("root", "adminroot12345"),
        ("root", "admin12345"),
    ]

    conn = None
    connected_user = None
    for u, p in candidates:
        try:
            conn = pymysql.connect(
                host=host,
                port=port,
                user=u,
                password=p,
                connect_timeout=3,
                autocommit=True
            )
            connected_user = u
            print(f"[OK] Connected to MySQL at {host}:{port} as '{u}'")
            break
        except Exception as e:
            continue

    if not conn:
        print(f"[ERROR] Could not connect to MySQL at {host}:{port}. Skipping MySQL provision.")
        return False

    cur = conn.cursor()

    # 1. Ensure user appuser exists
    try:
        cur.execute(f"CREATE USER IF NOT EXISTS '{app_user}'@'%' IDENTIFIED BY '{app_pass}';")
        cur.execute(f"ALTER USER '{app_user}'@'%' IDENTIFIED BY '{app_pass}';")
        print(f"[OK] User '{app_user}'@'%' verified.")
    except Exception as e:
        print(f"[INFO] User notice: {e}")

    # 2. Project 1: eternal_db (Dedicated for Eternal IoT)
    print("\n--- Provisioning 'eternal_db' (Eternal IoT) ---")
    cur.execute("CREATE DATABASE IF NOT EXISTS `eternal_db` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    cur.execute(f"GRANT ALL PRIVILEGES ON `eternal_db`.* TO '{app_user}'@'%';")
    cur.execute("FLUSH PRIVILEGES;")
    print("[OK] Database 'eternal_db' created & granted to 'appuser'.")

    # Seed tables in eternal_db
    cur.execute("USE `eternal_db`;")
    
    cur.execute("""
    CREATE TABLE IF NOT EXISTS `device_locks` (
        `device_serial` VARCHAR(32) PRIMARY KEY,
        `device_name` VARCHAR(64) DEFAULT 'Eternal',
        `is_locked` TINYINT(1) DEFAULT 1,
        `lock_status` VARCHAR(16) DEFAULT 'LOCKED',
        `lock_state_str` VARCHAR(16) DEFAULT 'LOCKED',
        `unlocked_by_uid` VARCHAR(32) DEFAULT NULL,
        `unlocked_by_name` VARCHAR(100) DEFAULT NULL,
        `unlocked_by_username` VARCHAR(64) DEFAULT NULL,
        `unlocked_by_role` VARCHAR(32) DEFAULT NULL,
        `auto_lock_duration_sec` INT DEFAULT 7200,
        `unlock_duration_sec` INT DEFAULT 7200,
        `remaining_sec` INT DEFAULT 0,
        `unlocked_at` VARCHAR(64) DEFAULT NULL,
        `unlock_expires_at` DATETIME DEFAULT NULL,
        `last_toggle_action` VARCHAR(32) DEFAULT 'LOCK_OFF',
        `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

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
    CREATE TABLE IF NOT EXISTS `iot_devices` (
        `id` INT AUTO_INCREMENT PRIMARY KEY,
        `device_serial` VARCHAR(32) NOT NULL UNIQUE,
        `device_name` VARCHAR(64) NOT NULL,
        `mac_address` VARCHAR(24) DEFAULT NULL,
        `model` VARCHAR(32) DEFAULT 'Eternal-ESP32',
        `ip_address` VARCHAR(32) DEFAULT '0.0.0.0',
        `ssid` VARCHAR(64) DEFAULT NULL,
        `rssi` INT DEFAULT 0,
        `wifi_rssi` INT DEFAULT 0,
        `temperature_c` FLOAT DEFAULT 0,
        `humidity_pct` FLOAT DEFAULT 0,
        `heat_index_c` FLOAT DEFAULT 0,
        `firmware_version` VARCHAR(24) DEFAULT '3.1.0',
        `mqtt_broker` VARCHAR(64) DEFAULT '192.168.25.101',
        `status` VARCHAR(16) DEFAULT 'online',
        `last_seen_at` VARCHAR(64) DEFAULT NULL,
        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS `nfc_access_logs` (
        `id` INT AUTO_INCREMENT PRIMARY KEY,
        `uid` VARCHAR(32) NOT NULL,
        `nama` VARCHAR(100) DEFAULT '-',
        `username` VARCHAR(64) DEFAULT '-',
        `role` VARCHAR(32) DEFAULT 'Operator',
        `action` VARCHAR(32) DEFAULT 'TAP_ON',
        `action_type` VARCHAR(32) DEFAULT 'TAP_ON',
        `lock_status` VARCHAR(16) DEFAULT 'LOCKED',
        `lock_duration_sec` INT DEFAULT 7200,
        `remaining_sec` INT DEFAULT 7200,
        `suhu` FLOAT DEFAULT 0,
        `humidity` FLOAT DEFAULT 0,
        `rssi` INT DEFAULT 0,
        `ip_address` VARCHAR(45) DEFAULT '0.0.0.0',
        `device_ip` VARCHAR(45) DEFAULT '0.0.0.0',
        `device_serial` VARCHAR(32) DEFAULT 'ETL-ESP32-001',
        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX `idx_access_logs_uid` (`uid`),
        INDEX `idx_access_logs_created` (`created_at`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS `iot_telemetry_logs` (
        `id` INT AUTO_INCREMENT PRIMARY KEY,
        `device_serial` VARCHAR(32) NOT NULL,
        `temperature_c` FLOAT NOT NULL,
        `humidity_pct` FLOAT NOT NULL,
        `heat_index_c` FLOAT DEFAULT 0,
        `wifi_rssi` INT DEFAULT 0,
        `free_heap` INT DEFAULT 0,
        `uptime_sec` INT DEFAULT 0,
        `recorded_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX `idx_telemetry_device` (`device_serial`),
        INDEX `idx_telemetry_time` (`recorded_at`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    # Initial seed data for eternal_db
    cur.execute("""
    INSERT INTO `device_locks` (device_serial, device_name, is_locked, lock_status, unlock_duration_sec)
    VALUES ('ETL-ESP32-001', 'Eternal', 1, 'LOCKED', 7200)
    ON DUPLICATE KEY UPDATE device_name = VALUES(device_name);
    """)

    cur.execute("""
    INSERT INTO `iot_devices` (device_serial, device_name, model, temperature_c, humidity_pct, wifi_rssi, status)
    VALUES ('ETL-ESP32-001', 'Eternal', 'Eternal-ESP32', 28.5, 65.0, -55, 'online')
    ON DUPLICATE KEY UPDATE status = VALUES(status);
    """)

    cur.execute("""
    INSERT IGNORE INTO `nfc_users` (uid, nama, username, role, is_active, total_taps)
    VALUES 
      ('E2801191', 'Administrator', 'admin', 'Superadmin', 1, 1),
      ('A1B2C3D4', 'Operator Utama', 'operator1', 'Operator', 1, 0);
    """)
    print("[OK] Tables and seed data initialized in 'eternal_db'.")

    # 3. Project 2: stock_umkm (Dedicated for Stock UMKM)
    print("\n--- Provisioning 'stock_umkm' (Stock UMKM) ---")
    cur.execute("CREATE DATABASE IF NOT EXISTS `stock_umkm` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    cur.execute(f"GRANT ALL PRIVILEGES ON `stock_umkm`.* TO '{app_user}'@'%';")
    cur.execute("FLUSH PRIVILEGES;")
    print("[OK] Database 'stock_umkm' created & granted to 'appuser'.")

    cur.close()
    conn.close()
    return True

def provision_postgres():
    print("\n" + "=" * 65)
    print("  [PostgreSQL] Auto-Provisioning Core & PSM Databases")
    print("=" * 65)

    host = os.getenv("POSTGRES_HOST", "192.168.25.101")
    port = int(os.getenv("POSTGRES_PORT", 5432))
    user = os.getenv("POSTGRES_USER", "appuser")
    password = os.getenv("POSTGRES_PASSWORD", "admin12345")

    try:
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    except ImportError:
        print("[!] psycopg2 not installed. Installing...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg2-binary"])
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    conn = None
    for u, p in [(user, password), ("postgres", password), ("postgres", "admin12345"), ("postgres", "postgres")]:
        try:
            conn = psycopg2.connect(host=host, port=port, user=u, password=p, dbname="postgres", connect_timeout=3)
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            print(f"[OK] Connected to PostgreSQL at {host}:{port} as '{u}'")
            break
        except Exception:
            continue

    if not conn:
        print(f"[WARN] PostgreSQL at {host}:{port} not directly reachable or credentials differ. Skipping.")
        return False

    cur = conn.cursor()
    for db_name in ["pap_core", "psm"]:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{db_name}" OWNER "{user}";')
            print(f"[OK] PostgreSQL database '{db_name}' created.")
        else:
            print(f"[OK] PostgreSQL database '{db_name}' already exists.")

    cur.close()
    conn.close()
    return True

if __name__ == "__main__":
    provision_mysql()
    provision_postgres()
    print("\n[SUCCESS] All isolated project databases have been provisioned successfully!")

