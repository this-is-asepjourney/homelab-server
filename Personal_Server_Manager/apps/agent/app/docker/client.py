import subprocess
import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class DockerManager:
    def __init__(self):
        self._sdk = None
        try:
            import docker
            self._sdk = docker.from_env()
        except Exception as e:
            logger.info(f"Docker SDK not available or daemon not running: {e}. Falling back to CLI.")

    def is_available(self) -> bool:
        if self._sdk:
            try:
                self._sdk.ping()
                return True
            except Exception:
                pass
        try:
            res = subprocess.run(["docker", "info"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
            return res.returncode == 0
        except Exception:
            return False

    def list_containers(self) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []

        if self._sdk:
            try:
                containers = []
                for c in self._sdk.containers.list(all=True):
                    ports_list = []
                    port_bindings = (c.attrs.get("NetworkSettings", {}).get("Ports") or {})
                    for internal_port, host_bindings in port_bindings.items():
                        internal_num = internal_port.split("/")[0]
                        proto = internal_port.split("/")[1] if "/" in internal_port else "tcp"
                        if host_bindings:
                            for hb in host_bindings:
                                ports_list.append({
                                    "internal": int(internal_num) if internal_num.isdigit() else internal_num,
                                    "external": int(hb.get("HostPort", internal_num)) if str(hb.get("HostPort", "")).isdigit() else internal_num,
                                    "protocol": proto,
                                })
                        else:
                            ports_list.append({
                                "internal": int(internal_num) if internal_num.isdigit() else internal_num,
                                "external": int(internal_num) if internal_num.isdigit() else internal_num,
                                "protocol": proto,
                            })
                    image_tags = c.image.tags if c.image and c.image.tags else [c.attrs.get("Config", {}).get("Image", "unknown")]
                    containers.append({
                        "docker_id": c.short_id,
                        "name": c.name,
                        "image": image_tags[0] if image_tags else "unknown",
                        "status": "running" if c.status == "running" else "stopped",
                        "state": c.status,
                        "ports": ports_list,
                    })
                return containers
            except Exception as e:
                logger.warning(f"SDK list_containers failed, trying CLI: {e}")

        try:
            cmd = ["docker", "ps", "-a", "--format", "{{json .}}"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            containers = []
            for line in res.stdout.strip().split("\n"):
                if line.strip():
                    item = json.loads(line)
                    containers.append({
                        "docker_id": item.get("ID", ""),
                        "name": item.get("Names", "").replace("/", ""),
                        "image": item.get("Image", ""),
                        "status": "running" if "Up" in item.get("Status", "") else "stopped",
                        "state": item.get("State", "exited"),
                        "ports": [],
                    })
            return containers
        except Exception as e:
            logger.error(f"Error listing containers: {e}")
            return []

    def list_images(self) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []
        try:
            cmd = ["docker", "images", "--format", "{{json .}}"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            images = []
            for line in res.stdout.strip().split("\n"):
                if line.strip():
                    item = json.loads(line)
                    images.append({
                        "id": item.get("ID", ""),
                        "repository": item.get("Repository", "<none>"),
                        "tag": item.get("Tag", "latest"),
                        "size": item.get("Size", "0 MB"),
                        "created": item.get("CreatedSince", "recently"),
                    })
            return images
        except Exception:
            return []

    def list_volumes(self) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []
        try:
            cmd = ["docker", "volume", "ls", "--format", "{{json .}}"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            volumes = []
            for line in res.stdout.strip().split("\n"):
                if line.strip():
                    item = json.loads(line)
                    volumes.append({
                        "name": item.get("Name", ""),
                        "driver": item.get("Driver", "local"),
                        "mountpoint": item.get("Mountpoint", f"/var/lib/docker/volumes/{item.get('Name', '')}/_data"),
                    })
            return volumes
        except Exception:
            return []

    def list_networks(self) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []
        try:
            cmd = ["docker", "network", "ls", "--format", "{{json .}}"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            networks = []
            for line in res.stdout.strip().split("\n"):
                if line.strip():
                    item = json.loads(line)
                    networks.append({
                        "name": item.get("Name", ""),
                        "driver": item.get("Driver", "bridge"),
                        "scope": item.get("Scope", "local"),
                    })
            return networks
        except Exception:
            return []

    def start_container(self, container_id: str) -> bool:
        try:
            res = subprocess.run(["docker", "start", container_id], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            return res.returncode == 0
        except Exception:
            return False

    def stop_container(self, container_id: str) -> bool:
        try:
            res = subprocess.run(["docker", "stop", container_id], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
            return res.returncode == 0
        except Exception:
            return False

    def restart_container(self, container_id: str) -> bool:
        try:
            res = subprocess.run(["docker", "restart", container_id], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
            return res.returncode == 0
        except Exception:
            return False

    def remove_container(self, container_id: str, force: bool = False) -> bool:
        try:
            args = ["docker", "rm"]
            if force:
                args.append("-f")
            args.append(container_id)
            res = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            return res.returncode == 0
        except Exception:
            return False

    def get_container_logs(self, container_id: str, tail: int = 100) -> str:
        try:
            res = subprocess.run(["docker", "logs", "--tail", str(tail), container_id], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            return res.stdout or res.stderr
        except Exception as e:
            return f"Error reading logs: {e}"

    def prune_system(self, all_images: bool = False) -> Dict[str, Any]:
        """Prune unused containers, networks, and images to free disk space."""
        try:
            cmd = ["docker", "system", "prune", "-f"]
            if all_images:
                cmd.append("-a")
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
            return {
                "success": res.returncode == 0,
                "output": res.stdout.strip() if res.stdout else res.stderr.strip()
            }
        except Exception as e:
            return {"success": False, "output": f"Prune failed: {e}"}

    def inspect_container(self, container_id: str) -> Dict[str, Any]:
        """Inspect container configuration, networking, mounts, and health."""
        if not self.is_available():
            return {}
        try:
            cmd = ["docker", "inspect", container_id]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                if data and len(data) > 0:
                    info = data[0]
                    # Filter sensitive environment variables
                    safe_envs = []
                    for env_line in info.get("Config", {}).get("Env", []):
                        parts = env_line.split("=", 1)
                        k = parts[0]
                        v = parts[1] if len(parts) > 1 else ""
                        if any(s in k.upper() for s in ["PASS", "SECRET", "KEY", "TOKEN", "AUTH"]):
                            safe_envs.append(f"{k}=********")
                        else:
                            safe_envs.append(f"{k}={v}")

                    net_settings = info.get("NetworkSettings", {})
                    networks = {}
                    for net_name, net_data in net_settings.get("Networks", {}).items():
                        networks[net_name] = {
                            "ip_address": net_data.get("IPAddress", ""),
                            "gateway": net_data.get("Gateway", ""),
                            "mac_address": net_data.get("MacAddress", "")
                        }

                    return {
                        "id": info.get("Id", "")[:12],
                        "name": info.get("Name", "").lstrip("/"),
                        "created": info.get("Created", ""),
                        "state": info.get("State", {}),
                        "image": info.get("Config", {}).get("Image", ""),
                        "cmd": info.get("Config", {}).get("Cmd", []),
                        "env": safe_envs,
                        "networks": networks,
                        "ip_address": net_settings.get("IPAddress", ""),
                        "ports": net_settings.get("Ports", {}),
                        "mounts": [
                            {
                                "type": m.get("Type", ""),
                                "source": m.get("Source", ""),
                                "destination": m.get("Destination", ""),
                                "mode": m.get("Mode", "")
                            }
                            for m in info.get("Mounts", [])
                        ],
                        "restart_policy": info.get("HostConfig", {}).get("RestartPolicy", {}),
                    }
        except Exception as e:
            logger.warning(f"Failed to inspect container {container_id}: {e}")
        return {}

    def get_all_container_stats(self) -> List[Dict[str, Any]]:
        """Collect live CPU and Memory statistics for all running containers."""
        if not self.is_available():
            return []
        try:
            cmd = ["docker", "stats", "--no-stream", "--format", "{{json .}}"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8)
            stats = []
            for line in res.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    stats.append({
                        "container_id": item.get("ID", ""),
                        "name": item.get("Name", ""),
                        "cpu_percent": item.get("CPUPerc", "0.0%").replace("%", "").strip(),
                        "mem_usage": item.get("MemUsage", "0B / 0B"),
                        "mem_percent": item.get("MemPerc", "0.0%").replace("%", "").strip(),
                        "net_io": item.get("NetIO", "0B / 0B"),
                        "block_io": item.get("BlockIO", "0B / 0B")
                    })
                except Exception:
                    pass
            return stats
        except Exception:
            return []

docker_manager = DockerManager()
