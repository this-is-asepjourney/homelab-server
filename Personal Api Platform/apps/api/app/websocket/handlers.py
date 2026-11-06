from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from apps.api.app.websocket.manager import ws_manager

ws_router = APIRouter()

@ws_router.websocket("/ws/servers/{server_id}/metrics")
@ws_router.websocket("/ws/servers/{server_id}/events")
async def server_metrics_ws(websocket: WebSocket, server_id: str):
    await ws_manager.connect_server_listener(server_id, websocket)
    try:
        while True:
            # Keepalive / listen for ping
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect_server_listener(server_id, websocket)

@ws_router.websocket("/ws/deployments/{deployment_id}/logs")
async def deployment_logs_ws(websocket: WebSocket, deployment_id: str):
    await ws_manager.connect_deployment_listener(deployment_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect_deployment_listener(deployment_id, websocket)

