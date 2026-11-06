# Personal API Platform (PAP)
## Final Technical Blueprint — Version 1.0

> **Purpose:** Central integration platform for multiple applications, IoT devices, databases, and homelab infrastructure.  
> **Architecture:** Modular Monolith  
> **Backend:** Python + FastAPI  
> **Database strategy:** Hybrid  
> **Authentication:** Hybrid (user authentication + machine-to-machine authentication)  
> **Network scope:** LAN/private network only  
> **Deployment:** Docker Compose on Ubuntu Server

---

## 1. Executive Summary

Personal API Platform (PAP) is a self-hosted integration platform that provides shared identity, authorization, project registration, integration adapters, monitoring access, and controlled communication between independently developed projects.

PAP is **not** intended to replace the business backend of every application. Each project retains ownership of its business logic and database. PAP provides shared integration capabilities and controlled access between systems.

### 1.1 Connected projects and services

| System | Technology | Intended integration |
|---|---|---|
| Stock UMKM | Laravel | Product, inventory, and business events |
| POS Cashier | Next.js | Product lookup, sales integration, identity |
| IoT Dashboard | Next.js | Device registry, status, telemetry |
| IoT devices | ESP32 / MQTT | Device identity, telemetry, commands |
| Prometheus | Existing Snap service | Metrics query and monitoring |
| Grafana | Existing Docker service | Visualization; direct Prometheus data source |
| PostgreSQL | Existing database service | PAP core database and/or approved project integration |
| MySQL | Existing database service | Stock UMKM integration, subject to least-privilege access |
| Future projects | Framework independent | Register as new PAP clients |

### 1.2 Design principles

1. One API platform, multiple independently deployable projects.
2. Modular Monolith first; extract services only when justified.
3. Each project owns its business data and business rules.
4. No unrestricted SQL execution endpoint.
5. Explicit authentication, authorization, and client scopes.
6. LAN-only binding by default.
7. Existing homelab service ports must not be changed by PAP deployment.
8. Secrets must not be committed to source control.
9. Monitoring metrics and business transactions must use appropriate storage systems.
10. Every privileged operation must be auditable.

---

## 2. Architecture Decisions

| Area | Decision |
|---|---|
| Application architecture | Modular Monolith |
| API framework | FastAPI |
| Language | Python 3.12+ |
| API style | REST |
| API version prefix | `/api/v1` |
| Core database | Dedicated PostgreSQL database for PAP |
| Project databases | Independent; accessed through controlled adapters |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| Validation | Pydantic |
| User authentication | Hybrid; local project login can remain during migration |
| Machine authentication | Client credentials / hashed API keys / device credentials |
| Authorization | RBAC + scopes |
| Message broker | Existing Mosquitto MQTT |
| Metrics | Existing Prometheus |
| Dashboards | Existing Grafana |
| Deployment | Docker Compose |
| Cache | Redis only when justified by measured need |
| External access | Disabled by default; LAN/private network only |

### 2.1 Modular Monolith

PAP runs as one FastAPI application with independently organized modules:

```text
PAP
├── Auth
├── Users
├── Projects
├── API Clients
├── Permissions
├── Database Registry
├── Integrations
├── IoT
├── Metrics
├── Monitoring
├── Server
├── Docker
├── Webhooks
└── Audit
```

Modules share the application runtime but must keep their routers, schemas, services, and repositories separated.

### 2.2 Why not Microservices initially?

The homelab has approximately 4 GB RAM. Running many separate services would add memory overhead and operational complexity. A Modular Monolith is easier to deploy, monitor, back up, and debug. A module can later be extracted into a separate service if its scaling or security requirements justify it.

---

## 3. High-Level Architecture

```mermaid
flowchart TB
    subgraph CLIENTS["Application / Client Layer"]
        STOCK["Stock UMKM - Laravel"]
        POS["POS Cashier - Next.js"]
        IOTWEB["IoT Dashboard - Next.js"]
        FUTURE["Future Projects"]
        ESP["ESP32 Devices"]
    end

    subgraph PAP["Personal API Platform - FastAPI"]
        CORE["API Core / Versioning"]
        AUTH["Authentication & Authorization"]
        PROJECT["Project & Client Registry"]
        BUSINESS["Business Integration Adapters"]
        IOT["IoT Module"]
        METRICS["Metrics & Monitoring Module"]
        AUDIT["Audit Logging"]
    end

    subgraph SERVICES["Existing / Independent Services"]
        PG["PostgreSQL"]
        MYSQL["MySQL"]
        MQTT["Mosquitto MQTT"]
        PROM["Prometheus"]
        GRAF["Grafana"]
        DOCKER["Docker Engine"]
    end

    STOCK --> CORE
    POS --> CORE
    IOTWEB --> CORE
    FUTURE --> CORE
    ESP --> MQTT
    CORE --> AUTH
    CORE --> PROJECT
    CORE --> BUSINESS
    CORE --> IOT
    CORE --> METRICS
    CORE --> AUDIT
    BUSINESS --> PG
    BUSINESS --> MYSQL
    IOT <--> MQTT
    METRICS --> PROM
    GRAF --> PROM
    METRICS -. authorized read .-> DOCKER
```

### 3.1 Important traffic paths

- Application clients call PAP over the LAN.
- PAP calls approved project APIs or database adapters.
- ESP32 publishes telemetry to MQTT; an IoT worker consumes it.
- Prometheus scrapes exporters and stores time-series metrics.
- Grafana queries Prometheus directly for dashboards.
- PAP queries Prometheus HTTP API for other applications that need controlled metrics access.

Grafana should not be forced through PAP for every Prometheus query. Direct Grafana-to-Prometheus access is simpler and avoids making PAP a monitoring bottleneck.

---

## 4. Network and Homelab Deployment Baseline

The following is the latest known baseline supplied for the homelab. Verify the actual server state before making changes.

| Component | Address / Port | Status |
|---|---|---|
| Ubuntu Server | Ubuntu Server 24.04.5 LTS | Existing |
| LAN host IP | `192.168.25.101` | Verify current address |
| PAP API | `192.168.25.101:8000` | New |
| Nextcloud Snap | Port `80` | Existing |
| Prometheus Snap | Port `9001` | Existing |
| Cockpit | Port `9090` | Existing |
| Mosquitto MQTT | Port `1883` | Existing |
| Grafana | Port `3001` | Existing |
| Uptime Kuma | Port `3002` | Existing |
| PostgreSQL | `100.106.63.90:5432` | Supplied database endpoint |
| MySQL | `100.106.63.90:3306` | Supplied database endpoint |

**Do not move or reassign existing service ports.** PAP uses port `8000` only.

The database address `100.106.63.90` is a private/overlay-network-style address, not the homelab LAN address `192.168.25.101`. Confirm that the Ubuntu host and PAP container can route to it. If it is a Tailscale address, verify that the host's Tailscale connection is active and that the required ACLs permit the database ports.

Do not expose database ports to the entire LAN or internet just to make the connection work.

---

## 5. Hybrid Database Strategy

PAP uses a dedicated core database and controlled adapters to independent project databases.

### 5.1 PAP core database

Recommended database:

```text
Database: pap_core
Purpose:
- users and project memberships
- projects and API clients
- API key metadata and scopes
- roles and permissions
- database connection metadata
- integration configuration
- device registry
- refresh-token/session metadata
- audit logs
- webhook subscriptions and delivery state
```

### 5.2 Existing PostgreSQL configuration supplied

The supplied PostgreSQL configuration is:

| Variable | Supplied value |
|---|---|
| `POSTGRES_DB` | `psm` |
| `POSTGRES_USER` | `appuser` |
| `POSTGRES_PASSWORD` | Supplied privately by user; do not commit |
| `POSTGRES_HOST` | `100.106.63.90` |
| `POSTGRES_PORT` | `5432` |

**Database ownership decision:** `psm` may be an existing Personal Server Manager database. Do not automatically run PAP migrations against it. First inspect its purpose, schema, owner, and current applications.

Recommended options:

1. Create a separate database named `pap_core` on the same PostgreSQL server, with a dedicated `pap_user`.
2. If `psm` is explicitly confirmed to be reserved for PAP, document that decision and use it only after checking that no other application owns its schema.
3. Do not use a PostgreSQL superuser for the PAP runtime.

Example database provisioning (run as an authorized PostgreSQL administrator, after confirming the target server):

```sql
CREATE ROLE pap_user LOGIN PASSWORD 'REPLACE_WITH_NEW_STRONG_SECRET';
CREATE DATABASE pap_core OWNER pap_user;
```

If the database already exists, do not run the creation commands blindly. Inspect first.

### 5.3 Existing MySQL configuration supplied

| Variable | Supplied value |
|---|---|
| `DB_CONNECTION` | `mysql` |
| `DB_HOST` | `100.106.63.90` |
| `DB_PORT` | `3306` |
| `DB_DATABASE` | `stock_umkm` |
| `DB_USERNAME` | `root` |
| `DB_PASSWORD` | Supplied privately by user; do not commit |

The supplied MySQL account is `root`. PAP should **not** use this account as its runtime identity.

Create a dedicated MySQL account for the exact integration operations required. Example (adapt host restrictions to the actual Docker routing source IP and MySQL policy):

```sql
CREATE USER 'pap_stock_reader'@'<PAP_SOURCE_HOST>'
IDENTIFIED BY 'REPLACE_WITH_NEW_STRONG_SECRET';

GRANT SELECT ON stock_umkm.* TO 'pap_stock_reader'@'<PAP_SOURCE_HOST>';
```

If PAP must perform writes, grant only the specific required operations and tables after the integration contract is defined. Do not grant global privileges.

The application should preferably integrate with Stock UMKM through its Laravel API rather than directly reading or writing its tables. Direct database access should be a controlled adapter for explicitly approved read use cases.

### 5.4 Database connection rules

- Never expose credentials in API responses, logs, screenshots, or Git.
- Do not store plaintext passwords in `database_connections`.
- Store a secret reference, not the secret itself.
- Use separate credentials per application and database.
- Restrict database users to the required database and operations.
- Use connection pooling with conservative pool sizes.
- Set connection and query timeouts.
- Do not create a generic public SQL execution endpoint.
- Validate all table/schema metadata requests against an allowlist.
- Back up databases before schema changes.

### 5.5 Database connection environment template

Use placeholders in `.env`; the actual secret file must be private and excluded from Git.

```env
# PAP CORE DATABASE - create separately
PAP_DATABASE_URL=postgresql+psycopg://pap_user:REPLACE_ME@100.106.63.90:5432/pap_core

# EXISTING POSTGRESQL REFERENCE
PSM_DATABASE_HOST=100.106.63.90
PSM_DATABASE_PORT=5432
PSM_DATABASE_NAME=psm
PSM_DATABASE_USER=appuser
PSM_DATABASE_PASSWORD=REPLACE_ME

# EXISTING STOCK UMKM MYSQL REFERENCE
STOCK_DB_HOST=100.106.63.90
STOCK_DB_PORT=3306
STOCK_DB_NAME=stock_umkm
STOCK_DB_USER=pap_stock_reader
STOCK_DB_PASSWORD=REPLACE_ME
```

Do not put actual passwords in `.env.example`, documentation, Docker Compose, or source code.

---

## 6. Database ERD

```mermaid
erDiagram
    USERS ||--o{ USER_PROJECT_MEMBERSHIPS : has
    PROJECTS ||--o{ USER_PROJECT_MEMBERSHIPS : has
    PROJECTS ||--o{ API_CLIENTS : owns
    API_CLIENTS ||--o{ API_KEYS : has
    API_CLIENTS ||--o{ CLIENT_SCOPES : assigned
    SCOPES ||--o{ CLIENT_SCOPES : includes
    USERS ||--o{ USER_ROLES : assigned
    ROLES ||--o{ USER_ROLES : includes
    ROLES ||--o{ ROLE_PERMISSIONS : includes
    PERMISSIONS ||--o{ ROLE_PERMISSIONS : includes
    PROJECTS ||--o{ DATABASE_CONNECTIONS : registers
    PROJECTS ||--o{ INTEGRATIONS : configures
    PROJECTS ||--o{ DEVICES : owns
    DEVICES ||--o{ DEVICE_CREDENTIALS : authenticates
    USERS ||--o{ REFRESH_TOKENS : owns
    USERS ||--o{ AUDIT_LOGS : performs
    PROJECTS ||--o{ AUDIT_LOGS : generates
    API_CLIENTS ||--o{ AUDIT_LOGS : generates
    PROJECTS ||--o{ WEBHOOK_SUBSCRIPTIONS : owns
    WEBHOOK_SUBSCRIPTIONS ||--o{ WEBHOOK_DELIVERIES : produces

    USERS {
        uuid id PK
        string email UK
        string password_hash
        string full_name
        boolean is_active
        timestamp created_at
    }

    PROJECTS {
        uuid id PK
        string slug UK
        string name
        string status
        timestamp created_at
    }

    USER_PROJECT_MEMBERSHIPS {
        uuid id PK
        uuid user_id FK
        uuid project_id FK
        string membership_role
    }

    API_CLIENTS {
        uuid id PK
        uuid project_id FK
        string client_id UK
        string name
        string client_type
        boolean is_active
    }

    API_KEYS {
        uuid id PK
        uuid client_id FK
        string key_hash
        timestamp expires_at
        timestamp revoked_at
    }

    SCOPES {
        uuid id PK
        string name UK
        string description
    }

    CLIENT_SCOPES {
        uuid client_id FK
        uuid scope_id FK
    }

    ROLES {
        uuid id PK
        string name UK
    }

    PERMISSIONS {
        uuid id PK
        string name UK
        string description
    }

    USER_ROLES {
        uuid user_id FK
        uuid role_id FK
    }

    ROLE_PERMISSIONS {
        uuid role_id FK
        uuid permission_id FK
    }

    DATABASE_CONNECTIONS {
        uuid id PK
        uuid project_id FK
        string name
        string engine
        string secret_reference
        boolean is_active
    }

    INTEGRATIONS {
        uuid id PK
        uuid project_id FK
        string integration_type
        jsonb configuration
        boolean is_active
    }

    DEVICES {
        uuid id PK
        uuid project_id FK
        string device_uid UK
        string device_type
        string status
    }

    DEVICE_CREDENTIALS {
        uuid id PK
        uuid device_id FK
        string credential_hash
        timestamp revoked_at
    }

    REFRESH_TOKENS {
        uuid id PK
        uuid user_id FK
        string token_hash
        timestamp expires_at
        timestamp revoked_at
    }

    AUDIT_LOGS {
        uuid id PK
        uuid project_id FK
        uuid user_id FK
        uuid client_id FK
        string action
        string resource
        timestamp created_at
    }

    WEBHOOK_SUBSCRIPTIONS {
        uuid id PK
        uuid project_id FK
        string event_type
        string target_reference
        boolean is_active
    }

    WEBHOOK_DELIVERIES {
        uuid id PK
        uuid subscription_id FK
        string event_id
        string status
        int attempt_count
        timestamp created_at
    }
```

### 6.1 Data modeling rules

- Use UUID primary keys.
- Add `created_at` and `updated_at` where applicable.
- Add unique constraints for project slugs, client IDs, scope names, and device UIDs.
- Add indexes for foreign keys and frequent lookup fields.
- Use database migrations; do not modify production schema manually without a migration.
- Store audit events as append-oriented records.
- Never store raw API keys or refresh tokens.

---

## 7. API Standards

Base URL:

```text
http://192.168.25.101:8000/api/v1
```

Development documentation:

```text
http://192.168.25.101:8000/docs
http://192.168.25.101:8000/redoc
```

### 7.1 HTTP conventions

| Method | Meaning |
|---|---|
| GET | Retrieve |
| POST | Create or execute a controlled action |
| PUT | Replace a resource |
| PATCH | Partially update |
| DELETE | Delete or revoke |

Use pagination for collection endpoints. Use filtering and sorting only through explicitly supported parameters.

### 7.2 Standard response

Success:

```json
{
  "success": true,
  "message": "Data retrieved successfully",
  "data": {
    "id": "uuid",
    "name": "Stock UMKM"
  },
  "meta": {
    "api_version": "v1",
    "request_id": "uuid"
  }
}
```

Error:

```json
{
  "success": false,
  "message": "Permission denied",
  "error": {
    "code": "INSUFFICIENT_SCOPE",
    "details": null
  },
  "meta": {
    "request_id": "uuid"
  }
}
```

Use appropriate HTTP status codes: `200`, `201`, `202`, `204`, `400`, `401`, `403`, `404`, `409`, `422`, `429`, and `500`.

### 7.3 Endpoint catalogue

#### System

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/ready` | Readiness including required dependencies |
| GET | `/system/info` | Platform information |
| GET | `/system/version` | API version |

#### Authentication

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/auth/login` | User login |
| POST | `/auth/refresh` | Refresh access token |
| POST | `/auth/logout` | Revoke current session |
| GET | `/auth/me` | Current identity |
| GET | `/auth/sessions` | List sessions |
| DELETE | `/auth/sessions/{session_id}` | Revoke session |

#### Projects and clients

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/projects` | List projects |
| POST | `/projects` | Register project |
| GET | `/projects/{project_id}` | Project details |
| PATCH | `/projects/{project_id}` | Update project |
| GET | `/clients` | List API clients |
| POST | `/clients` | Register API client |
| POST | `/clients/{client_id}/keys` | Issue API key |
| DELETE | `/clients/{client_id}/keys/{key_id}` | Revoke API key |
| PUT | `/clients/{client_id}/scopes` | Assign client scopes |

#### Database registry

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/database/connections` | List registered connections |
| GET | `/database/connections/{id}/health` | Test connection |
| GET | `/database/sources` | List approved data sources |
| GET | `/database/sources/{id}/schema` | Read approved schema metadata |

No unrestricted `/database/query` endpoint in the initial release.

#### Business integrations

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/integrations` | List integrations |
| GET | `/integrations/{id}/health` | Integration health |
| GET | `/integrations/stock-umkm/products` | Approved product lookup |
| GET | `/integrations/stock-umkm/inventory` | Approved inventory lookup |
| POST | `/integrations/stock-umkm/events` | Receive approved integration event |

These are PAP adapter routes and must call the owning project's supported service/API or a restricted repository adapter. They are not automatically available until implemented.

#### IoT

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/iot/devices` | List devices |
| POST | `/iot/devices` | Register device |
| GET | `/iot/devices/{device_id}` | Device detail |
| PATCH | `/iot/devices/{device_id}` | Update metadata |
| POST | `/iot/devices/{device_id}/credentials/rotate` | Rotate credential |
| GET | `/iot/devices/{device_id}/telemetry` | Query telemetry |
| GET | `/iot/devices/{device_id}/status` | Device status |
| POST | `/iot/devices/{device_id}/commands` | Create authorized command |

#### Metrics and monitoring

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/metrics/server` | Server metrics |
| GET | `/metrics/prometheus/query` | Instant query |
| GET | `/metrics/prometheus/range` | Range query |
| GET | `/metrics/prometheus/targets` | Scrape target status |
| GET | `/monitoring/services` | Service status |
| GET | `/monitoring/overview` | Monitoring summary |

#### Docker

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/docker/containers` | List containers |
| GET | `/docker/containers/{id}` | Container details |
| GET | `/docker/containers/{id}/stats` | Resource usage |
| POST | `/docker/containers/{id}/restart` | Restricted restart operation |

Docker management is disabled in the initial release unless a separately secured executor has been implemented. Do not mount the Docker socket into the general-purpose PAP API container.

#### Webhooks and audit

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/webhooks` | List subscriptions |
| POST | `/webhooks` | Create subscription |
| DELETE | `/webhooks/{id}` | Disable subscription |
| GET | `/audit-logs` | Read audit logs |

---

## 8. Hybrid Authentication and Authorization

PAP supports two principal identity paths.

### 8.1 User authentication

Used when a person signs in to an application.

- PAP-managed user identity can be introduced gradually.
- Existing Laravel and Next.js login systems may remain during migration.
- Applications must validate identity through a documented trusted integration contract.
- Use short-lived access tokens.
- Use refresh-token rotation and revocation.
- Consider OpenID Connect when standardized cross-application SSO is implemented.

Do not trust a user ID or role sent in a normal request body. Do not accept a token merely because another project generated it; validate its signature, issuer, audience, expiry, and permitted claims.

### 8.2 Machine-to-machine authentication

Used by backend services, workers, and IoT devices.

Recommended methods:

- OAuth2 client credentials for backend-to-backend integrations.
- Random API keys stored only as hashes for simple registered clients.
- Per-device credentials for ESP32.
- MQTT username/password or stronger broker-supported authentication per device.

Never put server-side client secrets in browser JavaScript or a Next.js `NEXT_PUBLIC_` variable.

### 8.3 Suggested scopes

```text
projects:read
projects:manage

inventory:read
inventory:write

transactions:read
transactions:write

iot:read
iot:write
iot:manage

metrics:read
server:read

docker:read
docker:restart

database:read
database:manage

audit:read
```

Scopes must be granted explicitly per client. A client must receive only the minimum required scopes.

### 8.4 Example access matrix

| Client | Inventory | Transactions | IoT | Metrics | Docker |
|---|---|---|---|---|---|
| Stock UMKM | Own service | Own service | None | None | None |
| POS Cashier | Read / approved write | Own service | None | None | None |
| IoT Dashboard | None | None | Read / manage | Read | None |
| ESP32 | None | None | Own device only | None | None |
| Admin client | Role-dependent | Role-dependent | Role-dependent | Read | Restricted |

---

## 9. Project Integration Design

### 9.1 Stock UMKM — Laravel

Responsibilities remain in Laravel:

- Product and inventory business rules.
- Stock validation.
- Transaction ownership.
- Database writes.
- Local user authentication during migration.

PAP integration:

1. Register Stock UMKM as a project and client.
2. Assign only required scopes.
3. Prefer Laravel API endpoints for business operations.
4. Publish an event after a committed business transaction.
5. Make event delivery retryable and idempotent.

Example event:

```json
{
  "event_id": "uuid",
  "event_type": "inventory.updated",
  "source": "stock_umkm",
  "occurred_at": "2026-11-02T07:30:00+07:00",
  "data": {
    "product_id": "123",
    "quantity": 25
  }
}
```

### 9.2 POS Cashier — Next.js

Responsibilities remain in the POS backend:

- Sales and payment workflows.
- POS transaction records.
- Cashier authorization.
- Local operational data.

PAP integration:

- Backend-to-backend authentication.
- Approved product and inventory lookup.
- Controlled transaction/inventory integration.
- Event publication and consumption.

Do not let browser code connect directly to PAP using a confidential client secret.

### 9.3 IoT Dashboard — Next.js

PAP provides:

- Device registry.
- Device metadata.
- Status and last-seen information.
- Telemetry query.
- Authorized device commands.
- Device configuration history.

### 9.4 ESP32 and MQTT

Suggested topic convention:

```text
pap/iot/{device_id}/telemetry
pap/iot/{device_id}/status
pap/iot/{device_id}/command
pap/iot/{device_id}/config
```

Example telemetry:

```json
{
  "device_id": "HPM55-0002",
  "timestamp": "2026-11-02T07:30:00+07:00",
  "temperature": 185.5,
  "counter": 120,
  "current": 2.4
}
```

The device identity must be verified from broker credentials or another authenticated device mechanism. The `device_id` field alone is not authentication.

Use MQTT QoS according to the message's importance. Commands should have correlation IDs, expiry, acknowledgements, and authorization checks. Do not expose arbitrary command publishing to ordinary clients.

### 9.5 Prometheus and Grafana

Recommended path:

```text
ESP32
  |
  v
Mosquitto
  |
  v
IoT Collector / Exporter
  |
  v
Prometheus
  |                    \
  v                     v
Grafana               PAP Metrics API
```

- Prometheus scrapes exporters.
- Grafana queries Prometheus directly.
- PAP queries Prometheus HTTP API for authorized application use.
- Prometheus is not a transactional database.
- Avoid high-cardinality labels such as unique request IDs, raw MAC addresses, or arbitrary user identifiers.

For detailed high-frequency telemetry history, evaluate a time-series database only when the retention and query requirements justify it. Prometheus is best for operational metrics and bounded-label time series.

---

## 10. Security Architecture

### 10.1 Network security

- Bind PAP to the server LAN IP, not `0.0.0.0` on the host.
- Do not configure router port forwarding.
- Do not expose PAP to the public internet.
- Permit port 8000 only from trusted LAN clients through host firewall policy.
- Verify private/overlay routing to `100.106.63.90`.
- Use HTTPS for sensitive credentials where feasible, even on private networks.
- Restrict CORS to known frontend origins.

### 10.2 Application security

- Password hashing with Argon2id.
- Short-lived access tokens.
- Refresh-token rotation and revocation.
- Hashed API keys.
- Per-client scopes.
- Per-device credentials.
- Request validation with Pydantic.
- Rate limiting per client.
- Request IDs and structured logs.
- Audit logging for privileged operations.
- Safe error responses without secrets or stack traces.

### 10.3 Docker security

- Run the API as a non-root user.
- Use resource limits.
- Avoid privileged containers.
- Do not mount the Docker socket into PAP.
- Keep secrets outside Git and container image layers.
- Pin dependency versions.
- Keep base images updated.
- Use read-only mounts where practical.

### 10.4 Secret handling

The database passwords supplied during planning are credentials and must be treated as exposed to this conversation. Before production:

1. Rotate the supplied MySQL root password if it is an active credential.
2. Rotate any other shared or reused password.
3. Create a restricted MySQL account for PAP.
4. Create a dedicated PostgreSQL role for PAP.
5. Keep real `.env` files out of Git.
6. Never paste secrets into issue trackers or documentation.

---

## 11. Repository Structure

```text
personal-api-platform/
├── app/
│   ├── main.py
│   ├── dependencies.py
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── security.py
│   │   ├── permissions.py
│   │   ├── exceptions.py
│   │   ├── logging.py
│   │   └── middleware.py
│   ├── modules/
│   │   ├── auth/
│   │   ├── users/
│   │   ├── projects/
│   │   ├── clients/
│   │   ├── permissions/
│   │   ├── database_registry/
│   │   ├── integrations/
│   │   ├── iot/
│   │   ├── metrics/
│   │   ├── monitoring/
│   │   ├── server/
│   │   ├── docker/
│   │   ├── webhooks/
│   │   └── audit/
│   ├── integrations/
│   │   ├── prometheus/
│   │   ├── mqtt/
│   │   ├── stock_umkm/
│   │   ├── mysql/
│   │   └── postgresql/
│   ├── schemas/
│   ├── services/
│   └── repositories/
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── security/
├── scripts/
├── docker/
│   └── Dockerfile
├── docs/
│   ├── architecture.md
│   ├── database.md
│   ├── authentication.md
│   ├── api-reference.md
│   ├── integrations.md
│   ├── security.md
│   └── deployment.md
├── .env.example
├── .gitignore
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
└── README.md
```

### Module conventions

Each business module should use a consistent structure:

```text
module_name/
├── router.py
├── schemas.py
├── models.py
├── service.py
└── repository.py
```

- `router.py`: HTTP routes and dependency wiring.
- `schemas.py`: request/response validation.
- `models.py`: SQLAlchemy models.
- `service.py`: business rules and orchestration.
- `repository.py`: database operations.

Keep external service adapters outside business routers. Do not put all application logic in `main.py`.

---

## 12. Docker Deployment

### 12.1 Deployment directory

```text
/opt/homelab/personal-api-platform/
├── app/
├── docker/
├── migrations/
├── tests/
├── docs/
├── .env
├── .env.example
├── .gitignore
├── docker-compose.yml
├── requirements.txt
└── README.md
```

### 12.2 Dockerfile

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY migrations ./migrations

RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 12.3 Initial requirements

Use a lock file and pinned versions before production.

```text
fastapi
uvicorn[standard]
sqlalchemy
psycopg[binary]
alembic
pydantic-settings
pwdlib[argon2]
PyJWT
httpx
paho-mqtt
prometheus-client
```

Add MySQL drivers only when a real MySQL adapter is implemented, for example `pymysql` or `asyncmy`, and choose one based on the selected SQLAlchemy execution model.

### 12.4 Docker Compose — API only

PostgreSQL and MySQL are existing services. This Compose file intentionally does not create replacement database containers.

```yaml
services:
  pap-api:
    build:
      context: .
      dockerfile: docker/Dockerfile
    container_name: pap-api
    restart: unless-stopped
    env_file:
      - .env
    ports:
      - "192.168.25.101:8000:8000"
    extra_hosts:
      - "host.docker.internal:host-gateway"
    mem_limit: 256m
    cpus: 0.50
    healthcheck:
      test:
        - CMD
        - curl
        - -fsS
        - http://127.0.0.1:8000/health
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
    networks:
      - pap-network

networks:
  pap-network:
    driver: bridge
```

**Important connectivity note:** the database endpoint `100.106.63.90` must be reachable from inside the PAP container. Test the route and TCP connectivity before deployment. Do not assume the host's VPN/overlay route is automatically available to Docker bridge containers. If it is not reachable, use a carefully designed host-gateway or network arrangement rather than exposing database services broadly.

The PostgreSQL and MySQL firewall rules must allow only the actual PAP source address or trusted network path.

### 12.5 Environment template

`.env.example`:

```env
APP_NAME=Personal API Platform
APP_ENV=development
APP_DEBUG=false
APP_VERSION=1.0.0

API_PREFIX=/api/v1

# Dedicated PAP core database; provision separately.
PAP_DATABASE_URL=postgresql+psycopg://pap_user:REPLACE_ME@100.106.63.90:5432/pap_core

# Existing PSM database reference; do not migrate it as PAP core by default.
PSM_DATABASE_HOST=100.106.63.90
PSM_DATABASE_PORT=5432
PSM_DATABASE_NAME=psm
PSM_DATABASE_USER=appuser
PSM_DATABASE_PASSWORD=REPLACE_ME

# Restricted Stock UMKM integration account; do not use MySQL root.
STOCK_DB_HOST=100.106.63.90
STOCK_DB_PORT=3306
STOCK_DB_NAME=stock_umkm
STOCK_DB_USER=pap_stock_reader
STOCK_DB_PASSWORD=REPLACE_ME

JWT_SECRET=REPLACE_WITH_RANDOM_SECRET
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

PROMETHEUS_URL=http://host.docker.internal:9001

MQTT_HOST=host.docker.internal
MQTT_PORT=1883
MQTT_USERNAME=REPLACE_ME
MQTT_PASSWORD=REPLACE_ME

CORS_ORIGINS=http://192.168.25.101
```

Generate a cryptographically random JWT secret. Never use the example values in production.

### 12.6 Git ignore

```gitignore
.env
.env.*
!.env.example
__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
dist/
build/
```

### 12.7 Initial deployment commands

Run only after the application source, configuration, and database connectivity are ready.

```bash
cd /opt/homelab/personal-api-platform

docker compose config
docker compose build
docker compose up -d

docker ps
docker logs pap-api
```

Test:

```bash
curl http://192.168.25.101:8000/health
```

Open:

```text
http://192.168.25.101:8000/docs
```

Do not run `docker compose down` in the existing database directory as part of PAP deployment.

---

## 13. Resource Planning

The server has approximately 4 GB RAM. Keep the first deployment minimal.

| Component | Initial policy |
|---|---|
| PAP API | Container memory limit 256 MB |
| PAP API CPU | 0.5 CPU limit |
| Existing PostgreSQL | Reuse only after database ownership and resource review |
| Existing MySQL | Reuse through restricted credentials |
| Redis | Deferred |
| Dedicated IoT worker | Deferred until telemetry volume requires it |
| Dedicated message queue | Not needed; existing MQTT is sufficient initially |

Container limits are ceilings, not guaranteed usage. Monitor actual RSS, CPU, swap, and database connections.

---

## 14. Implementation Roadmap

### Phase 0 — Server and connectivity audit

Tasks:

- Verify Ubuntu version and LAN IP.
- Verify Docker and Compose.
- Verify PostgreSQL endpoint and database ownership.
- Verify MySQL endpoint and account privileges.
- Verify routing from host and container to `100.106.63.90`.
- Verify Prometheus readiness at port 9001.
- Verify MQTT connectivity at port 1883.
- Check free RAM, disk, and existing container health.
- Rotate credentials that were shared in planning.

Deliverable: verified deployment prerequisites and a safe database access plan.

### Phase 1 — Foundation

Tasks:

- Create repository.
- Create FastAPI application.
- Configure settings.
- Configure SQLAlchemy.
- Configure dedicated `pap_core` database.
- Configure Alembic.
- Add `/health` and `/ready`.
- Add structured logging.
- Add Dockerfile and Compose.

Acceptance criteria:

- API starts in Docker.
- API binds only to the intended LAN host port.
- Database connection succeeds.
- Migration runs against `pap_core` only.
- Existing services remain unaffected.

### Phase 2 — Authentication and authorization

Tasks:

- User model and password hashing.
- Login and logout.
- JWT access tokens.
- Refresh-token rotation.
- API client registry.
- Hashed API keys or client credentials.
- RBAC.
- Scopes.
- Audit log.

Acceptance criteria:

- Valid user can authenticate.
- Invalid credentials are rejected.
- Revoked tokens/keys are rejected.
- Client without scope receives `403`.
- Secrets never appear in responses or logs.

### Phase 3 — Project registry and integration registry

Tasks:

- Register Stock UMKM.
- Register POS Cashier.
- Register IoT Dashboard.
- Register future projects.
- Create client credentials.
- Assign scopes.
- Store integration metadata and secret references.

Acceptance criteria:

- Each project has a unique ID and slug.
- Each client has its own identity.
- Permissions can be independently revoked.

### Phase 4 — Business project integration

Tasks:

- Define Stock UMKM integration contract.
- Implement Laravel adapter.
- Implement POS Cashier backend client.
- Product lookup.
- Inventory lookup.
- Event delivery.
- Idempotency and retry strategy.

Acceptance criteria:

- POS can read only approved Stock UMKM data.
- Failed event delivery can retry safely.
- Duplicate event delivery does not duplicate business effects.

### Phase 5 — IoT integration

Tasks:

- Device registry.
- Per-device credentials.
- MQTT subscriber.
- Telemetry schema validation.
- Device status and last-seen.
- Command authorization and acknowledgement.
- Prometheus exporter.

Acceptance criteria:

- Registered device can publish telemetry.
- Unknown device is rejected.
- Device identity cannot be impersonated by changing payload fields.
- Telemetry metrics appear in Prometheus.

### Phase 6 — Monitoring integration

Tasks:

- Prometheus HTTP API client.
- Instant and range query.
- Target status.
- Server metrics integration.
- Service health summary.
- Grafana dashboard and data-source configuration.

Acceptance criteria:

- PAP can query approved Prometheus metrics.
- Grafana continues querying Prometheus directly.
- Prometheus remains independent of PAP availability.

### Phase 7 — Developer administration

Tasks:

- Client management UI or admin API.
- API key issuance and revocation.
- Scope management.
- Integration health.
- Audit log viewer.
- Usage statistics.
- OpenAPI documentation.

### Phase 8 — Hardening and expansion

Tasks:

- Automated tests.
- Backup and restore drills.
- Dependency pinning.
- Security review.
- Rate limiting.
- Webhook retry and dead-letter handling.
- Optional Redis.
- Optional separate IoT worker.
- Performance profiling.
- Extract a module only if necessary.

---

## 15. Testing Strategy

### 15.1 Unit tests

- Authentication service.
- Scope validation.
- Project access rules.
- Input validation.
- Adapter mapping.
- Error handling.

### 15.2 Integration tests

- PostgreSQL connection.
- Alembic migrations.
- MySQL read-only integration.
- Prometheus query.
- MQTT publish/subscribe.
- Laravel adapter.
- POS backend client.

### 15.3 Security tests

- Invalid token.
- Expired token.
- Revoked API key.
- Missing scope.
- Cross-project access attempt.
- SQL injection attempts.
- Secret leakage in logs.
- Unauthorized device telemetry.
- Unauthorized Docker operation.

### 15.4 Operational tests

- Restart container.
- Restart host.
- Restore database backup.
- Handle database outage.
- Handle MQTT outage.
- Handle Prometheus outage.
- Confirm PAP failure does not stop independent applications.

---

## 16. Definition of Done

PAP v1.0 is considered ready for initial production use when:

- [ ] FastAPI runs on the Ubuntu homelab.
- [ ] PAP binds to the intended LAN address and port.
- [ ] Dedicated `pap_core` database exists.
- [ ] Alembic migrations work.
- [ ] Health and readiness endpoints work.
- [ ] User authentication works.
- [ ] Machine-to-machine authentication works.
- [ ] RBAC and scopes are enforced.
- [ ] Project and client registration works.
- [ ] Audit logs are recorded.
- [ ] Stock UMKM integration is tested.
- [ ] POS Cashier integration is tested.
- [ ] IoT device registration works.
- [ ] MQTT telemetry processing works.
- [ ] Prometheus integration works.
- [ ] Grafana dashboards remain functional.
- [ ] Backup and restore are tested.
- [ ] Existing homelab ports and services remain unchanged.

---

## 17. Immediate Next Steps

Recommended order:

1. Audit the existing PostgreSQL database named `psm`; confirm whether it belongs to Personal Server Manager or another application.
2. Decide and provision a separate `pap_core` database.
3. Rotate the supplied MySQL root credential if active.
4. Create a restricted MySQL account for Stock UMKM integration.
5. Verify host and container connectivity to `100.106.63.90:5432` and `100.106.63.90:3306`.
6. Create the `personal-api-platform` repository.
7. Implement Phase 1 only.
8. Verify PAP deployment on `192.168.25.101:8000`.
9. Continue with authentication and client registration.

**Do not begin with database writes, Docker control, or unrestricted SQL endpoints.** Establish identity, permissions, ownership, and auditability first.

---

## 18. Final Architecture Summary

```text
                    PERSONAL API PLATFORM
                         FastAPI Core
                              |
          +-------------------+-------------------+
          |                   |                   |
       Identity            Projects           Integrations
          |                   |                   |
     JWT / API Keys       Client Registry     Adapter Layer
          |                   |                   |
          +-------------------+-------------------+
                              |
              +---------------+---------------+
              |               |               |
          PostgreSQL        MySQL           MQTT
          pap_core        stock_umkm       ESP32
              |               |               |
              +---------------+---------------+
                              |
                      Monitoring Module
                              |
                         Prometheus
                              |
                           Grafana

Applications:
- Stock UMKM (Laravel)
- POS Cashier (Next.js)
- IoT Dashboard (Next.js)
- Future projects
```

**One platform. Multiple projects. Independent databases. Shared integration and security.**

The platform is designed to grow without requiring every project to be rewritten or moved into one database.
