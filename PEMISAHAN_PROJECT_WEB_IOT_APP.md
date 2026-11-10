# Pemisahan Arsitektur: WEB vs IOT vs APP

Dokumen ini mendefinisikan pemisahan modular (*separation of concerns*) yang tegas dan rapi antara domain **WEB**, **IOT**, **APP (PAP Core)**, dan **BUSINESS (UMKM)** di ekosistem Homelab Server.

---

## 1. Diagram Pemisahan Layer (High-Level Architecture)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. [WEB LAYER] — User Interface & Dashboards                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  • Mission Control & PSM Web      : http://192.168.25.101:3005              │
│  • Grafana Realtime Monitoring   : http://192.168.25.101:3001              │
│  • Armada Heatpress Fleet Web    : http://192.168.25.101:8088              │
│  • POS Cashier Web UI            : http://192.168.25.101:3000              │
│  • Ingress Gateway (Nginx)       : http://192.168.25.101:80 (CoreDNS :53)  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│ 2. [APP LAYER] — Central Core Gateway & Decoupled Engine                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  • PAP Core API Gateway (:8000)   : Single Entrypoint Backend Platform      │
│  • Decoupled Worker (pap-worker)  : IoT Watchdog, Auto-Backup, Maintenance  │
│  • PostgreSQL Databases (:5432)   : `psm` (infra), `pap_core` (identity)    │
└───────────────────▲───────────────────────────────────────▲─────────────────┘
                    │                                       │
┌───────────────────┴─────────────────┐   ┌─────────────────┴─────────────────┐
│ 3. [IOT LAYER] — Hardware & TSDB   │   │ 4. [BUSINESS / UMKM LAYER]        │
├─────────────────────────────────────┤   ├───────────────────────────────────┤
│ • Edge ESP32: Eternal Smart Lock    │   │ • POS Cashier Service             │
│ • Armada Heatpress (HPM55, AF450)   │   │ • Inventory & Transaksi           │
│ • Mosquitto Broker: :1883           │   │ • Database MySQL: `stock_umkm`    │
│ • Telegraf Telemetry: :9273         │   │   (:3306, port mandiri)           │
│ • InfluxDB v2 TSDB: :8086           │   │                                   │
│ • MySQL IoT Database: `eternal_db`  │   │                                   │
└─────────────────────────────────────┘   └───────────────────────────────────┘
```

---

## 2. Rincian Pemisahan Per Layer

### A. [IOT LAYER] — Edge Hardware, Sensor & Streaming
Domain ini mengurus hardware fisik, telemetri frekuensi tinggi, kunci solenoid, dan kartu RFID/NFC.
* **Firmware Edge**: `eternal` (ESP32 LilyGo T-Display).
* **Komunikasi Telemetri**: Mosquitto MQTT (`192.168.25.101:1883`).
  - Topik: `/SysCtrl`, `Eternal/SysCtrl`, `/Eternal/telemetry`, `/Eternal/lock`, `/Eternal/rfid`.
* **API Gateway yang Dituju**: **PAP Core API Gateway** (`http://192.168.25.101:8000/api`).
  > **PENTING**: IoT **TIDAK LAGI** mengacu pada "STOCK_UMKM_API". Seluruh registrasi NFC, handshake perangkat, dan audit log mengalir ke **PAP Core API**.
* **Database IoT**:
  1. **InfluxDB v2 (:8086)**: Bucket `eternal_telemetry` untuk metrik time-series (suhu, kelembapan, heat index, RSSI, status relay, tap NFC).
  2. **MySQL (:3306)**: Database `eternal_db` untuk state snapshot tabel `iot_devices`, `device_locks`, `nfc_users`, dan `nfc_access_logs`.

---

### B. [APP LAYER] — PAP Core Gateway & Background Engine
Domain ini adalah otak pusat integrasi platform homelab.
* **Service**: `pap-api` (Port `8000`).
  - Routing terpadu: `/api/v1/*`, `/api/nfc/*`, `/api/devices/*`.
  - Mengelola autentikasi inter-service, API keys, dan WebSocket streaming `/api/v1/traffic/ws`.
* **Decoupled Worker Engine**: `pap-worker`
  - Mengonsumsi pesan MQTT telemetri secara asinkron tanpa membebani gateway HTTP.
  - Menjalankan *Dead Man's Snitch Watchdog* (deteksi perangkat offline >90s).
  - Melakukan relay sinkronisasi whitelist kartu NFC dari MySQL ke MQTT broker setiap 5 menit.
  - Melakukan auto-backup disaster recovery database dan pruning retensi backup 7 hari.
  - Melakukan maintenance pruning log telemetri mentah MySQL >14 hari.
* **Database Platform**: PostgreSQL (:5432) database `pap_core` dan `psm`.

---

### C. [WEB LAYER] — Frontend Portals & Monitoring
Domain ini adalah antarmuka visual pengguna dan operator.
* **Mission Control (PSM Web)**: Port `3005` (Next.js dashboard server manajemen).
* **Grafana Monitoring**: Port `3001` (Visualisasi metrik realtime InfluxDB + MySQL).
* **Armada Heatpress Web Dashboard**: Port `8088` (Monitoring mesin cetak & IoT hub).
* **Nginx Ingress Router**: Port `80` / `443` (Reverse proxy dan SSL termination).

---

### D. [BUSINESS / UMKM LAYER] — POS & Transaksi Bisnis
Domain bisnis terisolasi murni untuk keperluan operasional kasir & penjualan.
* **Layanan**: Aplikasi Kasir POS & Inventori.
* **Database**: MySQL 8.4 database `stock_umkm` (:3306).
* **Webhook Event**: Terhubung ke PAP Core API melalui modul integrasi (`/api/v1/integrations/*`).

---

## 3. Matriks Perubahan Naming Modul & Variabel

| Modul Lama | Penamaan Baru (Standar Homelab) | Domain | Keterangan |
|---|---|---|---|
| `STOCK_UMKM_API_URL` (di IoT) | **`PAP_CORE_API_URL`** | **IOT ➔ APP** | ESP32 mengarah langsung ke Gateway Port 8000 |
| `STOCK_UMKM_API_KEY` (di IoT) | **`PAP_CORE_API_KEY`** | **IOT ➔ APP** | API Key otentikasi hardware ke PAP Core |
| `[UMKM-API]` (Log Serial ESP32) | **`[PAP-API]`** | **IOT** | Prefix log serial rapi dan tepat |
| `Staff Stock UMKM` (Role NFC) | **`Supervisor` / `Operator` / `Teknisi`** | **IOT** | Role realistis untuk smart lock |
| `STOCK_DB_*` (di IoT) | **`ETERNAL_DB_*`** | **IOT** | Database khusus IoT (`eternal_db`) |
| `stock_umkm` (Database) | **`stock_umkm`** | **BUSINESS** | Tetap terisolasi khusus untuk bisnis POS |
| `pap-api` | **PAP Core API Platform** | **APP** | Central API Gateway homelab |
| `psm-web` | **Mission Control / PSM Web** | **WEB** | Dashboard manajemen homelab |
