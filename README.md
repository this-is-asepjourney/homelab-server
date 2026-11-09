# Master Homelab Server

Arsitektur terpadu Homelab Server (`fa` - Dell OptiPlex 7050, Ubuntu 24.04.5 LTS) yang menyatukan seluruh proyek inti ke dalam satu orkestrasi Docker terpusat dengan prinsip **Zero Container Duplication** ("Menggunakan yang sudah ada") & **Dedicated Database Isolation**.

> 📖 **Panduan Alur Kerja & Komunikasi Antar-Proyek**: Untuk mempelajari bagaimana setiap modul, hardware ESP32, web dashboard, broker MQTT, dan database saling berkomunikasi secara realtime, silakan baca [**FLOW_SISTEM_HOMELAB.md**](file:///d:/repository/homelab-server/FLOW_SISTEM_HOMELAB.md).

---

## 1. Konsep: "Menggunakan Yang Sudah Ada"

Server telah memiliki layanan-layanan inti yang berjalan di level host atau docker independen (sesuai audit `port.md`). Untuk menghemat memori RAM (~4 GB) dan mencegah bentrok port (*address already in use*), stack ini **TIDAK membuat kontainer baru** untuk infrastruktur tersebut, melainkan menghubungkan aplikasi langsung ke layanan yang sudah aktif:

| Kategori Infrastruktur | Status Eksisting di Server | Alamat Akses dari Container | Digunakan Oleh Proyek |
| :--- | :--- | :--- | :--- |
| **Grafana Dashboard** | Port `3001` (Docker Utama) | `http://host.docker.internal:3001` | IoT Dashboard (Web Hub Proxy & Embed) |
| **Prometheus Metrics**| Port `9001` (Docker Container)| `http://host.docker.internal:9001` | IoT API & PSM Server Monitor |
| **Mosquitto MQTT** | Port `1883` (Host Daemon) | `192.168.25.101:1883` | Telegraf IoT & ESP32 Fleet |
| **PostgreSQL Server** | Port `5432` (Host Daemon) | `192.168.25.101:5432` | PSM API & Agent |
| **MySQL Database** | Port `3306` (Host Daemon) | `192.168.25.101:3306` | Stock UMKM & Core Database |
| **Uptime Kuma** | Port `3002` (Eksisting) | `192.168.25.101:3002` | Health Monitoring Global |
| **Vaultwarden** | Port `8080` (Eksisting) | `192.168.25.101:8080` | Password Manager |
| **Cockpit Console** | Port `9090` (Eksisting) | `192.168.25.101:9090` | Server Web Admin |

---

## 2. Struktur Proyek Terpadu

Stack Docker Homelab ini hanya menjalankan **kontainer aplikasi murni** dari ketiga proyek:

```text
/opt/
├── homelab/                         <- Layanan Infrastruktur Eksisting (Docker)
│   ├── databases/                   <- PostgreSQL (:5432) & MySQL (:3306)
│   ├── grafana/                     <- Grafana Utama (:3001)
│   ├── mosquitto/                   <- Mosquitto MQTT Broker (:1883)
│   ├── prometheus/                  <- Prometheus Docker (:9001, config/prometheus.yml)
│   └── uptime-kuma/                 <- Uptime Kuma (:3002)
├── dockge/                          <- Dockge Stack Manager
└── projects/homelab-server/         <- REPOSITORY UTAMA PROYEK
    ├── deploy.sh                    <- Script Deployment Otomatis Server
    ├── docker-compose.yml           <- Master Compose Terpadu (7 Containers)
    ├── homelab.py                   <- CLI Manajemen Terpadu Homelab
    ├── PANDUAN_OPERASIONAL.md       <- Panduan Lengkap Pengoperasian
    ├── data/mapping.db              <- SQLite Device Registry
    ├── Personal Api Platform/       <- pap-api (Port :8000)
    ├── Personal_Server_Manager/     <- psm-api (:8001), psm-web (:3005), psm-agent
    └── dashboard_iot/               <- iot-telegraf (:9273), iot-api (:8002), iot-web (:8088)
```

### Matriks Port Aplikasi

| Layanan | Kontainer | Port Host | Jaringan Internal | Keterangan |
| :--- | :--- | :--- | :--- | :--- |
| **PAP API** | `pap-api` | `8000` | `homelab-network` | Core API Gateway & Integrasi |
| **PSM API** | `psm-api` | `8001` | `homelab-network`, `psm-network` | Server Management Backend & Auth |
| **PSM Web** | `psm-web` | `3005` | `psm-network` | Frontend Dashboard PSM (Next.js) |
| **PSM Agent** | `psm-agent` | - | `psm-network` | Monitoring host docker & sistem |
| **IoT Telegraf** | `iot_telegraf` | `9273` | `iot-network` | MQTT to Prometheus Metrics Bridge |
| **IoT API** | `iot_device_mapping_api` | `8002` | `homelab-network`, `iot-network` | CRUD MAC ↔ Device & Status Mesin |
| **IoT Web** | `iot_dashboard_web` | `8088` | `iot-network` | Web Hub Heatpress & Reverse Proxy Grafana |

---

## 3. Isolasi Jaringan (Network Isolation)

Untuk mencegah konflik nama (seperti `api` yang digunakan oleh PSM Web dan IoT Web), arsitektur menggunakan 3 jaringan:

1. `psm-network`: Khusus untuk komunikasi internal PSM Web & Agent ke `psm-api` (alias `api`).
2. `iot-network`: Khusus untuk komunikasi internal IoT Web ke `iot-api` (alias `api`) dan Telegraf.
3. `homelab-network`: Jaringan backbone bersama yang memungkinkan `psm-api`, `iot-api`, dan `pap-api` saling berkomunikasi dengan aman tanpa bentrok.

---

## 4. Cara Menjalankan

### Opsi Utama: Deployment Otomatis via `deploy.sh` (Sangat Direkomendasikan)

Script ini dirancang khusus untuk struktur `/opt` di server `fa`. Menangani seluruh konfigurasi Prometheus (`/opt/homelab/prometheus/config/prometheus.yml`), inisialisasi database `psm`, build container, dan verifikasi healthcheck:

```bash
cd /opt/projects/homelab-server
chmod +x deploy.sh
./deploy.sh
```

### Opsi B: Menggunakan CLI Terpadu (`homelab.py`)

CLI ini otomatis memvalidasi dependensi dan memeriksa ketersediaan port:

```bash
# 1. Cek status semua layanan (Eksisting & Aplikasi)
python homelab.py status

# 2. Build semua image container
python homelab.py build

# 3. Jalankan seluruh stack homelab di latar belakang
python homelab.py up

# 4. Impor 4 dashboard Heatpress ke Grafana eksisting (:3001)
python homelab.py import-grafana --token <GRAFANA_SERVICE_TOKEN>

# 5. Hentikan stack
python homelab.py down
```

### Opsi C: Menggunakan Docker Compose Standar

```bash
# Menjalankan seluruh stack
docker compose up -d

# Memeriksa log
docker compose logs -f

# Menghentikan stack
docker compose down
```

---

## 5. Integrasi ke Prometheus & Grafana Eksisting

### Langkah 1: Hubungkan Prometheus Docker (:9001) ke Telegraf (:9273)

Tambahkan blok job scrape berikut ke file /opt/homelab/prometheus/config/prometheus.yml:

```yaml
scrape_configs:
  - job_name: 'iot_heatpress'
    scrape_interval: 5s
    scrape_timeout: 4s
    static_configs:
      - targets: ['192.168.25.101:9273']
        labels:
          environment: 'homelab'
          service: 'heatpress_iot'
```

Lalu reload atau restart container Prometheus:

```bash
# Opsi A: Reload via HTTP
curl -X POST http://192.168.25.101:9001/-/reload

# Opsi B: Restart container Prometheus di /opt/homelab/prometheus
cd /opt/homelab/prometheus && docker compose restart
```

### Langkah 2: Impor Dashboard ke Grafana Eksisting (:3001)

Jalankan script importer otomatis:

```bash
python dashboard_iot/scripts/import_to_existing_grafana.py --host 192.168.25.101 --port 3001 --token <API_TOKEN_GRAFANA>
```

Script akan otomatis membuat folder **"Heatpress Fleet Monitoring"** dan mengimpor 4 dashboard:

1. *Heatpress Executive Overview*
2. *Heatpress Machine Deep Dive*
3. *Heatpress Energy & Cost Tracker*
4. *Heatpress System Diagnostics*

---

## 6. Verifikasi & Pengujian

Jalankan test suite untuk memastikan semua modul valid:

```bash
# Test integrasi IoT
pytest dashboard_iot/tests

# Test sintaks docker-compose
docker compose config --quiet
```
