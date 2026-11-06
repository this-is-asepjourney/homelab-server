# API Reference Summary

Base URL: `http://192.168.25.101:8000/api/v1`

## Standard Envelope

All responses follow the PAP v1 envelope with `success`, `message`, `data` (or `error`), and `meta` (`api_version`, `request_id`).

## Endpoints

- **System**: `GET /health`, `GET /ready`, `GET /system/info`, `GET /system/version`, `GET /metrics`
- **Auth**: `POST /auth/login`, `POST /auth/token`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`, `GET /auth/sessions`, `DELETE /auth/sessions/{session_id}`
- **Projects & Clients**: `GET/POST /projects`, `GET/PATCH /projects/{id}`, `POST /projects/{id}/members`, `GET/POST /clients`, `POST /clients/{id}/keys`, `DELETE /clients/{id}/keys/{key_id}`, `PUT /clients/{id}/scopes`
- **Database Registry**: `GET/POST /database/connections`, `GET /database/connections/{id}/health`, `GET /database/sources`, `GET /database/sources/{id}/schema`
- **Business Integrations**: `GET/POST /integrations`, `GET /integrations/{id}/health`, `GET /integrations/stock-umkm/products`, `GET /integrations/stock-umkm/inventory`, `POST /integrations/stock-umkm/events`
- **IoT**: `GET/POST /iot/devices`, `GET/PATCH /iot/devices/{id}`, `POST /iot/devices/{id}/credentials/rotate`, `GET/POST /iot/devices/{id}/telemetry`, `GET /iot/devices/{id}/status`, `POST /iot/devices/{id}/commands`, `POST /iot/devices/{id}/commands/{correlation_id}/ack`
- **Metrics & Monitoring**: `GET /metrics/server`, `GET /metrics/prometheus/query`, `GET /metrics/prometheus/range`, `GET /metrics/prometheus/targets`, `GET /monitoring/services`, `GET /monitoring/overview`
- **Docker**: `GET /docker/containers`, `GET /docker/containers/{id}`, `GET /docker/containers/{id}/stats`, `POST /docker/containers/{id}/restart`
- **Webhooks & Audit**: `GET/POST /webhooks`, `DELETE /webhooks/{id}`, `GET /webhooks/{id}/deliveries`, `GET /audit-logs`

