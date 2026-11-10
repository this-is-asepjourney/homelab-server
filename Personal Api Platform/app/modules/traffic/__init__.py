"""Traffic module for real-time API communication streaming and topology telemetry."""
from app.modules.traffic.broadcaster import traffic_broadcaster
from app.modules.traffic.router import router

__all__ = ["traffic_broadcaster", "router"]
