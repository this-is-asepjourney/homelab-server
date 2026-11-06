'use client';

import React, { useState, useEffect } from 'react';
import {
  Sun,
  Moon,
  Laptop,
  Plus,
  Trash2,
  Users,
  Bell,
  BellRing,
  Send,
  CheckCircle2,
} from 'lucide-react';
import { useTheme } from '../../components/theme-provider';
import { api } from '../../lib/api';

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const [currentUser, setCurrentUser] = useState<any>(null);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [passwordMsg, setPasswordMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // User Management state
  const [users, setUsers] = useState<any[]>([]);
  const [newEmail, setNewEmail] = useState('');
  const [newFullName, setNewFullName] = useState('');
  const [newUserPassword, setNewUserPassword] = useState('');
  const [newRole, setNewRole] = useState('operator');

  // Notification & Alerting state
  const [notifConfig, setNotifConfig] = useState<any>({
    enabled: false,
    discord_webhook_url: '',
    telegram_bot_token: '',
    telegram_chat_id: '',
    cpu_threshold: 90,
    memory_threshold: 90,
    disk_threshold: 90,
    notify_server_offline: true,
    notify_deployments: true,
  });
  const [notifSaved, setNotifSaved] = useState(false);
  const [testingNotif, setTestingNotif] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  const loadUsers = async () => {
    try {
      const list = await api.getUsers();
      setUsers(list);
    } catch (_) {}
  };

  const loadNotifications = async () => {
    try {
      const data = await api.getNotificationSettings();
      if (data) setNotifConfig(data);
    } catch (_) {}
  };

  useEffect(() => {
    api.me().then((u) => setCurrentUser(u)).catch(() => {});
    loadUsers();
    loadNotifications();
  }, []);

  const handleSaveNotifications = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.updateNotificationSettings(notifConfig);
      setNotifSaved(true);
      setTimeout(() => setNotifSaved(false), 3000);
    } catch (err: any) {
      alert(err.message || 'Failed to save notification settings');
    }
  };

  const handleTestNotification = async () => {
    try {
      setTestingNotif(true);
      setTestResult(null);
      const res = await api.testNotification();
      setTestResult(
        `Test dispatched. Discord: ${res.results?.discord ? 'Delivered' : 'Not configured or failed'}, Telegram: ${
          res.results?.telegram ? 'Delivered' : 'Not configured or failed'
        }`
      );
    } catch (err: any) {
      setTestResult(err.message || 'Notification test failed');
    } finally {
      setTestingNotif(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordMsg(null);
    try {
      const data = await api.changePassword(currentPassword, newPassword);
      setPasswordMsg({ type: 'success', text: data.message || 'Password updated successfully' });
      setCurrentPassword('');
      setNewPassword('');
    } catch (err: any) {
      setPasswordMsg({ type: 'error', text: err.message || 'Password change failed' });
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createUser({
        name: newFullName,
        email: newEmail,
        password: newUserPassword,
        role: newRole,
      });
      setNewEmail('');
      setNewFullName('');
      setNewUserPassword('');
      setNewRole('operator');
      loadUsers();
    } catch (err: any) {
      alert(err.message || 'Failed to create user');
    }
  };

  const handleRoleChange = async (userId: string, role: string) => {
    try {
      await api.updateUser(userId, { role });
      loadUsers();
    } catch (err: any) {
      alert(err.message || 'Failed to update user role');
    }
  };

  const handleDeleteUser = async (userId: string) => {
    if (!confirm('Remove this user account?')) return;
    try {
      await api.deleteUser(userId);
      loadUsers();
    } catch (err: any) {
      alert(err.message || 'Failed to delete user');
    }
  };

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Settings & Security</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Manage system appearance, operator access, RBAC roles, security keys, and homelab integration.
        </p>
      </div>

      {/* Appearance Section */}
      <div className="p-6 rounded-xl border border-border bg-card shadow-sm space-y-4">
        <div>
          <h3 className="font-bold text-sm text-foreground">Appearance & Theme</h3>
          <p className="text-xs text-gray-500">Choose between dark mode, light mode, or synchronize with system.</p>
        </div>

        <div className="grid grid-cols-3 gap-3 max-w-md">
          <button
            onClick={() => setTheme('dark')}
            className={`flex items-center justify-center gap-2 p-3 rounded-lg border text-xs font-medium transition-all ${
              theme === 'dark'
                ? 'border-blue-500 bg-blue-500/10 text-blue-500 font-semibold'
                : 'border-border text-gray-400 hover:text-foreground'
            }`}
          >
            <Moon className="w-4 h-4 text-purple-400" />
            <span>Dark</span>
          </button>

          <button
            onClick={() => setTheme('light')}
            className={`flex items-center justify-center gap-2 p-3 rounded-lg border text-xs font-medium transition-all ${
              theme === 'light'
                ? 'border-blue-500 bg-blue-500/10 text-blue-500 font-semibold'
                : 'border-border text-gray-400 hover:text-foreground'
            }`}
          >
            <Sun className="w-4 h-4 text-amber-500" />
            <span>Light</span>
          </button>

          <button
            onClick={() => setTheme('system')}
            className={`flex items-center justify-center gap-2 p-3 rounded-lg border text-xs font-medium transition-all ${
              theme === 'system'
                ? 'border-blue-500 bg-blue-500/10 text-blue-500 font-semibold'
                : 'border-border text-gray-400 hover:text-foreground'
            }`}
          >
            <Laptop className="w-4 h-4 text-blue-400" />
            <span>System</span>
          </button>
        </div>
      </div>

      {/* Profile & Security */}
      <div className="p-6 rounded-xl border border-border bg-card shadow-sm space-y-4">
        <div>
          <h3 className="font-bold text-sm text-foreground">Operator Account</h3>
          <p className="text-xs text-gray-500">
            Logged in as {currentUser?.email || 'admin@psm.local'} ({currentUser?.role || 'owner'})
          </p>
        </div>

        <form onSubmit={handleChangePassword} className="space-y-3 max-w-md text-xs">
          {passwordMsg && (
            <div
              className={`p-2.5 rounded-lg border text-xs ${
                passwordMsg.type === 'success'
                  ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500'
                  : 'bg-rose-500/10 border-rose-500/20 text-rose-500'
              }`}
            >
              {passwordMsg.text}
            </div>
          )}

          <div>
            <label className="block text-gray-400 font-medium mb-1">Current Password</label>
            <input
              type="password"
              required
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-background border border-border text-foreground text-xs focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-gray-400 font-medium mb-1">New Password (Argon2id)</label>
            <input
              type="password"
              required
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-background border border-border text-foreground text-xs focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
          </div>

          <button
            type="submit"
            className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium"
          >
            Update Password
          </button>
        </form>
      </div>

      {/* Role-Based Access Control (RBAC) User Management */}
      <div className="p-6 rounded-xl border border-border bg-card shadow-sm space-y-4">
        <div className="flex items-center gap-2">
          <Users className="w-4 h-4 text-blue-500" />
          <div>
            <h3 className="font-bold text-sm text-foreground">Team & RBAC Access Control</h3>
            <p className="text-xs text-gray-500">Manage operator accounts and roles (Owner, Admin, Operator, Viewer).</p>
          </div>
        </div>

        <div className="space-y-2">
          {users.map((u) => (
            <div
              key={u.id}
              className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-3 rounded-lg border border-border bg-background text-xs"
            >
              <div>
                <span className="font-semibold text-foreground">{u.name || u.full_name}</span>
                <span className="text-gray-400 font-mono ml-2">({u.email})</span>
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={u.role}
                  onChange={(e) => handleRoleChange(u.id, e.target.value)}
                  className="px-2 py-1 rounded bg-card border border-border text-foreground text-xs"
                >
                  <option value="owner">Owner</option>
                  <option value="admin">Admin</option>
                  <option value="operator">Operator</option>
                  <option value="viewer">Viewer</option>
                </select>
                {currentUser?.id !== u.id && (
                  <button
                    onClick={() => handleDeleteUser(u.id)}
                    className="p-1.5 rounded hover:bg-rose-500/10 text-rose-500"
                    title="Delete User"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        <form onSubmit={handleCreateUser} className="pt-4 border-t border-border grid grid-cols-1 sm:grid-cols-5 gap-2.5 text-xs">
          <input
            type="text"
            required
            placeholder="Full Name"
            value={newFullName}
            onChange={(e) => setNewFullName(e.target.value)}
            className="px-3 py-2 rounded-lg bg-background border border-border text-foreground"
          />
          <input
            type="text"
            required
            placeholder="user@psm.local"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            className="px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono"
          />
          <input
            type="password"
            required
            placeholder="Password"
            value={newUserPassword}
            onChange={(e) => setNewUserPassword(e.target.value)}
            className="px-3 py-2 rounded-lg bg-background border border-border text-foreground"
          />
          <select
            value={newRole}
            onChange={(e) => setNewRole(e.target.value)}
            className="px-3 py-2 rounded-lg bg-background border border-border text-foreground"
          >
            <option value="admin">Admin</option>
            <option value="operator">Operator</option>
            <option value="viewer">Viewer</option>
          </select>
          <button
            type="submit"
            className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium flex items-center justify-center gap-1"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Add User</span>
          </button>
        </form>
      </div>

      {/* External Notifications & Alerting (Discord & Telegram) */}
      <div className="p-6 rounded-xl border border-border bg-card shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BellRing className="w-4 h-4 text-amber-500" />
            <div>
              <h3 className="font-bold text-sm text-foreground">External Alerts & Webhooks (Discord & Telegram)</h3>
              <p className="text-xs text-gray-500">
                Receive proactive alerts on Discord channel or Telegram chat when servers exceed resource limits.
              </p>
            </div>
          </div>
          {notifSaved && (
            <span className="flex items-center gap-1 text-emerald-500 text-xs font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" /> Saved
            </span>
          )}
        </div>

        <form onSubmit={handleSaveNotifications} className="space-y-4 text-xs">
          <div className="flex items-center gap-2 pt-1">
            <input
              type="checkbox"
              id="notif_enabled"
              checked={notifConfig.enabled}
              onChange={(e) => setNotifConfig({ ...notifConfig, enabled: e.target.checked })}
              className="rounded border-border text-blue-600 focus:ring-blue-500"
            />
            <label htmlFor="notif_enabled" className="text-foreground font-semibold cursor-pointer">
              Enable Proactive Webhook Alerts
            </label>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-400 font-medium mb-1">Discord Webhook URL</label>
              <input
                type="text"
                placeholder="https://discord.com/api/webhooks/..."
                value={notifConfig.discord_webhook_url}
                onChange={(e) => setNotifConfig({ ...notifConfig, discord_webhook_url: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono text-[11px]"
              />
            </div>

            <div>
              <label className="block text-gray-400 font-medium mb-1">Telegram Bot Token</label>
              <input
                type="text"
                placeholder="123456789:ABCdefGhIJKlmNoPQRstuVWXyz..."
                value={notifConfig.telegram_bot_token}
                onChange={(e) => setNotifConfig({ ...notifConfig, telegram_bot_token: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono text-[11px]"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-400 font-medium mb-1">Telegram Chat ID / Group ID</label>
              <input
                type="text"
                placeholder="e.g. -100123456789 or 98765432"
                value={notifConfig.telegram_chat_id}
                onChange={(e) => setNotifConfig({ ...notifConfig, telegram_chat_id: e.target.value })}
                className="w-full px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono text-[11px]"
              />
            </div>

            <div className="grid grid-cols-3 gap-2">
              <div>
                <label className="block text-gray-400 font-medium mb-1">CPU Max %</label>
                <input
                  type="number"
                  min="50"
                  max="99"
                  value={notifConfig.cpu_threshold}
                  onChange={(e) => setNotifConfig({ ...notifConfig, cpu_threshold: parseFloat(e.target.value) || 90 })}
                  className="w-full px-2.5 py-2 rounded-lg bg-background border border-border text-foreground font-mono text-[11px]"
                />
              </div>
              <div>
                <label className="block text-gray-400 font-medium mb-1">RAM Max %</label>
                <input
                  type="number"
                  min="50"
                  max="99"
                  value={notifConfig.memory_threshold}
                  onChange={(e) => setNotifConfig({ ...notifConfig, memory_threshold: parseFloat(e.target.value) || 90 })}
                  className="w-full px-2.5 py-2 rounded-lg bg-background border border-border text-foreground font-mono text-[11px]"
                />
              </div>
              <div>
                <label className="block text-gray-400 font-medium mb-1">Disk Max %</label>
                <input
                  type="number"
                  min="50"
                  max="99"
                  value={notifConfig.disk_threshold}
                  onChange={(e) => setNotifConfig({ ...notifConfig, disk_threshold: parseFloat(e.target.value) || 90 })}
                  className="w-full px-2.5 py-2 rounded-lg bg-background border border-border text-foreground font-mono text-[11px]"
                />
              </div>
            </div>
          </div>

          {testResult && (
            <div className="p-2.5 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-mono">
              {testResult}
            </div>
          )}

          <div className="flex items-center gap-3 pt-2">
            <button
              type="submit"
              className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium"
            >
              Save Alert Settings
            </button>
            <button
              type="button"
              onClick={handleTestNotification}
              disabled={testingNotif}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-border hover:bg-background text-foreground font-medium disabled:opacity-50"
            >
              <Send className="w-3.5 h-3.5 text-blue-400" />
              <span>{testingNotif ? 'Sending Test...' : 'Send Test Alert Notification'}</span>
            </button>
          </div>
        </form>
      </div>

      {/* Homelab Port Allocations Summary */}
      <div className="p-6 rounded-xl border border-border bg-card shadow-sm space-y-4">
        <div>
          <h3 className="font-bold text-sm text-foreground">Homelab Service Port Preservations</h3>
          <p className="text-xs text-gray-500">
            Dedicated homelab ports mapped in blueprint Section 12 to prevent conflicts:
          </p>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
          <div className="p-3 rounded-lg border border-border bg-background">
            <span className="text-gray-400 block text-[10px]">PSM Web</span>
            <span className="text-blue-500 font-bold">Port 3005</span>
          </div>
          <div className="p-3 rounded-lg border border-border bg-background">
            <span className="text-gray-400 block text-[10px]">PSM API</span>
            <span className="text-blue-500 font-bold">Port 8000</span>
          </div>
          <div className="p-3 rounded-lg border border-border bg-background">
            <span className="text-gray-400 block text-[10px]">Prometheus Snap</span>
            <span className="text-orange-500 font-bold">Port 9001</span>
          </div>
          <div className="p-3 rounded-lg border border-border bg-background">
            <span className="text-gray-400 block text-[10px]">Cockpit</span>
            <span className="text-foreground font-bold">Port 9090</span>
          </div>
          <div className="p-3 rounded-lg border border-border bg-background">
            <span className="text-gray-400 block text-[10px]">Nextcloud Snap</span>
            <span className="text-foreground font-bold">Port 80</span>
          </div>
          <div className="p-3 rounded-lg border border-border bg-background">
            <span className="text-gray-400 block text-[10px]">Grafana</span>
            <span className="text-foreground font-bold">Port 3001</span>
          </div>
          <div className="p-3 rounded-lg border border-border bg-background">
            <span className="text-gray-400 block text-[10px]">Uptime Kuma</span>
            <span className="text-foreground font-bold">Port 3002</span>
          </div>
          <div className="p-3 rounded-lg border border-border bg-background">
            <span className="text-gray-400 block text-[10px]">Mosquitto MQTT</span>
            <span className="text-foreground font-bold">Port 1883</span>
          </div>
        </div>
      </div>
    </div>
  );
}
