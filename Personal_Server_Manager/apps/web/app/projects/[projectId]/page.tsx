'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  FolderGit2,
  Rocket,
  Key,
  Settings,
  RefreshCw,
  ArrowLeft,
  Plus,
  Upload,
  Copy,
  Check,
  GitBranch,
  Database,
  CheckCircle2,
  Table,
  HardDrive,
  Globe,
  ExternalLink,
} from 'lucide-react';
import { api, formatBytes } from '../../../lib/api';
import { DeployProjectModal } from '../../../components/deploy-project-modal';

export default function ProjectDetailPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = params.projectId as string;

  const [project, setProject] = useState<any>(null);
  const [servers, setServers] = useState<any[]>([]);
  const [deployments, setDeployments] = useState<any[]>([]);
  const [envVars, setEnvVars] = useState<any[]>([]);
  const [dbInfo, setDbInfo] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'deployments' | 'database' | 'environment' | 'settings'>('deployments');
  const [loading, setLoading] = useState(true);
  const [deploying, setDeploying] = useState(false);
  const [deployModalOpen, setDeployModalOpen] = useState(false);
  const [portMappingsInput, setPortMappingsInput] = useState('');
  const [savingPorts, setSavingPorts] = useState(false);
  const [provisioningDb, setProvisioningDb] = useState(false);
  const [customDbName, setCustomDbName] = useState('');
  const [copiedWebhook, setCopiedWebhook] = useState(false);
  const [copiedDbUrl, setCopiedDbUrl] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // New env var form
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');

  const loadData = async () => {
    try {
      setLoading(true);
      const [p, d, env, dbData, s] = await Promise.all([
        api.getProject(projectId),
        api.getDeployments().then((list) => list.filter((item: any) => item.project_id === projectId)),
        api.getProjectEnvironment(projectId),
        api.getProjectDatabase(projectId),
        api.getServers().catch(() => []),
      ]);
      setProject(p);
      setDeployments(d);
      setEnvVars(env);
      setDbInfo(dbData);
      setServers(s);
      setPortMappingsInput(p?.port_mappings || '3000:3000');
      if (dbData?.db_name && !customDbName) {
        setCustomDbName(dbData.db_name);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [projectId]);

  const handleTriggerDeploy = async () => {
    try {
      setDeploying(true);
      const dep = await api.triggerGitDeployment(projectId, project?.branch || 'main');
      router.push(`/deployments/${dep.id}`);
    } catch (err: any) {
      alert(err.message || 'Deployment trigger failed');
      setDeploying(false);
    }
  };

  const handleZipUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      setDeploying(true);
      const dep = await api.uploadZipDeployment(projectId, file);
      router.push(`/deployments/${dep.id}`);
    } catch (err: any) {
      alert(err.message || 'ZIP upload deployment failed');
      setDeploying(false);
    }
  };

  const handleRollback = async (deploymentId: string) => {
    if (!confirm('Are you sure you want to rollback to this release?')) return;
    try {
      const dep = await api.rollbackDeployment(deploymentId);
      router.push(`/deployments/${dep.id}`);
    } catch (err: any) {
      alert(err.message || 'Rollback failed');
    }
  };

  const handleProvisionDatabase = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    try {
      setProvisioningDb(true);
      await api.provisionProjectDatabase(projectId, customDbName.trim() || undefined, true);
      await loadData();
    } catch (err: any) {
      alert(err.message || 'Failed to provision PostgreSQL database');
    } finally {
      setProvisioningDb(false);
    }
  };

  const handleSavePortMappings = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!portMappingsInput.trim()) return;
    try {
      setSavingPorts(true);
      await api.updateProject(projectId, { port_mappings: portMappingsInput.trim() });
      await loadData();
      alert('Port mappings Docker berhasil diperbarui!');
    } catch (err: any) {
      alert(err.message || 'Gagal memperbarui port mappings');
    } finally {
      setSavingPorts(false);
    }
  };

  const handleAddEnvVar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKey) return;
    try {
      const updated = [...envVars.map((v) => ({ key: v.key, value: v.masked_value })), { key: newKey, value: newValue }];
      await api.updateProjectEnvironment(projectId, updated);
      setNewKey('');
      setNewValue('');
      loadData();
    } catch (err: any) {
      alert(err.message || 'Failed to update environment');
    }
  };

  if (!project && !loading) {
    return <div className="p-8 text-center text-gray-500">Project not found.</div>;
  }

  const hostPortOnly = (project?.port_mappings || '3000:3000').split(':')[0]?.trim();
  const targetServer = servers.find((s) => s.id === project?.server_id);
  const serverHost = targetServer?.hostname || 'localhost';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-5">
        <div className="flex items-center gap-4">
          <button
            onClick={() => router.push('/projects')}
            className="p-2 rounded-lg border border-border hover:bg-card text-gray-400 hover:text-foreground transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-xl font-bold text-foreground">{project?.name || 'Project'}</h1>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                {project?.status}
              </span>
              <span className="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-blue-500/10 text-blue-500 border border-blue-500/20">
                <Globe className="w-3 h-3" />
                <span>Port: {project?.port_mappings || '3000:3000'}</span>
              </span>
              {dbInfo && (
                <button
                  onClick={() => setActiveTab('database')}
                  className="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors"
                >
                  <Database className="w-3 h-3" />
                  <span>PG: {dbInfo.db_name}</span>
                </button>
              )}
            </div>
            <p className="text-xs text-gray-400 font-mono mt-0.5">
              {project?.framework} • Hosted on {project?.server_name}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5 flex-wrap">
          {/* External Access Link if container port is available */}
          {hostPortOnly && (
            <a
              href={`http://${serverHost}:${hostPortOnly}`}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-500 text-xs font-semibold transition-colors shadow-sm"
              title="Buka aplikasi di tab baru"
            >
              <Globe className="w-3.5 h-3.5" />
              <span>Akses App</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          )}

          <button
            onClick={() => setDeployModalOpen(true)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold shadow-md shadow-blue-600/20 transition-all"
          >
            <Rocket className="w-4 h-4" />
            <span>Deploy Release</span>
          </button>

          <button
            onClick={handleTriggerDeploy}
            disabled={deploying}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-border hover:bg-card text-foreground text-xs font-medium transition-all disabled:opacity-50"
            title="Deploy commit terbaru"
          >
            <span>{deploying ? 'Deploying...' : 'Deploy Latest'}</span>
          </button>
        </div>
      </div>

      {/* Tabs Header */}
      <div className="flex items-center gap-2 border-b border-border text-sm overflow-x-auto pb-px">
        {[
          { key: 'deployments', label: `Deployments (${deployments.length})`, icon: Rocket },
          { key: 'database', label: `PostgreSQL DB (${dbInfo?.db_name || 'Auto'})`, icon: Database },
          { key: 'environment', label: `Environment (${envVars.length})`, icon: Key },
          { key: 'overview', label: 'Source & Build', icon: FolderGit2 },
          { key: 'settings', label: 'Settings', icon: Settings },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as any)}
              className={`flex items-center gap-2 px-4 py-2.5 font-medium border-b-2 transition-colors whitespace-nowrap text-xs ${
                isActive
                  ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                  : 'border-transparent text-gray-500 hover:text-foreground'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Tab: Deployments */}
      {activeTab === 'deployments' && (
        <div className="space-y-4">
          <div className="rounded-xl border border-border bg-card overflow-hidden">
            <div className="p-4 border-b border-border flex items-center justify-between">
              <h3 className="font-bold text-sm text-foreground">Release History</h3>
              <button onClick={loadData} className="text-xs text-blue-500 hover:underline flex items-center gap-1">
                <RefreshCw className="w-3 h-3" /> Refresh
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-background/60 text-gray-400 uppercase tracking-wider border-b border-border">
                  <tr>
                    <th className="p-3.5">Release</th>
                    <th className="p-3.5">Status</th>
                    <th className="p-3.5">Commit / Image</th>
                    <th className="p-3.5">Triggered At</th>
                    <th className="p-3.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {deployments.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="p-8 text-center text-gray-500">
                        No deployments yet. Click &quot;Deploy Latest&quot; or &quot;Deploy ZIP&quot; to build release v1.
                      </td>
                    </tr>
                  ) : (
                    deployments.map((d) => (
                      <tr key={d.id} className="hover:bg-gray-500/5 transition-colors">
                        <td className="p-3.5 font-mono font-bold text-foreground">
                          v{d.version}
                        </td>
                        <td className="p-3.5">
                          <span
                            className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase ${
                              d.status === 'success'
                                ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                                : d.status === 'failed'
                                ? 'bg-rose-500/10 text-rose-500'
                                : 'bg-amber-500/10 text-amber-500 animate-pulse'
                            }`}
                          >
                            {d.status}
                          </span>
                        </td>
                        <td className="p-3.5 font-mono text-gray-400">
                          {d.image_tag || d.commit_hash || 'HEAD'}
                        </td>
                        <td className="p-3.5 text-gray-400">
                          {new Date(d.created_at).toLocaleString()}
                        </td>
                        <td className="p-3.5 text-right space-x-2">
                          <Link
                            href={`/deployments/${d.id}`}
                            className="px-2.5 py-1 rounded border border-border hover:bg-gray-100 dark:hover:bg-gray-800 text-blue-500 font-medium"
                          >
                            Logs
                          </Link>
                          {d.status === 'success' && (
                            <button
                              onClick={() => handleRollback(d.id)}
                              className="px-2.5 py-1 rounded border border-border hover:bg-amber-500/10 text-amber-500 font-medium"
                              title="Rollback to this version"
                            >
                              Rollback
                            </button>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Tab: PostgreSQL Database Auto-Connect & Auto-Create */}
      {activeTab === 'database' && (
        <div className="space-y-6">
          <div className="rounded-xl border border-border bg-card p-5 space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-4">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                  <Database className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-sm text-foreground">PostgreSQL Auto-Connect & Auto-Provision</h3>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                        dbInfo?.connected
                          ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                          : 'bg-blue-500/10 text-blue-500 border border-blue-500/20'
                      }`}
                    >
                      {dbInfo?.connected ? 'CONNECTED & ACTIVE' : 'AUTO-PROVISION ON DEPLOY'}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {dbInfo?.message || 'Setiap kali project di-deploy, PSM otomatis memeriksa database di PostgreSQL, membuatnya jika belum ada, dan menghubungkannya ke container aplikasi.'}
                  </p>
                </div>
              </div>

              <form onSubmit={handleProvisionDatabase} className="flex items-center gap-2 text-xs">
                <input
                  type="text"
                  value={customDbName}
                  onChange={(e) => setCustomDbName(e.target.value)}
                  placeholder="database_name"
                  className="px-3 py-1.5 rounded-lg bg-background border border-border text-foreground font-mono text-xs w-40"
                />
                <button
                  type="submit"
                  disabled={provisioningDb}
                  className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium flex items-center gap-1.5 disabled:opacity-50 whitespace-nowrap"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>{provisioningDb ? 'Provisioning...' : 'Auto-Create / Sync DB'}</span>
                </button>
              </form>
            </div>

            {/* Connection Details Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs font-mono">
              <div className="p-3.5 rounded-xl bg-background border border-border">
                <span className="text-gray-400 font-sans block mb-1">Database Name</span>
                <span className="text-sm font-bold text-emerald-500">{dbInfo?.db_name || 'N/A'}</span>
              </div>
              <div className="p-3.5 rounded-xl bg-background border border-border">
                <span className="text-gray-400 font-sans block mb-1">Docker Network Host</span>
                <span className="text-sm font-bold text-foreground">
                  {dbInfo?.host || 'psm-postgres'}:{dbInfo?.port || 5432}
                </span>
              </div>
              <div className="p-3.5 rounded-xl bg-background border border-border">
                <span className="text-gray-400 font-sans block mb-1">Database User</span>
                <span className="text-sm font-bold text-foreground">{dbInfo?.user || 'psm'}</span>
              </div>
              <div className="p-3.5 rounded-xl bg-background border border-border">
                <span className="text-gray-400 font-sans block mb-1">Storage Size & Tables</span>
                <span className="text-sm font-bold text-blue-500">
                  {formatBytes(dbInfo?.size_bytes || 0)} • {dbInfo?.tables_count || 0} Tables
                </span>
              </div>
            </div>

            {/* Connection URL Copy Box */}
            <div className="space-y-2 text-xs">
              <label className="block text-gray-400 font-medium">
                Auto-Injected PostgreSQL Connection URI (<code>DATABASE_URL</code>):
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  readOnly
                  value={dbInfo?.masked_connection_url_internal || ''}
                  className="flex-1 px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono text-xs"
                />
                <button
                  onClick={() => {
                    if (dbInfo?.connection_url_internal) {
                      navigator.clipboard.writeText(dbInfo.connection_url_internal);
                      setCopiedDbUrl(true);
                      setTimeout(() => setCopiedDbUrl(false), 2000);
                    }
                  }}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border hover:bg-background text-foreground transition-all"
                >
                  {copiedDbUrl ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copiedDbUrl ? 'Copied Full URL' : 'Copy Full URL'}</span>
                </button>
              </div>
            </div>

            {/* Public Schema Tables List */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-semibold text-foreground flex items-center gap-1.5">
                  <Table className="w-3.5 h-3.5 text-blue-500" />
                  <span>Tables in Database &apos;{dbInfo?.db_name}&apos; ({dbInfo?.tables?.length || 0})</span>
                </span>
              </div>
              {dbInfo?.tables && dbInfo.tables.length > 0 ? (
                <div className="flex flex-wrap gap-2 pt-1">
                  {dbInfo.tables.map((tbl: string) => (
                    <span
                      key={tbl}
                      className="px-2.5 py-1 rounded-lg bg-background border border-border font-mono text-xs text-foreground"
                    >
                      {tbl}
                    </span>
                  ))}
                </div>
              ) : (
                <div className="p-4 rounded-lg bg-background border border-border text-xs text-gray-400">
                  Database <code>{dbInfo?.db_name}</code> sudah siap digunakan. Tabel akan otomatis dibuat saat aplikasi menjalankan migrasi saat deploy (misalnya <code>php artisan migrate --force</code>, Prisma, atau SQLAlchemy).
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Tab: Environment Variables */}
      {activeTab === 'environment' && (
        <div className="space-y-6">
          <div className="rounded-xl border border-border bg-card p-5 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <h3 className="font-bold text-sm text-foreground">Encrypted Environment Secrets</h3>
                <p className="text-xs text-gray-500 mt-0.5">
                  Variables are encrypted at rest with AES-Fernet encryption and merged with PostgreSQL auto-connect credentials during deployment.
                </p>
              </div>
              <button
                onClick={() => handleProvisionDatabase()}
                disabled={provisioningDb}
                className="px-3 py-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-500 text-xs font-medium flex items-center gap-1.5 self-start"
              >
                <Database className="w-3.5 h-3.5" />
                <span>Sync PostgreSQL Env Vars</span>
              </button>
            </div>

            {/* List */}
            <div className="space-y-2">
              {envVars.map((item) => (
                <div
                  key={item.key}
                  className="flex items-center justify-between p-3 rounded-lg border border-border bg-background text-xs font-mono"
                >
                  <span className="font-bold text-foreground">{item.key}</span>
                  <span className="text-gray-400">{item.masked_value}</span>
                </div>
              ))}
            </div>

            {/* Add new variable */}
            <form onSubmit={handleAddEnvVar} className="pt-4 border-t border-border flex gap-3 text-xs">
              <input
                type="text"
                placeholder="VARIABLE_KEY"
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                className="w-1/3 px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <input
                type="password"
                placeholder="SECRET_VALUE"
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                className="flex-1 px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                type="submit"
                className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium flex items-center gap-1"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Save Secret</span>
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Tab: Overview / Source */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Docker Network & Port Mappings Card */}
          <div className="rounded-xl border border-blue-500/20 bg-card p-5 space-y-4 text-xs font-mono">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 font-sans font-bold text-sm text-foreground">
                <Globe className="w-4 h-4 text-blue-500" />
                <span>Docker Port Mapping & Network</span>
              </div>
              {hostPortOnly && (
                <a
                  href={`http://${serverHost}:${hostPortOnly}`}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-sans font-medium transition-colors"
                >
                  <span>Buka di Browser</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="p-3 rounded-lg bg-background border border-border">
                <span className="text-gray-400 block mb-1">Mapping Konfigurasi</span>
                <span className="text-blue-500 font-bold text-sm">{project?.port_mappings || '3000:3000'}</span>
              </div>
              <div className="p-3 rounded-lg bg-background border border-border">
                <span className="text-gray-400 block mb-1">Server Host URL</span>
                <span className="text-foreground">
                  http://{serverHost}:{hostPortOnly}
                </span>
              </div>
              <div className="p-3 rounded-lg bg-background border border-border">
                <span className="text-gray-400 block mb-1">Network Docker</span>
                <span className="text-emerald-500">psm-network (bridge)</span>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-border bg-card p-5 space-y-4 text-xs font-mono">
            <h3 className="font-bold text-sm font-sans text-foreground">Source & Build Configuration</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="p-3 rounded-lg bg-background border border-border">
                <span className="text-gray-400 block mb-1">Source Type</span>
                <span className="text-foreground capitalize">{project?.source_type}</span>
              </div>
              <div className="p-3 rounded-lg bg-background border border-border">
                <span className="text-gray-400 block mb-1">Repository URL</span>
                <span className="text-foreground">{project?.repository_url || 'N/A (ZIP Upload)'}</span>
              </div>
              <div className="p-3 rounded-lg bg-background border border-border">
                <span className="text-gray-400 block mb-1">Branch</span>
                <span className="text-foreground">{project?.branch || 'main'}</span>
              </div>
              <div className="p-3 rounded-lg bg-background border border-border">
                <span className="text-gray-400 block mb-1">Dockerfile Path</span>
                <span className="text-foreground">{project?.dockerfile_path || 'Dockerfile'}</span>
              </div>
            </div>
          </div>

          {/* GitHub Auto-Deploy Webhook Card */}
          <div className="rounded-xl border border-border bg-card p-5 space-y-4">
            <div className="flex items-center gap-2">
              <div className="p-2 rounded-lg bg-purple-500/10 text-purple-500">
                <GitBranch className="w-4 h-4" />
              </div>
              <div>
                <h3 className="font-bold text-sm text-foreground">GitHub Webhook (Continuous Deployment to Docker)</h3>
                <p className="text-xs text-gray-500">
                  Automatically build and deploy directly to Docker every time you push code to GitHub.
                </p>
              </div>
            </div>

            <div className="space-y-2 text-xs">
              <label className="block text-gray-400 font-medium">Payload URL to configure in GitHub:</label>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  readOnly
                  value={typeof window !== 'undefined' ? `${window.location.origin}/api/v1/deployments/webhook/${projectId}` : `/api/v1/deployments/webhook/${projectId}`}
                  className="flex-1 px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono select-all text-xs"
                />
                <button
                  onClick={() => {
                    if (typeof window !== 'undefined') {
                      navigator.clipboard.writeText(`${window.location.origin}/api/v1/deployments/webhook/${projectId}`);
                      setCopiedWebhook(true);
                      setTimeout(() => setCopiedWebhook(false), 2000);
                    }
                  }}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border hover:bg-card text-foreground transition-all"
                >
                  {copiedWebhook ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copiedWebhook ? 'Copied' : 'Copy'}</span>
                </button>
              </div>
            </div>

            <div className="p-3.5 rounded-lg bg-background border border-border text-[11px] text-gray-500 space-y-1.5">
              <div className="font-semibold text-foreground">Cara memasang Webhook di GitHub:</div>
              <ol className="list-decimal list-inside space-y-1 text-gray-400">
                <li>Buka repositori GitHub Anda &gt; <strong>Settings</strong> &gt; <strong>Webhooks</strong> &gt; <strong>Add webhook</strong>.</li>
                <li>Tempel (Paste) URL di atas ke dalam kolom <strong>Payload URL</strong>.</li>
                <li>Pilih Content type: <code>application/json</code>.</li>
                <li>Pilih <em>&quot;Just the push event&quot;</em> lalu klik <strong>Add webhook</strong>.</li>
                <li>Selesai! Setiap Anda <code>git push</code>, PSM otomatis meng-clone, mem-build, membuat/menghubungkan database PostgreSQL, dan me-restart container Docker aplikasi Anda.</li>
              </ol>
            </div>
          </div>
        </div>
      )}

      {/* Tab: Settings */}
      {activeTab === 'settings' && (
        <div className="space-y-6">
          {/* Port Mappings Form */}
          <div className="rounded-xl border border-border bg-card p-5 space-y-4 text-xs">
            <div>
              <h3 className="font-bold text-sm text-foreground flex items-center gap-2">
                <Globe className="w-4 h-4 text-blue-500" />
                <span>Konfigurasi Port Mapping Docker</span>
              </h3>
              <p className="text-gray-500 mt-0.5">
                Ubah port host dan port internal container yang diekspos oleh Docker saat deployment berikutnya.
              </p>
            </div>

            <form onSubmit={handleSavePortMappings} className="space-y-3">
              <div>
                <label className="block text-gray-400 font-medium mb-1">
                  Port Mapping (Format: <code>HOST_PORT:CONTAINER_PORT</code>):
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={portMappingsInput}
                    onChange={(e) => setPortMappingsInput(e.target.value)}
                    placeholder="3000:3000"
                    className="flex-1 px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <button
                    type="submit"
                    disabled={savingPorts}
                    className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium disabled:opacity-50 transition-colors"
                  >
                    {savingPorts ? 'Menyimpan...' : 'Simpan Port'}
                  </button>
                </div>
              </div>

              {/* Quick Preset Buttons */}
              <div className="flex flex-wrap gap-2 pt-1 text-[11px]">
                <span className="text-gray-500 self-center">Preset:</span>
                {[
                  '3000:3000',
                  '8080:80',
                  '8000:8000',
                  '5000:5000',
                  '80:80',
                ].map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    onClick={() => setPortMappingsInput(preset)}
                    className="px-2.5 py-1 rounded-lg border border-border hover:bg-background text-gray-400 hover:text-foreground font-mono"
                  >
                    {preset}
                  </button>
                ))}
              </div>
            </form>
          </div>

          {/* Danger Zone */}
          <div className="rounded-xl border border-border bg-card p-5 space-y-4 text-xs">
            <h3 className="font-bold text-sm text-foreground">Project Danger Zone</h3>
            <p className="text-gray-500">Removing this project will stop all associated releases.</p>
            <button
              onClick={() => {
                if (confirm('Delete this project?')) {
                  api.deleteProject(projectId).then(() => router.push('/projects'));
                }
              }}
              className="px-4 py-2 rounded-lg bg-rose-600/10 hover:bg-rose-600/20 text-rose-600 font-medium"
            >
              Delete Project Permanently
            </button>
          </div>
        </div>
      )}

      {/* Deploy Release Modal */}
      <DeployProjectModal
        isOpen={deployModalOpen}
        onClose={() => setDeployModalOpen(false)}
        servers={servers}
        existingProject={project}
        onSuccess={() => loadData()}
      />
    </div>
  );
}
