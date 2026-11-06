# Installing the PSM Agent on Ubuntu Server

The PSM agent runs on each server you want to manage.

## Prerequisites
- Ubuntu Server 22.04 LTS or 24.04 LTS
- Docker Engine & Docker Compose installed
- Python 3.10+ (or run via Docker container)

## Method 1: Automatic Script Installation (Recommended)

1. Open the PSM Web Dashboard at `http://<control-plane>:3005/servers`.
2. Click **"Register Server"**, enter a server name, and copy the generated command.
3. Run the command on your target Ubuntu server:

```bash
curl -sSL http://<control-plane>:8000/install-agent.sh | \
  PSM_SERVER_ID="<your-server-id>" \
  PSM_TOKEN="<your-agent-token>" \
  PSM_CONTROL_PLANE="http://<control-plane>:8000" bash
```

4. Enable and start the systemd service:
```bash
sudo systemctl enable --now psm-agent
```

## Method 2: Docker Container Deployment

If you prefer running the agent inside Docker:

```bash
docker run -d \
  --name psm-agent \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /opt/psm:/opt/psm \
  -e SERVER_ID="<your-server-id>" \
  -e AGENT_TOKEN="<your-agent-token>" \
  -e CONTROL_PLANE_URL="http://<control-plane>:8000" \
  personal-server-manager-agent:latest
```

Once started, the agent immediately handshakes with the Control Plane and reports metrics every 5 seconds.

