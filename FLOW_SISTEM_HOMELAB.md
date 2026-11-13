# 📘 Blueprint & Flow Sistem Homelab Server
## Fokus: Aliran Data & Cara Sistem Bekerja (PAP • PSM • Dashboard IoT)

Dokumen ini mendokumentasikan secara presisi dan mendalam bagaimana seluruh aliran data (**data flow**) dan mekanisme kerja sistem berjalan di dalam ekosistem **Homelab Server (`fa` - 192.168.25.101 / Tailscale 100.106.63.90)**, dengan fokus utama pada sinergi tiga pilar aplikasi:
1. **PAP (Personal API Platform — Port 8000)**: Master Central API Gateway, integrasi data, dan orkestrasi kontrol.
2. **PSM (Personal Server Manager — Web: 3005, Agent: In-Host)**: PaaS Deployment Engine, lifecycle container Docker, dan database auto-provisioning.
3. **Dashboard IoT (HeatpressHub — Web: 8088, Telegraf: 9273)**: Telemetri mesin heatpress, keamanan solenoid lock, dan akses NFC RFID.

---

## 📑 Daftar Isi
1. [Arsitektur Triad & Master Topology Map](#1-arsitektur-triad--master-topology-map)
2. [Flow 1: Sistem Kerja & Aliran Data PAP (Central Core Gateway)](#flow-1-sistem-kerja--aliran-data-pap-central-core-gateway)
3. [Flow 2: Sistem Kerja & Aliran Data PSM (PaaS Deployment Engine)](#flow-2-sistem-kerja--aliran-data-psm-paas-deployment-engine)
4. [Flow 3: Sistem Kerja & Aliran Data Dashboard IoT (Heatpress Fleet)](#flow-3-sistem-kerja--aliran-data-dashboard-iot-heatpress-fleet)
5. [Flow 4: Interkoneksi Sinergis (PAP ↔ PSM ↔ Dashboard IoT)](#flow-4-interkoneksi-sinergis-pap--psm--dashboard-iot)
6. [Matriks Aliran Data, Protokol & Port](#matriks-aliran-data-protokol--port)
7. [Audit Resource & Proteksi Memori Server (Anti-OOM)](#audit-resource--proteksi-memori-server-anti-oom)

---

## 1. Arsitektur Triad & Master Topology Map

Diagram berikut mengilustrasikan bagaimana data mengalir di antara **PAP**, **PSM**, **Dashboard IoT**, serta infrastruktur native host (Postgres, MySQL, MQTT, Prometheus, CoreDNS, Ingress Router):

```mermaid
flowchart TD
    subgraph Clients["🌐 Pengguna & Perangkat Luar"]
        UserBrowser["💻 Web Browser (LAN / Tailscale)"]
        GitHub["🐙 GitHub Cloud (Push / Webhook)"]
        ESP32["📟 ESP32 Microcontroller (192.168.25.104)"]
    end

    subgraph IngressGateway["🚪 Network Ingress & Resolusi Nama"]
        DNS["🧭 CoreDNS (:53)\nResolve *.homelab & *.fa.local"]
        Nginx["🚪 Nginx Ingress Router (:80)\nVirtual Host Reverse Proxy"]
    end

    subgraph TRIAD["⚡ TIGA PILAR UTAMA SISTEM"]
        subgraph PSM_STACK["1. PSM (Server & App Manager)"]
            PSM_Web["🎛️ PSM Web Console (:3005)\npsm.homelab"]
            PSM_Agent["⚙️ PSM Agent Worker\n(Docker Socket Engine)"]
        end

        subgraph PAP_STACK["2. PAP (Master Central Gateway)"]
            PAP_Core["🛡️ PAP Core API (:8000)\napi.homelab / core-api\n• Auth & RBAC (JWT & API Key)\n• Project Control Plane\n• IoT Fleet Registry\n• DNS & Ingress Auto-Sync\n• DB Provisioning Engine"]
        end

        subgraph IOT_STACK["3. Dashboard IoT (Heatpress Fleet)"]
            IOT_Web["📟 HeatpressHub Web (:8088)\niot.homelab"]
            Telegraf["🔄 Telegraf Metrics Exporter (:9273)"]
        end
    end

    subgraph HostDaemons["🗄️ Layanan Native Host (Zero Container Duplication)"]
        PG["🐘 PostgreSQL Server (:5432)\n• Database 'pap_core'\n• Database 'psm'\n• Project DBs (misal: pos_db)"]
        MY["🐬 MySQL 8.4 Server (:3306)\n• Database 'eternal_db' (IoT/NFC)\n• Database 'stock_umkm'"]
        MQTT["📡 Mosquitto Broker (:1883)\nTopik: /SysCtrl, Eternal/#"]
        PROM["📈 Prometheus Server (:9001)\nTSDB Metrics Engine"]
        GRAF["📊 Grafana Utama (:3001)\ngrafana.homelab"]
    end

    subgraph Workspaces["📦 Workspace Aplikasi Terdeploy"]
        AppContainers["🚀 Deployed App Container (misal: pos-main :3101)\npos-main-upgrade-v2.homelab"]
    end

    %% Ingress & Routing
    UserBrowser -->|Query Domain| DNS
    UserBrowser -->|HTTP Port 80| Nginx
    Nginx -->|Route psm.homelab| PSM_Web
    Nginx -->|Route iot.homelab| IOT_Web
    Nginx -->|Route /api/ atau api.homelab| PAP_Core
    Nginx -->|Route *.homelab apps| AppContainers

    %% Interkoneksi Triad
    PSM_Web <-->|REST API + WebSockets| PAP_Core
    IOT_Web <-->|REST API /api/devices| PAP_Core
    PAP_Core -->|Dispatch Job Deployment| PSM_Agent
    PSM_Agent -->|Build & Run Containers| AppContainers

    %% GitHub Webhook
    GitHub -->|Push Event Webhook| PAP_Core

    %% IoT Flow
    ESP32 -->|1. MQTT Pub Telemetri| MQTT
    ESP32 <-->|2. HTTP NFC Verification| PAP_Core
    MQTT --> Telegraf --> PROM --> GRAF
    GRAF -->|Direct Query| MY

    %% Database Wire
    PAP_Core --> PG
    PAP_Core --> MY
    AppContainers -.->|Auto-Wired Connection| PG
    AppContainers -.->|Auto-Wired Connection| MY
```

---

## Flow 1: Sistem Kerja & Aliran Data PAP (Central Core Gateway)

**PAP (Personal API Platform)** adalah jantung komunikasi seluruh sistem. PAP bertindak sebagai **Single Source of Truth** untuk identitas, otorisasi, metadata proyek, dan registrasi perangkat.

```mermaid
sequenceDiagram
    autonumber
    participant Client as Klien (PSM / IoT / Developer)
    participant Nginx as Nginx Router (:80)
    participant PAP as 🛡️ PAP Core API (:8000)
    participant Auth as Modul Auth & RBAC
    participant PG as 🐘 PostgreSQL (:5432)
    participant DNS as 🧭 CoreDNS (:53)
    participant HostNginx as 🚪 Nginx Conf.d

    Client->>Nginx: Request HTTP (Header: Bearer JWT atau X-API-Key)
    Nginx->>PAP: Proxy Pass ke http://pap-api:8000
    
    PAP->>Auth: Validasi Signature Token / Hash API Key
    alt Token / Key Valid
        Auth-->>PAP: Identity Confirmed (User / Agent / Device Scope)
    else Tidak Valid
        Auth-->>Client: HTTP 401 Unauthorized / 403 Forbidden
    end

    alt Operasi Manajemen Proyek / Deploy
        PAP->>PG: Baca/Tulis Data ke database 'psm' & 'pap_core'
        PAP->>DNS: Update file /etc/coredns/homelab.hosts
        PAP->>HostNginx: Tulis file upstream virtual host /etc/nginx/conf.d/projects/
        PAP-->>Client: HTTP 200 OK (Job Dispatched / Config Synced)
    else Operasi IoT Device Registry
        PAP->>PG: Ambil metadata armada mesin heatpress
        PAP-->>Client: JSON Hierarchy Fleet (HPM 55, AF-450, APM-LOGO)
    end
```

### Cara PAP Bekerja:
1. **Modular Monolith Runtime**: Semua modul (*Auth, Projects, Deployments, IoT, DNS, DB Provisioning*) berada dalam satu proses FastAPI yang sangat hemat RAM (~384 MB).
2. **Dual-Layer Authentication**:
   - **Sesi Pengguna (Human-to-Machine)**: Menggunakan JWT Token dengan masa kedaluwarsa aman untuk akses PSM Web Console.
   - **Antar-Layanan (Machine-to-Machine)**: Menggunakan `X-API-Key` dengan hashing SHA-256 untuk PSM Agent, Telegraf, dan hardware ESP32.
3. **Automated Ingress & Local DNS Synchronization**:
   Setiap kali ada project baru yang di-deploy, PAP otomatis menyuntikkan entri domain baru ke file [dns/homelab.hosts](file:///d:/repository/homelab-server/dns/homelab.hosts) dan menghasilkan file konfigurasi reverse-proxy di [router/conf.d/projects/](file:///d:/repository/homelab-server/router/conf.d/projects/).

---

## Flow 2: Sistem Kerja & Aliran Data PSM (PaaS Deployment Engine)

**PSM (Personal Server Manager)** berfungsi sebagai platform-as-a-service (PaaS) lokal yang mengotomatisasi pembangunan dan peluncuran aplikasi dari Git repository atau file ZIP ke dalam container Docker.

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Developer / User
    participant Web as 🎛️ PSM Web Console (:3005)
    participant API as 🛡️ PAP Core API (:8000)
    participant PGHost as 🐘 PostgreSQL Server (:5432)
    participant Agent as ⚙️ PSM Agent Worker
    participant Docker as 🐳 Docker Engine
    participant Router as 🚪 Nginx Ingress (:80)

    Dev->>Web: 1. Input Repo Git, Port Host (:3101), dan DB Engine
    Web->>API: POST /api/v1/deployments/git
    
    Note over API,PGHost: Auto-Provisioning Database (Pilar Zero Duplication)
    API->>PGHost: Periksa keberadaan DB 'pos_db'. Jika belum ada: CREATE DATABASE & USER
    API->>API: Generate kredensial DATABASE_URL terenkripsi AES
    API->>API: Buat Job Deployment ID & Simpan ke DB 'psm'
    
    API->>Agent: Dispatch Job ke Agent Antrean
    
    Note over Agent,Docker: 5 Tahapan Pipeline Deployment
    Agent->>Agent: [STAGE 1/5] Clone Git (Suntik GitHub Token jika private, fallback branch 'Main' vs 'main')
    Agent->>Agent: [STAGE 2/5] Tulis file .env (Inject DATABASE_URL, DB_HOST, DB_USER)
    Agent->>Agent: [STAGE 3/5] Generate multi-stage Dockerfile & .dockerignore
    Agent->>Docker: [STAGE 4/5] docker build -t pos-main:v2 (Throttled: --memory=768m)
    Agent->>Docker: [STAGE 5/5] docker run -p 3101:3000 --network homelab-network
    
    Agent-->>API: Status Deployment: SUCCESS
    API->>Router: Daftarkan Virtual Host 'pos-main-upgrade-v2.homelab' -> port 3101
    API-->>Web: Live Stream Update: Deployment v2 Selesai & Running
    Web-->>Dev: Tampilkan Status Hijau ● RUNNING & Tautan Akses
```

### Cara PSM Bekerja:
1. **GitHub Full Access Integration**:
   - Mendukung Personal Access Token (PAT) tersimpan aman untuk meng-clone repositori privat (`x-access-token:{token}@github.com`).
   - **Smart Branch Resolution**: Jika branch diisi `main` namun di GitHub bernama `Main` (kapital), builder secara cerdas mencoba branch alternatif atau langsung meng-clone default HEAD branch tanpa membatalkan deployment.
2. **Auto-Wiring Database Host**:
   - PSM tidak menduplikasi container database. Sistem secara cerdas memanggil PostgreSQL (`:5432`) atau MySQL (`:3306`) host, membuat database dan user khusus, lalu menyuntikkan variabel environment ke container aplikasi.
3. **Resource Guard (Anti-Freeze)**:
   - Container aplikasi dibatasi maksimal memori `768 MB` dan `1.0 CPU` agar proses kompilasi (`npm run build`) tidak menguras memori server Dell OptiPlex 7050.

---

## Flow 3: Sistem Kerja & Aliran Data Dashboard IoT (Heatpress Fleet)

**Dashboard IoT (HeatpressHub)** mengelola telemetri real-time, status kunci solenoid relay, dan kontrol akses fisik kartu NFC pada mesin heatpress konveksi.

```mermaid
sequenceDiagram
    autonumber
    actor Operator as Operator Mesin (Kartu NFC)
    participant HW as 📟 ESP32 Controller (192.168.25.104)
    participant Buzzer as 🔊 Buzzer KY-012 (GPIO 25)
    participant Solenoid as 🔌 Solenoid Lock (GPIO 26)
    participant MQTT as 📡 Mosquitto Broker (:1883)
    participant Telegraf as 🔄 Telegraf Exporter (:9273)
    participant Prom as 📈 Prometheus (:9001)
    participant Graf as 📊 Grafana (:3001)
    participant PAP as 🛡️ PAP Core API (:8000)
    participant MySQL as 🐬 MySQL eternal_db (:3306)
    participant IOTWeb as 📟 Dashboard IoT Web (:8088)

    Note over HW,MQTT: ALUR TELEMETRI SENSOR (Setiap 5 Detik)
    HW->>MQTT: Publish JSON ke '/SysCtrl' (Suhu DHT11, Kelembaban, Status Lock)
    MQTT->>Telegraf: Forward Paket Telemetri
    Telegraf->>Telegraf: Parse Tag OpenMetrics (:9273/metrics)
    Prom->>Telegraf: Scrape Metrik Time-Series
    Graf->>Prom: Query PromQL & Tampilkan Realtime Gauge Suhu
    
    Note over Operator,Solenoid: ALUR AKSES NFC & KONTROL SOLENOID
    Operator->>HW: Tempel Kartu NFC (UID: 058E208F87A200)
    HW->>PAP: GET /api/nfc/users/058E208F87A200 (Verifikasi Kredensial)
    PAP->>MySQL: SELECT * FROM nfc_users WHERE uid = ...
    MySQL-->>PAP: User Valid (Ferdiansyah - Role: Operator)
    PAP-->>HW: HTTP 200 OK (Granted)
    
    HW->>Buzzer: Bip 1x Tegas (100ms)
    HW->>Solenoid: Set HIGH (Kunci Solenoid Terbuka / UNLOCKED)
    HW->>MQTT: Publish /SysCtrl (status: UNLOCKED by Ferdiansyah)
    HW->>PAP: POST /api/nfc/tap (Audit Log)
    PAP->>MySQL: INSERT INTO nfc_access_logs & UPDATE device_locks
    PAP-->>IOTWeb: Push Live Alert: Mesin Dibuka oleh Ferdiansyah
```

### Cara Dashboard IoT Bekerja:
1. **Edge Caching di ESP32**:
   - ESP32 menyimpan kartu yang telah terverifikasi ke dalam memori Flash NVS lokal. Jika jaringan LAN terputus sejenak, mesin tetap dapat dioperasikan secara offline.
2. **Telemetry Decoupling**:
   - Data suhu dipancarkan via protokol ringan **MQTT** ke broker Mosquitto, diserap oleh **Telegraf**, dan disimpan di **Prometheus**. Hal ini mencegah database transaksional terbebani oleh jutaan baris data log sensor.
3. **Sinkronisasi Dua Arah dari Web ke Hardware**:
   - Saat admin mendaftarkan kartu baru di [iot_dashboard_web](file:///d:/repository/homelab-server/dashboard_iot/web), PAP API secara instan mem-push data user ke REST endpoint ESP32 (`http://192.168.25.104/api/nfc/register_user`) tanpa perlu me-restart hardware.

---

## Flow 4: Interkoneksi Sinergis (PAP ↔ PSM ↔ Dashboard IoT)

Ketiga subsistem tidak berjalan sendiri-sendiri, melainkan saling berkomunikasi melalui protokol yang terstandarisasi:

```mermaid
flowchart LR
    subgraph PSM["🎛️ PSM"]
        P1["Manajemen Kontainer"]
        P2["Provisioning DB"]
    end

    subgraph PAP["🛡️ PAP Core Gateway"]
        M1["State Sync Engine"]
        M2["IoT Fleet Manager"]
        M3["DNS & Virtual Host"]
    end

    subgraph IOT["📟 Dashboard IoT"]
        I1["Telemetry Monitoring"]
        I2["NFC Role Management"]
    end

    PSM -- "1. Push State Proyek & Kontainer\n(/api/v1/integrations/psm/sync)" --> PAP
    PAP -- "2. Dispatch Job Build & Auto-Wiring" --> PSM
    IOT -- "3. Query Armada Mesin & Status Kunci\n(/api/v1/pap/iot/fleet)" --> PAP
    PAP -- "4. Validasi Kartu NFC & Catat Log Akses" --> IOT
```

1. **PSM ke PAP (`/api/v1/integrations/psm/sync`)**:
   - Secara periodik dan setiap ada perubahan container, PSM mengirimkan *snapshot* seluruh server, proyek, dan status container ke PAP. Jika terjadi kendala, PAP memiliki mode *local standby fallback*.
2. **Dashboard IoT ke PAP (`/api/v1/pap/iot/fleet`)**:
   - Dashboard IoT mengambil struktur hierarki mesin (HPM 55, AF-450, APM-LOGO) melalui PAP Core Gateway, sehingga otorisasi peran pengguna (Supervisor vs Operator) tetap tersentralisasi.
3. **Shared Ingress & DNS**:
   - CoreDNS dan Nginx Router dikelola bersama oleh PAP, sehingga `psm.homelab`, `iot.homelab`, dan aplikasi yang terdeploy (seperti `pos-main-upgrade-v2.homelab`) langsung dapat diakses di port 80 tanpa konflik port.

---

## Matriks Aliran Data, Protokol & Port

| Aliran Data | Sumber | Tujuan | Protokol | Port | Keterangan Data |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **User Access** | Browser Klien | CoreDNS | DNS (UDP/TCP) | `:53` | Resolusi domain `*.homelab` |
| **Virtual Host** | Browser Klien | Nginx Router | HTTP | `:80` | Proxy pass ke container target |
| **PSM API Calls** | PSM Web | PAP Core API | HTTP REST / JSON | `:8000` | Operasi kontrol, deploy, audit |
| **IoT Telemetry** | ESP32 Hardware | Mosquitto | MQTT (TCP) | `:1883` | Payload JSON sensor `/SysCtrl` |
| **Metrics Pipeline** | Mosquitto | Telegraf | MQTT Pub/Sub | `:1883` | Ekstraksi metrik OpenMetrics |
| **Metrics Scrape** | Prometheus | Telegraf | HTTP GET | `:9273` | Scrape time-series metrik IoT |
| **Metrics Dashboard**| Grafana | Prometheus | HTTP PromQL | `:9001` | Query grafik suhu & utilisasi |
| **IoT SQL State** | PAP API / Grafana | MySQL (`eternal_db`) | MySQL Protocol | `:3306` | Data log kartu NFC & device lock |
| **Core State** | PAP API / PSM | PostgreSQL (`pap_core`, `psm`) | PostgreSQL Wire | `:5432` | Data proyek, user, audit log |
| **GitHub Push** | GitHub Cloud | PAP API | HTTP POST Webhook | `:8000` | Trigger auto-deploy commit baru |

---

## Audit Resource & Proteksi Memori Server (Anti-OOM)

Server fisik menggunakan **Dell OptiPlex 7050 (Intel Core i5, RAM 4 GB)**. Untuk menjaga stabilitas maksimal, arsitektur menerapkan batas memori ketat di `docker-compose.yml`:

| Kontainer / Service | Batas Memori (RAM Limit) | Alokasi CPU | Status Kinerja |
| :--- | :---: | :---: | :--- |
| **`pap-api`** | `384 MB` | 0.75 CPU | Stabil (FastAPI Modular Monolith) |
| **`psm-web`** | `256 MB` | 0.50 CPU | Cepat (Next.js Standalone Build) |
| **`psm-agent`** | `192 MB` | 0.25 CPU | Ringan (Worker Daemon) |
| **`homelab_router`** | `96 MB` | 0.25 CPU | Sangat Ringan (Nginx Alpine) |
| **`homelab_dns`** | `64 MB` | 0.15 CPU | Instan (CoreDNS Golang binary) |
| **`iot_telegraf`** | `128 MB` | 0.25 CPU | Efisien (MQTT to OpenMetrics) |
| **`iot_dashboard_web`**| `128 MB` | 0.25 CPU | Ringan (Nginx Static HTML/JS) |
| **Deployed Apps** | `768 MB` | 1.00 CPU | Terpagari dari OOM Crash |
| **Total Stack Docker** | **~1.2 GB** | - | **Menyisakan ~2.8 GB RAM untuk OS Ubuntu & Host DBs** |

> [!NOTE]
> Layanan berat seperti **MinIO (S3)** dan **InfluxDB** telah dihapus dari Docker Compose stack karena redundan dengan filesystem native dan Prometheus. Langkah ini berhasil menghemat **~1.15 GB RAM**, menjamin server tidak mengalami *disk thrashing* saat proses build aplikasi berlangsung.
