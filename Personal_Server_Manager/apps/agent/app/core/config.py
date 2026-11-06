import os
try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseModel as BaseSettings  # type: ignore

class AgentSettings(BaseSettings):
    SERVER_ID: str = os.getenv("SERVER_ID", "default-server")
    AGENT_TOKEN: str = os.getenv("AGENT_TOKEN", "psm_agent_token_dev")
    CONTROL_PLANE_URL: str = os.getenv("CONTROL_PLANE_URL", "http://localhost:8000")
    AGENT_VERSION: str = "0.1.0"
    
    # Intervals in seconds (from Section 9.3)
    HEARTBEAT_INTERVAL: int = 15
    METRICS_INTERVAL: int = 5
    INVENTORY_INTERVAL: int = 30
    
    # Workspace paths
    BASE_DIR: str = os.getenv("PSM_BASE_DIR", "./storage/psm")
    WORKSPACE_DIR: str = os.path.join(os.getenv("PSM_BASE_DIR", "./storage/psm"), "workspaces")
    RELEASE_DIR: str = os.path.join(os.getenv("PSM_BASE_DIR", "./storage/psm"), "releases")

    model_config = {
        "env_file": ".env",
        "extra": "ignore"
    }

agent_settings = AgentSettings()
os.makedirs(agent_settings.WORKSPACE_DIR, exist_ok=True)
os.makedirs(agent_settings.RELEASE_DIR, exist_ok=True)

