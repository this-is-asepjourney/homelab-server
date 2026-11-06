# Personal Server Manager (PSM)

> **Self-hosted Multi-Server Management Platform**  
> Control Plane + Multi-Server Agent Architecture with Git/ZIP Deployments, Real-time Monitoring & Docker Orchestration.

---

## 🌟 Highlights

- **Control Plane + Agent Architecture**: Manage multiple Linux / Ubuntu servers behind NAT from a single web dashboard.
- **Port-Conflict Free**: Preserves existing homelab services (Nextcloud on `80`, Prometheus on `9001`, Cockpit on `9090`, Grafana on `3001`, Uptime Kuma on `3002`). PSM Web runs on `3005`, PSM API on `8000`.
- **Zero Arbitrary Shell Execution**: Hardened security using strict handler allowlists (`container.start`, `container.stop`, `deployment.git`, `deployment.rollback`, etc.).
- **Dual Source Deployment**: Deploy directly from Git repositories or drag-and-drop ZIP archives with Zip Slip protection.
- **Real-Time Telemetry & Logs**: Outbound WebSocket Secure (WSS) streaming of CPU, memory, disk, network, and live container build logs.
- **Encrypted Secrets**: Project environment variables are encrypted at rest using AES-Fernet encryption.
- **Seamless Local & Docker Execution**: Production-ready `docker-compose.yml` with SQLite fallback for offline development.

---

## 📁 Monorepo Structure

```text
personal-server-manager/
├── apps/
│   ├── web/                     # Next.js 14 App Router + TypeScript + Tailwind CSS
│   ├── api/                     # Python FastAPI Backend + SQLAlchemy 2.0 + WebSockets
│   └── agent/                   # Python Agent with psutil & Docker SDK
├── packages/
│   ├── shared-types/            # Shared TypeScript data models
│   ├── protocol/                # Agent event & payload protocols
│   └── api-client/              # Client SDK
├── infrastructure/
│   ├── docker/                  # Dockerfile.api, Dockerfile.web, Dockerfile.agent
│   ├── systemd/                 # psm-agent.service systemd unit
│   ├── prometheus/              # Prometheus integration
│   └── scripts/                 # install-agent.sh installation script
├── docs/                        # Complete technical documentation
├── docker-compose.yml           # Multi-container orchestration
├── .env.example                 # Environment configuration template
└── README.md
```

---

## 🚀 Quick Start (Development)

### 1. Start the Backend API

```bash
# In repository root
pip install -r apps/api/requirements.txt
python -m uvicorn apps.api.app.main:app --reload --port 8000
```

The API will auto-create database tables and seed default administrator credentials:
- **Email**: `admin@psm.local`
- **Password**: `Admin12345!`
- **API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

### 2. Start the Frontend Web App

```bash
cd apps/web
npm install
npm run dev
```

Open [http://localhost:3005](http://localhost:3005) in your browser.

### 3. Run the Agent (Node / Server)

```bash
pip install -r apps/agent/requirements.txt
python -m apps.agent.app.main
```

---

## 🐳 Docker Compose Deployment

To run the entire PSM stack in Docker:

```bash
docker compose up -d --build
```

Access the dashboard at `http://localhost:3005`.

---

## 🧪 Testing

To run the full unit and integration test suite:

```bash
# Run both Backend API and Agent tests
python -m pytest apps/
```

---

## 📜 Documentation

- [System Architecture](docs/architecture.md)
- [Database Schema & ERD](docs/database.md)
- [REST API & WebSockets](docs/api.md)
- [Deployment Engine & Rollbacks](docs/deployment.md)
- [Security Blueprint](docs/security.md)
- [Agent Installation Guide](docs/agent-installation.md)

