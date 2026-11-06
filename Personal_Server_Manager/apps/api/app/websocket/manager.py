import json
from typing import Dict, Set, Optional, Any
from fastapi import WebSocket

class WebSocketManager:
    def __init__(self):
        # server_id -> set of browser websockets listening for server metrics/events
        self.server_listeners: Dict[str, Set[WebSocket]] = {}
        # deployment_id -> set of browser websockets listening for deployment logs
        self.deployment_listeners: Dict[str, Set[WebSocket]] = {}
        # server_id -> active agent websocket connection
        self.agent_connections: Dict[str, WebSocket] = {}

    # --- Browser subscriptions ---
    async def connect_server_listener(self, server_id: str, websocket: WebSocket):
        await websocket.accept()
        if server_id not in self.server_listeners:
            self.server_listeners[server_id] = set()
        self.server_listeners[server_id].add(websocket)

    def disconnect_server_listener(self, server_id: str, websocket: WebSocket):
        if server_id in self.server_listeners:
            self.server_listeners[server_id].discard(websocket)
            if not self.server_listeners[server_id]:
                del self.server_listeners[server_id]

    async def broadcast_server_event(self, server_id: str, event_data: dict):
        if server_id in self.server_listeners:
            message = json.dumps(event_data)
            dead = set()
            for ws in self.server_listeners[server_id]:
                try:
                    await ws.send_text(message)
                except Exception:
                    dead.add(ws)
            for ws in dead:
                self.server_listeners[server_id].discard(ws)

    # --- Deployment log streaming ---
    async def connect_deployment_listener(self, deployment_id: str, websocket: WebSocket):
        await websocket.accept()
        if deployment_id not in self.deployment_listeners:
            self.deployment_listeners[deployment_id] = set()
        self.deployment_listeners[deployment_id].add(websocket)

    def disconnect_deployment_listener(self, deployment_id: str, websocket: WebSocket):
        if deployment_id in self.deployment_listeners:
            self.deployment_listeners[deployment_id].discard(websocket)
            if not self.deployment_listeners[deployment_id]:
                del self.deployment_listeners[deployment_id]

    async def broadcast_deployment_log(self, deployment_id: str, log_data: dict):
        if deployment_id in self.deployment_listeners:
            message = json.dumps(log_data)
            dead = set()
            for ws in self.deployment_listeners[deployment_id]:
                try:
                    await ws.send_text(message)
                except Exception:
                    dead.add(ws)
            for ws in dead:
                self.deployment_listeners[deployment_id].discard(ws)

    # --- Agent connection ---
    async def register_agent(self, server_id: str, websocket: WebSocket):
        await websocket.accept()
        self.agent_connections[server_id] = websocket

    def unregister_agent(self, server_id: str, websocket: WebSocket):
        if self.agent_connections.get(server_id) == websocket:
            del self.agent_connections[server_id]

    def is_agent_connected(self, server_id: str) -> bool:
        return server_id in self.agent_connections

    async def send_to_agent(self, server_id: str, message: dict) -> bool:
        ws = self.agent_connections.get(server_id)
        if ws:
            try:
                await ws.send_text(json.dumps(message))
                return True
            except Exception:
                if self.agent_connections.get(server_id) == ws:
                    del self.agent_connections[server_id]
        return False

ws_manager = WebSocketManager()

