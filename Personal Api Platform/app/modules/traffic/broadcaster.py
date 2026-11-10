"""Real-time API Traffic Event Broadcaster for Homelab Architecture Map.

Streams live HTTP and WebSocket traffic passing through the PAP Core Central Gateway
to connected browser clients via WebSocket and Server-Sent Events (SSE).
"""

import asyncio
from collections import deque
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Set
from fastapi import WebSocket

logger = logging.getLogger("homelab.traffic")


class TrafficBroadcaster:
    """Manages real-time API traffic streaming to UI clients via WebSocket and SSE."""

    def __init__(self, max_history: int = 120):
        self._websockets: Set[WebSocket] = set()
        self._history: deque = deque(maxlen=max_history)
        self._subscribers: Set[asyncio.Queue] = set()
        self._total_requests: int = 0
        self._total_latency_ms: float = 0.0
        self._started_at = time.time()

    @property
    def total_requests(self) -> int:
        return self._total_requests

    @property
    def avg_latency_ms(self) -> float:
        if self._total_requests == 0:
            return 1.2
        return round(self._total_latency_ms / self._total_requests, 1)

    def record_and_broadcast(
        self,
        method: str,
        path: str,
        status: int,
        duration_ms: float,
        client_ip: str = "127.0.0.1",
        source: Optional[str] = None,
        target: str = "core",
        sub_target: Optional[str] = None,
        tag: Optional[str] = None,
        color: Optional[str] = None,
        detail: Optional[str] = None,
    ):
        """Record an API request and broadcast it to connected live listeners."""
        # Filter internal traffic polling / noise
        if path.startswith(("/api/v1/traffic", "/ws/traffic", "/favicon.ico")):
            return

        # Classify source and sub-target if not explicitly given
        if not source:
            source = self._classify_source(client_ip, path)
        if not sub_target:
            sub_target = self._classify_sub_target(path)
        if not tag:
            tag = self._classify_tag(path, status)
        if not color:
            color = self._classify_color(source, sub_target, status)
        if not detail:
            detail = f"{method} {path} -> {status} ({duration_ms:.1f}ms) from {client_ip}"

        self._total_requests += 1
        self._total_latency_ms += duration_ms

        event = {
            "id": f"tr-{int(time.time() * 1000) % 1000000}",
            "type": "api_traffic",
            "method": method,
            "path": path,
            "status": status,
            "duration_ms": round(duration_ms, 2),
            "client_ip": client_ip,
            "source": source,
            "target": target,
            "sub_target": sub_target,
            "tag": tag,
            "color": color,
            "detail": detail,
            "total_requests": self._total_requests,
            "avg_latency_ms": self.avg_latency_ms,
            "timestamp": time.time(),
        }

        self._history.append(event)

        # Dispatch async broadcast safely
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._broadcast(event))
        except RuntimeError:
            pass

    def _classify_source(self, client_ip: str, path: str) -> str:
        if "192.168.25.104" in client_ip or path.startswith("/api/nfc") or "/devices" in path:
            return "esp32"
        if ":3005" in client_ip or path.startswith(("/api/v1/projects", "/api/v1/servers", "/api/v1/containers", "/api/v1/deployments", "/ws/servers")):
            return "psm"
        if path.startswith(("/api/v1/stock", "/stock")):
            return "stock"
        if path.startswith("/metrics") or "Prometheus" in client_ip:
            return "grafana"
        if path.startswith("/api/v1/backups"):
            return "hub"
        if path.startswith("/api/v1/dns"):
            return "psm"
        return "hub"

    def _classify_sub_target(self, path: str) -> Optional[str]:
        if path.startswith("/api/v1/stock") or "/nfc" in path:
            return "mysql"
        if "/influx" in path or "/telemetry" in path:
            return "influxdb"
        if path.startswith(("/api/v1/projects", "/api/v1/servers", "/api/v1/auth", "/api/v1/users", "/api/v1/deployments")):
            return "postgres"
        if path.startswith("/api/v1/backups"):
            return "postgres"
        if "/mqtt" in path or "/devices" in path:
            return "mqtt"
        if "/metrics" in path:
            return "grafana"
        return None

    def _classify_tag(self, path: str, status: int) -> str:
        if status >= 400:
            return "ERR_HTTP"
        if "/nfc" in path:
            return "NFC_REAL"
        if "/stock" in path:
            return "STOCK_API"
        if "/projects" in path or "/deployments" in path:
            return "PSM_CORE"
        if "/devices" in path:
            return "IOT_FLEET"
        if "/backups" in path:
            return "BACKUP_ENG"
        if "/metrics" in path:
            return "PROM_SCRAPE"
        if "/dns" in path:
            return "LOCAL_DNS"
        return "API_REAL"

    def _classify_color(self, source: str, sub_target: Optional[str], status: int) -> str:
        if status >= 400:
            return "#ef4444"
        colors = {
            "esp32": "#38bdf8",     # Sky blue
            "hub": "#34d399",       # Emerald green
            "stock": "#fbbf24",     # Amber
            "psm": "#a78bfa",       # Purple
            "grafana": "#f43f5e",   # Rose
            "mysql": "#f59e0b",     # Orange
            "postgres": "#60a5fa",  # Indigo/Blue
            "mqtt": "#06b6d4",      # Cyan
            "influxdb": "#c084fc",  # Purple TSDB
            "router": "#38bdf8",    # Sky Blue Ingress
        }
        return colors.get(source, "#3b82f6")

    async def _broadcast(self, event: dict):
        message = json.dumps(event)

        # 1. Connected WebSockets
        dead_ws = set()
        for ws in list(self._websockets):
            try:
                await ws.send_text(message)
            except Exception:
                dead_ws.add(ws)
        if dead_ws:
            self._websockets.difference_update(dead_ws)

        # 2. SSE Queues
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except Exception:
                pass

    async def connect_ws(self, websocket: WebSocket):
        await websocket.accept()
        self._websockets.add(websocket)
        logger.info("Traffic WebSocket client connected (active: %d)", len(self._websockets))

    def disconnect_ws(self, websocket: WebSocket):
        self._websockets.discard(websocket)

    async def subscribe_sse(self) -> AsyncGenerator[str, None]:
        q = asyncio.Queue(maxsize=100)
        self._subscribers.add(q)
        try:
            while True:
                event = await q.get()
                if event is None:
                    break
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            self._subscribers.discard(q)

    async def shutdown(self):
        """Immediately closes all live WebSocket connections and wakes SSE generators on shutdown."""
        for ws in list(self._websockets):
            try:
                await ws.close(code=1001, reason="Server shutdown")
            except Exception:
                pass
        self._websockets.clear()

        for q in list(self._subscribers):
            try:
                q.put_nowait(None)
            except Exception:
                pass
        self._subscribers.clear()

    def get_recent(self) -> List[Dict[str, Any]]:
        return list(self._history)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_requests": self._total_requests,
            "avg_latency_ms": self.avg_latency_ms,
            "connected_ws_clients": len(self._websockets),
            "active_sse_subscribers": len(self._subscribers),
            "recent_count": len(self._history),
            "uptime_seconds": round(time.time() - self._started_at, 1),
        }


traffic_broadcaster = TrafficBroadcaster()

