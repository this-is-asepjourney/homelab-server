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
  Terminal,
  AlertTriangle,
  Play,
  Square,
  FileCode,
  Download,
  Eye,
  Sparkles,
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
  const [containerInfo, setContainerInfo] = useState<any>(null);
  const [containerLogs, setContainerLogs] = useState<string>('');
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [restartingContainer, setRestartingContainer] = useState(false);
  const [autoRefreshLogs, setAutoRefreshLogs] = useState(true);
  const [copiedLogs, setCopiedLogs] = useState(false);
  const [activeTab, setActiveTab] = useState<'overview' | 'deployments' | 'terminal' | 'dockerfile' | 'database' | 'environment' | 'settings'>('terminal');
  const [loading, setLoading] = useState(true);
  const [deploying, setDeploying] = useState(false);
  const [deployModalOpen, setDeployModalOpen] = useState(false);
  const [portMappingsInput, setPortMappingsInput] = useState('');
  const [savingPorts, setSavingPorts] = useState(false);
  const [provisioningDb, setProvisioningDb] = useState(false);
  const [customDbName, setCustomDbName] = useState('');
  const [selectedDbType, setSelectedDbType] = useState<string>('postgres');
  const [copiedWebhook, setCopiedWebhook] = useState(false);
  const [copiedDbUrl, setCopiedDbUrl] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const terminalEndRef = useRef<HTMLDivElement>(null);

  // Dockerfile Setup Assistant state
  const [dockerfileData, setDockerfileData] = useState<any>(null);
  const [dockerfileContent, setDockerfileContent] = useState<string>('');
  const [dockerignoreContent, setDockerignoreContent] = useState<string>('');
  const [dockerfileSubTab, setDockerfileSubTab] = useState<'dockerfile' | 'dockerignore'>('dockerfile');
  const [savingDockerfile, setSavingDockerfile] = useState(false);
  const [loadingDockerfile, setLoadingDockerfile] = useState(false);
  const [dockerfileTemplates, setDockerfileTemplates] = useState<any>({});
  const [selectedTemplateKey, setSelectedTemplateKey] = useState<string>('');
  const [copiedDockerfile, setCopiedDockerfile] = useState(false);
  const [saveSuccessMsg, setSaveSuccessMsg] = useState('');

  // New env var form
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');

  const fetchContainerLogs = async () => {
    try {
      setLoadingLogs(true);
      const [cInfo, cLogs] = await Promise.all([
        api.getProjectContainer(projectId).catch(() => null),
        api.getProjectContainerLogs(projectId, 250).catch(() => ({ logs: '' })),
      ]);
      setContainerInfo(cInfo);
      setContainerLogs(cLogs?.logs || '');
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingLogs(false);
    }
  };

  const handleRestartContainer = async () => {
    try {
      setRestartingContainer(true);
      await api.restartProjectContainer(projectId);
      await fetchContainerLogs();
    } catch (err: any) {
      alert(err.message || 'Gagal me-restart container');
    } finally {
      setRestartingContainer(false);
    }
  };

  const loadData = async () => {
    try {
      setLoading(true);
      const [p, d, env, dbData, s, cInfo, cLogs] = await Promise.all([
        api.getProject(projectId),
        api.getDeployments().then((list) => list.filter((item: any) => item.project_id === projectId)),
        api.getProjectEnvironment(projectId),
        api.getProjectDatabase(projectId),
        api.getServers().catch(() => []),
        api.getProjectContainer(projectId).catch(() => null),
        api.getProjectContainerLogs(projectId, 250).catch(() => ({ logs: '' })),
      ]);
      setProject(p);
      setDeployments(d);
      setEnvVars(env);
      setDbInfo(dbData);
      setServers(s);
      setContainerInfo(cInfo);
      setContainerLogs(cLogs?.logs || '');
      setPortMappingsInput(p?.port_mappings || '3000:3000');
      setSelectedDbType(p?.db_type || dbData?.db_type || 'postgres');
      if (dbData?.db_name) {
        setCustomDbName(dbData.db_name);
      } else if (p?.db_name) {
        setCustomDbName(p.db_name);
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

  const loadDockerfile = async () => {
    try {
      setLoadingDockerfile(true);
      const [dfRes, tmplRes] = await Promise.all([
        api.getProjectDockerfile(projectId).catch(() => null),
        api.getDockerfileTemplates().catch(() => ({ templates: {} })),
      ]);
      if (dfRes) {
        setDockerfileData(dfRes);
        setDockerfileContent(dfRes.dockerfile || '');
        setDockerignoreContent(dfRes.dockerignore || '');
      }
      if (tmplRes && tmplRes.templates) {
        setDockerfileTemplates(tmplRes.templates);
      }
    } catch (e) {
      console.error('Failed to load dockerfile:', e);
    } finally {
      setLoadingDockerfile(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'dockerfile') {
      loadDockerfile();
    }
  }, [activeTab, projectId]);

  const handleSaveDockerfile = async () => {
    try {
      setSavingDockerfile(true);
      setSaveSuccessMsg('');
      await api.updateProjectDockerfile(projectId, {
        dockerfile: dockerfileContent,
        dockerignore: dockerignoreContent,
        dockerfile_path: dockerfileData?.dockerfile_path || 'Dockerfile',
      });
      setSaveSuccessMsg('✓ Dockerfile dan .dockerignore berhasil disimpan ke workspace project!');
      setTimeout(() => setSaveSuccessMsg(''), 4000);
      loadDockerfile();
    } catch (err: any) {
      alert(err.message || 'Gagal menyimpan Dockerfile');
    } finally {
      setSavingDockerfile(false);
    }
  };

  const handleApplyTemplate = (tmplKey: string) => {
    setSelectedTemplateKey(tmplKey);
    const tmpl = dockerfileTemplates[tmplKey];
    if (tmpl && tmpl.sample_content) {
      setDockerfileContent(tmpl.sample_content);
    }
  };

  const handleRegenerateDockerfile = async () => {
    try {
      setLoadingDockerfile(true);
      const res = await api.generateDockerfilePreview({
        framework: project?.framework || 'Next.js',
        template_key: selectedTemplateKey || undefined,
        project_name: project?.name,
      });
      if (res && res.dockerfile) {
        setDockerfileContent(res.dockerfile);
        if (res.dockerignore) setDockerignoreContent(res.dockerignore);
        setSaveSuccessMsg('✓ Dockerfile profesional di-generate ulang! Klik "Simpan ke Workspace" untuk menerapkan.');
        setTimeout(() => setSaveSuccessMsg(''), 4000);
      }
    } catch (err: any) {
      alert(err.message || 'Gagal generate ulang Dockerfile');
    } finally {
      setLoadingDockerfile(false);
    }
  };

  useEffect(() => {
    if (!autoRefreshLogs || activeTab !== 'terminal') return;
    const interval = setInterval(() => {
      fetchContainerLogs();
    }, 3500);
    return () => clearInterval(interval);
  }, [autoRefreshLogs, activeTab, projectId]);

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

  const handleProvisionDatabase = async (e?: React.FormEvent, forcedType?: string) => {
    if (e) e.preventDefault();
    try {
      setProvisioningDb(true);
      const targetType = forcedType || selectedDbType || project?.db_type || 'postgres';
      const targetName = customDbName.trim() || undefined;
      // Update project record with the chosen engine & name
      await api.updateProject(projectId, {
        db_type: targetType,
        db_name: targetName,
      });
      // Provision/sync with provider engine
      await api.provisionProjectDatabase(projectId, targetName, true, targetType);
      await loadData();
    } catch (err: any) {
      alert(err.message || 'Failed to provision or sync database');
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

  const currentDbType = (project?.db_type || dbInfo?.db_type || 'postgres').toLowerCase();
  const dbTypeLabel =
    currentDbType === 'mysql'
      ? 'MySQL'
      : currentDbType === 'mariadb'
      ? 'MariaDB'
      : currentDbType === 'sqlite'
      ? 'SQLite'
      : currentDbType === 'none'
      ? 'Stateless'
      : 'PostgreSQL';
  const dbTypeBadge =
    currentDbType === 'mysql'
      ? 'MySQL'
      : currentDbType === 'mariadb'
      ? 'MariaDB'
      : currentDbType === 'sqlite'
      ? 'SQLite'
      : currentDbType === 'none'
      ? 'No DB'
      : 'PG';

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
              {containerInfo && (
                <button
                  onClick={() => setActiveTab('terminal')}
                  className={`flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold border transition-all ${
                    containerInfo.running
                      ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20 hover:bg-emerald-500/20'
                      : containerInfo.state === 'exited'
                      ? 'bg-rose-500/10 text-rose-500 border-rose-500/20 hover:bg-rose-500/20'
                      : 'bg-amber-500/10 text-amber-500 border-amber-500/20 hover:bg-amber-500/20'
                  }`}
                  title="Klik untuk membuka Terminal Logs container"
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${containerInfo.running ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`} />
                  <span>Container: {containerInfo.running ? 'RUNNING' : (containerInfo.state === 'exited' ? `EXITED (${containerInfo.exit_code ?? 1})` : containerInfo.state || 'STOPPED')}</span>
                </button>
              )}
              <span className="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-blue-500/10 text-blue-500 border border-blue-500/20">
                <Globe className="w-3 h-3" />
                <span>Port: {project?.port_mappings || '3000:3000'}</span>
              </span>
              {dbInfo && currentDbType !== 'none' && (
                <button
                  onClick={() => setActiveTab('database')}
                  className="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 hover:bg-emerald-500/20 transition-colors"
                >
                  <Database className="w-3 h-3" />
                  <span>{dbTypeBadge}: {dbInfo.db_name || project?.name}</span>
                </button>
              )}
            </div>
            <p className="text-xs text-gray-400 font-mono mt-0.5">
              {project?.framework} • Hosted on {project?.server_name}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5 flex-wrap">
          {/* Local DNS Ingress Link */}
          <a
            href={`http://${project?.domain || `${(project?.name || 'app').toLowerCase().replace(/[^a-z0-9_-]/g, '-')}.homelab`}`}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-indigo-500/30 bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 text-xs font-semibold transition-colors shadow-sm"
            title="Buka via Local DNS & Ingress Router (Port 80)"
          >
            <Globe className="w-3.5 h-3.5" />
            <span>{project?.domain || `${(project?.name || 'app').toLowerCase().replace(/[^a-z0-9_-]/g, '-')}.homelab`}</span>
            <ExternalLink className="w-3 h-3" />
          </a>

          {/* External Access Link if container port is available */}
          {hostPortOnly && (
            <a
              href={`http://${serverHost}:${hostPortOnly}`}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-500 text-xs font-semibold transition-colors shadow-sm"
              title="Buka via Port Langsung Server"
            >
              <span>Port :{hostPortOnly}</span>
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
          {
            key: 'terminal',
            label: 'Terminal Logs',
            icon: Terminal,
            badge: containerInfo?.running ? 'Running' : (containerInfo?.state === 'exited' ? `Exited (${containerInfo?.exit_code ?? 1})` : null),
            badgeColor: containerInfo?.running ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20' : 'bg-rose-500/10 text-rose-500 border border-rose-500/20',
          },
          { key: 'deployments', label: `Deployments (${deployments.length})`, icon: Rocket },
          {
            key: 'dockerfile',
            label: 'Dockerfile',
            icon: FileCode,
            badge: dockerfileData?.exists ? 'Workspace' : (dockerfileData?.is_generated ? 'Auto PaaS' : null),
            badgeColor: dockerfileData?.exists ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20' : 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20',
          },
          { key: 'database', label: `Database (${dbTypeBadge})`, icon: Database },
          { key: 'environment', label: `Environment (${envVars.length})`, icon: Key },
          { key: 'overview', label: 'Source & Build', icon: FolderGit2 },
          { key: 'settings', label: 'Settings', icon: Settings },
        ].map((tab: any) => {
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
              {tab.badge && (
                <span className={`px-1.5 py-0.2 rounded text-[9px] font-mono font-bold ${tab.badgeColor || 'bg-gray-500/20 text-gray-400'}`}>
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Tab: Container Terminal Logs */}
      {activeTab === 'terminal' && (
        <div className="space-y-4">
          <div className="rounded-xl border border-border bg-card overflow-hidden shadow-sm">
            {/* Header Controls */}
            <div className="p-4 border-b border-border bg-background/50 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-blue-500/10 text-blue-500">
                  <Terminal className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-sm text-foreground">
                      Container Console &amp; Terminal Logs
                    </h3>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase ${
                        containerInfo?.running
                          ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                          : containerInfo?.state === 'exited'
                          ? 'bg-rose-500/10 text-rose-500 border border-rose-500/20'
                          : 'bg-amber-500/10 text-amber-500 border border-amber-500/20'
                      }`}
                    >
                      {containerInfo?.running ? '● RUNNING' : `● ${containerInfo?.state || 'STOPPED'} (Exit: ${containerInfo?.exit_code ?? 0})`}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 font-mono mt-0.5">
                    Container: {containerInfo?.container_name || project?.name} • Image: {containerInfo?.image || `${project?.name}:latest`}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                <label className="flex items-center gap-1.5 text-xs text-gray-400 mr-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={autoRefreshLogs}
                    onChange={(e) => setAutoRefreshLogs(e.target.checked)}
                    className="rounded border-border text-blue-600 focus:ring-blue-500"
                  />
                  <span>Live Stream (3s)</span>
                </label>

                <button
                  onClick={fetchContainerLogs}
                  disabled={loadingLogs}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border hover:bg-card text-foreground text-xs font-medium transition-colors disabled:opacity-50"
                  title="Muat ulang log"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${loadingLogs ? 'animate-spin' : ''}`} />
                  <span>Refresh</span>
                </button>

                <button
                  onClick={handleRestartContainer}
                  disabled={restartingContainer}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 hover:bg-amber-500/20 text-amber-500 text-xs font-medium transition-colors disabled:opacity-50"
                  title="Restart container Docker"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${restartingContainer ? 'animate-spin' : ''}`} />
                  <span>{restartingContainer ? 'Restarting...' : 'Restart Container'}</span>
                </button>

                <button
                  onClick={() => {
                    if (containerLogs) {
                      navigator.clipboard.writeText(containerLogs);
                      setCopiedLogs(true);
                      setTimeout(() => setCopiedLogs(false), 2000);
                    }
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border hover:bg-card text-foreground text-xs font-medium transition-colors"
                >
                  {copiedLogs ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copiedLogs ? 'Copied' : 'Copy'}</span>
                </button>
              </div>
            </div>

            {/* Error or Stopped Banner */}
            {containerInfo?.exit_code !== undefined && containerInfo.exit_code !== 0 && !containerInfo.running && (
              <div className="bg-rose-500/10 border-b border-rose-500/20 px-4 py-3 flex items-start gap-2.5 text-xs text-rose-400">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-rose-500" />
                <div>
                  <span className="font-bold">Container Berhenti atau Crash (Exit Code: {containerInfo.exit_code})</span>
                  <p className="text-gray-400 text-[11px] mt-0.5">
                    {containerInfo.error || 'Aplikasi di dalam container berhenti atau gagal saat booting. Silakan tinjau log terminal di bawah untuk melihat pesan error aplikasi.'}
                  </p>
                </div>
              </div>
            )}

            {/* Terminal Screen */}
            <div className="bg-[#0b0f19] p-4 text-xs font-mono text-gray-200 overflow-x-auto min-h-[380px] max-h-[560px] overflow-y-auto leading-relaxed border-t border-border/40 select-text">
              {containerLogs ? (
                containerLogs.split('\n').map((line, idx) => {
                  const isError = line.toLowerCase().includes('error') || line.toLowerCase().includes('fatal') || line.toLowerCase().includes('exception') || line.toLowerCase().includes('failed');
                  const isWarn = line.toLowerCase().includes('warn') || line.toLowerCase().includes('notice');
                  const isInfo = line.toLowerCase().includes('info') || line.toLowerCase().includes('ready') || line.toLowerCase().includes('running') || line.toLowerCase().includes('started');
                  return (
                    <div key={idx} className="flex gap-3 hover:bg-white/5 py-0.5 px-1 rounded">
                      <span className="text-gray-600 select-none text-[10px] w-8 text-right shrink-0">{idx + 1}</span>
                      <span
                        className={`break-all ${
                          isError
                            ? 'text-rose-400 font-semibold'
                            : isWarn
                            ? 'text-amber-300'
                            : isInfo
                            ? 'text-blue-300'
                            : 'text-gray-300'
                        }`}
                      >
                        {line}
                      </span>
                    </div>
                  );
                })
              ) : (
                <div className="flex flex-col items-center justify-center h-48 text-gray-500 space-y-2">
                  <Terminal className="w-8 h-8 opacity-40" />
                  <span>Tidak ada log output yang terekam atau container belum berjalan.</span>
                </div>
              )}
              <div ref={terminalEndRef} />
            </div>
          </div>
        </div>
      )}

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

      {/* Tab: Dockerfile & PaaS Build Configuration */}
      {activeTab === 'dockerfile' && (
        <div className="space-y-6">
          {/* Header Card */}
          <div className="rounded-xl border border-indigo-500/20 bg-card p-5 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-4">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                  <FileCode className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-sm text-foreground">Dockerfile & Build Configuration</h3>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                        dockerfileData?.exists
                          ? 'bg-blue-500/10 text-blue-400 border-blue-500/20'
                          : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                      }`}
                    >
                      {dockerfileData?.exists
                        ? `✓ Workspace: ${dockerfileData?.dockerfile_path || 'Dockerfile'}`
                        : '⚡ Auto-Generated (PaaS Standard)'}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                    Personal Server Manager mendukung deployment profesional dengan Dockerfile multi-stage production dan proteksi context .dockerignore.
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={loadDockerfile}
                  disabled={loadingDockerfile}
                  className="px-3 py-1.5 rounded-lg border border-border hover:bg-background text-gray-400 hover:text-foreground text-xs font-medium transition-colors flex items-center gap-1.5"
                  title="Muat ulang dari disk"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${loadingDockerfile ? 'animate-spin' : ''}`} />
                  <span>Reload</span>
                </button>
                <button
                  type="button"
                  onClick={handleSaveDockerfile}
                  disabled={savingDockerfile}
                  className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors flex items-center gap-1.5 shadow-sm"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>{savingDockerfile ? 'Menyimpan...' : 'Simpan ke Workspace'}</span>
                </button>
              </div>
            </div>

            {/* Save Success Alert */}
            {saveSuccessMsg && (
              <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs flex items-center gap-2 animate-in fade-in duration-200">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span>{saveSuccessMsg}</span>
              </div>
            )}

            {/* Template Presets Bar */}
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-3 rounded-lg bg-background border border-border text-xs">
              <div className="flex items-center gap-2 flex-1">
                <Sparkles className="w-4 h-4 text-amber-400 shrink-0" />
                <span className="text-gray-400 font-medium whitespace-nowrap">Template Stack Preset:</span>
                <select
                  value={selectedTemplateKey}
                  onChange={(e) => handleApplyTemplate(e.target.value)}
                  className="flex-1 px-3 py-1.5 rounded-lg bg-card border border-border text-foreground text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
                >
                  <option value="">Pilih Preset Template Profesional...</option>
                  {Object.keys(dockerfileTemplates).map((k) => (
                    <option key={k} value={k}>
                      {dockerfileTemplates[k].name} (Port: {dockerfileTemplates[k].default_port})
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <button
                  type="button"
                  onClick={handleRegenerateDockerfile}
                  disabled={loadingDockerfile}
                  className="px-3 py-1.5 rounded-lg border border-indigo-500/30 hover:bg-indigo-500/10 text-indigo-400 text-xs font-medium transition-colors flex items-center gap-1"
                >
                  <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                  <span>Generate Ulang Otomatis</span>
                </button>
              </div>
            </div>

            {/* File Switcher & Code Editor */}
            <div className="space-y-2">
              <div className="flex items-center justify-between border-b border-border pb-2">
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setDockerfileSubTab('dockerfile')}
                    className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-colors flex items-center gap-1.5 ${
                      dockerfileSubTab === 'dockerfile'
                        ? 'bg-indigo-600/15 text-indigo-400 border border-indigo-500/30'
                        : 'text-gray-400 hover:text-foreground'
                    }`}
                  >
                    <FileCode className="w-3.5 h-3.5" />
                    <span>Dockerfile</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setDockerfileSubTab('dockerignore')}
                    className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-colors flex items-center gap-1.5 ${
                      dockerfileSubTab === 'dockerignore'
                        ? 'bg-indigo-600/15 text-indigo-400 border border-indigo-500/30'
                        : 'text-gray-400 hover:text-foreground'
                    }`}
                  >
                    <span>.dockerignore</span>
                    <span className="px-1.5 py-0.2 rounded text-[9px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      Context Guard
                    </span>
                  </button>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      const text = dockerfileSubTab === 'dockerfile' ? dockerfileContent : dockerignoreContent;
                      navigator.clipboard.writeText(text);
                      setCopiedDockerfile(true);
                      setTimeout(() => setCopiedDockerfile(false), 2000);
                    }}
                    className="px-2.5 py-1 rounded-md border border-border hover:bg-background text-gray-400 hover:text-foreground text-xs flex items-center gap-1 transition-colors"
                  >
                    {copiedDockerfile ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
                    <span>{copiedDockerfile ? 'Copied' : 'Salin'}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const text = dockerfileSubTab === 'dockerfile' ? dockerfileContent : dockerignoreContent;
                      const fname = dockerfileSubTab === 'dockerfile' ? 'Dockerfile' : '.dockerignore';
                      const blob = new Blob([text], { type: 'text/plain' });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url;
                      a.download = fname;
                      a.click();
                      URL.revokeObjectURL(url);
                    }}
                    className="px-2.5 py-1 rounded-md border border-border hover:bg-background text-gray-400 hover:text-foreground text-xs flex items-center gap-1 transition-colors"
                  >
                    <Download className="w-3 h-3" />
                    <span>Unduh</span>
                  </button>
                </div>
              </div>

              {/* Textarea Code Editor */}
              <div className="relative rounded-lg border border-border bg-[#0d1117] overflow-hidden">
                <textarea
                  value={dockerfileSubTab === 'dockerfile' ? dockerfileContent : dockerignoreContent}
                  onChange={(e) => {
                    if (dockerfileSubTab === 'dockerfile') {
                      setDockerfileContent(e.target.value);
                    } else {
                      setDockerignoreContent(e.target.value);
                    }
                  }}
                  rows={20}
                  spellCheck={false}
                  className="w-full p-4 bg-transparent text-gray-200 font-mono text-xs focus:outline-none resize-y leading-relaxed"
                  placeholder={dockerfileSubTab === 'dockerfile' ? '# Masukkan konten Dockerfile...' : '# Masukkan pola .dockerignore...'}
                />
              </div>
            </div>

            {/* Architecture Highlights / Explanations */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 text-xs">
              <div className="p-3 rounded-lg border border-border bg-background/50 space-y-1">
                <div className="font-semibold text-foreground flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-blue-400" />
                  <span>Multi-Stage Standalone</span>
                </div>
                <p className="text-[11px] text-gray-400 leading-normal">
                  Memisahkan layer instalasi dependencies, build, dan runner runtime sehingga ukuran final image berkurang drastis (&lt;120MB) dan proses build cepat.
                </p>
              </div>

              <div className="p-3 rounded-lg border border-border bg-background/50 space-y-1">
                <div className="font-semibold text-foreground flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Non-Root Security User</span>
                </div>
                <p className="text-[11px] text-gray-400 leading-normal">
                  Container dijalankan oleh user aplikasi non-root terisolasi (seperti <code>nextjs</code>, <code>node</code>, <code>appuser</code>) untuk melindungi sistem host homelab.
                </p>
              </div>

              <div className="p-3 rounded-lg border border-border bg-background/50 space-y-1">
                <div className="font-semibold text-foreground flex items-center gap-1.5">
                  <FileCode className="w-3.5 h-3.5 text-purple-400" />
                  <span>Proteksi Context Guard</span>
                </div>
                <p className="text-[11px] text-gray-400 leading-normal">
                  File <code>.dockerignore</code> otomatis mencegah direktori berat host (<code>node_modules</code>, <code>.git</code>, <code>.venv</code>) dikirim ke daemon Docker.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

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
                    <h3 className="font-bold text-sm text-foreground">{dbTypeLabel} Auto-Connect & Auto-Provision</h3>
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
                    {dbInfo?.message || `Setiap kali project di-deploy, PSM otomatis memeriksa database di ${dbTypeLabel}, membuatnya jika belum ada, dan menghubungkannya ke container aplikasi.`}
                  </p>
                </div>
              </div>

              <form onSubmit={handleProvisionDatabase} className="flex flex-wrap items-center gap-2 text-xs">
                <select
                  value={selectedDbType}
                  onChange={(e) => setSelectedDbType(e.target.value)}
                  className="px-2.5 py-1.5 rounded-lg bg-background border border-border text-foreground font-mono text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                >
                  <option value="mysql">MySQL (:3306)</option>
                  <option value="postgres">PostgreSQL (:5432)</option>
                  <option value="sqlite">SQLite (File)</option>
                  <option value="none">Stateless (No DB)</option>
                </select>
                <input
                  type="text"
                  value={customDbName}
                  onChange={(e) => setCustomDbName(e.target.value)}
                  placeholder="database_name"
                  className="px-3 py-1.5 rounded-lg bg-background border border-border text-foreground font-mono text-xs w-36 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
                <button
                  type="submit"
                  disabled={provisioningDb}
                  className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium flex items-center gap-1.5 disabled:opacity-50 whitespace-nowrap shadow-sm transition-colors"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>{provisioningDb ? 'Syncing...' : 'Save & Sync DB'}</span>
                </button>
              </form>
            </div>

            {/* Connection Details Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs font-mono">
              <div className="p-3.5 rounded-xl bg-background border border-border">
                <span className="text-gray-400 font-sans block mb-1">Database Engine</span>
                <span className="text-sm font-bold text-foreground">
                  {currentDbType === 'mysql' && 'MySQL (Port 3306)'}
                  {currentDbType === 'mariadb' && 'MariaDB (Port 3306)'}
                  {currentDbType === 'postgres' && 'PostgreSQL (Port 5432)'}
                  {currentDbType === 'sqlite' && 'SQLite (Embedded File)'}
                  {currentDbType === 'none' && 'None / Stateless'}
                </span>
              </div>
              <div className="p-3.5 rounded-xl bg-background border border-border">
                <span className="text-gray-400 font-sans block mb-1">Database Name</span>
                <span className="text-sm font-bold text-emerald-500">{dbInfo?.db_name || (currentDbType === 'none' ? 'None' : 'N/A')}</span>
              </div>
              <div className="p-3.5 rounded-xl bg-background border border-border">
                <span className="text-gray-400 font-sans block mb-1">Docker Network Host</span>
                <span className="text-sm font-bold text-foreground">
                  {currentDbType === 'sqlite'
                    ? (dbInfo?.file_path || '/data/*.db')
                    : currentDbType === 'none'
                    ? 'N/A'
                    : `${dbInfo?.host || '192.168.25.101'}:${dbInfo?.port || (currentDbType === 'mysql' ? 3306 : 5432)}`}
                </span>
              </div>
              <div className="p-3.5 rounded-xl bg-background border border-border">
                <span className="text-gray-400 font-sans block mb-1">Storage Size & Tables</span>
                <span className="text-sm font-bold text-blue-500">
                  {formatBytes(dbInfo?.size_bytes || 0)} • {dbInfo?.tables_count ?? (dbInfo?.tables?.length || 0)} Tables
                </span>
              </div>
            </div>

            {/* Connection URL Copy Box */}
            {currentDbType !== 'none' && (
              <div className="space-y-2 text-xs">
                <label className="block text-gray-400 font-medium">
                  Auto-Injected {dbTypeLabel} Connection URI (<code>DATABASE_URL</code>):
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    readOnly
                    value={dbInfo?.masked_connection_url_internal || dbInfo?.connection_url_internal || ''}
                    className="flex-1 px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono text-xs"
                  />
                  <button
                    onClick={() => {
                      const urlToCopy = dbInfo?.connection_url_internal || dbInfo?.masked_connection_url_internal;
                      if (urlToCopy) {
                        navigator.clipboard.writeText(urlToCopy);
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
            )}

            {/* Schema Tables List */}
            {currentDbType !== 'none' && (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-foreground flex items-center gap-1.5">
                    <Table className="w-3.5 h-3.5 text-blue-500" />
                    <span>Tables in Database &apos;{dbInfo?.db_name}&apos; ({dbInfo?.tables?.length || 0})</span>
                  </span>
                </div>
                {dbInfo?.tables && dbInfo.tables.length > 0 ? (
                  <div className="flex flex-wrap gap-2 pt-1 max-h-48 overflow-y-auto">
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
                    Database <code>{dbInfo?.db_name}</code> sudah siap digunakan di {dbTypeLabel}. Tabel akan otomatis dibuat saat aplikasi menjalankan migrasi saat deploy (misalnya <code>php artisan migrate --force</code>, Prisma, atau SQLAlchemy).
                  </div>
                )}
              </div>
            )}
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
                  Variables are encrypted at rest with AES-Fernet encryption and merged with {dbTypeLabel} auto-connect credentials during deployment.
                </p>
              </div>
              <button
                onClick={() => handleProvisionDatabase()}
                disabled={provisioningDb}
                className="px-3 py-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-500 text-xs font-medium flex items-center gap-1.5 self-start"
              >
                <Database className="w-3.5 h-3.5" />
                <span>Sync {dbTypeLabel} Env Vars</span>
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
                <li>Selesai! Setiap Anda <code>git push</code>, PSM otomatis meng-clone, mem-build, membuat/menghubungkan database {dbTypeLabel}, dan me-restart container Docker aplikasi Anda.</li>
              </ol>
            </div>
          </div>
        </div>
      )}

      {/* Tab: Settings */}
      {activeTab === 'settings' && (
        <div className="space-y-6">
          {/* Database Engine & Configuration Form */}
          <div className="rounded-xl border border-border bg-card p-5 space-y-4 text-xs">
            <div>
              <h3 className="font-bold text-sm text-foreground flex items-center gap-2">
                <Database className="w-4 h-4 text-emerald-500" />
                <span>Konfigurasi Engine & Nama Database</span>
              </h3>
              <p className="text-gray-500 mt-0.5">
                Ubah jenis database (MySQL, PostgreSQL, SQLite, atau Stateless) dan nama database yang dihubungkan ke container aplikasi.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-gray-400 font-medium mb-1">Database Engine:</label>
                <select
                  value={selectedDbType}
                  onChange={(e) => setSelectedDbType(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500"
                >
                  <option value="mysql">MySQL (:3306) — Cocok untuk Laravel, PHP, WordPress</option>
                  <option value="postgres">PostgreSQL (:5432) — Cocok untuk Django, Node, Next.js, FastAPI</option>
                  <option value="sqlite">SQLite (File /data/*.db) — Embedded file database</option>
                  <option value="none">Stateless / No Database</option>
                </select>
              </div>
              <div>
                <label className="block text-gray-400 font-medium mb-1">Nama Database:</label>
                <input
                  type="text"
                  value={customDbName}
                  onChange={(e) => setCustomDbName(e.target.value)}
                  placeholder="database_name"
                  className="w-full px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
              </div>
            </div>

            <div className="flex items-center justify-between pt-1">
              <span className="text-[11px] text-gray-400">
                Saat disimpan, variabel koneksi (<code>DATABASE_URL</code>, <code>DB_CONNECTION</code>, <code>DB_HOST</code>, dll.) otomatis diperbarui.
              </span>
              <button
                type="button"
                onClick={() => handleProvisionDatabase()}
                disabled={provisioningDb}
                className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium disabled:opacity-50 transition-colors flex items-center gap-1.5 whitespace-nowrap shadow-sm"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>{provisioningDb ? 'Menyimpan...' : 'Simpan & Sinkronkan Database'}</span>
              </button>
            </div>
          </div>
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
