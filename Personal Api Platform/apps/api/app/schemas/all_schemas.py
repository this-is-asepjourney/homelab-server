from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

# --- Auth & User Schemas ---
class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserResponse"

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str = "operator"

class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    theme: Optional[str] = None
    is_active: Optional[bool] = None

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    role: str
    theme: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- Server Schemas ---
class ServerCreate(BaseModel):
    name: str
    hostname: Optional[str] = "localhost"
    description: Optional[str] = None
    os_name: Optional[str] = "Ubuntu Server"
    os_version: Optional[str] = "24.04 LTS"
    architecture: Optional[str] = "x86_64"

class ServerUpdate(BaseModel):
    name: Optional[str] = None
    hostname: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class AgentInfoResponse(BaseModel):
    id: str
    agent_version: str
    connected_at: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    revoked_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class MetricsSnapshot(BaseModel):
    cpu_usage: float
    memory_usage: float
    memory_used_bytes: int
    memory_total_bytes: int
    disk_usage: float
    disk_used_bytes: int
    disk_total_bytes: int
    network_rx: float
    network_tx: float
    uptime: int
    load_avg: Optional[List[float]] = None
    cpu_cores: Optional[int] = None
    container_stats: Optional[List[Dict[str, Any]]] = None
    disk_partitions: Optional[List[Dict[str, Any]]] = None
    recorded_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ServerResponse(BaseModel):
    id: str
    owner_id: str
    name: str
    hostname: str
    description: Optional[str] = None
    os_name: str
    os_version: str
    architecture: str
    status: str
    last_seen: Optional[datetime] = None
    created_at: datetime
    agent: Optional[AgentInfoResponse] = None
    latest_metrics: Optional[MetricsSnapshot] = None

    model_config = ConfigDict(from_attributes=True)

class ServerRegistrationResponse(BaseModel):
    server_id: str
    agent_token: str
    install_command: str
    docker_run_command: str

# --- Agent Schemas ---
class AgentRegisterRequest(BaseModel):
    server_id: str
    agent_token: str
    agent_version: str = "0.1.0"
    os_name: Optional[str] = None
    os_version: Optional[str] = None
    architecture: Optional[str] = None
    hostname: Optional[str] = None

class HeartbeatRequest(BaseModel):
    agent_id: str
    server_id: str
    agent_version: str = "0.1.0"
    status: str = "online"

class AgentInventoryRequest(BaseModel):
    server_id: str
    containers: List[Dict[str, Any]] = []
    images: List[Dict[str, Any]] = []
    volumes: List[Dict[str, Any]] = []
    networks: List[Dict[str, Any]] = []

# --- Metrics Schemas ---
class MetricsReportRequest(BaseModel):
    server_id: str
    cpu_usage: float
    memory_usage: float
    memory_used_bytes: int = 0
    memory_total_bytes: int = 0
    disk_usage: float
    disk_used_bytes: int = 0
    disk_free_bytes: int = 0
    disk_total_bytes: int = 0
    disk_read_bytes: int = 0
    disk_write_bytes: int = 0
    disk_read_count: int = 0
    disk_write_count: int = 0
    disk_read_bytes_per_sec: float = 0.0
    disk_write_bytes_per_sec: float = 0.0
    network_rx_bytes_per_sec: float = 0.0
    network_tx_bytes_per_sec: float = 0.0
    network_total_rx_bytes: int = 0
    network_total_tx_bytes: int = 0
    network_packets_recv: int = 0
    network_packets_sent: int = 0
    network_err_in: int = 0
    network_err_out: int = 0
    network_drop_in: int = 0
    network_drop_out: int = 0
    network_interfaces: Optional[List[Dict[str, Any]]] = None
    listening_ports: Optional[List[Dict[str, Any]]] = None
    connection_stats: Optional[Dict[str, Any]] = None
    uptime_seconds: int = 0
    load_avg: Optional[List[float]] = None
    cpu_cores: Optional[int] = None
    container_stats: Optional[List[Dict[str, Any]]] = None
    disk_partitions: Optional[List[Dict[str, Any]]] = None

# --- Container Schemas ---
class ContainerResponse(BaseModel):
    id: str
    server_id: str
    docker_id: str
    name: str
    image: str
    status: str
    state: str
    ports: Optional[List[Dict[str, Any]]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ContainerActionRequest(BaseModel):
    action: str  # start, stop, restart, remove

class EnvironmentVariableItem(BaseModel):
    key: str
    value: str

class EnvironmentUpdateRequest(BaseModel):
    variables: List[EnvironmentVariableItem]

class EnvironmentItemResponse(BaseModel):
    key: str
    masked_value: str
    updated_at: datetime

# --- Project Schemas ---
class ProjectCreate(BaseModel):
    server_id: str
    name: str
    description: Optional[str] = None
    framework: str = "Node.js / Docker"
    source_type: str = "git"  # git, upload
    repository_url: Optional[str] = None
    branch: Optional[str] = "main"
    dockerfile_path: Optional[str] = "Dockerfile"
    compose_path: Optional[str] = "docker-compose.yml"
    auto_provision_db: bool = True
    database_name: Optional[str] = None
    port_mappings: Optional[str] = "3000:3000"
    environment_variables: Optional[List[EnvironmentVariableItem]] = None
    auto_deploy: bool = True

class ProjectDatabaseProvisionRequest(BaseModel):
    db_name: Optional[str] = None
    override_env: bool = True

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    framework: Optional[str] = None
    repository_url: Optional[str] = None
    branch: Optional[str] = None
    dockerfile_path: Optional[str] = None
    compose_path: Optional[str] = None
    port_mappings: Optional[str] = None

class ProjectResponse(BaseModel):
    id: str
    server_id: str
    server_name: Optional[str] = None
    owner_id: str
    name: str
    description: Optional[str] = None
    framework: str
    source_type: str
    status: str
    repository_url: Optional[str] = None
    branch: Optional[str] = None
    dockerfile_path: Optional[str] = None
    compose_path: Optional[str] = None
    port_mappings: Optional[str] = "3000:3000"
    deployment_id: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- Deployment Schemas ---
class DeploymentCreateGit(BaseModel):
    project_id: str
    branch: Optional[str] = None
    commit_hash: Optional[str] = None
    port_mappings: Optional[str] = None
    environment_variables: Optional[List[EnvironmentVariableItem]] = None

class DeploymentCreateCompose(BaseModel):
    project_id: str
    compose_path: Optional[str] = "docker-compose.yml"

class DeploymentResponse(BaseModel):
    id: str
    project_id: str
    project_name: Optional[str] = None
    version: int
    commit_hash: Optional[str] = None
    image_tag: Optional[str] = None
    status: str
    triggered_by: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[int] = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class DeploymentLogResponse(BaseModel):
    id: str
    deployment_id: str
    sequence: int
    level: str
    message: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- Job Schemas ---
class JobResponse(BaseModel):
    id: str
    server_id: str
    deployment_id: Optional[str] = None
    job_type: str
    payload: Dict[str, Any]
    status: str
    priority: int
    attempts: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class JobCompleteRequest(BaseModel):
    status: str  # success, failed
    error_message: Optional[str] = None
    output: Optional[Dict[str, Any]] = None
    duration_seconds: int = 0

class JobLogBatchRequest(BaseModel):
    logs: List[Dict[str, Any]]  # [{"level": "info", "message": "...", "sequence": 1}]

# --- Backup Schemas ---
class BackupCreate(BaseModel):
    name: str
    backup_type: str = "database"  # database, project, volume
    target_id: Optional[str] = None

class BackupResponse(BaseModel):
    id: str
    name: str
    backup_type: str
    target_id: Optional[str] = None
    size_bytes: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# --- Audit Schemas ---
class AuditLogResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
