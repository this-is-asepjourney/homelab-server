# Personal Server Manager (PSM) Architecture

Personal Server Manager (PSM) is a self-hosted server management platform architected using the **Control Plane + Multi-Server Agent** pattern.

```
                    LAPTOP / HP / BROWSER
                             |
                         HTTPS / WSS
                             |
                    +-------------------+
                    |    CONTROL PLANE  |
                    |                   |
                    | Next.js Frontend  | (Port 3005)
                    | FastAPI Backend   | (Port 8000)
                    | Job Worker        |
                    | PostgreSQL        | (Port 5432)
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

## Core Components

### 1. Control Plane
- **Frontend (Next.js 14 App Router, TypeScript, Tailwind CSS, Lucide)**:
  - Runs on port `3005` to avoid colliding with homelab services (e.g. Grafana on `3001`, Uptime Kuma on `3002`).
  - Supports Dark Mode and Light Mode with system preference toggle.
  - Complete navigation: Dashboard, Servers, Projects, Deployments, Monitoring, Storage, Activity, Settings.
- **Backend API (FastAPI, Python 3.13, Pydantic v2)**:
  - Exposes REST API v1 (`/api/v1`) and real-time WebSockets.
  - JWT authentication with short-lived access tokens and revocable refresh tokens.
  - Argon2id password hashing.
  - AES-Fernet encryption for environment variables.
- **Database (PostgreSQL + SQLAlchemy 2.0)**:
  - Primary keys are UUIDs.
  - Stores users, sessions, servers, agents, projects, deployments, deployment logs, job queues, containers, volumes, metrics, and audit logs.
  - Queue engine uses `FOR UPDATE SKIP LOCKED`.
  - Zero-config SQLite fallback for local development and offline unit testing.

### 2. Multi-Server Agent
- Installed on each managed Linux node (Ubuntu Server).
- Outbound persistent WebSocket connection to Control Plane with exponential backoff reconnect.
- Telemetry collection via `psutil` (CPU, RAM, Disk, Network IO, System uptime).
- Docker Engine management via Docker SDK and CLI.
- Strict allowlist job executor preventing arbitrary shell execution.

### 3. Homelab Port Mapping
| Service | Port | Status |
|---|---|---|
| Nextcloud Snap | 80 | Preserved |
| Mosquitto MQTT | 1883 | Preserved |
| Grafana | 3001 | Preserved |
| Uptime Kuma | 3002 | Preserved |
| **PSM Web** | **3005** | **New Dashboard** |
| **PSM API** | **8000** | **Backend REST/WSS** |
| Cockpit | 9090 | Preserved |
| Prometheus Snap | 9001 | Metrics Source |
| PSM PostgreSQL | 5432 | Internal DB |

