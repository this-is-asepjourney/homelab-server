# Master Homelab Server

Arsitektur terpadu Homelab Server (`fa` - Dell OptiPlex 7050, Ubuntu 24.04.5 LTS) yang menyatukan 3 proyek inti ke dalam satu orkestrasi Docker terpusat dengan prinsip **Zero Container Duplication** ("Menggunakan yang sudah ada").

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
homelab-server/
├── Personal Api Platform/      -> pap-api (Port 8000)
├── Personal_Server_Manager/    -> psm-api (Port 8001), psm-web (Port 3005), psm-agent
├── dashboard_iot/              -> iot-telegraf (Port 9273), iot-api (Port 8002), iot-web (Port 8088)
├── docker-compose.yml          -> Master Compose terpadu
├── homelab.py                  -> CLI Manajemen Terpadu Homelab
├── .env                        -> Konfigurasi IP, port, token, dan kredensial
└── port.md                     -> Pemetaan port aktual server fa
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

### Opsi A: Menggunakan CLI Terpadu (`homelab.py`)

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

### Opsi B: Menggunakan Docker Compose Standar

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

Tambahkan blok job scrape berikut ke konfigurasi Prometheus eksisting di server (misal `/var/snap/prometheus/current/prometheus.yml`):

```yaml
scrape_configs:
  - job_name: 'iot_heatpress'
    scrape_interval: 5s
    static_configs:
      - targets: ['127.0.0.1:9273']
        labels:
          environment: 'homelab'
          service: 'heatpress_iot'
```

Lalu restart atau reload Prometheus:

```bash
sudo systemctl restart snap.prometheus.prometheus
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
