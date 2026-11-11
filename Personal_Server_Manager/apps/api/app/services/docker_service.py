import json
import logging
import os
import re
import subprocess
from typing import Any, Dict, List, Optional

logger = logging.getLogger("psm.docker")

DOCKER_SOCKET_PATH = "/var/run/docker.sock"


def decode_docker_stream(data: bytes) -> str:
    """Decode Docker multiplexed log stream (stdout=1, stderr=2 with 8-byte header) or plain text."""
    if not data:
        return ""
    length = len(data)
    # Check if header matches Docker's standard multiplexing stream format
    if length >= 8 and data[0] in (1, 2) and data[1] == 0 and data[2] == 0 and data[3] == 0:
        lines = []
        idx = 0
        while idx + 8 <= length:
            stream_type = data[idx]  # 1: stdout, 2: stderr
            frame_len = int.from_bytes(data[idx + 4 : idx + 8], byteorder="big")
            idx += 8
            if idx + frame_len <= length:
                chunk = data[idx : idx + frame_len].decode("utf-8", errors="replace")
                lines.append(chunk)
                idx += frame_len
            else:
                chunk = data[idx:].decode("utf-8", errors="replace")
                lines.append(chunk)
                break
        return "".join(lines)
    return data.decode("utf-8", errors="replace")


class DockerEngineService:
    @classmethod
    def is_socket_available(cls) -> bool:
        return os.path.exists(DOCKER_SOCKET_PATH)

    @classmethod
    def _get_uds_client(cls):
        import httpx

        if cls.is_socket_available():
            try:
                transport = httpx.HTTPTransport(uds=DOCKER_SOCKET_PATH)
                return httpx.Client(transport=transport, base_url="http://docker", timeout=8.0)
            except Exception as e:
                logger.warning("Failed to create UDS httpx client: %s", e)
        return None

    @classmethod
    def list_containers(cls) -> List[Dict[str, Any]]:
        """List all containers from Docker daemon."""
        client = cls._get_uds_client()
        if client:
            try:
                resp = client.get("/containers/json?all=1")
                if resp.status_code == 200:
                    items = resp.json()
                    results = []
                    for it in items:
                        names = it.get("Names") or []
                        primary_name = names[0].lstrip("/") if names else it.get("Id", "")[:12]
                        results.append({
                            "docker_id": it.get("Id", "")[:12],
                            "full_id": it.get("Id", ""),
                            "name": primary_name,
                            "names": [n.lstrip("/") for n in names],
                            "image": it.get("Image", ""),
                            "status": it.get("Status", ""),
                            "state": it.get("State", ""),
                            "ports": it.get("Ports", []),
                        })
                    return results
            except Exception as e:
                logger.warning("UDS list_containers error: %s", e)

        # Fallback to CLI
        try:
            res = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{json .}}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            containers = []
            for line in res.stdout.strip().split("\n"):
                if line.strip():
                    item = json.loads(line)
                    name = item.get("Names", "").replace("/", "")
                    containers.append({
                        "docker_id": item.get("ID", ""),
                        "full_id": item.get("ID", ""),
                        "name": name,
                        "names": [name],
                        "image": item.get("Image", ""),
                        "status": item.get("Status", ""),
                        "state": item.get("State", "unknown"),
                        "ports": [],
                    })
            return containers
        except Exception:
            return []

    @classmethod
    def inspect_container(cls, cid_or_name: str) -> Dict[str, Any]:
        """Inspect detailed container state (exit code, health, started_at, finished_at, error)."""
        client = cls._get_uds_client()
        if client:
            try:
                resp = client.get(f"/containers/{cid_or_name}/json")
                if resp.status_code == 200:
                    data = resp.json()
                    state = data.get("State", {})
                    net_settings = data.get("NetworkSettings", {})
                    return {
                        "id": data.get("Id", "")[:12],
                        "full_id": data.get("Id", ""),
                        "name": data.get("Name", "").lstrip("/"),
                        "image": data.get("Config", {}).get("Image", ""),
                        "state": state.get("Status", "unknown"),
                        "running": state.get("Running", False),
                        "restarting": state.get("Restarting", False),
                        "oom_killed": state.get("OOMKilled", False),
                        "dead": state.get("Dead", False),
                        "exit_code": state.get("ExitCode"),
                        "error": state.get("Error", ""),
                        "started_at": state.get("StartedAt", ""),
                        "finished_at": state.get("FinishedAt", ""),
                        "ports": net_settings.get("Ports", {}),
                        "ip_address": net_settings.get("IPAddress", ""),
                    }
            except Exception as e:
                logger.warning("UDS inspect error for %s: %s", cid_or_name, e)

        # Fallback to CLI
        try:
            res = subprocess.run(
                ["docker", "inspect", cid_or_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                data = json.loads(res.stdout)
                if data:
                    item = data[0]
                    state = item.get("State", {})
                    net = item.get("NetworkSettings", {})
                    return {
                        "id": item.get("Id", "")[:12],
                        "full_id": item.get("Id", ""),
                        "name": item.get("Name", "").lstrip("/"),
                        "image": item.get("Config", {}).get("Image", ""),
                        "state": state.get("Status", "unknown"),
                        "running": state.get("Running", False),
                        "restarting": state.get("Restarting", False),
                        "oom_killed": state.get("OOMKilled", False),
                        "dead": state.get("Dead", False),
                        "exit_code": state.get("ExitCode"),
                        "error": state.get("Error", ""),
                        "started_at": state.get("StartedAt", ""),
                        "finished_at": state.get("FinishedAt", ""),
                        "ports": net.get("Ports", {}),
                        "ip_address": net.get("IPAddress", ""),
                    }
        except Exception:
            pass
        return {}

    @classmethod
    def get_container_logs(cls, cid_or_name: str, tail: int = 150) -> str:
        """Fetch raw live logs (stdout + stderr) from container."""
        client = cls._get_uds_client()
        if client:
            try:
                resp = client.get(
                    f"/containers/{cid_or_name}/logs?stdout=1&stderr=1&tail={tail}&timestamps=0"
                )
                if resp.status_code == 200:
                    return decode_docker_stream(resp.content)
            except Exception as e:
                logger.warning("UDS logs error for %s: %s", cid_or_name, e)

        # Fallback to CLI
        try:
            res = subprocess.run(
                ["docker", "logs", "--tail", str(tail), cid_or_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
            output = res.stdout or res.stderr
            return output if output else "No log output recorded yet for this container."
        except Exception as e:
            return f"Error retrieving logs: {e}"

    @classmethod
    def restart_container(cls, cid_or_name: str) -> bool:
        """Restart container."""
        client = cls._get_uds_client()
        if client:
            try:
                resp = client.post(f"/containers/{cid_or_name}/restart?t=5")
                return resp.status_code in (204, 200)
            except Exception as e:
                logger.warning("UDS restart error: %s", e)

        try:
            res = subprocess.run(["docker", "restart", cid_or_name], timeout=15)
            return res.returncode == 0
        except Exception:
            return False

    @classmethod
    def find_container_by_project(
        cls, project_name: str, project_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Match container by project name, slug, or project ID."""
        all_containers = cls.list_containers()
        if not all_containers:
            return None

        clean_slug = re.sub(r"[^a-zA-Z0-9_.-]", "-", project_name.lower())
        candidates = [
            project_name.lower(),
            clean_slug,
            clean_slug.replace("-", "_"),
            clean_slug.replace("_", "-"),
        ]
        if project_id:
            candidates.append(f"proj-{project_id}")
            candidates.append(project_id[:12])

        # 1. Exact match on any candidate
        for c in all_containers:
            c_name = c.get("name", "").lower()
            all_names = [n.lower() for n in c.get("names", [])]
            for cand in candidates:
                if c_name == cand or cand in all_names:
                    return c

        # 2. Substring match
        for c in all_containers:
            c_name = c.get("name", "").lower()
            if clean_slug in c_name or project_name.lower() in c_name:
                return c

        return None

