# Personal Server Manager (PSM)

## Blueprint Teknis Lengkap --- v1.0

**Jenis aplikasi:** Self-hosted server management platform\
**Arsitektur:** Control Plane + Multi-Server Agent\
**Deployment:** Git Repository dan Upload ZIP\
**Antarmuka:** Dark Mode dan Light Mode\
**Target awal:** Ubuntu Server + Docker Engine\
**Status dokumen:** Blueprint rancangan, bukan implementasi production

------------------------------------------------------------------------

## 1. Visi dan tujuan

Personal Server Manager (PSM) adalah web application untuk mengelola
beberapa server milik sendiri melalui satu dashboard. Pengguna dapat
memantau resource server, mengelola Docker, melakukan deployment project
dari Git atau ZIP, dan melihat histori aktivitas tanpa harus
terus-menerus menggunakan SSH.

### Tujuan utama

1.  Mengelola beberapa server Linux dari satu control panel.
2.  Memantau CPU, RAM, disk, network, uptime, dan container.
3.  Mengelola Docker containers, images, volumes, dan networks.
4.  Melakukan deployment dari Git repository atau upload ZIP.
5.  Mengelola project, environment variables, deployment logs, dan
    rollback.
6.  Menyediakan audit trail dan kontrol keamanan untuk setiap tindakan
    penting.

### Batasan MVP

-   Target awal adalah Ubuntu Server dengan Docker Engine.
-   Akses dashboard awal hanya melalui LAN atau jaringan privat.
-   MVP tidak menyediakan terminal bebas atau arbitrary shell command.
-   Deployment hanya menjalankan job dan operasi yang sudah diizinkan.
-   Satu control plane dapat mengelola beberapa server agent.
-   Monitoring historis menggunakan Prometheus, bukan menyimpan semua
    sampel metrics di tabel aplikasi.

------------------------------------------------------------------------

## 2. Keputusan teknologi

  --------------------------------------------------------------------------
  Lapisan                 Teknologi               Tanggung jawab
  ----------------------- ----------------------- --------------------------
  Frontend                Next.js App Router +    Dashboard dan interaksi
                          TypeScript              pengguna

  UI                      Tailwind CSS +          Design system
                          shadcn/ui               

  Icons                   Lucide                  Ikon

  Charts                  Recharts                Grafik monitoring

  Tables                  TanStack Table          Tabel
                                                  server/container/project

  Form validation         React Hook Form + Zod   Validasi form

  Backend API             Python FastAPI          REST API dan business
                                                  logic

  ORM                     SQLAlchemy              Akses database

  Migration               Alembic                 Perubahan skema database

  Database                PostgreSQL              User, server, project,
                                                  job, deployment

  Agent                   Python                  Eksekusi job dan
                                                  pengumpulan data

  System metrics          psutil + Node Exporter  Metrik host

  Docker                  Docker SDK for Python + Container dan deployment
                          Docker Compose          

  Container metrics       cAdvisor                Metrik container

  Metrics storage         Prometheus              Time-series metrics

  Realtime                WebSocket Secure (WSS)  Event, status, dan log

  Queue awal              PostgreSQL job table    Antrean pekerjaan

  Authentication          Argon2id +              Autentikasi
                          access/refresh token    

  Deployment              Docker Compose          Menjalankan control plane
  --------------------------------------------------------------------------

### Prinsip pemilihan teknologi

-   Jangan menambahkan Redis atau message broker sebelum benar-benar
    diperlukan.
-   Gunakan PostgreSQL sebagai job queue awal dengan
    `FOR UPDATE SKIP LOCKED`.
-   Gunakan Prometheus untuk metrics historis.
-   Gunakan Docker SDK dari agent, bukan mengekspos Docker API ke
    jaringan.
-   Pisahkan proses frontend, API, worker, dan agent secara logis.

------------------------------------------------------------------------

## 3. Arsitektur keseluruhan

PSM menggunakan pola **Control Plane + Agent**.

``` text
                    LAPTOP / HP / BROWSER
                             |
                         HTTPS / WSS
                             |
                    +-------------------+
                    |    CONTROL PLANE  |
                    |                   |
                    | Next.js Frontend  |
                    | FastAPI Backend   |
                    | Job Worker        |
                    | PostgreSQL        |
                    +---------+---------+
                              |
                 Outbound authenticated WSS
                              |
             +----------------+----------------+
             |                |                |
        +----v-----+     +----v-----+     +----v-----+
        | Agent A  |     | Agent B  |     | Agent C  |
        | Ubuntu   |     | Ubuntu   |     | Ubuntu   |
        +----+-----+     +----+-----+     +----+-----+
             |                |                |
          Docker           Docker           Docker
          Engine           Engine           Engine
```

### 3.1 Control Plane

Control Plane adalah pusat pengelolaan. Komponennya:

-   **Frontend:** dashboard, server list, project, deployment,
    monitoring, settings.
-   **Backend API:** autentikasi, validasi, business logic, database
    access.
-   **Job Worker:** mengambil job dari database dan mengatur status
    pekerjaan.
-   **PostgreSQL:** menyimpan konfigurasi, histori, dan antrean.
-   **Metrics integration:** mengambil data dari Prometheus.

### 3.2 Server Agent

Setiap server yang dikelola memasang satu PSM Agent. Agent bertugas:

-   Registrasi dan autentikasi ke Control Plane.
-   Mengirim heartbeat dan system information.
-   Mengumpulkan metrics host.
-   Membaca inventory Docker.
-   Menjalankan job yang sudah diizinkan.
-   Menjalankan build dan Docker Compose deployment.
-   Mengirim progress dan logs.
-   Reconnect jika koneksi terputus.

### 3.3 Komunikasi

Agent memulai koneksi keluar ke Control Plane melalui HTTPS/WSS. Dengan
demikian, server di belakang NAT tidak perlu membuka port agent ke
internet.

Rekomendasi keamanan:

-   TLS untuk semua koneksi.
-   Token identitas unik per agent.
-   mTLS sebagai peningkatan untuk production.
-   Rotasi dan pencabutan credential agent.
-   Heartbeat dan reconnect dengan exponential backoff.
-   Validasi schema untuk setiap event.
-   Pisahkan channel agent dari WebSocket browser.

------------------------------------------------------------------------

## 4. Modul aplikasi

### 4.1 Overview Dashboard

-   Total server.
-   Server online, offline, degraded, maintenance.
-   CPU dan RAM rata-rata atau per server.
-   Disk usage.
-   Network traffic.
-   Container running/stopped.
-   Deployment terakhir.
-   Alert penting.

### 4.2 Server Management

-   Tambah dan hapus server.
-   Registrasi agent.
-   Edit nama dan deskripsi server.
-   OS, kernel, architecture, hostname.
-   Agent version dan last seen.
-   Status koneksi.
-   Resource usage.
-   Riwayat koneksi dan aktivitas.

### 4.3 Docker Management

-   Daftar container.
-   Detail container.
-   Start, stop, restart.
-   Remove container dengan konfirmasi.
-   Container logs.
-   Container stats.
-   Daftar images dan penghapusan image.
-   Daftar volumes.
-   Daftar networks.
-   Inspect informasi Docker yang aman ditampilkan.

### 4.4 Deployment Center

-   Git deployment.
-   ZIP deployment.
-   Dockerfile build.
-   Docker Compose deployment.
-   Build logs realtime.
-   Deployment progress.
-   Deployment history.
-   Cancel job jika aman.
-   Health check.
-   Rollback ke release sebelumnya.

### 4.5 Project Management

-   Daftar project.
-   Project detail.
-   Server tujuan.
-   Source type.
-   Repository dan branch.
-   Dockerfile/Compose path.
-   Environment variables.
-   Port dan domain metadata.
-   Container terkait.
-   Deployment history.
-   Resource usage.

### 4.6 Monitoring Center

-   Host metrics.
-   Container metrics.
-   CPU/RAM/disk/network history.
-   Prometheus integration.
-   Alert rules dan status alert.
-   Per-server dan per-container view.

### 4.7 Storage & Backup

-   Informasi Docker volumes.
-   Backup metadata.
-   Backup project configuration.
-   Backup database.
-   Backup file project jika diperlukan.
-   Restore workflow dengan konfirmasi dan audit.

### 4.8 Settings & Security

-   User management.
-   Role-based access control.
-   Agent credentials.
-   API credentials.
-   Audit logs.
-   Theme preference.
-   Retention settings.
-   Backup settings.

------------------------------------------------------------------------

## 5. Frontend blueprint

### 5.1 Route structure

``` text
/
├── login
├── dashboard
├── servers
│   ├── page
│   ├── add
│   └── [serverId]
│       ├── overview
│       ├── resources
│       ├── containers
│       ├── images
│       ├── volumes
│       ├── networks
│       └── settings
├── projects
│   ├── page
│   ├── create
│   └── [projectId]
│       ├── overview
│       ├── deployments
│       ├── logs
│       ├── environment
│       └── settings
├── deployments
│   ├── page
│   └── [deploymentId]
├── monitoring
│   ├── overview
│   ├── servers
│   └── containers
├── storage
├── activity
└── settings
    ├── profile
    ├── appearance
    ├── users
    ├── security
    └── system
```

### 5.2 UI libraries

-   Tailwind CSS.
-   shadcn/ui.
-   Lucide icons.
-   Recharts.
-   TanStack Table.
-   React Hook Form.
-   Zod.

### 5.3 Tema

Sediakan Dark Mode dan Light Mode. Simpan preferensi pada profil
pengguna agar konsisten lintas perangkat. Sediakan system preference
sebagai opsi tambahan.

### 5.4 UX penting

-   Tampilkan konfirmasi untuk tindakan destruktif.
-   Tampilkan status job dan progress yang jelas.
-   Gunakan pagination untuk daftar container dan deployment.
-   Log harus dapat di-scroll dan memiliki timestamp.
-   Jangan mengirim secret environment ke browser setelah disimpan.
-   Tampilkan indikator server stale/offline berdasarkan heartbeat.

------------------------------------------------------------------------

## 6. Database design

Gunakan PostgreSQL, SQLAlchemy, dan Alembic. Primary key utama
menggunakan UUID. Gunakan timezone-aware timestamps dan simpan waktu
dalam UTC.

### 6.1 ERD

``` mermaid
erDiagram
    USERS ||--o{ PROJECTS : owns
    USERS ||--o{ SERVERS : registers
    USERS ||--o{ AUDIT_LOGS : creates
    SERVERS ||--|| AGENTS : has
    SERVERS ||--o{ PROJECTS : hosts
    SERVERS ||--o{ SERVER_METRICS : reports
    SERVERS ||--o{ CONTAINERS : runs
    PROJECTS ||--o{ DEPLOYMENTS : has
    PROJECTS ||--o{ ENVIRONMENT_VARIABLES : configures
    DEPLOYMENTS ||--o{ DEPLOYMENT_LOGS : generates
    DEPLOYMENTS ||--o{ JOBS : schedules

    USERS {
      uuid id PK
      string name
      string email
      string password_hash
      string role
      string theme
      timestamp created_at
    }
    SERVERS {
      uuid id PK
      uuid owner_id FK
      string name
      string hostname
      string status
      string os_name
      timestamp created_at
    }
    AGENTS {
      uuid id PK
      uuid server_id FK
      string agent_version
      timestamp last_seen
    }
    PROJECTS {
      uuid id PK
      uuid server_id FK
      uuid owner_id FK
      string name
      string framework
      string source_type
      string status
    }
    DEPLOYMENTS {
      uuid id PK
      uuid project_id FK
      string commit_hash
      string image_tag
      string status
      timestamp started_at
      timestamp finished_at
    }
    JOBS {
      uuid id PK
      uuid server_id FK
      uuid deployment_id FK
      string job_type
      string status
      json payload
      timestamp created_at
    }
    DEPLOYMENT_LOGS {
      uuid id PK
      uuid deployment_id FK
      string level
      text message
      timestamp created_at
    }
    ENVIRONMENT_VARIABLES {
      uuid id PK
      uuid project_id FK
      string key
      text encrypted_value
    }
    CONTAINERS {
      uuid id PK
      uuid server_id FK
      string docker_id
      string name
      string image
      string status
    }
    SERVER_METRICS {
      uuid id PK
      uuid server_id FK
      float cpu_usage
      float memory_usage
      float disk_usage
      timestamp recorded_at
    }
    AUDIT_LOGS {
      uuid id PK
      uuid user_id FK
      string action
      string resource_type
      timestamp created_at
    }
```

Catatan: ERD ini menunjukkan relasi inti. Metrics historis sebaiknya
disimpan di Prometheus; tabel metrics PostgreSQL hanya diperlukan untuk
snapshot ringkas atau cache jika ada kebutuhan khusus.

### 6.2 Daftar tabel

  Tabel                     Tanggung jawab
  ------------------------- ----------------------------------------
  `users`                   Akun pengguna
  `user_sessions`           Sesi dan refresh token yang di-hash
  `servers`                 Metadata server
  `agents`                  Identitas agent dan status
  `agent_tokens`            Credential agent yang di-hash/dirotasi
  `projects`                Project aplikasi
  `project_sources`         Konfigurasi Git atau ZIP
  `deployments`             Riwayat deployment
  `deployment_logs`         Log build/deploy
  `jobs`                    Antrean pekerjaan
  `containers`              Cache inventory container
  `volumes`                 Cache inventory volumes
  `docker_networks`         Cache inventory networks
  `environment_variables`   Secret project terenkripsi
  `backups`                 Metadata backup
  `notifications`           Notifikasi
  `audit_logs`              Audit aktivitas

### 6.3 Kolom utama

#### `users`

  Kolom           Tipe           Catatan
  --------------- -------------- -----------------------------
  id              UUID           Primary key
  name            VARCHAR(100)   Nama pengguna
  email           VARCHAR(255)   Unique
  password_hash   TEXT           Argon2id
  role            VARCHAR(30)    owner/admin/operator/viewer
  theme           VARCHAR(20)    system/dark/light
  is_active       BOOLEAN        Status akun
  created_at      TIMESTAMPTZ    UTC
  updated_at      TIMESTAMPTZ    UTC

#### `servers`

  Kolom          Tipe           Catatan
  -------------- -------------- ---------------------------------------------
  id             UUID           Primary key
  owner_id       UUID           FK users
  name           VARCHAR(100)   Nama tampilan
  hostname       VARCHAR(255)   Hostname
  description    TEXT           Opsional
  os_name        VARCHAR(100)   Nama OS
  os_version     VARCHAR(100)   Versi OS
  architecture   VARCHAR(30)    amd64/arm64
  status         VARCHAR(30)    online/offline/degraded/maintenance/pending
  last_seen      TIMESTAMPTZ    Heartbeat terakhir
  created_at     TIMESTAMPTZ    UTC

#### `agents`

  Kolom             Tipe          Catatan
  ----------------- ------------- --------------------
  id                UUID          Primary key
  server_id         UUID          FK servers, unique
  agent_version     VARCHAR(30)   Versi agent
  credential_hash   TEXT          Hash credential
  connected_at      TIMESTAMPTZ   Koneksi terakhir
  last_seen         TIMESTAMPTZ   Heartbeat
  revoked_at        TIMESTAMPTZ   Null jika aktif

#### `projects`

  Kolom         Tipe           Catatan
  ------------- -------------- -----------------------------
  id            UUID           Primary key
  server_id     UUID           FK servers
  owner_id      UUID           FK users
  name          VARCHAR(150)   Nama project
  description   TEXT           Opsional
  framework     VARCHAR(50)    Next.js/Laravel/FastAPI/dll
  source_type   VARCHAR(20)    git/upload
  status        VARCHAR(30)    active/stopped/failed
  created_at    TIMESTAMPTZ    UTC

#### `project_sources`

  Kolom               Tipe           Catatan
  ------------------- -------------- ------------------------------------------
  id                  UUID           Primary key
  project_id          UUID           FK projects
  repository_url      TEXT           URL Git
  branch              VARCHAR(150)   Branch
  credential_ref      TEXT           Referensi secret, bukan secret plaintext
  dockerfile_path     VARCHAR(255)   Default Dockerfile
  compose_path        VARCHAR(255)   Path Compose
  upload_object_key   TEXT           Lokasi arsip ZIP

#### `deployments`

  ---------------------------------------------------------------------------------------------------------------------------
  Kolom                   Tipe                    Catatan
  ----------------------- ----------------------- ---------------------------------------------------------------------------
  id                      UUID                    Primary key

  project_id              UUID                    FK projects

  version                 INTEGER                 Nomor release

  commit_hash             VARCHAR(100)            Jika sumber Git

  image_tag               VARCHAR(255)            Image release

  status                  VARCHAR(30)             queued/preparing/building/deploying/success/failed/cancelled/rolling_back

  triggered_by            UUID                    FK users

  started_at              TIMESTAMPTZ             Mulai

  finished_at             TIMESTAMPTZ             Selesai

  duration_seconds        INTEGER                 Durasi
  ---------------------------------------------------------------------------------------------------------------------------

#### `jobs`

  Kolom           Tipe          Catatan
  --------------- ------------- -----------------------------------------
  id              UUID          Primary key
  server_id       UUID          FK servers
  deployment_id   UUID          FK deployments, nullable
  job_type        VARCHAR(50)   Jenis handler
  payload         JSONB         Data tervalidasi
  status          VARCHAR(30)   queued/running/success/failed/cancelled
  priority        INTEGER       Prioritas
  attempts        INTEGER       Jumlah percobaan
  max_attempts    INTEGER       Batas retry
  locked_at       TIMESTAMPTZ   Waktu claim
  created_at      TIMESTAMPTZ   UTC
  finished_at     TIMESTAMPTZ   UTC

#### `deployment_logs`

  Kolom           Tipe          Catatan
  --------------- ------------- --------------------
  id              UUID          Primary key
  deployment_id   UUID          FK deployments
  sequence        BIGINT        Urutan log
  level           VARCHAR(20)   info/warning/error
  message         TEXT          Isi log
  created_at      TIMESTAMPTZ   UTC

Tambahkan unique constraint pada `(deployment_id, sequence)`.

#### `environment_variables`

  Kolom             Tipe           Catatan
  ----------------- -------------- ---------------
  id                UUID           Primary key
  project_id        UUID           FK projects
  key               VARCHAR(255)   Nama variabel
  encrypted_value   BYTEA/TEXT     Ciphertext
  created_at        TIMESTAMPTZ    UTC
  updated_at        TIMESTAMPTZ    UTC

### 6.4 Index dan constraint

Minimal:

-   Unique index `users.email`.
-   Index `servers.status`, `servers.last_seen`.
-   Unique `agents.server_id`.
-   Index `projects.server_id`, `projects.owner_id`.
-   Index `deployments.project_id`, `deployments.created_at`.
-   Index `jobs.status`, `jobs.server_id`, `jobs.created_at`.
-   Index `deployment_logs.deployment_id`.
-   Index `audit_logs.created_at`, `audit_logs.user_id`.

Gunakan foreign key dan aturan delete yang eksplisit. Hindari cascade
delete untuk data deployment dan audit yang harus dipertahankan.

### 6.5 Retention

-   Deployment logs: atur retention, misalnya 30--90 hari.
-   Audit logs: retensi lebih panjang sesuai kebutuhan.
-   Job records: arsipkan job lama.
-   Prometheus: atur retention berdasarkan kapasitas disk.
-   Jangan menyimpan password, token, atau secret dalam audit log.

------------------------------------------------------------------------

## 7. REST API blueprint

Base path:

``` text
/api/v1
```

Semua endpoint harus memiliki autentikasi dan authorization yang sesuai.
Endpoint agent menggunakan identitas agent, bukan token user.

### 7.1 Authentication

  Method   Endpoint                  Fungsi
  -------- ------------------------- -----------------
  POST     `/auth/login`             Login
  POST     `/auth/logout`            Logout
  POST     `/auth/refresh`           Refresh session
  GET      `/auth/me`                Profil pengguna
  POST     `/auth/change-password`   Ganti password

### 7.2 Servers

  Method   Endpoint                    Fungsi
  -------- --------------------------- ---------------------------
  GET      `/servers`                  Daftar server
  POST     `/servers`                  Membuat registrasi server
  GET      `/servers/{id}`             Detail server
  PATCH    `/servers/{id}`             Edit metadata
  DELETE   `/servers/{id}`             Hapus/unregister server
  GET      `/servers/{id}/status`      Status server
  GET      `/servers/{id}/metrics`     Snapshot metrics
  POST     `/servers/{id}/reconnect`   Meminta reconnect
  GET      `/servers/{id}/agent`       Informasi agent

### 7.3 Agent

  Method   Endpoint                       Fungsi
  -------- ------------------------------ --------------------------------
  POST     `/agents/register`             Registrasi agent
  POST     `/agents/heartbeat`            Heartbeat
  POST     `/agents/metrics`              Kirim snapshot metrics
  POST     `/agents/jobs/{id}/claim`      Claim job bila memakai polling
  POST     `/agents/jobs/{id}/complete`   Hasil job
  POST     `/agents/jobs/{id}/logs`       Kirim log
  WS       `/agents/connect`              Koneksi WSS agent

Pilih satu mekanisme job delivery utama. Untuk rancangan ini, gunakan
koneksi WSS persisten untuk notifikasi job dan endpoint HTTPS untuk
acknowledgment/log batch. Jika WSS terputus, agent dapat polling sebagai
fallback.

### 7.4 Docker

  Method   Endpoint                                   Fungsi
  -------- ------------------------------------------ ------------------
  GET      `/servers/{id}/containers`                 Daftar container
  GET      `/servers/{id}/containers/{cid}`           Detail container
  POST     `/servers/{id}/containers/{cid}/start`     Start
  POST     `/servers/{id}/containers/{cid}/stop`      Stop
  POST     `/servers/{id}/containers/{cid}/restart`   Restart
  DELETE   `/servers/{id}/containers/{cid}`           Remove
  GET      `/servers/{id}/containers/{cid}/logs`      Logs
  GET      `/servers/{id}/containers/{cid}/stats`     Stats
  GET      `/servers/{id}/images`                     Images
  GET      `/servers/{id}/volumes`                    Volumes
  GET      `/servers/{id}/networks`                   Networks

### 7.5 Projects

  Method   Endpoint                       Fungsi
  -------- ------------------------------ --------------------
  GET      `/projects`                    Daftar project
  POST     `/projects`                    Buat project
  GET      `/projects/{id}`               Detail project
  PATCH    `/projects/{id}`               Update project
  DELETE   `/projects/{id}`               Hapus project
  GET      `/projects/{id}/containers`    Container project
  GET      `/projects/{id}/deployments`   Deployment history
  GET      `/projects/{id}/environment`   Daftar environment
  PUT      `/projects/{id}/environment`   Update environment

### 7.6 Deployments

  Method   Endpoint                              Fungsi
  -------- ------------------------------------- ---------------------
  POST     `/deployments/git`                    Buat Git deployment
  POST     `/deployments/upload-sessions`        Buat upload session
  POST     `/deployments/{id}/finalize-upload`   Finalisasi upload
  POST     `/deployments/compose`                Compose deployment
  GET      `/deployments`                        Daftar deployment
  GET      `/deployments/{id}`                   Detail deployment
  POST     `/deployments/{id}/cancel`            Cancel
  POST     `/deployments/{id}/rollback`          Rollback
  GET      `/deployments/{id}/logs`              Log deployment

Gunakan upload streaming/multipart atau object storage; hindari memuat
ZIP besar seluruhnya ke RAM API.

### 7.7 Monitoring

  Method   Endpoint                        Fungsi
  -------- ------------------------------- ------------------------
  GET      `/monitoring/overview`          Ringkasan semua server
  GET      `/monitoring/servers/{id}`      Metrics server
  GET      `/monitoring/containers/{id}`   Metrics container
  GET      `/monitoring/history`           Historical metrics
  GET      `/monitoring/alerts`            Daftar alert

### 7.8 WebSocket frontend

``` text
/ws/servers/{server_id}/metrics
/ws/servers/{server_id}/events
/ws/deployments/{deployment_id}/logs
/ws/containers/{container_id}/logs
```

Contoh event:

``` json
{
  "event": "server.metrics.updated",
  "server_id": "uuid",
  "data": {
    "cpu_usage": 35.5,
    "memory_usage": 62.1,
    "disk_usage": 48.2
  }
}
```

Validasi authorization pada saat koneksi dan untuk setiap subscription.
Jangan menganggap UUID sebagai bukti akses.

------------------------------------------------------------------------

## 8. Deployment engine

PSM memiliki dua source provider: Git dan ZIP. Keduanya masuk ke
pipeline build/deploy yang sama.

### 8.1 Git workflow

``` text
User memilih repository dan branch
             |
             v
       Control Plane
             |
       Buat deployment
             |
          Buat job
             |
             v
          Agent
             |
       Clone / Fetch
             |
      Validasi source
             |
        Docker build
             |
       Compose deploy
             |
        Health check
             |
       Success / Failed
             |
       Simpan log dan status
```

Konfigurasi contoh:

``` yaml
project:
  name: sample-app
  source:
    type: git
    repository: https://github.com/example/sample-app.git
    branch: main
  build:
    type: dockerfile
    dockerfile: Dockerfile
  deploy:
    type: compose
    compose_file: docker-compose.yml
```

Repository privat menggunakan credential khusus dengan permission
minimum. Jangan meminta atau menyimpan password akun Git secara
plaintext.

### 8.2 ZIP workflow

1.  Browser meminta upload session.
2.  Backend membuat upload ID dan batas ukuran.
3.  Browser upload file secara streaming/multipart.
4.  File disimpan di temporary/object storage.
5.  Agent mengambil file menggunakan signed URL berumur pendek.
6.  Agent memverifikasi SHA-256.
7.  Agent memvalidasi dan mengekstrak ZIP ke workspace terisolasi.
8.  Pipeline build/deploy dimulai.

Validasi wajib:

-   Cegah ZIP path traversal (`../`).
-   Tolak symlink yang tidak diperlukan.
-   Batasi ukuran arsip dan hasil ekstraksi.
-   Batasi jumlah file dan kedalaman direktori.
-   Batasi waktu ekstraksi.
-   Jangan mengeksekusi file sebelum validasi.
-   Hapus temporary file sesuai kebijakan.

### 8.3 Release directory

``` text
/opt/psm/
├── workspaces/
│   └── project-uuid/
├── releases/
│   └── project-uuid/
│       ├── release-001/
│       ├── release-002/
│       └── release-003/
├── current/
│   └── project-uuid/
└── backups/
```

Deployment:

1.  Ambil source.
2.  Buat release directory baru.
3.  Validasi Dockerfile/Compose.
4.  Build image dengan tag unik.
5.  Deploy menggunakan nama Compose project yang konsisten.
6.  Jalankan health check.
7.  Tandai release sukses.
8.  Pertahankan metadata release lama untuk rollback.

Rollback harus menyimpan image tag, konfigurasi deployment, dan metadata
release. Rollback aplikasi tidak otomatis membatalkan perubahan schema
database; migration database perlu strategi kompatibilitas dan backup
tersendiri.

### 8.4 Build isolation

Build dari source pengguna adalah aktivitas berisiko tinggi. Untuk
production:

-   Jalankan build dengan batas CPU, RAM, disk, dan waktu.
-   Gunakan workspace terpisah per deployment.
-   Jangan mount Docker socket ke container build.
-   Pertimbangkan builder terisolasi atau server build khusus.
-   Jangan menjalankan build sebagai root jika dapat dihindari.
-   Batasi akses jaringan build bila memungkinkan.
-   Bersihkan image dan workspace sementara sesuai retention.

------------------------------------------------------------------------

## 9. Server Agent blueprint

### 9.1 Struktur folder agent

``` text
psm-agent/
├── app/
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── identity.py
│   │   ├── connection.py
│   │   ├── heartbeat.py
│   │   └── event_bus.py
│   ├── collectors/
│   │   ├── cpu.py
│   │   ├── memory.py
│   │   ├── disk.py
│   │   ├── network.py
│   │   └── system.py
│   ├── docker/
│   │   ├── client.py
│   │   ├── containers.py
│   │   ├── images.py
│   │   ├── volumes.py
│   │   ├── networks.py
│   │   └── logs.py
│   ├── deployment/
│   │   ├── git.py
│   │   ├── upload.py
│   │   ├── builder.py
│   │   ├── compose.py
│   │   ├── healthcheck.py
│   │   └── rollback.py
│   ├── jobs/
│   │   ├── executor.py
│   │   ├── registry.py
│   │   └── handlers.py
│   └── security/
│       ├── authentication.py
│       ├── validation.py
│       └── permissions.py
├── tests/
└── requirements.txt
```

### 9.2 Startup lifecycle

1.  Baca konfigurasi lokal.
2.  Baca identitas server.
3.  Hubungkan ke Control Plane.
4.  Autentikasi agent.
5.  Kirim informasi sistem.
6.  Mulai heartbeat.
7.  Mulai metrics collector.
8.  Terima notifikasi job.
9.  Validasi job terhadap allowlist handler.
10. Eksekusi job.
11. Kirim progress, logs, dan hasil.
12. Reconnect jika koneksi terputus.

### 9.3 Interval awal

  Aktivitas              Interval
  -------------------- ----------
  Heartbeat              15 detik
  CPU metrics             5 detik
  RAM metrics             5 detik
  Disk metrics           30 detik
  Docker inventory       30 detik
  Container stats        10 detik
  System information      5 menit

Interval dapat diubah berdasarkan kapasitas server. Untuk host 4 GB RAM,
hindari polling terlalu agresif.

### 9.4 Contoh heartbeat

``` json
{
  "agent_id": "agent-001",
  "server_id": "server-001",
  "agent_version": "0.1.0",
  "status": "online",
  "timestamp": "2026-10-30T07:00:00Z"
}
```

### 9.5 Contoh job

``` json
{
  "job_id": "job-123",
  "type": "container.restart",
  "payload": {
    "container_id": "abc123"
  }
}
```

Handler harus memvalidasi:

-   Job ID.
-   Identitas server.
-   Jenis job yang diizinkan.
-   Schema payload.
-   Hak akses.
-   Batas waktu.
-   Idempotency dan status job.

Jangan menyediakan endpoint arbitrary command seperti `POST /execute`
yang menerima shell command dari pengguna.

------------------------------------------------------------------------

## 10. Struktur monorepo

``` text
personal-server-manager/
├── apps/
│   ├── web/
│   │   ├── app/
│   │   ├── components/
│   │   ├── features/
│   │   │   ├── dashboard/
│   │   │   ├── servers/
│   │   │   ├── containers/
│   │   │   ├── deployments/
│   │   │   ├── projects/
│   │   │   ├── monitoring/
│   │   │   └── settings/
│   │   ├── hooks/
│   │   ├── lib/
│   │   ├── types/
│   │   └── package.json
│   ├── api/
│   │   ├── app/
│   │   │   ├── api/v1/
│   │   │   ├── core/
│   │   │   ├── database/
│   │   │   ├── models/
│   │   │   ├── schemas/
│   │   │   ├── repositories/
│   │   │   ├── services/
│   │   │   ├── workers/
│   │   │   ├── websocket/
│   │   │   └── main.py
│   │   ├── migrations/
│   │   ├── tests/
│   │   └── requirements.txt
│   └── agent/
│       ├── app/
│       │   ├── core/
│       │   ├── collectors/
│       │   ├── docker/
│       │   ├── deployment/
│       │   ├── jobs/
│       │   ├── security/
│       │   └── main.py
│       ├── tests/
│       └── requirements.txt
├── packages/
│   ├── shared-types/
│   ├── api-client/
│   └── protocol/
├── infrastructure/
│   ├── docker/
│   ├── prometheus/
│   ├── grafana/
│   ├── systemd/
│   └── scripts/
├── docs/
│   ├── architecture.md
│   ├── database.md
│   ├── api.md
│   ├── deployment.md
│   ├── security.md
│   └── agent-installation.md
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

------------------------------------------------------------------------

## 11. Control Plane Docker Compose awal

Contoh berikut adalah kerangka awal development, bukan file production
final.

``` yaml
services:
  web:
    build: ./apps/web
    container_name: psm-web
    restart: unless-stopped
    ports:
      - "3005:3000"
    depends_on:
      - api

  api:
    build: ./apps/api
    container_name: psm-api
    restart: unless-stopped
    expose:
      - "8000"
    environment:
      DATABASE_URL: ${DATABASE_URL}
    depends_on:
      - postgres

  postgres:
    image: postgres:17
    container_name: psm-postgres
    restart: unless-stopped
    volumes:
      - psm-postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: psm
      POSTGRES_USER: psm
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}

volumes:
  psm-postgres:
```

Sebelum production, tambahkan:

-   Health checks.
-   Migration job.
-   Worker service.
-   Upload storage.
-   Resource limits.
-   Network isolation.
-   PostgreSQL backup.
-   Secret management.
-   Log rotation.
-   Non-root container users.
-   Pinned image versions.
-   TLS/reverse proxy sesuai kebutuhan.

------------------------------------------------------------------------

## 12. Integrasi dengan homelab yang sudah ada

Pertahankan port layanan yang telah ditetapkan.

  Layanan                      Port Integrasi PSM
  ----------------- --------------- ---------------------
  Nextcloud Snap                 80 Tidak diubah
  Prometheus Snap              9001 Sumber metrics
  Cockpit                      9090 Monitoring tambahan
  Mosquitto                    1883 Tidak diubah
  Grafana                      3001 Dashboard tambahan
  Uptime Kuma                  3002 Uptime monitoring
  PSM Web                      3005 Dashboard baru
  PSM API             8000 internal Backend
  PSM PostgreSQL      5432 internal Database

### Strategi monitoring

-   Integrasikan Prometheus yang sudah ada.
-   Gunakan Node Exporter pada server Linux.
-   Gunakan cAdvisor untuk container metrics.
-   PSM membaca data melalui Prometheus HTTP API.
-   Hindari memasang Prometheus kedua tanpa kebutuhan.
-   Atur retention dan kapasitas disk.

### Resource constraint

Server utama memiliki RAM sekitar 4 GB. Karena itu:

-   Mulai dengan satu worker deployment.
-   Batasi concurrency build menjadi satu.
-   Gunakan monitoring yang sudah tersedia.
-   Batasi log retention.
-   Hindari service tambahan yang tidak dibutuhkan.
-   Pertimbangkan build pada server terpisah jika beban meningkat.

------------------------------------------------------------------------

## 13. Security blueprint

PSM mempunyai hak untuk mengendalikan Docker. Docker socket pada
praktiknya memberikan kemampuan sangat tinggi terhadap host. Karena itu,
agent harus dianggap sebagai komponen berprivilege tinggi.

### 13.1 Authentication

-   Password hashing Argon2id.
-   Access token berumur pendek.
-   Refresh token yang dapat dicabut dan disimpan dalam bentuk hash.
-   Rate limiting login.
-   Session revocation.
-   MFA dapat ditambahkan setelah MVP.

### 13.2 Authorization

Role awal:

  Role       Hak akses
  ---------- ------------------------------------------------------
  Owner      Seluruh pengaturan dan tindakan
  Admin      Mengelola server, project, dan user sesuai kebijakan
  Operator   Operasi server dan deployment yang diizinkan
  Viewer     Membaca dashboard dan metrics

Terapkan authorization pada setiap resource dan endpoint. Jangan hanya
menyembunyikan tombol pada frontend.

### 13.3 Agent security

-   Credential unik per agent.
-   Credential dapat dirotasi dan dicabut.
-   TLS/WSS.
-   mTLS untuk production.
-   Job allowlist.
-   Validasi payload.
-   Replay protection dan expiry.
-   Audit setiap job.
-   Jangan membuka Docker TCP API tanpa pengamanan.
-   Jangan memberikan akses terminal bebas pada MVP.

### 13.4 Deployment security

-   Batasi ukuran ZIP.
-   Cegah path traversal.
-   Isolasi workspace.
-   Validasi Docker Compose.
-   Batasi privileged mode.
-   Batasi host path mounts.
-   Batasi resource build.
-   Jangan mount Docker socket ke build container.
-   Enkripsi Git credentials dan environment secrets.
-   Masking secret pada logs.

### 13.5 Secret management

Gunakan encryption at rest dengan kunci enkripsi terpisah dari database.
Simpan master key melalui secret file atau mekanisme secret management
yang sesuai. Sediakan proses key rotation dan backup kunci yang aman.

### 13.6 Audit

Catat sekurangnya:

-   User login/logout.
-   Server registration/removal.
-   Container start/stop/restart/remove.
-   Project create/update/delete.
-   Deployment trigger/cancel/rollback.
-   Environment variable changes.
-   Agent credential rotation.
-   Backup/restore.

Jangan mencatat password, token, private key, atau nilai secret ke audit
log.

------------------------------------------------------------------------

## 14. Roadmap implementasi

Estimasi berikut untuk satu developer yang mengerjakan secara bertahap.
Durasi dapat berubah sesuai pengalaman dan hasil pengujian.

### Fase 1 --- Project Foundation (3--5 hari)

-   [ ] Setup monorepo.
-   [ ] Setup Next.js + TypeScript.
-   [ ] Setup FastAPI.
-   [ ] Setup PostgreSQL.
-   [ ] Setup SQLAlchemy.
-   [ ] Setup Alembic.
-   [ ] Authentication.
-   [ ] Dashboard layout.
-   [ ] Dark/Light Mode.

**Hasil:** aplikasi dapat dijalankan secara lokal, login, dan
menampilkan dashboard dasar.

### Fase 2 --- Multi-server Agent (4--6 hari)

-   [ ] Agent identity.
-   [ ] Agent registration.
-   [ ] Agent authentication.
-   [ ] Heartbeat.
-   [ ] Server inventory.
-   [ ] WSS connection.
-   [ ] Reconnect handling.
-   [ ] Server online/offline status.

**Hasil:** control plane dapat mendaftarkan dan memantau setidaknya dua
server.

### Fase 3 --- Server Monitoring (3--5 hari)

-   [ ] CPU.
-   [ ] RAM.
-   [ ] Disk.
-   [ ] Network.
-   [ ] Uptime.
-   [ ] Prometheus integration.
-   [ ] Historical charts.
-   [ ] Monitoring dashboard.

**Hasil:** dashboard menampilkan metrics server secara aktual dan
historis.

### Fase 4 --- Docker Management (5--7 hari)

-   [ ] Container inventory.
-   [ ] Start/stop/restart.
-   [ ] Container logs.
-   [ ] Container stats.
-   [ ] Image management.
-   [ ] Volume inventory.
-   [ ] Network inventory.
-   [ ] Audit actions.

**Hasil:** Docker pada server terdaftar dapat dikelola melalui
dashboard.

### Fase 5 --- Deployment Engine (7--12 hari)

-   [ ] Git source provider.
-   [ ] ZIP upload.
-   [ ] Upload validation.
-   [ ] Dockerfile build.
-   [ ] Compose deployment.
-   [ ] Job queue.
-   [ ] Realtime logs.
-   [ ] Health checks.
-   [ ] Deployment history.
-   [ ] Rollback.

**Hasil:** project dapat dikirim dari laptop ke server dan di-deploy
melalui browser.

### Fase 6 --- Project Management (4--6 hari)

-   [ ] Project dashboard.
-   [ ] Project detail.
-   [ ] Environment management.
-   [ ] Port metadata.
-   [ ] Container association.
-   [ ] Resource usage.

**Hasil:** seluruh project dapat dikelola dari satu halaman.

### Fase 7 --- Security & Backup (4--7 hari)

-   [ ] Role-based access.
-   [ ] Audit logs.
-   [ ] Agent credential rotation.
-   [ ] Secret encryption.
-   [ ] Database backup.
-   [ ] Project backup.
-   [ ] Restore testing.

**Hasil:** fitur administrasi dan pemulihan dasar siap diuji.

### Fase 8 --- Production & Optimization (3--5 hari)

-   [ ] Integration testing.
-   [ ] Error handling.
-   [ ] Resource optimization.
-   [ ] Agent update mechanism.
-   [ ] Deployment production.
-   [ ] Documentation.
-   [ ] Security review.

**Hasil:** PSM versi 0.1.0 siap digunakan untuk homelab dengan batasan
MVP yang terdokumentasi.

**Estimasi total: sekitar 33--53 hari kerja.**

------------------------------------------------------------------------

## 15. MVP acceptance criteria

Versi 0.1.0 dinyatakan memenuhi target jika:

-   [ ] Pengguna dapat login.
-   [ ] Pengguna dapat memilih Dark/Light Mode.
-   [ ] Minimal dua server Ubuntu dapat didaftarkan.
-   [ ] Status online/offline server tampil benar.
-   [ ] CPU, RAM, disk, dan network dapat dilihat.
-   [ ] Container dari kedua server dapat ditampilkan.
-   [ ] Container dapat start, stop, dan restart.
-   [ ] Container logs dapat dibaca.
-   [ ] Project dapat dibuat dari Git.
-   [ ] Project dapat dibuat dari ZIP.
-   [ ] Docker Compose dapat dijalankan.
-   [ ] Build logs tampil secara realtime.
-   [ ] Deployment history tersimpan.
-   [ ] Rollback release aplikasi dapat dilakukan.
-   [ ] Audit logs mencatat tindakan penting.
-   [ ] Agent credential dapat dicabut.
-   [ ] Backend dan database tidak terekspos tanpa kebutuhan.

------------------------------------------------------------------------

## 16. Urutan pengerjaan yang disarankan

Jangan mulai dari deployment engine. Urutan yang paling aman:

1.  Fondasi monorepo.
2.  Frontend dan backend.
3.  Database dan authentication.
4.  Agent registration.
5.  Heartbeat dan server status.
6.  Monitoring.
7.  Docker management.
8.  Job queue.
9.  Git deployment.
10. ZIP deployment.
11. Rollback.
12. Security hardening dan backup.

Deployment bergantung pada komunikasi agent, autentikasi, job queue, dan
Docker manager. Fondasi yang stabil akan mengurangi kesulitan debugging.

------------------------------------------------------------------------

## 17. Development workflow

Pengembangan dilakukan dari laptop Windows, sedangkan Control Plane
dijalankan di mini PC Ubuntu.

``` text
LENOVO WINDOWS
  |
  +-- VS Code
  +-- Next.js
  +-- FastAPI
  +-- Python Agent
  +-- Git
        |
        v
      GITHUB
        |
        v
UBUNTU HOMELAB
  |
  +-- PSM Control Plane
  +-- PostgreSQL
  +-- PSM Agent
  +-- Prometheus integration
```

Workflow:

1.  Coding dan testing lokal di Windows.
2.  Commit ke Git.
3.  Push ke repository.
4.  Deploy Control Plane ke Ubuntu.
5.  Install agent pada server target.
6.  Verifikasi koneksi dan metrics.
7.  Uji deployment pada project dummy.
8.  Baru gunakan untuk project penting setelah backup dan rollback
    teruji.

------------------------------------------------------------------------

## 18. Keputusan arsitektur final

  Area                       Keputusan
  -------------------------- -----------------------------
  Product                    Personal Server Manager
  Version target             0.1.0
  Frontend                   Next.js + TypeScript
  UI                         Tailwind + shadcn/ui
  Theme                      Dark + Light
  Backend                    FastAPI
  ORM                        SQLAlchemy
  Migration                  Alembic
  Database                   PostgreSQL
  Agent                      Python
  Docker                     Docker SDK + Compose
  Monitoring                 Prometheus
  Host metrics               Node Exporter
  Container metrics          cAdvisor
  Realtime                   WebSocket Secure
  Job queue                  PostgreSQL
  Deployment source          Git + ZIP
  Architecture               Control Plane + Multi-Agent
  Initial access             LAN/private network
  Control Plane deployment   Docker Compose

------------------------------------------------------------------------

## 19. Langkah pertama: Fase 1

Mulai dengan membuat repository:

``` text
personal-server-manager
```

Implementasi pertama harus menghasilkan:

1.  Struktur monorepo.
2.  Next.js berjalan.
3.  FastAPI berjalan.
4.  PostgreSQL berjalan.
5.  Alembic migration pertama.
6.  Login dan logout.
7.  Dashboard layout.
8.  Dark/Light Mode.
9.  Docker Compose untuk development.

Jangan menginstal atau mengubah service homelab yang sudah ada sebelum
aplikasi lokal berhasil diuji.

### Catatan port homelab

Pertahankan konfigurasi layanan yang sudah digunakan:

-   Nextcloud: `80`
-   Prometheus: `9001`
-   Cockpit: `9090`
-   MQTT: `1883`
-   Grafana: `3001`
-   Uptime Kuma: `3002`
-   PSM Web: `3005`
-   PSM API: internal `8000`
-   PSM PostgreSQL: internal `5432`

**Target akhir:** satu dashboard pribadi yang dapat memantau beberapa
server, mengelola Docker, dan melakukan deployment project dari laptop
melalui browser.

------------------------------------------------------------------------

*Dokumen ini merupakan blueprint teknis awal. Detail implementasi,
threat model, skema migration, dan konfigurasi production harus
divalidasi dan diuji sebelum digunakan untuk mengelola server penting.*
