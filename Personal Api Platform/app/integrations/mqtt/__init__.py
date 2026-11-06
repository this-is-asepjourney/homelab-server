"""Mosquitto MQTT adapter for ESP32 telemetry subscription and command publishing."""

import json
import socket
from typing import Any

from app.core.config import get_settings
from app.core.logging import logger


class MqttAdapter:
    """Adapter managing MQTT topic conventions and command publication to Mosquitto."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password_ref: str = "MQTT_PASSWORD",
    ) -> None:
        settings = get_settings()
        self.host = host or settings.MQTT_HOST
        self.port = port or settings.MQTT_PORT
        self.username = username or settings.MQTT_USERNAME
        self.password = settings.resolve_secret_reference(password_ref) or ""
        self.enabled = settings.MQTT_ENABLED

    @staticmethod
    def telemetry_topic(device_uid: str) -> str:
        return f"pap/iot/{device_uid}/telemetry"

    @staticmethod
    def status_topic(device_uid: str) -> str:
        return f"pap/iot/{device_uid}/status"

    @staticmethod
    def command_topic(device_uid: str) -> str:
        return f"pap/iot/{device_uid}/command"

    @staticmethod
    def config_topic(device_uid: str) -> str:
        return f"pap/iot/{device_uid}/config"

    def check_health(self) -> dict[str, Any]:
        if not self.enabled:
            return {
                "service": "mosquitto_mqtt",
                "host": self.host,
                "port": self.port,
                "reachable": False,
                "status": "disabled_by_config",
            }
        try:
            with socket.create_connection((self.host, self.port), timeout=2.0):
                return {
                    "service": "mosquitto_mqtt",
                    "host": self.host,
                    "port": self.port,
                    "reachable": True,
                    "status": "online",
                }
        except Exception:
            return {
                "service": "mosquitto_mqtt",
                "host": self.host,
                "port": self.port,
                "reachable": False,
                "status": "offline",
            }

    def publish_command(
        self,
        device_uid: str,
        correlation_id: str,
        command: str,
        parameters: dict[str, Any],
        expires_at_iso: str,
        qos: int = 1,
    ) -> bool:
        """Publish an authorized command message to pap/iot/{device_id}/command."""
        topic = self.command_topic(device_uid)
        message_payload = {
            "device_id": device_uid,
            "correlation_id": correlation_id,
            "command": command,
            "parameters": parameters,
            "expires_at": expires_at_iso,
        }
        if not self.enabled:
            logger.info(
                f"MQTT disabled; command {correlation_id} queued for topic {topic}",
                extra={"extra_data": {"topic": topic, "correlation_id": correlation_id}},
            )
            return True

        try:
            import paho.mqtt.publish as publish

            auth = None
            if self.username and self.username != "REPLACE_ME":
                auth = {"username": self.username, "password": self.password}

            publish.single(
                topic=topic,
                payload=json.dumps(message_payload),
                qos=qos,
                retain=False,
                hostname=self.host,
                port=self.port,
                auth=auth,
            )
            return True
        except Exception as exc:
            logger.warning(f"Failed to publish MQTT command {correlation_id}: {type(exc).__name__}")
            return False

