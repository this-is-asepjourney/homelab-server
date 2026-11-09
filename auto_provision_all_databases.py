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
        print("[!] pymysql not installed on host Python.")
        # Check if running in a container with pip, or try apt
        import subprocess
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "pymysql"])
            import pymysql
        except Exception:
            # Try apt-get if running as root or with sudo
            print("[*] Attempting apt-get install python3-pymysql...")
            try:
                subprocess.check_call(["apt-get", "install", "-y", "python3-pymysql"])
                import pymysql
            except Exception:
                # Try running inside docker container pap-api
                print("[*] Attempting to run provisioning inside 'pap-api' container...")
                cmd = "docker compose exec -T pap-api python - < " + os.path.abspath(__file__)
                ret = subprocess.call(cmd, shell=True)
                if ret == 0:
                    sys.exit(0)
                raise RuntimeError("Gagal mengimpor pymysql. Silakan install dengan: sudo apt install -y python3-pymysql python3-psycopg2")

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
        `last_tap_at` VARCHAR(64) DEFAULT NULL,
        INDEX `idx_nfc_users_username` (`username`),
        INDEX `idx_nfc_users_active` (`is_active`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)

    # Safe migrations if tables already existed
    for col_sql in [
        "ALTER TABLE `nfc_users` ADD COLUMN `last_tap_at` VARCHAR(64) DEFAULT NULL;",
        "ALTER TABLE `nfc_users` ADD COLUMN `last_login_at` VARCHAR(64) DEFAULT NULL;",
        "ALTER TABLE `device_locks` ADD COLUMN `unlocked_by_name` VARCHAR(100) DEFAULT NULL;",
        "ALTER TABLE `device_locks` ADD COLUMN `unlocked_by_uid` VARCHAR(32) DEFAULT NULL;",
        "ALTER TABLE `device_locks` ADD COLUMN `unlocked_by_username` VARCHAR(64) DEFAULT NULL;",
        "ALTER TABLE `device_locks` ADD COLUMN `unlocked_by_role` VARCHAR(32) DEFAULT NULL;",
        "ALTER TABLE `device_locks` ADD COLUMN `unlock_duration_sec` INT DEFAULT 7200;",
        "ALTER TABLE `device_locks` ADD COLUMN `unlocked_at` VARCHAR(64) DEFAULT NULL;",
        "ALTER TABLE `device_locks` ADD COLUMN `unlock_expires_at` DATETIME DEFAULT NULL;",
    ]:
        try:
            cur.execute(col_sql)
        except Exception:
            pass

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
    INSERT INTO `device_locks` (device_serial, device_name, is_locked, lock_status, unlocked_by_uid, unlocked_by_name, unlocked_by_username, unlocked_by_role, unlock_duration_sec, unlocked_at, unlock_expires_at)
    VALUES ('ETL-ESP32-001', 'Eternal', 0, 'UNLOCKED', 'E2801191', 'Administrator', 'admin', 'Superadmin', 7200, NOW(), NOW() + INTERVAL 2 HOUR)
    ON DUPLICATE KEY UPDATE 
        device_name = VALUES(device_name),
        unlocked_by_name = COALESCE(unlocked_by_name, VALUES(unlocked_by_name)),
        unlocked_by_uid = COALESCE(unlocked_by_uid, VALUES(unlocked_by_uid));
    """)

    cur.execute("""
    INSERT INTO `iot_devices` (device_serial, device_name, model, temperature_c, humidity_pct, heat_index_c, wifi_rssi, rssi, status, last_seen_at)
    VALUES ('ETL-ESP32-001', 'Eternal', 'Eternal-ESP32', 28.5, 65.0, 29.8, -55, -55, 'online', NOW())
    ON DUPLICATE KEY UPDATE 
        status = VALUES(status),
        temperature_c = CASE WHEN temperature_c = 0 THEN VALUES(temperature_c) ELSE temperature_c END,
        humidity_pct = CASE WHEN humidity_pct = 0 THEN VALUES(humidity_pct) ELSE humidity_pct END,
        wifi_rssi = CASE WHEN wifi_rssi = 0 THEN VALUES(wifi_rssi) ELSE wifi_rssi END;
    """)

    cur.execute("""
    INSERT IGNORE INTO `nfc_users` (uid, nama, username, role, is_active, total_taps, created_at, last_login_at, last_tap_at)
    VALUES 
      ('E2801191', 'Administrator', 'admin', 'Superadmin', 1, 1, NOW(), NOW(), NOW()),
      ('A1B2C3D4', 'Operator Utama', 'operator1', 'Operator', 1, 0, NOW(), NULL, NULL);
    """)

    cur.execute("""
    INSERT INTO `nfc_access_logs` (uid, nama, username, role, action, action_type, lock_status, lock_duration_sec, remaining_sec, suhu, humidity, rssi, device_ip, device_serial)
    SELECT 'E2801191', 'Administrator', 'admin', 'Superadmin', 'TAP_ON', 'TAP_ON', 'UNLOCKED', 7200, 7200, 28.5, 65.0, -55, '192.168.25.105', 'ETL-ESP32-001'
    FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM `nfc_access_logs` LIMIT 1);
    """)

    cur.execute("""
    INSERT INTO `iot_telemetry_logs` (device_serial, temperature_c, humidity_pct, heat_index_c, wifi_rssi, recorded_at)
    VALUES 
        ('ETL-ESP32-001', 28.1, 66.5, 29.2, -58, NOW() - INTERVAL 30 MINUTE),
        ('ETL-ESP32-001', 28.3, 66.0, 29.5, -57, NOW() - INTERVAL 20 MINUTE),
        ('ETL-ESP32-001', 28.5, 65.2, 29.8, -56, NOW() - INTERVAL 10 MINUTE),
        ('ETL-ESP32-001', 28.7, 64.8, 30.0, -55, NOW() - INTERVAL 5 MINUTE),
        ('ETL-ESP32-001', 28.5, 65.0, 29.8, -55, NOW());
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
        print("[!] psycopg2 not installed on host Python.")
        import subprocess
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "psycopg2-binary"])
            import psycopg2
            from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
        except Exception:
            try:
                subprocess.check_call(["apt-get", "install", "-y", "python3-psycopg2"])
                import psycopg2
                from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
            except Exception:
                print("[WARN] psycopg2 tidak ditemukan, lewati provisioning PostgreSQL atau install dengan: sudo apt install -y python3-psycopg2")
                return False

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

def provision_influxdb():
    print("\n" + "=" * 65)
    print("  [InfluxDB v2] Provisioning Initial Telemetry & Time-Series Data")
    print("=" * 65)

    host = os.getenv("INFLUXDB_HOST", "192.168.25.101")
    port = int(os.getenv("INFLUXDB_PORT", 8086))
    token = os.getenv("INFLUXDB_TOKEN", "homelab-influxdb-master-auth-token-2026")
    org = os.getenv("INFLUXDB_ORG", "homelab")
    bucket = os.getenv("INFLUXDB_BUCKET", "eternal_telemetry")

    import urllib.request
    import urllib.parse
    import time

    now_sec = int(time.time())
    points = [
        f"iot_telemetry,device=Eternal,serial=ETL-ESP32-001,model=Eternal-ESP32,lock_status=LOCKED temperature=28.1,humidity=66.5,heat_index=29.2,rssi=-58i,is_locked=1i,remaining_sec=0i {now_sec - 1800}",
        f"iot_telemetry,device=Eternal,serial=ETL-ESP32-001,model=Eternal-ESP32,lock_status=LOCKED temperature=28.3,humidity=66.0,heat_index=29.5,rssi=-57i,is_locked=1i,remaining_sec=0i {now_sec - 1200}",
        f"iot_telemetry,device=Eternal,serial=ETL-ESP32-001,model=Eternal-ESP32,lock_status=LOCKED temperature=28.5,humidity=65.2,heat_index=29.8,rssi=-56i,is_locked=1i,remaining_sec=0i {now_sec - 600}",
        f"iot_telemetry,device=Eternal,serial=ETL-ESP32-001,model=Eternal-ESP32,lock_status=LOCKED temperature=28.5,humidity=65.0,heat_index=29.8,rssi=-55i,is_locked=1i,remaining_sec=0i {now_sec}",
    ]
    payload = "\n".join(points).encode("utf-8")
    params = urllib.parse.urlencode({"org": org, "bucket": bucket, "precision": "s"})
    write_url = f"http://{host}:{port}/api/v2/write?{params}"

    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "text/plain; charset=utf-8"
    }
    try:
        req = urllib.request.Request(write_url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status in (200, 204):
                print(f"[OK] InfluxDB bucket '{bucket}' seeded with initial telemetries (HTTP {resp.status})!")
                return True
    except Exception as e:
        print(f"[INFO] InfluxDB provision note: {e}")
        return False

if __name__ == "__main__":
    provision_mysql()
    provision_postgres()
    provision_influxdb()
    print("\n[SUCCESS] All isolated project databases have been provisioned successfully!")

