import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Boolean, Integer, Float, DateTime, ForeignKey, JSON, BigInteger
)
from sqlalchemy.orm import relationship
from apps.api.app.database.session import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(String(30), default="operator", nullable=False)  # owner, admin, operator, viewer
    theme = Column(String(20), default="system", nullable=False)  # system, dark, light
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    servers = relationship("Server", back_populates="owner", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="owner")
    audit_logs = relationship("AuditLog", back_populates="user")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    refresh_token_hash = Column(Text, nullable=False)
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="sessions")


class Server(Base):
    __tablename__ = "servers"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    hostname = Column(String(255), default="localhost", nullable=False)
    description = Column(Text, nullable=True)
    os_name = Column(String(100), default="Ubuntu Server", nullable=False)
    os_version = Column(String(100), default="24.04 LTS", nullable=False)
    architecture = Column(String(30), default="x86_64", nullable=False)
    status = Column(String(30), default="pending", nullable=False, index=True)  # online, offline, degraded, maintenance, pending
    last_seen = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    owner = relationship("User", back_populates="servers")
    agent = relationship("Agent", uselist=False, back_populates="server", cascade="all, delete-orphan")
    agent_tokens = relationship("AgentToken", back_populates="server", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="server")
    metrics = relationship("ServerMetric", back_populates="server", cascade="all, delete-orphan")
    containers = relationship("Container", back_populates="server", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="server", cascade="all, delete-orphan")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    server_id = Column(String(36), ForeignKey("servers.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    agent_version = Column(String(30), default="0.1.0", nullable=False)
    credential_hash = Column(Text, nullable=False)
    connected_at = Column(DateTime(timezone=True), nullable=True)
    last_seen = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    server = relationship("Server", back_populates="agent")


class AgentToken(Base):
    __tablename__ = "agent_tokens"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    server_id = Column(String(36), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(Text, nullable=False)
    name = Column(String(100), default="default", nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    server = relationship("Server", back_populates="agent_tokens")


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    server_id = Column(String(36), ForeignKey("servers.id"), nullable=False, index=True)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    framework = Column(String(50), default="Node.js / Docker", nullable=False)
    source_type = Column(String(20), default="git", nullable=False)  # git, upload
    status = Column(String(30), default="active", nullable=False)  # active, stopped, failed
    port_mappings = Column(String(255), default="3000:3000", nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    server = relationship("Server", back_populates="projects")
    owner = relationship("User", back_populates="projects")
    source = relationship("ProjectSource", uselist=False, back_populates="project", cascade="all, delete-orphan")
    deployments = relationship("Deployment", back_populates="project", cascade="all, delete-orphan")
    environment_variables = relationship("EnvironmentVariable", back_populates="project", cascade="all, delete-orphan")


class ProjectSource(Base):
    __tablename__ = "project_sources"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), unique=True, nullable=False)
    repository_url = Column(Text, nullable=True)
    branch = Column(String(150), default="main", nullable=True)
    credential_ref = Column(Text, nullable=True)
    dockerfile_path = Column(String(255), default="Dockerfile", nullable=True)
    compose_path = Column(String(255), default="docker-compose.yml", nullable=True)
    upload_object_key = Column(Text, nullable=True)

    project = relationship("Project", back_populates="source")


class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, default=1, nullable=False)
    commit_hash = Column(String(100), nullable=True)
    image_tag = Column(String(255), nullable=True)
    status = Column(String(30), default="queued", nullable=False)  # queued, preparing, building, deploying, success, failed, cancelled, rolling_back
    triggered_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, default=0, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    project = relationship("Project", back_populates="deployments")
    logs = relationship("DeploymentLog", back_populates="deployment", cascade="all, delete-orphan", order_by="DeploymentLog.sequence")
    jobs = relationship("Job", back_populates="deployment")


class DeploymentLog(Base):
    __tablename__ = "deployment_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    deployment_id = Column(String(36), ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence = Column(BigInteger, nullable=False)
    level = Column(String(20), default="info", nullable=False)  # info, warning, error
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    deployment = relationship("Deployment", back_populates="logs")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    server_id = Column(String(36), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    deployment_id = Column(String(36), ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True)
    job_type = Column(String(50), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    status = Column(String(30), default="queued", nullable=False, index=True)  # queued, running, success, failed, cancelled
    priority = Column(Integer, default=10, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    server = relationship("Server", back_populates="jobs")
    deployment = relationship("Deployment", back_populates="jobs")


class EnvironmentVariable(Base):
    __tablename__ = "environment_variables"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(255), nullable=False)
    encrypted_value = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    project = relationship("Project", back_populates="environment_variables")


class Container(Base):
    __tablename__ = "containers"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    server_id = Column(String(36), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    docker_id = Column(String(100), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    image = Column(String(255), nullable=False)
    status = Column(String(50), default="stopped", nullable=False)
    state = Column(String(50), default="exited", nullable=False)
    ports = Column(JSON, nullable=True, default=list)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    server = relationship("Server", back_populates="containers")


class Volume(Base):
    __tablename__ = "volumes"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    server_id = Column(String(36), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    driver = Column(String(50), default="local", nullable=False)
    mountpoint = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class DockerNetwork(Base):
    __tablename__ = "docker_networks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    server_id = Column(String(36), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    driver = Column(String(50), default="bridge", nullable=False)
    scope = Column(String(50), default="local", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class DockerImage(Base):
    __tablename__ = "docker_images"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    server_id = Column(String(36), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    image_id = Column(String(100), nullable=False)
    repository = Column(String(255), nullable=False)
    tag = Column(String(100), default="latest", nullable=False)
    size = Column(String(50), default="0 MB", nullable=False)
    created_since = Column(String(100), default="recently", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class Backup(Base):
    __tablename__ = "backups"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(150), nullable=False)
    backup_type = Column(String(50), default="database", nullable=False)  # database, project, volume
    target_id = Column(String(36), nullable=True)
    size_bytes = Column(BigInteger, default=0, nullable=False)
    status = Column(String(30), default="completed", nullable=False)  # completed, failed, restoring
    file_path = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True, default=dict)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    level = Column(String(20), default="info", nullable=False)  # info, warning, critical
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)



class ServerMetric(Base):
    __tablename__ = "server_metrics"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    server_id = Column(String(36), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    cpu_usage = Column(Float, default=0.0, nullable=False)
    memory_usage = Column(Float, default=0.0, nullable=False)
    memory_used_bytes = Column(BigInteger, default=0, nullable=False)
    memory_total_bytes = Column(BigInteger, default=0, nullable=False)
    disk_usage = Column(Float, default=0.0, nullable=False)
    disk_used_bytes = Column(BigInteger, default=0, nullable=False)
    disk_total_bytes = Column(BigInteger, default=0, nullable=False)
    network_rx = Column(Float, default=0.0, nullable=False)
    network_tx = Column(Float, default=0.0, nullable=False)
    uptime = Column(Integer, default=0, nullable=False)
    recorded_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    server = relationship("Server", back_populates="metrics")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(100), nullable=False)  # auth.login, server.create, container.restart, etc.
    resource_type = Column(String(50), nullable=False)  # user, server, container, project, deployment
    resource_id = Column(String(100), nullable=True)
    details = Column(JSON, nullable=True, default=dict)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    user = relationship("User", back_populates="audit_logs")

