# 📘 Blueprint & Alur Komunikasi Antar-Project Homelab Server

Dokumen ini menjelaskan secara menyeluruh bagaimana seluruh modul, komponen perangkat keras (hardware), kontainer aplikasi, broker pesan, serta basis data (database) saling berkomunikasi dan bekerja sama di dalam ekosistem **Homelab Server (`fa` - 192.168.25.101 / Tailscale 100.106.63.90)**.

---

## 📑 Daftar Isi
1. [Filosofi Arsitektur & Prinsip Desain](#1-filosofi-arsitektur--prinsip-desain)
2. [Peta Topologi Seluruh Sistem (Master Map)](#2-peta-topologi-seluruh-sistem-master-map)
3. [Alur Komunikasi Mendalam (Step-by-Step Flow)](#3-alur-komunikasi-mendalam-step-by-step-flow)
   - [Flow 1: Tap Kartu NFC, Validasi Akses & Buzzer Feedback](#flow-1-tap-kartu-nfc-validasi-akses--buzzer-feedback)
   - [Flow 2: Pendaftaran User & Sinkronisasi Role dari Web ke ESP32](#flow-2-pendaftaran-user--sinkronisasi-role-dari-web-ke-esp32)
   - [Flow 3: Telemetri Sensor Suhu & Pipeline Monitoring Grafana](#flow-3-telemetri-sensor-suhu--pipeline-monitoring-grafana)
   - [Flow 4: Routing Domain Lokal (CoreDNS & Ingress Gateway)](#flow-4-routing-domain-lokal-coredns--ingress-gateway)
   - [Flow 5: Transaksi Kasir & Inventori Stock UMKM](#flow-5-transaksi-kasir--inventori-stock-umkm)
   - [Flow 6: Disaster Recovery & Engine Backup Otomatis](#flow-6-disaster-recovery--engine-backup-otomatis)
4. [Isolasi Database Mandiri (Database Partitioning)](#4-isolasi-database-mandiri-database-partitioning)
5. [Matriks Port, Jaringan & Protokol Komunikasi](#5-matriks-port-jaringan--protokol-komunikasi)
6. [Konfigurasi Hardware ESP32 & Modul KY-012](#6-konfigurasi-hardware-esp32--modul-ky-012)
7. [Panduan Diagnostik & Verifikasi Aliran Data](#7-panduan-diagnostik--verifikasi-aliran-data)

---

## 1. Filosofi Arsitektur & Prinsip Desain

Homelab server dibangun di atas tiga pilar utama:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   3 PILAR UTAMA HOMELAB SERVER                         │
├──────────────────────────┬─────────────────────────┬───────────────────┤
│ 1. ONE CENTRAL GATEWAY   │ 2. DEDICATED DATABASES  │ 3. ZERO CONTAINER │
│    Semua modul backend   │ Setiap proyek memiliki  │    DUPLICATION    │
│    (IoT, PSM, Stock,     │ database mandiri, tidak │ Menggunakan MySQL │
│    Backup) disatukan ke  │ dicampur ke dalam satu  │ host, Postgres,   │
│    PAP Core (:8000)      │ database raksasa        │ Mosquitto &       │
│    tanpa duplikasi code. │ (appdb dihapus).        │ Grafana eksisting.│
└──────────────────────────┴─────────────────────────┴───────────────────┘
```

---

## 2. Peta Topologi Seluruh Sistem (Master Map)

Diagram flowchart berikut menggambarkan keterkaitan fisik dan logika antar seluruh komponen:

```mermaid
flowchart TD
    subgraph Klien["💻 Perangkat Pengguna / Klien"]
        Browser["🌐 Web Browser (PC / Ponsel)"]
        Scanner["📱 Aplikasi POS Kasir UMKM"]
    end

    subgraph Hardware["⚡ Perangkat Keras Lapangan (Hardware)"]
        ESP32["📟 ESP32 Eternal (192.168.25.104)<br/>• Modul RC522 RFID/NFC<br/>• Sensor DHT11 Suhu/Hum<br/>• Solenoid Relay (GPIO 26)<br/>• Buzzer KY-012 (GPIO 25)"]
    end

    subgraph Networking["🌐 Jaringan & Ingress Router"]
        DNS["🧭 CoreDNS (:53)<br/>Resolve *.homelab & *.fa.local"]
        NginxRouter["🚪 Nginx Ingress Gateway (:80)<br/>Virtual Host Reverse Proxy"]
    end

    subgraph CoreGateway["🛡️ PAP Central API Gateway (:8000)"]
        API["⚙️ PAP Core Orchestrator<br/>• IoT Fleet & NFC Controller<br/>• PSM Control Plane Engine<br/>• Stock UMKM API Provider<br/>• Backup & Disaster Engine"]
        MissionControl["🖥️ Mission Control Web UI<br/>(http://192.168.25.101:8000)"]
    end

    subgraph Frontends["🖥️ Antarmuka Web Proyek"]
        HeatpressWeb["📟 HeatpressHub Web (:8088)<br/>iot.homelab"]
        PSMWeb["🎛️ PSM Console (:3005)<br/>psm.homelab"]
    end

    subgraph TelemetryPipeline["📊 Pipeline Telemetri & Visualisasi"]
        MQTT["📡 Mosquitto MQTT Broker (:1883)<br/>Topik: /SysCtrl, Eternal/#"]
        Telegraf["🔄 Telegraf Exporter (:9273)<br/>MQTT to Prometheus Parser"]
        Prometheus["📈 Prometheus Server (:9001)<br/>Metrics TSDB Scraper"]
        Grafana["📊 Grafana Utama (:3001)<br/>grafana.homelab"]
    end

    subgraph DatabaseServers["🗄️ Basis Data Terisolasi (Database Servers)"]
        subgraph MySQLServer["🐬 MySQL 8.4 Server (:3306)"]
            DB_Eternal["📦 eternal_db<br/>(nfc_users, device_locks,<br/>nfc_access_logs, iot_telemetry)"]
            DB_Stock["📦 stock_umkm<br/>(products, transactions,<br/>inventory_logs)"]
        end

        subgraph PostgresServer["🐘 PostgreSQL Server (:5432)"]
            DB_PAP["📦 pap_core<br/>(devices, backups, api_keys)"]
            DB_PSM["📦 psm<br/>(servers, containers, users)"]
        end
    end

    %% Relasi Navigasi & Jaringan
    Browser -->|1. Query Domain| DNS
    Browser -->|2. HTTP Request| NginxRouter
    NginxRouter -->|Route iot.homelab| HeatpressWeb
    NginxRouter -->|Route psm.homelab| PSMWeb
    NginxRouter -->|Route grafana.homelab| Grafana
    NginxRouter -->|Route /api/| API

    %% Relasi ESP32 Hardware
    ESP32 -->|MQTT Publish Telemetri| MQTT
    ESP32 -->|REST Live Verification| API
    API -->|Push User Baru ke RAM/NVS| ESP32

    %% Relasi Telemetri
    MQTT -->|Subscribe /SysCtrl| Telegraf
    Telegraf -->|Metrics Expose :9273| Prometheus
    Prometheus -->|PromQL Query| Grafana
    Grafana -->|Direct SQL Query| DB_Eternal

    %% Relasi Core API ke Frontend & DB
    HeatpressWeb -->|REST API Call| API
    PSMWeb -->|REST API Call| API
    Scanner -->|Order API| API
    MissionControl -->|Direct Loopback| API

    %% Relasi Database
    API -->|Read/Write NFC & IoT| DB_Eternal
    API -->|Read/Write POS Stock| DB_Stock
    API -->|Read/Write Core Data| DB_PAP
    API -->|Read/Write Server Data| DB_PSM
```

---

## 3. Alur Komunikasi Mendalam (Step-by-Step Flow)

### Flow 1: Tap Kartu NFC, Validasi Akses & Buzzer Feedback

Alur ini terjadi saat kartu fisik didekatkan ke modul RC522 pada ESP32:

```mermaid
sequenceDiagram
    autonumber
    actor User as Operator (Kartu NFC)
    participant HW as 📟 ESP32 (192.168.25.104)
    participant Buzzer as 🔊 Buzzer KY-012 (GPIO 25)
    participant Relay as 🔌 Relay Solenoid (GPIO 26)
    participant Core as 🛡️ PAP Core API (:8000)
    participant DB as 🐬 MySQL eternal_db (:3306)
    participant MQTT as 📡 Mosquitto Broker (:1883)
    participant Web as 📟 HeatpressHub Web (:8088)

    User->>HW: Tempel Kartu (UID: 058E208F87A200)
    HW->>HW: Cek Cache Memori Lokal (whitelistCards)
    
    alt Kartu Belum Ada di Memori Lokal (Fallback Live Sync)
        HW->>Core: GET /api/nfc/users/058E208F87A200
        Core->>DB: SELECT * FROM nfc_users WHERE uid = '058E208F87A200'
        DB-->>Core: Data User (Ferdiansyah, Role: Operator, is_active: 1)
        Core-->>HW: HTTP 200 OK (JSON Profil User)
        HW->>HW: Simpan User ke NVS Flash & RAM Lokal
    end

    alt Kartu Terdaftar & Aktif (GRANTED)
        HW->>Buzzer: Bip 1x Tegas (100ms)
        HW->>Relay: Set HIGH (Kunci Terbuka / UNLOCKED)
        HW->>HW: Set Timer Auto-Lock 2 Jam (7200 detik)
        HW->>MQTT: Publish /SysCtrl & /Eternal/rfid (status: granted)
        HW->>Core: POST /api/nfc/tap (Catat Audit Log)
        Core->>DB: INSERT INTO nfc_access_logs & UPDATE device_locks
        Core-->>Web: Live Event Update (Status: UNLOCKED by Ferdiansyah)
    else Kartu Tidak Dikenal / Ditolak (DENIED)
        HW->>Buzzer: Beeeep! Beeeep! 2x Panjang (220ms + 250ms)
        HW->>Relay: Tetap LOW (Terkunci / LOCKED)
        HW->>MQTT: Publish /SysCtrl (status: denied, action: NFC_DENIED)
        HW->>Core: POST /api/nfc/tap (Catat Akses Ilegal)
        Core->>DB: INSERT INTO nfc_access_logs (Guest, action: DENIED)
        Core-->>Web: Munculkan Banner Kuning: "Kartu Baru Terdeteksi - Daftarkan?"
    end
```

---

### Flow 2: Pendaftaran User & Sinkronisasi Role dari Web ke ESP32

Alur sinkronisasi dua arah saat supervisor atau admin mendaftarkan kartu di Web HeatpressHub:

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Supervisor / Admin
    participant Web as 📟 HeatpressHub Web (:8088)
    participant Core as 🛡️ PAP Core API (:8000)
    participant DB as 🐬 MySQL eternal_db (:3306)
    participant HW as 📟 ESP32 (192.168.25.104)

    Admin->>Web: Buka Menu "NFC Access & Roles"
    Admin->>Web: Klik "+ Daftarkan Kartu Ini" atau Isi Modal Form
    Note over Admin,Web: UID: 058E208F87A200, Nama: Ferdiansyah, Role: Operator
    Web->>Core: POST /api/nfc/users {uid, nama, username, role, pin}
    
    Core->>DB: INSERT INTO nfc_users ... ON DUPLICATE KEY UPDATE
    DB-->>Core: Query OK (ID User dibuat/diperbarui)
    
    Note over Core,HW: Sinkronisasi Otomatis Tanpa Perlu Restart Hardware
    Core->>HW: HTTP POST http://192.168.25.104/api/nfc/register_user
    HW->>HW: rfidRegisterOrUpdateUser() -> Tulis ke Flash NVS
    HW-->>Core: HTTP 200 OK (User Berhasil Disimpan ke RAM)
    
    Core-->>Web: HTTP 200 OK ("Pengguna NFC Berhasil Disimpan & Disinkronkan")
    Web->>Web: Refresh Tabel Pengguna NFC secara Realtime
```

---

### Flow 3: Telemetri Sensor Suhu & Pipeline Monitoring Grafana

Alur pembacaan data sensor suhu/kelembaban DHT11 dari fisik hingga grafik Grafana:

```mermaid
sequenceDiagram
    autonumber
    participant Sensor as 🌡️ Sensor DHT11 (GPIO 4)
    participant HW as 📟 ESP32 (192.168.25.104)
    participant MQTT as 📡 Mosquitto Broker (:1883)
    participant Telegraf as 🔄 Telegraf Container (:9273)
    participant Prometheus as 📈 Prometheus (:9001)
    participant DB as 🐬 MySQL eternal_db (:3306)
    participant Grafana as 📊 Grafana Utama (:3001)

    loop Setiap 5 Detik
        Sensor->>HW: Baca Data Suhu (misal 36.4°C) & Kelembaban (37%)
        HW->>MQTT: Publish JSON ke topik /SysCtrl & Eternal/SysCtrl
        HW->>DB: INSERT INTO iot_telemetry_logs (Riwayat Historis)
    end

    MQTT->>Telegraf: Forward Paket Pesan MQTT
    Telegraf->>Telegraf: Ekstraksi Tag: MCID, model, nama, suhu, humidity, lock_status
    Telegraf->>Telegraf: Expose Metrik OpenMetrics di http://iot-telegraf:9273/metrics

    loop Scrape Interval (10 Detik)
        Prometheus->>Telegraf: HTTP GET http://192.168.25.101:9273/metrics
        Telegraf-->>Prometheus: Time-series Metrics data
    end

    loop Dashboard Auto-Refresh (5 Detik)
        Grafana->>Prometheus: Query PromQL: sysctrl_suhu or eternal_iot_suhu
        Prometheus-->>Grafana: Nilai Suhu Realtime -> Panel Gauge Hijau
        Grafana->>DB: Query SQL: SELECT * FROM device_locks & nfc_access_logs
        DB-->>Grafana: Status Lock, Timer & Log Tap -> Panel Tabel & Stat
    end
```

---

### Flow 4: Routing Domain Lokal (CoreDNS & Ingress Gateway)

Alur resolusi domain lokal tanpa perlu mengetik nomor port yang rumit:

```mermaid
sequenceDiagram
    autonumber
    actor Client as Perangkat Klien (Laptop / HP)
    participant CoreDNS as 🧭 CoreDNS (:53)
    participant Router as 🚪 Nginx Ingress Router (:80)
    participant App as 📦 Kontainer Aplikasi Tujuan

    Client->>CoreDNS: DNS Query: Berapa IP dari "iot.homelab"?
    CoreDNS-->>Client: Jawaban: 192.168.25.101 (atau 100.106.63.90 jika via Tailscale)

    Client->>Router: HTTP GET http://iot.homelab:80/
    Router->>Router: Periksa Blok Virtual Host conf.d
    alt Domain iot.homelab
        Router->>App: Proxy Pass ke http://iot-web:80/ (Port Internal Kontainer)
    else Domain psm.homelab
        Router->>App: Proxy Pass ke http://psm-web:3000/
    else Domain grafana.homelab
        Router->>App: Proxy Pass ke http://host.docker.internal:3001/
    else Direct IP Path /iot/
        Router->>App: Proxy Pass ke http://iot-web:80/
    end
    App-->>Router: Konten HTML / CSS / JS / JSON
    Router-->>Client: Halaman Web Ditampilkan Mulus
```

---

### Flow 5: Transaksi Kasir & Inventori Stock UMKM

Pemisahan basis data menjamin transaksi kasir toko tidak terganggu oleh traffic data sensor IoT:

```mermaid
sequenceDiagram
    autonumber
    actor Kasir as Operator Kasir / Barcode Scanner
    participant POS as 📱 Aplikasi Kasir POS UMKM
    participant Core as 🛡️ PAP Core API (:8000)
    participant DBStock as 🐬 MySQL stock_umkm (:3306)

    Kasir->>POS: Scan Barcode Barang & Selesaikan Pembayaran
    POS->>Core: POST /api/v1/stock/transactions (Header: Bearer API_KEY)
    Core->>Core: Validasi Token & Sanitasi Input
    Core->>DBStock: BEGIN TRANSACTION
    Core->>DBStock: INSERT INTO orders (order_no, total_price, payment_method)
    Core->>DBStock: UPDATE inventory SET stock_qty = stock_qty - 1 WHERE item_code = 'XYZ'
    Core->>DBStock: COMMIT
    DBStock-->>Core: Transaksi Sukses
    Core-->>POS: HTTP 201 Created (Receipt No: #TRX-9921)
    POS-->>Kasir: Cetak Struk Belanja
```

---

### Flow 6: Disaster Recovery & Engine Backup Otomatis

Alur pencadangan data komprehensif untuk memastikan sistem aman dari kehilangan data:

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Admin Homelab / Cron Task
    participant Core as 🛡️ PAP Core API (:8000)
    participant MySQL as 🐬 MySQL Server (:3306)
    participant Postgres as 🐘 PostgreSQL Server (:5432)
    participant Storage as 📁 Volume /app/backups

    Admin->>Core: POST /api/v1/backups/create {scope: "all", note: "Auto-Daily"}
    Core->>Core: Buat direktori sementara /tmp/backup_timestamp/

    par Cadangkan PostgreSQL
        Core->>Postgres: pg_dump dbname=pap_core > pap_core.sql
        Core->>Postgres: pg_dump dbname=psm > psm.sql
    and Cadangkan MySQL
        Core->>MySQL: mysqldump database=eternal_db > eternal_db.sql
        Core->>MySQL: mysqldump database=stock_umkm > stock_umkm.sql
    and Cadangkan Konfigurasi
        Core->>Core: Copy docker-compose.yml, .env, Corefile, telegraf.conf
    end

    Core->>Core: Buat file manifest.json (Metadata SHA-256, ukuran, daftar DB)
    Core->>Core: Kompresi ke format tar.gz menggunakan gzip
    Core->>Storage: Pindahkan arsip ke /app/backups/homelab_all_timestamp.tar.gz
    Core-->>Admin: HTTP 200 OK ("Backup Sukses: Ukuran 14.2 MB, SHA256: 7f8a...")
```

---

## 4. Isolasi Database Mandiri (Database Partitioning)

Untuk memenuhi kepatuhan isolasi data, seluruh basis data dipisah secara tegas:

| Mesin Database | Nama Database | Hak Akses Pengguna | Digunakan Oleh Modul | Deskripsi Isi Tabel |
| :--- | :--- | :--- | :--- | :--- |
| **MySQL 8.4** | `eternal_db` | `appuser` / `admin12345` | Eternal IoT ESP32 & HeatpressHub | `nfc_users`, `nfc_access_logs`, `device_locks`, `iot_devices`, `iot_telemetry_logs` |
| **MySQL 8.4** | `stock_umkm` | `appuser` / `admin12345` | Aplikasi Kasir POS & Inventori UMKM | `products`, `categories`, `orders`, `stock_ledger`, `suppliers` |
| **PostgreSQL** | `pap_core` | `appuser` / `admin12345` | PAP Central API Gateway Core | `devices`, `projects`, `backups`, `api_tokens`, `system_settings` |
| **PostgreSQL** | `psm` | `appuser` / `admin12345` | Personal Server Manager | `psm_users`, `servers`, `monitored_containers`, `audit_events` |

> [!IMPORTANT]
> **Tidak ada lagi penggunaan `appdb` sebagai basis data sapu jagat**. Masing-masing aplikasi beroperasi pada ruang datanya sendiri, sehingga migrasi atau kegagalan satu modul tidak akan merusak modul lainnya.

---

## 5. Matriks Port, Jaringan & Protokol Komunikasi

| Port Host | Protokol | Komponen / Kontainer | Peran dalam Arsitektur | Klien yang Menghubungi |
| :--- | :--- | :--- | :--- | :--- |
| **`:53`** | DNS (UDP/TCP) | `homelab_dns` (CoreDNS) | Resolusi nama domain lokal | Seluruh PC/HP di jaringan LAN & Tailscale |
| **`:80`** | HTTP | `homelab_router` (Nginx) | Ingress Gateway Virtual Host | Web Browser Klien |
| **`:1883`** | MQTT (TCP) | Mosquitto (Host Daemon) | Broker pesan pub/sub telemetri | ESP32 Hardware & Telegraf |
| **`:3001`** | HTTP | Grafana Server (Host/Docker)| Visualisasi metrik & analitik | Web Browser Admin & Embed iFrame |
| **`:3005`** | HTTP | `psm-web` (Next.js) | Frontend GUI Server Manager | Web Browser Admin |
| **`:3306`** | MySQL | MySQL 8.4 Server (Host) | Penyimpanan IoT & POS Stock | PAP API, ESP32, DbGate, Grafana |
| **`:5432`** | PostgreSQL | PostgreSQL 16 (Host) | Penyimpanan Core Gateway & PSM | PAP API & PSM Engine |
| **`:8000`** | HTTP REST | `pap-api` (FastAPI) | Master Core API & Orchestrator | Web Frontend, ESP32, Script CLI |
| **`:8088`** | HTTP | `iot_dashboard_web` (Nginx) | Portal Web HeatpressHub Fleet | Web Browser Operator / Supervisor |
| **`:9001`** | HTTP | Prometheus (Docker) | Database metrik time-series | Grafana Server |
| **`:9273`** | HTTP | `iot_telegraf` | Exporter metrik MQTT | Prometheus Scraper |

---

## 6. Konfigurasi Hardware ESP32 & Modul KY-012

Hardware ESP32 Eternal menggunakan modul microcontroller LilyGo T-Display dengan tata letak pin berikut:

```
                      ESP32 ETERNAL (LilyGo T-Display)
                          ┌─────────────────────┐
                          │     ANTENNA WIFI    │
                          │   (192.168.25.104)  │
                          ├─────────────────────┤
   DHT11 Data Pin ◄───────┤ GPIO 4              │
     RC522 SS/SDA ◄───────┤ GPIO 5              │
        RC522 SCK ◄───────┤ GPIO 18             │
       RC522 MISO ◄───────┤ GPIO 19             │
       OLED I2C SDA ◄─────┤ GPIO 21             │
       OLED I2C SCL ◄─────┤ GPIO 22             │
       RC522 MOSI ◄───────┤ GPIO 23             │
   KY-012 Buzzer Signal ◄─┤ GPIO 25 (Active H)  │
   Relay Solenoid Lock ◄──┤ GPIO 26 (Active H)  │
        RC522 RST ◄───────┤ GPIO 27             │
    Tombol BOOT / Nav ◄───┤ GPIO 0              │
                          └─────────────────────┘
```

### Karakteristik Respon Nada Buzzer KY-012:
1. **Booting Sukses**: Bip 2x pendek (`80ms` & `120ms`) saat sistem siap dan terkoneksi ke WiFi.
2. **NFC Diterima (Granted)**: Bip 1x tegas (`100ms`) saat kunci terbuka atau tertutup oleh pengguna yang valid.
3. **NFC Ditolak (Denied)**: Beeep! Beeep! 2x panjang (`220ms` & `250ms`) saat kartu belum terdaftar di whitelist.

---

## 7. Panduan Diagnostik & Verifikasi Aliran Data

Jika Anda ingin memverifikasi bahwa seluruh alur di atas berjalan dengan sehat di server homelab (`fa@fa`), gunakan perintah-perintah berikut:

```bash
# 1. Audit status konektivitas seluruh layanan homelab
python3 homelab.py status

# 2. Cek status database eternal_db & tabel nfc_users
mysql -u appuser -padmin12345 -h 127.0.0.1 eternal_db -e "SELECT id, uid, nama, username, role, is_active FROM nfc_users;"

# 3. Cek live paket MQTT yang dipancarkan oleh ESP32
mosquitto_sub -h 127.0.0.1 -p 1883 -u iotuser -P 25022002 -t "/SysCtrl" -v

# 4. Tes API Gateway Core Healthcheck
curl -i http://127.0.0.1:8000/health

# 5. Uji Coba Cek User NFC langsung dari terminal
curl -i http://127.0.0.1:8000/api/nfc/users/058E208F87A200
```
