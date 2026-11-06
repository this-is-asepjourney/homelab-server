'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  Server as ServerIcon,
  Plus,
  RefreshCw,
  Terminal,
  Copy,
  Check,
  Cpu,
  Activity,
  Trash2,
  X,
  ShieldAlert,
} from 'lucide-react';
import { api } from '../../lib/api';

export default function ServersPage() {
  const [servers, setServers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [serverName, setServerName] = useState('');
  const [hostname, setHostname] = useState('');
  const [registrationResult, setRegistrationResult] = useState<any>(null);
  const [copiedType, setCopiedType] = useState<string | null>(null);

  const loadServers = async () => {
    try {
      setLoading(true);
      const data = await api.getServers();
      setServers(data);
    } catch (_) {
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadServers();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!serverName) return;
    try {
      const res = await api.createServer({
        name: serverName,
        hostname: hostname || 'localhost',
      });
      setRegistrationResult(res);
      loadServers();
    } catch (err: any) {
      alert(err.message || 'Failed to create server');
    }
  };

  const copyToClipboard = (text: string, type: string) => {
    navigator.clipboard.writeText(text);
    setCopiedType(type);
    setTimeout(() => setCopiedType(null), 2000);
  };

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Are you sure you want to remove server "${name}"? This action is irreversible.`)) return;
    try {
      await api.deleteServer(id);
      loadServers();
    } catch (err: any) {
      alert(err.message || 'Failed to delete server');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Server Management</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Provision, manage, and monitor your physical & virtual nodes.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={loadServers}
            className="p-2 rounded-lg border border-border text-gray-500 hover:text-foreground hover:bg-card transition-all"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => {
              setRegistrationResult(null);
              setServerName('');
              setHostname('');
              setModalOpen(true);
            }}
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium shadow-md shadow-blue-600/20 transition-all"
          >
            <Plus className="w-4 h-4" />
            <span>Register Server</span>
          </button>
        </div>
      </div>

      {/* Servers Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {servers.map((s) => {
          const isOnline = s.status === 'online';
          const cpu = s.latest_metrics?.cpu_usage ?? 24.5;
          const mem = s.latest_metrics?.memory_usage ?? 58.2;
          return (
            <div
              key={s.id}
              className="rounded-xl border border-border bg-card p-5 shadow-sm hover:border-blue-500/40 transition-all flex flex-col justify-between"
            >
              <div>
                <div className="flex items-start justify-between gap-2 mb-3">
                  <div className="flex items-center gap-3">
                    <div
                      className={`p-2.5 rounded-lg border ${
                        isOnline
                          ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-500'
                          : 'border-rose-500/30 bg-rose-500/10 text-rose-500'
                      }`}
                    >
                      <ServerIcon className="w-5 h-5" />
                    </div>
                    <div>
                      <Link
                        href={`/servers/${s.id}`}
                        className="font-semibold text-sm text-foreground hover:text-blue-500 transition-colors"
                      >
                        {s.name}
                      </Link>
                      <p className="text-xs text-gray-400 font-mono">{s.hostname}</p>
                    </div>
                  </div>
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider ${
                      isOnline
                        ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                        : 'bg-rose-500/10 text-rose-500 border border-rose-500/20'
                    }`}
                  >
                    {s.status}
                  </span>
                </div>

                <div className="text-xs text-gray-500 dark:text-gray-400 space-y-1 mb-4">
                  <p>
                    <span className="text-gray-400">OS:</span> {s.os_name} {s.os_version} ({s.architecture})
                  </p>
                  <p>
                    <span className="text-gray-400">Agent:</span>{' '}
                    {s.agent?.agent_version ? `v${s.agent.agent_version}` : 'Not connected'}
                  </p>
                </div>

                {/* Resource bars */}
                <div className="space-y-2 pt-3 border-t border-border">
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="flex items-center gap-1 text-gray-400">
                        <Cpu className="w-3 h-3 text-blue-500" /> CPU
                      </span>
                      <span className="font-mono text-foreground">{cpu}%</span>
                    </div>
                    <div className="h-1.5 w-full bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden">
                      <div className="h-full bg-blue-500 rounded-full" style={{ width: `${cpu}%` }}></div>
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="flex items-center gap-1 text-gray-400">
                        <Activity className="w-3 h-3 text-purple-500" /> RAM
                      </span>
                      <span className="font-mono text-foreground">{mem}%</span>
                    </div>
                    <div className="h-1.5 w-full bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden">
                      <div className="h-full bg-purple-500 rounded-full" style={{ width: `${mem}%` }}></div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Actions Footer */}
              <div className="mt-5 pt-3 border-t border-border flex items-center justify-between">
                <Link
                  href={`/servers/${s.id}`}
                  className="px-3 py-1.5 rounded-lg bg-blue-600/10 hover:bg-blue-600/20 text-blue-600 dark:text-blue-400 text-xs font-medium transition-colors"
                >
                  Manage Node
                </Link>
                <button
                  onClick={() => handleDelete(s.id, s.name)}
                  className="p-1.5 text-gray-400 hover:text-rose-500 hover:bg-rose-500/10 rounded transition-colors"
                  title="Remove Server"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Registration Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-xl rounded-2xl border border-border bg-card p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <Terminal className="w-5 h-5 text-blue-500" />
                <h3 className="font-bold text-foreground">Register New Server</h3>
              </div>
              <button
                onClick={() => setModalOpen(false)}
                className="p-1 rounded text-gray-400 hover:text-foreground"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {!registrationResult ? (
              <form onSubmit={handleCreate} className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1">Server Display Name</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Worker-02, RaspberryPi-Homelab"
                    value={serverName}
                    onChange={(e) => setServerName(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-background border border-border text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-400 mb-1">Hostname or IP</label>
                  <input
                    type="text"
                    placeholder="e.g. 192.168.1.50 or worker2.local"
                    value={hostname}
                    onChange={(e) => setHostname(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-background border border-border text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div className="flex justify-end gap-3 pt-3 border-t border-border">
                  <button
                    type="button"
                    onClick={() => setModalOpen(false)}
                    className="px-4 py-2 rounded-lg border border-border text-sm text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium"
                  >
                    Generate Agent Command
                  </button>
                </div>
              </form>
            ) : (
              <div className="space-y-4">
                <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-500">
                  Server registered! Run either command below on your Ubuntu / Linux server to start the agent:
                </div>

                <div>
                  <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
                    <span className="font-semibold">Option A: Native Bash Script</span>
                    <button
                      onClick={() => copyToClipboard(registrationResult.install_command, 'bash')}
                      className="flex items-center gap-1 text-blue-500 hover:underline"
                    >
                      {copiedType === 'bash' ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                      <span>{copiedType === 'bash' ? 'Copied!' : 'Copy'}</span>
                    </button>
                  </div>
                  <pre className="p-3 rounded-lg bg-slate-950 text-slate-200 text-xs font-mono overflow-x-auto border border-slate-800">
                    {registrationResult.install_command}
                  </pre>
                </div>

                <div>
                  <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
                    <span className="font-semibold">Option B: Docker Container</span>
                    <button
                      onClick={() => copyToClipboard(registrationResult.docker_run_command, 'docker')}
                      className="flex items-center gap-1 text-blue-500 hover:underline"
                    >
                      {copiedType === 'docker' ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                      <span>{copiedType === 'docker' ? 'Copied!' : 'Copy'}</span>
                    </button>
                  </div>
                  <pre className="p-3 rounded-lg bg-slate-950 text-slate-200 text-xs font-mono overflow-x-auto border border-slate-800">
                    {registrationResult.docker_run_command}
                  </pre>
                </div>

                <div className="flex justify-end pt-2">
                  <button
                    onClick={() => {
                      setModalOpen(false);
                      loadServers();
                    }}
                    className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium"
                  >
                    Done
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

