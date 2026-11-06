import { formatBytes, formatDuration } from './utils';
export { formatBytes, formatDuration };

export function getApiBase(): string {
  if (process.env.NEXT_PUBLIC_API_URL && process.env.NEXT_PUBLIC_API_URL.trim() !== '') {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  if (typeof window !== 'undefined') {
    // Same-origin: requests go to the web port (3005) and are proxied by Next.js
    // rewrites to the API container. Works over LAN, Tailscale, or a reverse proxy
    // without exposing port 8000 to the browser.
    return '';
  }
  return process.env.INTERNAL_API_URL || 'http://api:8000';
}

export function getWsBase(): string {
  if (process.env.NEXT_PUBLIC_WS_URL && process.env.NEXT_PUBLIC_WS_URL.trim() !== '') {
    return process.env.NEXT_PUBLIC_WS_URL;
  }
  if (typeof window !== 'undefined') {
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${wsProto}//${window.location.hostname}:8000`;
  }
  return 'ws://localhost:8000';
}

export function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('psm_access_token');
}

export function setAuthToken(token: string) {
  if (typeof window !== 'undefined') {
    localStorage.setItem('psm_access_token', token);
  }
}

export function clearAuth() {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('psm_access_token');
    localStorage.removeItem('psm_user');
  }
}

export async function fetchWithAuth(endpoint: string, options: RequestInit = {}) {
  const token = getAuthToken();
  const headers = new Headers(options.headers || {});

  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  const baseUrl = getApiBase();
  const url = endpoint.startsWith('http') ? endpoint : `${baseUrl}${endpoint}`;
  const response = await fetch(url, { ...options, headers });

  if (response.status === 401 && typeof window !== 'undefined' && !window.location.pathname.includes('/login')) {
    clearAuth();
    window.location.href = '/login';
  }

  return response;
}

export const api = {
  // Auth
  async login(email: string, password: string) {
    const baseUrl = getApiBase();
    const res = await fetch(`${baseUrl}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Authentication failed' }));
      throw new Error(err.detail || 'Login failed');
    }
    const data = await res.json();
    setAuthToken(data.access_token);
    if (typeof window !== 'undefined') {
      localStorage.setItem('psm_user', JSON.stringify(data.user));
    }
    return data;
  },

  async me() {
    const res = await fetchWithAuth('/api/v1/auth/me');
    if (!res.ok) throw new Error('Not authenticated');
    return res.json();
  },

  async changePassword(currentPassword: string, newPassword: string) {
    const res = await fetchWithAuth('/api/v1/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'Password change failed');
    return data;
  },

  async logout() {
    try {
      await fetchWithAuth('/api/v1/auth/logout', { method: 'POST' });
    } catch (_) {}
    clearAuth();
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
  },

  // Users
  async getUsers() {
    const res = await fetchWithAuth('/api/v1/users');
    return res.ok ? res.json() : [];
  },

  async createUser(data: { name: string; email: string; password: string; role: string }) {
    const res = await fetchWithAuth('/api/v1/users', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to create user');
    }
    return res.json();
  },

  async updateUser(id: string, data: any) {
    const res = await fetchWithAuth(`/api/v1/users/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to update user');
    return res.json();
  },

  async deleteUser(id: string) {
    const res = await fetchWithAuth(`/api/v1/users/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete user');
    return res.json();
  },

  // Servers
  async getServers() {
    const res = await fetchWithAuth('/api/v1/servers');
    if (!res.ok) throw new Error('Failed to fetch servers');
    return res.json();
  },

  async getServer(id: string) {
    const res = await fetchWithAuth(`/api/v1/servers/${id}`);
    if (!res.ok) throw new Error('Failed to fetch server');
    return res.json();
  },

  async createServer(data: { name: string; hostname?: string; description?: string }) {
    const res = await fetchWithAuth('/api/v1/servers', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to create server');
    return res.json();
  },

  async updateServer(id: string, data: { name?: string; hostname?: string; description?: string; status?: string }) {
    const res = await fetchWithAuth(`/api/v1/servers/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to update server');
    return res.json();
  },

  async deleteServer(id: string) {
    const res = await fetchWithAuth(`/api/v1/servers/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete server');
    return res.json();
  },

  async getServerMetrics(id: string, limit = 30) {
    const res = await fetchWithAuth(`/api/v1/servers/${id}/metrics?limit=${limit}`);
    if (!res.ok) return [];
    return res.json();
  },

  async reconnectServer(id: string) {
    const res = await fetchWithAuth(`/api/v1/servers/${id}/reconnect`, { method: 'POST' });
    return res.json();
  },

  async revokeAgent(id: string) {
    const res = await fetchWithAuth(`/api/v1/servers/${id}/agent/revoke`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to revoke agent credentials');
    return res.json();
  },

  async rotateAgentToken(id: string) {
    const res = await fetchWithAuth(`/api/v1/servers/${id}/agent/rotate`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to rotate agent credentials');
    return res.json();
  },

  async pruneServer(id: string, allImages = false) {
    const res = await fetchWithAuth(`/api/v1/servers/${id}/prune?all_images=${allImages}`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to dispatch Docker prune');
    return res.json();
  },

  // Containers
  async getContainers(serverId: string) {
    const res = await fetchWithAuth(`/api/v1/servers/${serverId}/containers`);
    if (!res.ok) return [];
    return res.json();
  },

  async containerAction(serverId: string, cid: string, action: 'start' | 'stop' | 'restart' | 'remove') {
    const method = action === 'remove' ? 'DELETE' : 'POST';
    const path = action === 'remove' ? `/api/v1/servers/${serverId}/containers/${cid}` : `/api/v1/servers/${serverId}/containers/${cid}/${action}`;
    const res = await fetchWithAuth(path, { method });
    if (!res.ok) throw new Error(`Failed to ${action} container`);
    return res.json();
  },

  async getContainerLogs(serverId: string, cid: string, tail = 100) {
    const res = await fetchWithAuth(`/api/v1/servers/${serverId}/containers/${cid}/logs?tail=${tail}`);
    if (!res.ok) return { logs: 'Unable to fetch logs.' };
    return res.json();
  },

  async getImages(serverId: string) {
    const res = await fetchWithAuth(`/api/v1/servers/${serverId}/images`);
    return res.ok ? res.json() : [];
  },

  async getVolumes(serverId: string) {
    const res = await fetchWithAuth(`/api/v1/servers/${serverId}/volumes`);
    return res.ok ? res.json() : [];
  },

  async getNetworks(serverId: string) {
    const res = await fetchWithAuth(`/api/v1/servers/${serverId}/networks`);
    return res.ok ? res.json() : [];
  },

  // Projects
  async getProjects() {
    const res = await fetchWithAuth('/api/v1/projects');
    if (!res.ok) throw new Error('Failed to fetch projects');
    return res.json();
  },

  async getProject(id: string) {
    const res = await fetchWithAuth(`/api/v1/projects/${id}`);
    if (!res.ok) throw new Error('Failed to fetch project');
    return res.json();
  },

  async createProject(data: any) {
    const res = await fetchWithAuth('/api/v1/projects', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to create project');
    return res.json();
  },

  async updateProject(id: string, data: any) {
    const res = await fetchWithAuth(`/api/v1/projects/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to update project');
    }
    return res.json();
  },

  async deleteProject(id: string) {
    const res = await fetchWithAuth(`/api/v1/projects/${id}`, { method: 'DELETE' });
    return res.json();
  },

  async getProjectEnvironment(id: string) {
    const res = await fetchWithAuth(`/api/v1/projects/${id}/environment`);
    return res.ok ? res.json() : [];
  },

  async updateProjectEnvironment(id: string, variables: Array<{ key: string; value: string }>) {
    const res = await fetchWithAuth(`/api/v1/projects/${id}/environment`, {
      method: 'PUT',
      body: JSON.stringify({ variables }),
    });
    return res.json();
  },

  async getProjectDatabase(id: string) {
    const res = await fetchWithAuth(`/api/v1/projects/${id}/database`);
    return res.ok ? res.json() : null;
  },

  async provisionProjectDatabase(id: string, dbName?: string, overrideEnv = true) {
    const res = await fetchWithAuth(`/api/v1/projects/${id}/database/provision`, {
      method: 'POST',
      body: JSON.stringify({ db_name: dbName || null, override_env: overrideEnv }),
    });
    if (!res.ok) throw new Error('Failed to provision PostgreSQL database');
    return res.json();
  },

  async getAllPostgresDatabases() {
    const res = await fetchWithAuth('/api/v1/projects/databases/list');
    return res.ok ? res.json() : { databases: [] };
  },

  // Deployments
  async getDeployments() {
    const res = await fetchWithAuth('/api/v1/deployments');
    return res.ok ? res.json() : [];
  },

  async getDeployment(id: string) {
    const res = await fetchWithAuth(`/api/v1/deployments/${id}`);
    return res.ok ? res.json() : null;
  },

  async triggerGitDeployment(
    projectId: string,
    branch = 'main',
    portMappings?: string,
    envVars?: Array<{ key: string; value: string }>
  ) {
    const res = await fetchWithAuth('/api/v1/deployments/git', {
      method: 'POST',
      body: JSON.stringify({
        project_id: projectId,
        branch,
        port_mappings: portMappings || undefined,
        environment_variables: envVars || undefined,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to trigger deployment');
    }
    return res.json();
  },

  async uploadZipDeployment(
    projectId: string,
    file: File,
    portMappings?: string,
    envVars?: Array<{ key: string; value: string }>
  ) {
    const formData = new FormData();
    formData.append('file', file);
    if (portMappings) {
      formData.append('port_mappings', portMappings);
    }
    if (envVars && envVars.length > 0) {
      formData.append('env_vars_json', JSON.stringify(envVars));
    }
    const res = await fetchWithAuth(`/api/v1/deployments/${projectId}/finalize-upload`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to upload and deploy ZIP');
    }
    return res.json();
  },

  async getDeploymentLogs(id: string) {
    const res = await fetchWithAuth(`/api/v1/deployments/${id}/logs`);
    return res.ok ? res.json() : [];
  },

  async cancelDeployment(id: string) {
    const res = await fetchWithAuth(`/api/v1/deployments/${id}/cancel`, { method: 'POST' });
    if (!res.ok) throw new Error('Cancel failed');
    return res.json();
  },

  async rollbackDeployment(id: string) {
    const res = await fetchWithAuth(`/api/v1/deployments/${id}/rollback`, { method: 'POST' });
    if (!res.ok) throw new Error('Rollback failed');
    return res.json();
  },

  // Monitoring
  async getMonitoringOverview() {
    const res = await fetchWithAuth('/api/v1/monitoring/overview');
    return res.ok ? res.json() : null;
  },

  async getMonitoringHistory(serverId?: string) {
    const qs = serverId ? `?server_id=${serverId}` : '';
    const res = await fetchWithAuth(`/api/v1/monitoring/history${qs}`);
    return res.ok ? res.json() : [];
  },

  async getPrometheusStatus() {
    const res = await fetchWithAuth('/api/v1/monitoring/prometheus/status');
    return res.ok ? res.json() : null;
  },

  async updatePrometheusConfig(prometheusUrl: string) {
    const res = await fetchWithAuth('/api/v1/monitoring/prometheus/config', {
      method: 'POST',
      body: JSON.stringify({ prometheus_url: prometheusUrl }),
    });
    if (!res.ok) throw new Error('Failed to save Prometheus URL');
    return res.json();
  },

  async getStorageTelemetry(serverId?: string) {
    const qs = serverId ? `?server_id=${serverId}` : '';
    const res = await fetchWithAuth(`/api/v1/monitoring/storage${qs}`);
    return res.ok ? res.json() : null;
  },

  async getNetworkTelemetry(serverId?: string) {
    const qs = serverId ? `?server_id=${serverId}` : '';
    const res = await fetchWithAuth(`/api/v1/monitoring/network${qs}`);
    return res.ok ? res.json() : null;
  },

  async probeNetworkTarget(target: string, port?: number) {
    const res = await fetchWithAuth('/api/v1/monitoring/network/probe', {
      method: 'POST',
      body: JSON.stringify({ target, port }),
    });
    if (!res.ok) throw new Error('Probe request failed');
    return res.json();
  },

  // Backups
  async getBackups() {
    const res = await fetchWithAuth('/api/v1/backups');
    return res.ok ? res.json() : [];
  },

  async createBackup(data: { name: string; backup_type: string; target_id?: string }) {
    const res = await fetchWithAuth('/api/v1/backups', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to create backup');
    return res.json();
  },

  async restoreBackup(id: string) {
    const res = await fetchWithAuth(`/api/v1/backups/${id}/restore`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to restore backup');
    return res.json();
  },

  async deleteBackup(id: string) {
    const res = await fetchWithAuth(`/api/v1/backups/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete backup');
    return res.json();
  },

  // Audit Logs
  async getAuditLogs() {
    const res = await fetchWithAuth('/api/v1/audit-logs');
    return res.ok ? res.json() : [];
  },

  async exportAuditLogs(format: 'csv' | 'json' = 'csv') {
    const res = await fetchWithAuth(`/api/v1/audit-logs/export?format=${format}`);
    if (!res.ok) throw new Error('Failed to export audit logs');
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `psm_audit_logs_${new Date().toISOString().slice(0, 10)}.${format}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  },

  // Templates & App Store
  async getTemplates() {
    const res = await fetchWithAuth('/api/v1/templates');
    return res.ok ? res.json() : [];
  },

  async deployTemplate(data: {
    server_id: string;
    template_id: string;
    project_name: string;
    port?: number;
    environment_variables?: Record<string, string>;
  }) {
    const res = await fetchWithAuth('/api/v1/templates/deploy', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Template deployment failed' }));
      throw new Error(err.detail || 'Template deployment failed');
    }
    return res.json();
  },

  // Container Inspection
  async inspectContainer(serverId: string, cid: string) {
    const res = await fetchWithAuth(`/api/v1/servers/${serverId}/containers/${cid}/inspect`);
    if (!res.ok) throw new Error('Failed to inspect container');
    return res.json();
  },

  // Notifications & Alerts
  async getNotificationSettings() {
    const res = await fetchWithAuth('/api/v1/notifications/settings');
    return res.ok ? res.json() : null;
  },

  async updateNotificationSettings(data: any) {
    const res = await fetchWithAuth('/api/v1/notifications/settings', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to update notification settings');
    return res.json();
  },

  async testNotification() {
    const res = await fetchWithAuth('/api/v1/notifications/test', {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Notification test failed');
    return res.json();
  },

  async getRecentAlerts() {
    const res = await fetchWithAuth('/api/v1/notifications/alerts');
    return res.ok ? res.json() : [];
  },

  async clearAlerts() {
    const res = await fetchWithAuth('/api/v1/notifications/alerts/clear', {
      method: 'POST',
    });
    return res.ok ? res.json() : null;
  },

  // Personal API Platform (Main API / API Utama) & IoT Fleet Integration
  async getPapStatus() {
    const res = await fetchWithAuth('/api/v1/pap/status');
    return res.ok ? res.json() : null;
  },

  async syncWithPap() {
    const res = await fetchWithAuth('/api/v1/pap/sync', { method: 'POST' });
    if (!res.ok) throw new Error('Failed to sync with Personal API Platform');
    return res.json();
  },

  async getPapIotFleet() {
    const res = await fetchWithAuth('/api/v1/pap/iot/fleet');
    return res.ok ? res.json() : null;
  },

  // Backup file download
  async downloadBackup(backupId: string, filename: string) {
    const res = await fetchWithAuth(`/api/v1/backups/${backupId}/download`);
    if (!res.ok) throw new Error('Failed to download backup snapshot');
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename || `psm_backup_${backupId}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  },
};
