export type UserRole = 'owner' | 'admin' | 'operator' | 'viewer';
export type ThemePreference = 'system' | 'dark' | 'light';

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  theme: ThemePreference;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export type ServerStatus = 'online' | 'offline' | 'degraded' | 'maintenance' | 'pending';

export interface Server {
  id: string;
  owner_id: string;
  name: string;
  hostname: string;
  description?: string | null;
  os_name: string;
  os_version: string;
  architecture: string;
  status: ServerStatus;
  last_seen: string | null;
  created_at: string;
  agent?: AgentInfo | null;
  latest_metrics?: ServerMetrics | null;
}

export interface AgentInfo {
  id: string;
  server_id: string;
  agent_version: string;
  connected_at: string | null;
  last_seen: string | null;
  revoked_at: string | null;
}

export interface ServerMetrics {
  server_id: string;
  cpu_usage: number; // percentage
  memory_usage: number; // percentage
  memory_used_bytes: number;
  memory_total_bytes: number;
  disk_usage: number; // percentage
  disk_used_bytes: number;
  disk_total_bytes: number;
  network_rx_bytes_per_sec: number;
  network_tx_bytes_per_sec: number;
  uptime_seconds: number;
  recorded_at: string;
}

export interface Container {
  id: string;
  server_id: string;
  docker_id: string;
  name: string;
  image: string;
  status: 'running' | 'stopped' | 'restarting' | 'paused' | 'exited';
  state: string;
  created: string;
  ports?: Array<{ internal: number; external: number; protocol: string }>;
  cpu_percent?: number;
  memory_percent?: number;
}

export interface Project {
  id: string;
  server_id: string;
  server_name?: string;
  owner_id: string;
  name: string;
  description?: string | null;
  framework: string;
  source_type: 'git' | 'upload';
  status: 'active' | 'stopped' | 'failed';
  created_at: string;
  repository_url?: string | null;
  branch?: string | null;
  dockerfile_path?: string;
  compose_path?: string;
}

export type DeploymentStatus =
  | 'queued'
  | 'preparing'
  | 'building'
  | 'deploying'
  | 'success'
  | 'failed'
  | 'cancelled'
  | 'rolling_back';

export interface Deployment {
  id: string;
  project_id: string;
  project_name?: string;
  version: number;
  commit_hash?: string | null;
  image_tag?: string | null;
  status: DeploymentStatus;
  triggered_by?: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds?: number | null;
  created_at: string;
}

export interface DeploymentLog {
  id: string;
  deployment_id: string;
  sequence: number;
  level: 'info' | 'warning' | 'error';
  message: string;
  created_at: string;
}

export interface AuditLog {
  id: string;
  user_id: string;
  user_name?: string;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  details?: Record<string, any>;
  ip_address?: string | null;
  created_at: string;
}

