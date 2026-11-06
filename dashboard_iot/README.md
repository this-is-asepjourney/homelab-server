# IoT Dashboard — Heat Press Monitoring System

Platform monitoring IoT berbasis Docker untuk memantau mesin heat press secara real-time. Data dari perangkat ESP32/MC dikirim melalui MQTT, diproses oleh Telegraf, disimpan di Prometheus, divisualisasikan di Grafana, dan dikelola melalui Web Dashboard buatan sendiri.

---

## Arsitektur Sistem

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PERANGKAT IoT                                │
│   [ESP32 / MC Heat Press]  ──── MQTT ──────────────────────────►   │
│         (MAC Address sebagai ID unik)        Broker: 10.109.25.97  │
└──────────────────────────────────────────────────────┬──────────────┘
                                                       │
                                                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     DOCKER COMPOSE STACK                            │
│                                                                     │
│   [Telegraf] ──subscribe──► [MQTT Broker]                           │
│       │  Parse JSON, buat tag MAC/MCID                              │
│       │  Expose metrics di :9273                                    │
│       ▼                                                             │
│   [Prometheus] ──scrape──► telegraf:9273                            │
│       │  Simpan time-series metrics                                 │
│       │  Expose di :9090                                            │
│       ▼                                                             │
│   [Grafana] ──query──► Prometheus                                   │
│       │  Dashboard real-time per device (filter by $mac)            │
│       │  Port Standalone: :3003 (Direct) atau :8088/grafana/         │
│       │  Atau terintegrasi ke Grafana Homelab Eksisting (:3001)     │
│       │                                                             │
│   [FastAPI] ──SQLite──► Device Registry                             │
│       │  CRUD: MAC → Name, Model, Location                          │
│       │  Status: query Prometheus cek device aktif                  │
│       │  Accessible via Nginx: :8088/api/ atau Direct: :8002        │
│       ▼                                                             │
│   [Nginx] ──serve──► Web Dashboard (HTML/CSS/JS)                    │
│       │  / → Web UI                                                 │
│       │  /api/ → FastAPI                                            │
│       └─ /grafana/ → Grafana                                        │
└─────────────────────────────────────────────────────────────────────┘
                    │
                    ▼ Browser
         ┌──────────────────────┐
         │  Web Dashboard       │
         │  localhost:8088      │
         │  - Device Table      │
         │  - Status Online/    │
         │    Offline           │
         │  - Grafana iframe    │
         └──────────────────────┘
```

---

## Hirarki Armada Mesin Heatpress

Sistem kini mendukung struktur hirarki berbasis kategori mesin dan sub-model:

```
🔥 Heatpress (Fleet Root)
  ├── 📟 HPM 55        — Double Station Pneumatic Heat Press (Tekanan 4-8 Bar, Suhu s/d 250°C)
  ├── 📟 AF-450        — Automatic Flatbed Heat Press 450 (Auto-Open Elektromagnetik, Suhu s/d 220°C)
  ├── 📟 APM-LOGO      — Auto Positioning Logo Heat Press (Sensor Laser Guide & Micro-Cylinder)
  └── ⏳ Coming Soon   — Next-Gen Intelligent Heat Press (Multi-Zone PID & Load-Cell Digital)
```

---

## Fitur

### 1. Hirarki Armada (Fleet Hierarchy View)
- **Tampilan Kartu Armada** — Kartu interaktif untuk HPM 55, AF-450, APM-LOGO, dan Coming Soon
- **Spesifikasi Model** — Menampilkan ringkasan teknologi (Pneumatic, Flatbed, Auto-Positioning)
- **Status per Model** — Jumlah unit terdaftar dan indikator online/offline per model
- **Aksi Cepat** — Filter tabel langsung ke model tertentu, monitor live di Grafana, atau tambah unit

### 2. Device Registry & Model Filter Pills
- **Model Pills Bar** — Filter cepat 1-klik di tabel (`Semua Heatpress`, `HPM 55`, `AF-450`, `APM-LOGO`, `Coming Soon`)
- **Preset Model di Modal** — Chip pilihan cepat untuk HPM 55, AF-450, APM-LOGO, dan Coming Soon dengan auto-fill
- **Tambah/Edit/Hapus Device** — Manajemen lengkap MAC Address, MCID, model, lokasi, dan deskripsi
- **Cari Device** — Filter real-time berdasarkan nama, MAC, MCID, lokasi, atau model

### 3. Status Online / Offline
- Setiap device ditampilkan dengan badge **🟢 Online** atau **⚫ Offline**
- Status ditentukan dari data Prometheus: jika device mengirim metric dalam **5 menit terakhir** → Online
- Stat cards di bagian atas menampilkan:
  - **Total Devices** — jumlah device yang terdaftar
  - **Online** — jumlah device aktif (hijau, dengan animasi pulse)
  - **Offline** — jumlah device tidak aktif
  - **Ter-mapping (MCID)** — jumlah device yang sudah dipasangkan dengan MCID
  - **Last Updated** — waktu terakhir polling status
- Status diperbarui otomatis setiap **30 detik**

### 4. Multi-Model Dedicated Dashboards & Universal Monitoring (Grafana)
- **Dashboard Universal (Seluruh Armada)** (`/grafana/d/iot-universal/`):
  - Memonitor seluruh armada lintas model mesin Heatpress (HPM 55, AF-450, APM-LOGO) dalam satu layar komparasi terpadu.
  - Dilengkapi filter cascading: **Filter Model** (`Semua Model`, `HPM 55`, `AF-450`, `APM-LOGO`) dan **Filter Device (MAC)**.
- **Dashboard Dedicated per Model Mesin (Terpisah & Tidak Tercampur)**:
  - 🔥 **Dashboard HPM 55** (`/grafana/d/hpm55-monitoring/`): Khusus model HPM 55 (Double Station Pneumatik, 4-8 Bar, suhu s/d 250°C, platen shuttle dual station). Filter device otomatis hanya menampilkan unit-unit HPM 55.
  - ⚡ **Dashboard AF-450** (`/grafana/d/af450-dashboard/`): Khusus model AF-450 (Automatic Flatbed 450, auto-open elektromagnetik, suhu s/d 220°C, flatbed 40x50cm). Filter device otomatis hanya menampilkan unit-unit AF-450.
  - 🏷️ **Dashboard APM-LOGO** (`/grafana/d/apmlogo-dashboard/`): Khusus model APM-LOGO (Auto Positioning Motion Logo, micro-cylinder pneumatik, laser guide, suhu s/d 230°C, compact platen 15x15cm). Filter device otomatis hanya menampilkan unit-unit APM-LOGO.
- **Dashboard Switcher Tabs**: Pindah antar dashboard dalam 1 klik langsung di Web UI tanpa reload halaman.
- **Device Filter Dinamis**: Pilihan pantau seluruh unit model tersebut (`All Units`) atau fokus ke satu perangkat spesifik.
- **Direct Monitoring Routing**: Dari kartu armada atau tabel Device Manager, klik tombol icon monitor langsung membuka dashboard khusus model device tersebut dengan device otomatis terpilih.

### 5. Statistik & Notifikasi
- Statistik jumlah device dan per model diperbarui otomatis
- Toast notification untuk setiap aksi dan perubahan status device (Online/Offline)
- Animasi pulse pada dot status device yang sedang Online


---

## MQTT Topics & Metric

Telegraf subscribe ke broker MQTT `10.109.25.97:1883` pada topic berikut:

| Topic                | Metric Name     | Keterangan                        |
|----------------------|-----------------|-----------------------------------|
| `+/SysCtrl`          | `sysctrl`       | Status mesin (ON/OFF), versi, IP  |
| `+/Event/Cnt`        | `event_cnt`     | Hitungan event proses             |
| `+/Event/Handling`   | `event_handling`| Event handling proses             |
| `+/Event/Mchn_time`  | `machine_time`  | Waktu operasional mesin           |
| `+/Heatpress`        | `heatpress`     | Data tekanan/suhu heat press      |

**Tag penting:** `MAC`, `IOT_MAC`, `MCID` — digunakan sebagai identifier unik device di Prometheus dan Grafana.

> Metric `sysctrl` adalah acuan utama untuk penentuan status Online/Offline. Device yang mengirim `sysctrl` dalam 5 menit terakhir dianggap **Online**.

---

## Cara Menambahkan Device Baru

1. Buka Web Dashboard: [http://localhost:8088](http://localhost:8088)
2. Klik tombol **+ Add Device**
3. Isi form:
   - **MAC Address** *(wajib)* — format `XX:XX:XX:XX:XX:XX`, contoh: `AA:BB:CC:DD:EE:FF`
   - **Device Name** *(wajib)* — nama deskriptif, contoh: `Heat Press Line 1`
   - **Model** *(opsional)* — tipe hardware, contoh: `ESP32-WROOM`
   - **Location** *(opsional)* — lokasi fisik, contoh: `Factory Floor A`
4. Klik **Save Device**

> MAC Address yang dimasukkan harus sesuai dengan MAC yang dikirim device melalui MQTT (field `MAC` atau `IOT_MAC` dalam JSON payload). Ini adalah kunci penghubung antara data metrik di Prometheus dengan informasi device di dashboard.

---

## Services & Port (IoT Stack — Zero Duplicate Containers)

Stack Docker IoT dirancang secara modular dan **tidak membuat container duplikat** untuk Grafana maupun Prometheus, melainkan langsung memanfaatkan aplikasi yang sudah terinstall di server homelab:

| Service | Container | Host Port | Status / Integrasi Homelab |
|---|---|---|---|
| **Telegraf** | `iot_telegraf` | **`9273`** | Bridge MQTT ke format Prometheus exporter |
| **FastAPI** | `iot_device_mapping_api` | **`8002`** | Device registry & query status ke Prometheus eksisting (:9001) |
| **Nginx (Web)** | `iot_dashboard_web` | **`8088`** | Web Dashboard Armada & proxy ke Grafana eksisting (:3001) |
| *Prometheus* | *(Eksisting Server)* | **`9001`** | **Memakai Prometheus Snap yang sudah aktif di server** |
| *Grafana* | *(Eksisting Server)* | **`3001`** | **Memakai Grafana yang sudah aktif di server** |

> **Anti-Tabrakan Port**: Saat Anda menjalankan `docker compose up -d`, hanya 3 kontainer unik di atas (`iot_telegraf`, `iot_device_mapping_api`, `iot_dashboard_web`) yang dibuat. Tidak ada container Prometheus atau Grafana kedua yang dijalankan, sehingga resource RAM server (~4 GB) hemat dan port 3001/9001 tidak pernah bentrok.

---

## Cara Menghubungkan ke Prometheus & Grafana Eksisting

### Langkah 1: Tambahkan Telegraf Target ke Prometheus Eksisting Server (:9001)
Buka file konfigurasi Prometheus Snap di server (`/var/snap/prometheus/current/prometheus.yml` atau `/etc/prometheus/prometheus.yml`) dan tambahkan blok berikut di bawah `scrape_configs:`:
```yaml
scrape_configs:
  - job_name: 'iot_telegraf'
    scrape_interval: 5s
    static_configs:
      - targets: ['127.0.0.1:9273']
```
Lalu reload Prometheus:
```bash
sudo snap restart prometheus
# atau: curl -X POST http://localhost:9001/-/reload
```

### Langkah 2: Impor Dashboard Heatpress ke Grafana Eksisting (:3001)
Jalankan skrip impor otomatis yang telah disediakan:
```bash
python scripts/setup_homelab_integrations.py --host 192.168.25.101 --user admin --password adminpassword
```
Skrip ini akan mengunggah ke-4 dashboard Heatpress (Universal Fleet, HPM 55, AF-450, APM-LOGO) langsung ke instance Grafana yang sudah ada di port `3001`.

### Langkah 3: Jalankan Stack IoT
```bash
cd dashboard_iot
docker compose up -d
```
Akses Web Hub di: **`http://localhost:8088`** (atau `http://192.168.25.101:8088`). Web dashboard akan langsung terhubung ke Grafana eksisting di port `3001` dan data dari Prometheus di port `9001`.

---

## Matriks Alokasi Port Homelab Server (Berdasarkan Audit `port.md`)

Seluruh port layanan di server homelab (`fa` - Dell OptiPlex 7050, Ubuntu 24.04 LTS) dipetakan secara ketat berdasarkan status listening (`ss -lntp`):

| Layanan / Proyek | Port Host | Local Binding (`port.md`) | Process / Container | Keterangan & Status |
|---|---|---|---|---|
| SSH | `22` | `0.0.0.0:22`, `[::]:22` | `sshd` | Remote server access |
| Mosquitto MQTT | `1883` | `0.0.0.0:1883`, `[::]:1883` | `docker-proxy` (mosquitto) | Broker MQTT IoT (Shared) |
| **Grafana Utama** | **`3001`** | `192.168.25.101:3001` | `docker-proxy` (grafana) | **Monitoring Utama (Eksisting Terinstall)** |
| Uptime Kuma | `3002` | `192.168.25.101:3002` | `docker-proxy` (uptime-kuma) | Uptime monitoring |
| **Dedicated IoT Grafana** | **`3003`** | `0.0.0.0:3003` *(Rekomendasi)* | `iot_grafana` *(Opsi 2)* | Dedicated Grafana IoT (Bebas bentrok) |
| PSM Web | `3005` | `0.0.0.0:3005`, `[::]:3005` | `docker-proxy` (psm-web) | Personal Server Manager Web |
| MySQL | `3306` | `192.168.25.101:3306`, `100.106.63.90:3306` | `docker-proxy` (homelab-mysql) | Database Stock UMKM |
| Dockge | `5001` | `192.168.25.101:5001` | `docker-proxy` (dockge) | Docker Stack Manager |
| PostgreSQL | `5432` | `192.168.25.101:5432`, `100.106.63.90:5432` | `docker-proxy` (homelab-postgres) | Database Server (psm & pap_core) |
| PAP API | `8000` | `192.168.25.101:8000` | `docker-proxy` (pap-api) | Personal API Platform Core |
| PSM API | `8001` | `0.0.0.0:8001`, `[::]:8001` | `docker-proxy` (psm-api) | PSM Control Plane Backend |
| **IoT Mapping API** | **`8002`** | `0.0.0.0:8002` *(Rekomendasi)* | `iot_device_mapping_api` | Backend IoT Registry (Bebas bentrok) |
| Vaultwarden | `8080` | `0.0.0.0:8080`, `[::]:8080` | `docker-proxy` (vaultwarden) | Password Vault |
| Apache | `8081` | `*:8081` | `httpd` | Web server Apache |
| **IoT Web Hub** | **`8088`** | `0.0.0.0:8088` *(Rekomendasi)* | `iot_dashboard_web` | Nginx Hub Dashboard Mesin Heatpress |
| Prometheus | `9001` | `*:9001` | `prometheus` | Prometheus metrics storage (Snap) |
| Cockpit | `9090` | `*:9090` | `cockpit-tls` | Linux Server Web Console |
| Calico Node | `9099` | `127.0.0.1:9099` | `calico-node` | K8s networking |
| **IoT Prometheus** | **`9095`** | `0.0.0.0:9095` *(Rekomendasi)* | `iot_prometheus` *(Opsi)* | Local Scraper IoT (Bebas dari :9090 Cockpit) |
| **IoT Telegraf** | **`9273`** | `0.0.0.0:9273` *(Rekomendasi)* | `iot_telegraf` | MQTT to Prometheus metrics exporter |
| Kubernetes / MicroK8s | `10250, 16443, 25000` | Local/All | `kubelite`, `cluster-agent` | K8s Cluster |

---

## Konfigurasi Environment (`.env`)

```env
# Grafana login
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=adminpassword

# Port konfigurasi (bebas bentrok)
IOT_WEB_PORT=8088
IOT_API_PORT=8002
IOT_GRAFANA_PORT=3003
IOT_PROMETHEUS_PORT=9095
IOT_TELEGRAF_PORT=9273

# Koneksi ke layanan Homelab
MQTT_BROKER_HOST=192.168.25.101
MQTT_TAILSCALE_HOST=100.106.63.90
PROMETHEUS_URL=http://192.168.25.101:9001
PAP_API_URL=http://192.168.25.101:8000
```

---

## API Endpoints (FastAPI)

Base URL: `http://localhost/api` (via Nginx) atau `http://localhost:8000`

| Method   | Endpoint                           | Deskripsi                                  |
|----------|------------------------------------|--------------------------------------------|
| `GET`    | `/api/devices/hierarchy`           | **Struktur hirarki model Heatpress & unit**|
| `GET`    | `/api/devices/`                    | Ambil semua device (filter: category, model) |
| `POST`   | `/api/devices/`                    | Tambah device baru                         |
| `GET`    | `/api/devices/{mac}`               | Ambil info satu device                     |
| `PUT`    | `/api/devices/{mac}`               | Update info device (nama, model, lokasi)   |
| `DELETE` | `/api/devices/{mac}`               | Hapus device                               |
| `GET`    | `/api/devices/statuses`            | **Status Online/Offline semua device**     |
| `GET`    | `/api/devices/{mac}/status`        | Status Online/Offline satu device          |
| `GET`    | `/api/devices/{mac}/last-seen`     | Waktu terakhir device mengirim data        |

Dokumentasi interaktif: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Struktur Direktori

```
dashboard_iot/
├── docker-compose.yml          # Definisi semua services
├── .env                        # Konfigurasi credentials
│
├── web/                        # Web Dashboard (Nginx + Static)
│   ├── index.html              # UI utama
│   ├── app.js                  # Logic JS (fetch, render, polling)
│   ├── style.css               # Styling (glassmorphism, dark mode)
│   └── nginx.conf              # Konfigurasi reverse proxy Nginx
│
├── api/                        # Device Mapping API (FastAPI + SQLite)
│   ├── main.py                 # Endpoints + status via Prometheus
│   ├── models.py               # SQLAlchemy model (Device table)
│   ├── schemas.py              # Pydantic schemas
│   ├── crud.py                 # Database operations
│   ├── database.py             # SQLite connection
│   ├── requirements.txt        # Python dependencies
│   ├── Dockerfile              # Build image FastAPI
│   └── data/                   # SQLite database file (persisted)
│       └── devices.db
│
├── telegraf/
│   └── telegraf.conf           # MQTT subscribe + Prometheus export config
│
├── prometheus/                 # Prometheus scrape config
│
└── grafana/                    # Grafana provisioning
    ├── provisioning/           # Datasource & dashboard config otomatis
    └── dashboards/             # JSON dashboard definitions
```

---

## Cara Menjalankan

```bash
# Clone repo & masuk direktori
cd dashboard_iot

# Start semua service (pertama kali, atau setelah ubah Dockerfile)
docker compose up -d --build

# Start tanpa build ulang
docker compose up -d

# Lihat log semua service
docker compose logs -f

# Lihat log service tertentu
docker compose logs -f api

# Stop semua service
docker compose down
```

### Rebuild setelah perubahan kode:

| Komponen diubah          | Perintah rebuild                          |
|--------------------------|-------------------------------------------|
| `api/` (Python/Backend)  | `docker compose up -d --build api`        |
| `web/` (HTML/JS/CSS)     | Langsung refresh browser (file di-mount)  |
| `docker-compose.yml`     | `docker compose up -d`                    |
| `telegraf/telegraf.conf` | `docker compose restart telegraf`         |

---

## Flow Data Lengkap

```
1. [ESP32/MC]
   └─ Kirim JSON via MQTT ke topic: {DeviceID}/SysCtrl
      Contoh payload:
      {
        "MAC": "AA:BB:CC:DD:EE:FF",
        "IOT_MAC": "AA:BB:CC:DD:EE:FF",
        "MCID": "MC001",
        "STS": "ON",
        "VER": "1.2.3",
        "MCIP": "192.168.1.100"
      }

2. [Telegraf]
   └─ Subscribe topic +/SysCtrl
   └─ Parse JSON, simpan MAC sebagai tag Prometheus
   └─ Expose metric: sysctrl{MAC="AA:BB:CC:DD:EE:FF"} di port 9273

3. [Prometheus]
   └─ Scrape telegraf:9273 setiap 5 detik
   └─ Simpan time-series data

4. [Web Dashboard - JS]
   └─ Setiap 30 detik: GET /api/devices/statuses
   └─ FastAPI query Prometheus:
      count by (MAC) (count_over_time(sysctrl[5m]))
   └─ Jika MAC ada di result → Online ✅
   └─ Jika tidak ada → Offline ❌
   └─ Render badge di tabel

5. [Grafana Multi-Model & Universal Dashboard]
   └─ Dashboard Universal: /d/iot-universal/?var-model=...&var-mac=...
   └─ Dashboard HPM 55 Dedicated: /d/hpm55-monitoring/?var-mac=...
   └─ Dashboard AF-450 Dedicated: /d/af450-dashboard/?var-mac=...
   └─ Dashboard APM-LOGO Dedicated: /d/apmlogo-dashboard/?var-mac=...
   └─ Dashboard query Prometheus terfilter sesuai model & device tanpa tercampur
```

---

## Tech Stack

| Layer       | Teknologi                      |
|-------------|--------------------------------|
| Hardware    | ESP32 / Microcontroller        |
| Messaging   | MQTT (Mosquitto broker)        |
| Ingestion   | Telegraf 1.29                  |
| Storage     | Prometheus (time-series)       |
| Visualization | Grafana 10.4.0               |
| Backend API | FastAPI + SQLite (SQLAlchemy)  |
| Web UI      | HTML5 + Vanilla JS + CSS3      |
| Proxy       | Nginx (Alpine)                 |
| Container   | Docker + Docker Compose        |
