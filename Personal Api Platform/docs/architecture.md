# Architecture Overview

Personal API Platform (PAP) uses a **Modular Monolith** architecture on FastAPI (`Python 3.12+`).

## Module Organization

All domain modules reside under `app/modules/` and keep their `router.py`, `schemas.py`, `models.py`, `service.py`, and `repository.py` separated:

- `auth`: Login, OAuth2 client credentials, refresh-token rotation, session management.
- `users`: User accounts and role assignments.
- `permissions`: RBAC roles, permissions, and API client scopes.
- `projects`: Project registry and user memberships.
- `clients`: API client registration, hashed API keys, and scope assignment.
- `database_registry`: Connection metadata (using `secret_reference`) and allowlisted schema inspection.
- `integrations`: Stock UMKM and POS Cashier adapters and idempotent event ingestion.
- `iot`: ESP32 device registry, credential rotation, telemetry ingestion, and MQTT command publishing.
- `metrics`: Server metrics and Prometheus HTTP API instant/range/target queries.
- `monitoring`: Service status and platform overview.
- `server`: Liveness (`/health`), readiness (`/ready`), system info, version, and Prometheus exporter (`/metrics`).
- `docker`: Controlled container inspection (disabled by default unless an external secured executor is enabled).
- `webhooks`: Event subscriptions and delivery state tracking.
- `audit`: Append-oriented audit log for privileged operations.

