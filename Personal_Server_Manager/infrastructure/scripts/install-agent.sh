#!/usr/bin/env bash
set -e

# ========================================================
# PSM Agent Automatic Installer for Ubuntu Server
# ========================================================

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo)."
  exit 1
fi

if [ -z "$PSM_SERVER_ID" ] || [ -z "$PSM_TOKEN" ]; then
  echo "Error: PSM_SERVER_ID and PSM_TOKEN environment variables must be supplied."
  echo "Example:"
  echo "  curl -sSL http://<CONTROL_PLANE>:8000/install-agent.sh | PSM_SERVER_ID=xxx PSM_TOKEN=yyy bash"
  exit 1
fi

CONTROL_PLANE_URL="${PSM_CONTROL_PLANE:-http://localhost:8000}"
INSTALL_DIR="/opt/psm/agent"

echo "Setting up PSM Agent directory: $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
mkdir -p /opt/psm/workspaces
mkdir -p /opt/psm/releases

# Install python3 dependencies if needed
apt-get update -y
apt-get install -y python3 python3-pip python3-venv git curl

# Write environment configuration
cat <<EOF > "$INSTALL_DIR/agent.env"
SERVER_ID=$PSM_SERVER_ID
AGENT_TOKEN=$PSM_TOKEN
CONTROL_PLANE_URL=$CONTROL_PLANE_URL
PSM_BASE_DIR=/opt/psm
EOF

chmod 600 "$INSTALL_DIR/agent.env"
echo "PSM Agent configuration written to $INSTALL_DIR/agent.env."
echo "Agent installation complete. Ready to run via systemd or docker."

