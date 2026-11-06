# Personal API Platform (PAP)

Self-hosted **Modular Monolith** integration platform built with **Python 3.12+ and FastAPI** for homelab infrastructure, business applications (`Stock UMKM`, `POS Cashier`, `IoT Dashboard`), ESP32/MQTT devices, and Prometheus/Grafana monitoring.

## Key Capabilities

- **Hybrid Authentication & Authorization**: User JWT access tokens with refresh-token rotation, OAuth2 M2M client credentials, SHA-256 hashed API keys, per-device IoT credentials, RBAC roles, and granular scopes.
- **Hybrid Database Strategy**: Dedicated `pap_core` PostgreSQL database for platform identity/registry/audit state, with controlled least-privilege adapters for external PostgreSQL (`psm`) and MySQL (`stock_umkm`) databases.
- **Project & Client Registry**: Multi-project isolation (`stock-umkm`, `pos-cashier`, `iot-dashboard`, and future projects).
- **Business Integration Adapters**: Controlled product and inventory lookup, idempotent event ingestion (`inventory.updated`), and webhook delivery with retry/dead-letter handling.
- **IoT & Telemetry Module**: ESP32 device registration, credential rotation, anti-spoofing telemetry ingestion, bounded-label Prometheus metric exposition (`/metrics`), and authorized MQTT command publishing.
- **Security Hardening**: LAN-only host binding (`192.168.25.101:8000`), no unrestricted SQL execution endpoint, secret-reference storage, automatic log secret redaction, sliding-window rate limiting, and append-oriented audit logging.

## Quick Start (Development & Testing)

```bash
# Run Phase 0 connectivity & configuration audit
python scripts/phase0_audit.py

# Run automated unit, integration, and security test suite
pytest -v

# Start development server locally
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Homelab Docker Deployment

```bash
cp .env.example .env
# Edit .env with private credentials (never commit .env)

docker compose config
docker compose build
docker compose up -d

curl http://192.168.25.101:8000/health
```

## Documentation

- [Architecture](docs/architecture.md)
- [Database Strategy](docs/database.md)
- [Authentication & Scopes](docs/authentication.md)
- [API Reference](docs/api-reference.md)
- [Project Integrations](docs/integrations.md)
- [Security Architecture](docs/security.md)
- [Deployment Guide](docs/deployment.md)

