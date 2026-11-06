# Project Integrations

## Stock UMKM (Laravel) & POS Cashier (Next.js)

- **Product & Inventory Lookup**: POS Cashier queries `GET /api/v1/integrations/stock-umkm/products` and `GET /api/v1/integrations/stock-umkm/inventory` using a backend API key with `inventory:read` scope.
- **Event Publication**: Stock UMKM publishes committed events (`inventory.updated`) to `POST /api/v1/integrations/stock-umkm/events` with a unique `event_id`.
- **Idempotency**: Duplicate deliveries with the same `event_id` are detected via `integration_events` and safely acknowledged without duplicating downstream state changes or webhook deliveries.

## ESP32, Mosquitto MQTT, and Prometheus

- Topic convention: `pap/iot/{device_id}/telemetry`, `pap/iot/{device_id}/status`, `pap/iot/{device_id}/command`, `pap/iot/{device_id}/config`.
- Validated telemetry updates bounded-label Prometheus gauges (`pap_iot_device_temperature_celsius`, `pap_iot_device_counter_value`, `pap_iot_device_current_amperes`) exposed at `/metrics`.
- Grafana queries Prometheus (`:9001`) directly; applications requiring controlled metrics access query PAP's `/api/v1/metrics/prometheus/*` endpoints.

## Three-Project Hub Architecture (`Personal API Platform` as Main API)

1. **Personal API Platform (`D:\repository\Personal Api Platform`, Port `8000`)** — Main API (`API Utama`):
   - Central hub for project & client registry, RBAC/API key authentication (`X-API-Key`), Heatpress IoT Fleet registry (`/api/v1/iot/fleet/*` & `/api/devices/*`), and cross-project orchestration (`/api/v1/integrations/hub/overview`).
2. **Personal Server Manager (`D:\repository\Personal_Server_Manager`, Web `:3005`, API `:8001`)**:
   - Authenticates to PAP using `PAP_PSM_SERVICE_KEY` (`client_id: psm-control-plane`).
   - Pushes server, project, and Docker container state via `POST /api/v1/integrations/psm/sync` and consumes the unified hub overview & Heatpress IoT Fleet via `/api/v1/pap/status` and `/api/v1/pap/iot/fleet`.
3. **Heatpress IoT Dashboard (`D:\repository\dashboard_iot`, Web `:8088`, API `:8002`)**:
   - Authenticates to PAP using `PAP_IOT_SERVICE_KEY` (`client_id: iot-dashboard-backend`).
   - Synchronizes all Heatpress device registrations (`HPM 55`, `AF-450`, `APM-LOGO`, `comingsoon`), MAC ↔ MCID mappings, and Prometheus telemetry status with PAP Main API (`/api/devices/*`, `/api/pap/sync`, `/api/pap/status`).


