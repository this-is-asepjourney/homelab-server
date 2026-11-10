"""API endpoints for Real-time Traffic Streaming and Topology Telemetry."""

import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.modules.traffic.broadcaster import traffic_broadcaster

router = APIRouter(prefix="/traffic", tags=["Topology & Traffic Streaming"])


class SimulateRequest(BaseModel):
    action: str = "nfc_tap"  # "nfc_tap", "telemetry", "stock", "psm_deploy", "backup"
    client_ip: str = "192.168.25.104"


@router.websocket("/ws")
async def websocket_traffic_endpoint(websocket: WebSocket):
    """Realtime WebSocket endpoint streaming all live API calls."""
    await traffic_broadcaster.connect_ws(websocket)
    try:
        # Keep connection open; client can send pings
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        traffic_broadcaster.disconnect_ws(websocket)
    except Exception:
        traffic_broadcaster.disconnect_ws(websocket)


@router.get("/stream")
async def sse_traffic_stream():
    """Server-Sent Events (SSE) fallback stream for live API traffic."""
    return StreamingResponse(
        traffic_broadcaster.subscribe_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/recent")
async def get_recent_traffic() -> Dict[str, Any]:
    """Retrieve recent API traffic history for topology hydration."""
    return {
        "status": "success",
        "data": traffic_broadcaster.get_recent(),
        "stats": traffic_broadcaster.get_stats(),
    }


@router.get("/stats")
async def get_traffic_stats() -> Dict[str, Any]:
    """Retrieve real-time traffic statistics."""
    return {
        "status": "success",
        "data": traffic_broadcaster.get_stats(),
    }


class TrafficEventPayload(BaseModel):
    method: str = "GET"
    path: str = "/"
    status: int = 200
    duration_ms: float = 1.0
    client_ip: str = "127.0.0.1"
    source: Optional[str] = None
    target: str = "core"
    sub_target: Optional[str] = None
    tag: Optional[str] = None
    color: Optional[str] = None
    detail: Optional[str] = None


@router.post("/event")
async def ingest_traffic_event(payload: TrafficEventPayload) -> Dict[str, Any]:
    """Ingests a traffic event into the broadcaster from external workers or decoupled background tasks."""
    traffic_broadcaster.record_and_broadcast(
        method=payload.method,
        path=payload.path,
        status=payload.status,
        duration_ms=payload.duration_ms,
        client_ip=payload.client_ip,
        source=payload.source,
        target=payload.target,
        sub_target=payload.sub_target,
        tag=payload.tag,
        color=payload.color,
        detail=payload.detail,
    )
    return {"status": "ok"}


@router.post("/simulate")
async def simulate_api_action(payload: SimulateRequest) -> Dict[str, Any]:
    """Triggers realistic multi-hop event through the central core gateway."""
    action = payload.action

    if action == "nfc_tap":
        traffic_broadcaster.record_and_broadcast(
            method="POST",
            path="/api/nfc/tap",
            status=200,
            duration_ms=2.1,
            client_ip=payload.client_ip or "192.168.25.104",
            source="esp32",
            target="core",
            sub_target="mysql",
            tag="NFC_TAP",
            color="#34d399",
            detail="ESP32 (192.168.25.104) -> POST /api/nfc/tap [UID: 058E208F87A200]",
        )
        # Follow-up DB verification and relay/buzzer feedback
        asyncio.create_task(_delay_broadcast(0.35, "core", "mysql", "DB_AUTH", "#fbbf24", "Core -> MySQL :3306 [SELECT user FROM nfc_users WHERE uid=...]"))
        asyncio.create_task(_delay_broadcast(0.70, "core", "esp32", "UNLOCKED", "#22d3ee", "Core -> ESP32 [Relay GPIO26 HIGH 2 Jam, Buzzer Bip 1x]"))
        asyncio.create_task(_delay_broadcast(0.90, "core", "hub", "FLEET_SYNC", "#34d399", "Core -> HeatpressHub [Operator Ferdiansyah Active]"))

    elif action == "nfc_sync":
        traffic_broadcaster.record_and_broadcast(
            method="POST",
            path="/api/nfc/users",
            status=201,
            duration_ms=3.4,
            client_ip="192.168.25.101:8088",
            source="hub",
            target="core",
            sub_target="mysql",
            tag="USER_REG",
            color="#34d399",
            detail="HeatpressHub Web -> POST /api/nfc/users [UID: 058E208F87A200 Ferdiansyah]",
        )
        asyncio.create_task(_delay_broadcast(0.35, "core", "mysql", "MYSQL_WRITE", "#fbbf24", "Core -> MySQL eternal_db [INSERT INTO nfc_users]"))
        asyncio.create_task(_delay_broadcast(0.70, "core", "esp32", "NVS_PUSH", "#38bdf8", "Core -> ESP32 POST /api/nfc/register_user [Tulis ke Flash NVS]"))

    elif action == "telemetry":
        traffic_broadcaster.record_and_broadcast(
            method="MQTT_PUB",
            path="/SysCtrl",
            status=200,
            duration_ms=1.4,
            client_ip=payload.client_ip or "192.168.25.104",
            source="esp32",
            target="mqtt",
            sub_target="influxdb",
            tag="MQTT_PUB",
            color="#38bdf8",
            detail="ESP32 -> Mosquitto :1883 [/SysCtrl {temp: 36.4°C, hum: 37%, rssi: -55dBm}]",
        )
        asyncio.create_task(_delay_broadcast(0.35, "mqtt", "core", "MQTT_SUB", "#38bdf8", "Mosquitto :1883 -> Core MqttInfluxConsumer (Async Worker)"))
        asyncio.create_task(_delay_broadcast(0.65, "core", "influxdb", "INFLUX_WRITE", "#c084fc", "Core -> InfluxDB 2.7 :8086 [bucket=eternal_telemetry, org=homelab]"))
        asyncio.create_task(_delay_broadcast(0.95, "influxdb", "grafana", "GRAFANA_QUERY", "#ec4899", "Grafana :3001 <- Mixed Flux Query [eternal-iot-dashboard]"))

    elif action == "dns_ingress":
        traffic_broadcaster.record_and_broadcast(
            method="DNS_QUERY",
            path="*.homelab",
            status=200,
            duration_ms=0.8,
            client_ip=payload.client_ip or "192.168.25.105",
            source="router",
            target="core",
            sub_target="hub",
            tag="DNS_INGRESS",
            color="#38bdf8",
            detail="CoreDNS (:53) + Nginx Ingress (:80) -> Resolving iot.homelab to 192.168.25.101",
        )
        asyncio.create_task(_delay_broadcast(0.35, "router", "hub", "VHOST_IOT", "#34d399", "Ingress :80 -> ProxyPass to HeatpressHub Web (:8088)"))
        asyncio.create_task(_delay_broadcast(0.60, "router", "psm", "VHOST_PSM", "#a78bfa", "Ingress :80 -> ProxyPass to PSM Console (:3005)"))

    elif action == "stock":
        traffic_broadcaster.record_and_broadcast(
            method="POST",
            path="/api/v1/stock/transactions",
            status=201,
            duration_ms=3.1,
            client_ip=payload.client_ip or "192.168.25.101",
            source="stock",
            target="core",
            sub_target="mysql",
            tag="STOCK_POS",
            color="#fbbf24",
            detail="Kasir POS -> POST /api/v1/stock/transactions [Order #TRX-8821 Rp 145.000]",
        )
        asyncio.create_task(_delay_broadcast(0.4, "core", "mysql", "MYSQL_WRITE", "#fbbf24", "Core -> MySQL stock_umkm [INSERT INTO transactions]"))

    elif action == "psm_deploy":
        traffic_broadcaster.record_and_broadcast(
            method="POST",
            path="/api/v1/deployments/git",
            status=200,
            duration_ms=4.8,
            client_ip=payload.client_ip or "192.168.25.101:3005",
            source="psm",
            target="core",
            sub_target="postgres",
            tag="PSM_DEPLOY",
            color="#a78bfa",
            detail="PSM Console (:3005) -> POST /api/v1/deployments/git [Release v1.2]",
        )
        asyncio.create_task(_delay_broadcast(0.4, "core", "postgres", "PG_SYNC", "#60a5fa", "Core -> PostgreSQL psm [UPDATE project_status SET active]"))

    elif action == "backup":
        traffic_broadcaster.record_and_broadcast(
            method="POST",
            path="/api/v1/backups/create",
            status=200,
            duration_ms=6.2,
            client_ip=payload.client_ip or "192.168.25.101",
            source="hub",
            target="core",
            sub_target="postgres",
            tag="BACKUP_ENG",
            color="#f43f5e",
            detail="Disaster Recovery Engine -> Snapshotting DB & Configs",
        )
        asyncio.create_task(_delay_broadcast(0.4, "core", "postgres", "PG_DUMP", "#60a5fa", "Core -> PostgreSQL :5432 [pg_dump psm, pap_core]"))
        asyncio.create_task(_delay_broadcast(0.4, "core", "mysql", "MYSQL_DUMP", "#f59e0b", "Core -> MySQL :3306 [mysqldump eternal_db, stock_umkm]"))

    return {
        "status": "success",
        "action": action,
        "message": f"Simulated action '{action}' dispatched through core gateway",
    }


async def _delay_broadcast(delay: float, source: str, target: str, tag: str, color: str, detail: str):
    await asyncio.sleep(delay)
    traffic_broadcaster.record_and_broadcast(
        method="EVENT",
        path=f"/internal/{tag.lower()}",
        status=200,
        duration_ms=round(delay * 10, 1),
        source=source,
        target=target,
        tag=tag,
        color=color,
        detail=detail,
    )

