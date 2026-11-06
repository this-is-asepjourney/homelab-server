export type JobType =
  | 'container.start'
  | 'container.stop'
  | 'container.restart'
  | 'container.remove'
  | 'deployment.git'
  | 'deployment.zip'
  | 'deployment.compose'
  | 'deployment.rollback'
  | 'server.ping'
  | 'system.inventory';

export interface HeartbeatPayload {
  agent_id: string;
  server_id: string;
  agent_version: string;
  status: 'online' | 'degraded';
  timestamp: string;
}

export interface MetricsPayload {
  server_id: string;
  cpu_usage: number;
  memory_usage: number;
  memory_used_bytes: number;
  memory_total_bytes: number;
  disk_usage: number;
  disk_used_bytes: number;
  disk_total_bytes: number;
  network_rx_bytes_per_sec: number;
  network_tx_bytes_per_sec: number;
  uptime_seconds: number;
  timestamp: string;
}

export interface JobNotification {
  event: 'job.dispatch';
  job_id: string;
  job_type: JobType;
  server_id: string;
  payload: Record<string, any>;
  timeout_seconds?: number;
}

export interface JobResultPayload {
  job_id: string;
  server_id: string;
  status: 'success' | 'failed';
  error_message?: string | null;
  output?: Record<string, any>;
  duration_seconds: number;
}

