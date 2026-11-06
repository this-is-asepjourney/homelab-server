'use client';

import React, { useState, useEffect, useId } from 'react';
import { useRouter } from 'next/navigation';
import {
  FolderGit2,
  GitBranch,
  Upload,
  Rocket,
  Server as ServerIcon,
  Globe,
  Key,
  Database,
  Plus,
  Trash2,
  X,
  Eye,
  EyeOff,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  Layers,
  FileCode,
  ExternalLink,
  FileText,
  Sparkles,
  HelpCircle,
  AlertCircle,
} from 'lucide-react';
import { api, formatBytes } from '../lib/api';

interface DeployProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (createdProject: any) => void;
  servers: any[];
  defaultServerId?: string;
  existingProject?: any; // If provided, modal operates in "Deploy Release" mode
}

export function DeployProjectModal({
  isOpen,
  onClose,
  onSuccess,
  servers,
  defaultServerId,
  existingProject,
}: DeployProjectModalProps) {
  const router = useRouter();
  const fileInputId = useId();

  // Wizard step: 1 = Source, 2 = Port Mapping, 3 = Environment & DB, 4 = Review & Deploy
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3 | 4>(1);

  // Step 1: Source
  const [name, setName] = useState(existingProject?.name || '');
  const [serverId, setServerId] = useState(existingProject?.server_id || defaultServerId || (servers[0]?.id || ''));
  const [framework, setFramework] = useState(existingProject?.framework || 'Next.js');
  const [sourceType, setSourceType] = useState<'git' | 'upload'>(existingProject?.source_type || 'git');
  const [repositoryUrl, setRepositoryUrl] = useState(existingProject?.repository_url || '');
  const [branch, setBranch] = useState(existingProject?.branch || 'main');
  const [commitHash, setCommitHash] = useState('');
  const [zipFile, setZipFile] = useState<File | null>(null);

  // Step 2: Ports
  const [hostPort, setHostPort] = useState('3000');
  const [containerPort, setContainerPort] = useState('3000');
  const [additionalPorts, setAdditionalPorts] = useState<Array<{ host: string; container: string }>>([]);

  // Step 3: Environment & DB
  const [envMode, setEnvMode] = useState<'table' | 'raw'>('table');
  const [envRows, setEnvRows] = useState<Array<{ key: string; value: string; isSecret?: boolean }>>([
    { key: 'NODE_ENV', value: 'production', isSecret: false },
  ]);
  const [rawEnvText, setRawEnvText] = useState('');
  const [autoProvisionDb, setAutoProvisionDb] = useState(true);
  const [customDbName, setCustomDbName] = useState('');
  const [showSecrets, setShowSecrets] = useState(false);

  // Submission
  const [deploying, setDeploying] = useState(false);
  const [deployStatusText, setDeployStatusText] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  // Initialize from existing project if supplied
  useEffect(() => {
    if (existingProject) {
      setName(existingProject.name || '');
      setServerId(existingProject.server_id || servers[0]?.id || '');
      setFramework(existingProject.framework || 'Next.js');
      setSourceType(existingProject.source_type || 'git');
      setRepositoryUrl(existingProject.repository_url || '');
      setBranch(existingProject.branch || 'main');

      // Parse existing port mappings (e.g. "8080:3000" or "3000:3000")
      if (existingProject.port_mappings) {
        const parts = existingProject.port_mappings.split(',').map((p: string) => p.trim());
        if (parts.length > 0 && parts[0].includes(':')) {
          const [hp, cp] = parts[0].split(':');
          setHostPort(hp);
          setContainerPort(cp);
          if (parts.length > 1) {
            setAdditionalPorts(
              parts.slice(1).map((p: string) => {
                const [h, c] = p.split(':');
                return { host: h || '', container: c || '' };
              })
            );
          }
        }
      }
    } else if (servers.length > 0 && !serverId) {
      setServerId(servers[0].id);
    }
  }, [existingProject, servers]);

  if (!isOpen) return null;

  // Selected server details
  const selectedServer = servers.find((s) => s.id === serverId) || servers[0];
  const serverHost = selectedServer?.hostname || 'localhost';

  // Quick port presets
  const applyPortPreset = (hp: string, cp: string) => {
    setHostPort(hp);
    setContainerPort(cp);
  };

  // Change framework presets
  const handleFrameworkChange = (fw: string) => {
    setFramework(fw);
    if (fw === 'Next.js' || fw === 'Node.js' || fw === 'React / Vite') {
      applyPortPreset('3000', '3000');
    } else if (fw === 'FastAPI' || fw === 'Django / Python') {
      applyPortPreset('8000', '8000');
    } else if (fw === 'Laravel' || fw === 'PHP') {
      applyPortPreset('8080', '80');
    } else if (fw === 'Flask') {
      applyPortPreset('5000', '5000');
    } else if (fw === 'Static HTML') {
      applyPortPreset('8080', '80');
    }
  };

  // Auto-name detection from Git URL or ZIP
  const handleRepoUrlChange = (url: string) => {
    setRepositoryUrl(url);
    if (!name || name === 'my-app') {
      try {
        const clean = url.replace(/\.git$/, '');
        const segs = clean.split('/');
        const last = segs[segs.length - 1];
        if (last) {
          setName(last.toLowerCase().replace(/[^a-z0-9_-]/g, '-'));
        }
      } catch (_) {}
    }
  };

  const handleZipFileChange = (file: File | null) => {
    setZipFile(file);
    if (file && (!name || name === 'my-app')) {
      const base = file.name.replace(/\.zip$/i, '');
      setName(base.toLowerCase().replace(/[^a-z0-9_-]/g, '-'));
    }
  };

  // Env table <-> raw sync
  const syncTableToRaw = (rows: Array<{ key: string; value: string }>) => {
    const text = rows
      .filter((r) => r.key.trim())
      .map((r) => `${r.key.trim()}=${r.value}`)
      .join('\n');
    setRawEnvText(text);
  };

  const syncRawToTable = (text: string) => {
    const lines = text.split('\n');
    const newRows: Array<{ key: string; value: string }> = [];
    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line || line.startsWith('#')) continue;
      const idx = line.indexOf('=');
      if (idx !== -1) {
        newRows.push({
          key: line.slice(0, idx).trim(),
          value: line.slice(idx + 1).trim(),
        });
      }
    }
    setEnvRows(newRows.length > 0 ? newRows : [{ key: '', value: '' }]);
  };

  const addEnvRow = () => {
    setEnvRows((prev) => [...prev, { key: '', value: '' }]);
  };

  const updateEnvRow = (idx: number, field: 'key' | 'value', val: string) => {
    setEnvRows((prev) => {
      const copy = [...prev];
      copy[idx][field] = val;
      return copy;
    });
  };

  const removeEnvRow = (idx: number) => {
    setEnvRows((prev) => prev.filter((_, i) => i !== idx));
  };

  // Compile final port mappings string
  const compilePortMappings = (): string => {
    const list = [`${hostPort.trim()}:${containerPort.trim()}`];
    for (const ap of additionalPorts) {
      if (ap.host.trim() && ap.container.trim()) {
        list.push(`${ap.host.trim()}:${ap.container.trim()}`);
      }
    }
    return list.join(', ');
  };

  // Compile final env vars
  const compileEnvVars = (): Array<{ key: string; value: string }> => {
    if (envMode === 'raw') {
      const lines = rawEnvText.split('\n');
      const vars: Array<{ key: string; value: string }> = [];
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) continue;
        const eq = trimmed.indexOf('=');
        if (eq > 0) {
          vars.push({
            key: trimmed.slice(0, eq).trim(),
            value: trimmed.slice(eq + 1).trim(),
          });
        }
      }
      return vars;
    }
    return envRows.filter((r) => r.key.trim().length > 0);
  };

  // Final Action: Create & Deploy
  const handleDeploy = async () => {
    setErrorMsg('');
    if (!name.trim()) {
      setErrorMsg('Project Name is required.');
      setCurrentStep(1);
      return;
    }
    if (sourceType === 'git' && !repositoryUrl.trim()) {
      setErrorMsg('GitHub repository URL is required.');
      setCurrentStep(1);
      return;
    }
    if (sourceType === 'upload' && !zipFile && !existingProject) {
      setErrorMsg('Please select a project ZIP file.');
      setCurrentStep(1);
      return;
    }
    if (!hostPort || !containerPort) {
      setErrorMsg('Host and container ports are required.');
      setCurrentStep(2);
      return;
    }

    try {
      setDeploying(true);
      const portString = compilePortMappings();
      const envVariables = compileEnvVars();

      // If existing project: trigger deployment directly
      if (existingProject) {
        setDeployStatusText('Updating project configuration and launching container...');
        if (sourceType === 'upload' && zipFile) {
          const dep = await api.uploadZipDeployment(existingProject.id, zipFile, portString, envVariables);
          onClose();
          router.push(`/deployments/${dep.id}`);
        } else {
          const dep = await api.triggerGitDeployment(existingProject.id, branch || 'main', portString, envVariables);
          onClose();
          router.push(`/deployments/${dep.id}`);
        }
        return;
      }

      // Creating a new project flow
      setDeployStatusText('Creating project record & configuring Docker network...');
      const created = await api.createProject({
        server_id: serverId,
        name: name.trim(),
        framework,
        source_type: sourceType,
        repository_url: sourceType === 'git' ? repositoryUrl.trim() : null,
        branch: sourceType === 'git' ? branch || 'main' : null,
        port_mappings: portString,
        auto_provision_db: autoProvisionDb,
        database_name: customDbName.trim() || null,
        environment_variables: envVariables,
        auto_deploy: sourceType === 'git',
      });

      if (sourceType === 'upload' && zipFile) {
        setDeployStatusText('Uploading ZIP archive & initiating Docker build...');
        const dep = await api.uploadZipDeployment(created.id, zipFile, portString, envVariables);
        onClose();
        if (onSuccess) onSuccess(created);
        router.push(`/deployments/${dep.id}`);
        return;
      }

      onClose();
      if (onSuccess) onSuccess(created);

      // If Git deployment was triggered automatically, redirect to deployment logs
      if (created.deployment_id) {
        router.push(`/deployments/${created.deployment_id}`);
      } else {
        router.push(`/projects/${created.id}`);
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Deployment initialization failed');
    } finally {
      setDeploying(false);
      setDeployStatusText('');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-in fade-in duration-200">
      <div className="w-full max-w-3xl rounded-2xl border border-border bg-card shadow-2xl flex flex-col max-h-[92vh] overflow-hidden text-foreground">
        {/* Header */}
        <div className="px-6 py-4 border-b border-border flex items-center justify-between bg-card/80 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-blue-600/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
              <Rocket className="w-5 h-5" />
            </div>
            <div>
              <h2 className="font-bold text-base text-foreground flex items-center gap-2">
                <span>{existingProject ? `Deploy Release • ${existingProject.name}` : 'Deploy Project ke Docker'}</span>
                <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-500/10 text-blue-500 border border-blue-500/20 uppercase tracking-wide">
                  Fast Docker Pipeline
                </span>
              </h2>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Langkah mudah deploy container via Git atau ZIP dengan port mapping & environment variables.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            disabled={deploying}
            className="p-1.5 rounded-lg text-gray-400 hover:text-foreground hover:bg-background transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Stepper Wizard Indicator */}
        <div className="px-6 py-3 border-b border-border/80 bg-background/50 grid grid-cols-4 gap-2 text-xs">
          {[
            { step: 1, label: '1. Source Project', icon: FolderGit2 },
            { step: 2, label: '2. Port Mapping', icon: Globe },
            { step: 3, label: '3. Environment (.env)', icon: Key },
            { step: 4, label: '4. Review & Deploy', icon: Rocket },
          ].map((item) => {
            const Icon = item.icon;
            const isCurrent = currentStep === item.step;
            const isDone = currentStep > item.step;
            return (
              <button
                key={item.step}
                type="button"
                onClick={() => !deploying && setCurrentStep(item.step as any)}
                className={`flex items-center gap-2 px-3 py-2 rounded-xl transition-all text-left ${
                  isCurrent
                    ? 'bg-blue-600 text-white font-semibold shadow-sm'
                    : isDone
                    ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 font-medium'
                    : 'text-gray-400 hover:text-foreground hover:bg-card/50'
                }`}
              >
                <Icon className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate">{item.label}</span>
              </button>
            );
          })}
        </div>

        {/* Body Content */}
        <div className="p-6 overflow-y-auto space-y-5 flex-1">
          {errorMsg && (
            <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-500 text-xs flex items-center gap-2.5">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* STEP 1: SOURCE PROJECT */}
          {currentStep === 1 && (
            <div className="space-y-5 animate-in fade-in duration-150">
              {/* Source Type Selector */}
              <div>
                <label className="block text-xs font-semibold text-foreground mb-2">Metode Sumber Project</label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => setSourceType('git')}
                    className={`flex items-center gap-3 p-3.5 rounded-xl border text-left transition-all ${
                      sourceType === 'git'
                        ? 'border-blue-500 bg-blue-500/10 text-blue-600 dark:text-blue-400 ring-2 ring-blue-500/20'
                        : 'border-border bg-card hover:border-gray-400 text-gray-400 hover:text-foreground'
                    }`}
                  >
                    <FolderGit2 className="w-5 h-5 shrink-0" />
                    <div>
                      <div className="font-semibold text-xs text-foreground">GitHub / Git Repository</div>
                      <div className="text-[11px] text-gray-500">Clone otomatis via branch atau webhook CI/CD</div>
                    </div>
                  </button>

                  <button
                    type="button"
                    onClick={() => setSourceType('upload')}
                    className={`flex items-center gap-3 p-3.5 rounded-xl border text-left transition-all ${
                      sourceType === 'upload'
                        ? 'border-purple-500 bg-purple-500/10 text-purple-600 dark:text-purple-400 ring-2 ring-purple-500/20'
                        : 'border-border bg-card hover:border-gray-400 text-gray-400 hover:text-foreground'
                    }`}
                  >
                    <Upload className="w-5 h-5 shrink-0" />
                    <div>
                      <div className="font-semibold text-xs text-foreground">Upload File ZIP</div>
                      <div className="text-[11px] text-gray-500">Kirim source code arsip langsung dari komputer</div>
                    </div>
                  </button>
                </div>
              </div>

              {/* Source Specific Inputs */}
              {sourceType === 'git' ? (
                <div className="space-y-3.5 p-4 rounded-xl border border-border bg-background/50">
                  <div>
                    <label className="block text-xs font-medium text-foreground mb-1">
                      Repository URL <span className="text-rose-500">*</span>
                    </label>
                    <div className="relative">
                      <FolderGit2 className="w-4 h-4 text-gray-400 absolute left-3 top-2.5" />
                      <input
                        type="url"
                        required
                        placeholder="https://github.com/username/my-project.git"
                        value={repositoryUrl}
                        onChange={(e) => handleRepoUrlChange(e.target.value)}
                        className="w-full pl-9 pr-3 py-2 rounded-lg bg-background border border-border text-foreground text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-foreground mb-1">Branch</label>
                      <div className="relative">
                        <GitBranch className="w-4 h-4 text-gray-400 absolute left-3 top-2.5" />
                        <input
                          type="text"
                          placeholder="main"
                          value={branch}
                          onChange={(e) => setBranch(e.target.value)}
                          className="w-full pl-9 pr-3 py-2 rounded-lg bg-background border border-border text-foreground text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-foreground mb-1">
                        Commit Hash <span className="text-gray-500 text-[10px]">(opsional)</span>
                      </label>
                      <input
                        type="text"
                        placeholder="HEAD (latest)"
                        value={commitHash}
                        onChange={(e) => setCommitHash(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg bg-background border border-border text-foreground text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>
                  </div>
                </div>
              ) : (
                <div className="p-4 rounded-xl border border-border bg-background/50 space-y-3">
                  <label className="block text-xs font-medium text-foreground mb-1">
                    Upload File Arsip ZIP <span className="text-rose-500">*</span>
                  </label>
                  <label
                    htmlFor={fileInputId}
                    className="border-2 border-dashed border-border hover:border-purple-500/50 rounded-xl p-6 flex flex-col items-center justify-center cursor-pointer bg-card/50 hover:bg-purple-500/5 transition-all text-center"
                  >
                    <input
                      id={fileInputId}
                      type="file"
                      accept=".zip"
                      onChange={(e) => handleZipFileChange(e.target.files?.[0] || null)}
                      className="hidden"
                    />
                    <Upload className="w-8 h-8 text-purple-500 mb-2" />
                    {zipFile ? (
                      <div className="space-y-1">
                        <span className="font-semibold text-xs text-foreground flex items-center justify-center gap-1.5">
                          <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                          {zipFile.name}
                        </span>
                        <span className="text-[11px] text-gray-400">{formatBytes(zipFile.size)}</span>
                      </div>
                    ) : (
                      <div className="space-y-1">
                        <span className="font-semibold text-xs text-foreground">Klik atau Tarik file .ZIP ke sini</span>
                        <p className="text-[11px] text-gray-500">Maksimum ukuran arsip hingga 100 MB</p>
                      </div>
                    )}
                  </label>
                </div>
              )}

              {/* General Project Settings */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-foreground mb-1">
                    Nama Project <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="my-awesome-app"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-background border border-border text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-foreground mb-1">Target Host Server</label>
                  <div className="relative">
                    <ServerIcon className="w-4 h-4 text-gray-400 absolute left-3 top-2.5" />
                    <select
                      value={serverId}
                      onChange={(e) => setServerId(e.target.value)}
                      className="w-full pl-9 pr-3 py-2 rounded-lg bg-background border border-border text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      {servers.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name} ({s.hostname}) - {s.status}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="sm:col-span-2">
                  <label className="block text-xs font-medium text-foreground mb-1">Framework / Stack Preset</label>
                  <select
                    value={framework}
                    onChange={(e) => handleFrameworkChange(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-background border border-border text-foreground text-xs"
                  >
                    <option value="Next.js">Next.js (Port 3000)</option>
                    <option value="Node.js">Node.js / Express / Nest (Port 3000 / 4000)</option>
                    <option value="FastAPI">Python FastAPI / Uvicorn (Port 8000)</option>
                    <option value="Laravel">Laravel / PHP (Port 8080 / 80)</option>
                    <option value="Flask">Python Flask (Port 5000)</option>
                    <option value="Static HTML">Static HTML / Nginx (Port 80)</option>
                    <option value="Docker Compose">Docker Compose (Stack Specification)</option>
                  </select>
                  <p className="text-[11px] text-gray-500 mt-1">
                    💡 PSM otomatis memeriksa Dockerfile. Jika belum ada di project Anda, PSM akan otomatis membuat Dockerfile optimal untuk stack {framework}!
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* STEP 2: PORT CONFIGURATION */}
          {currentStep === 2 && (
            <div className="space-y-5 animate-in fade-in duration-150">
              <div className="p-4 rounded-xl border border-blue-500/20 bg-blue-500/5 space-y-2">
                <div className="flex items-center gap-2 text-xs font-bold text-blue-500">
                  <Globe className="w-4 h-4" />
                  <span>Konfigurasi Port Docker Container</span>
                </div>
                <p className="text-xs text-gray-400">
                  Tentukan bagaimana trafik dari browser diarahkan ke aplikasi di dalam container Docker Anda.
                </p>
              </div>

              {/* Visual Traffic Flow Diagram */}
              <div className="p-4 rounded-xl border border-border bg-background flex flex-col sm:flex-row items-center justify-between gap-4 text-xs font-mono">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 rounded-lg bg-blue-600/10 text-blue-500 border border-blue-500/20">
                    <Globe className="w-4 h-4" />
                  </div>
                  <div>
                    <span className="text-gray-500 text-[10px] block">Akses Luar / Browser</span>
                    <span className="font-bold text-foreground">
                      http://{serverHost}:{hostPort || '3000'}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2 text-gray-500">
                  <span className="text-[10px]">diteruskan ke</span>
                  <ArrowRight className="w-4 h-4 text-blue-500" />
                </div>

                <div className="flex items-center gap-3">
                  <div className="p-2.5 rounded-lg bg-emerald-600/10 text-emerald-500 border border-emerald-500/20">
                    <Layers className="w-4 h-4" />
                  </div>
                  <div>
                    <span className="text-gray-500 text-[10px] block">Port Internal Container</span>
                    <span className="font-bold text-emerald-500">Port :{containerPort || '3000'}</span>
                  </div>
                </div>
              </div>

              {/* Primary Port Inputs */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-foreground mb-1">
                    Host Port (Server Port) <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="number"
                    required
                    min={1}
                    max={65535}
                    value={hostPort}
                    onChange={(e) => setHostPort(e.target.value)}
                    placeholder="3000"
                    className="w-full px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <span className="text-[10px] text-gray-500">Port yang dibuka di server Ubuntu Anda</span>
                </div>

                <div>
                  <label className="block text-xs font-medium text-foreground mb-1">
                    Container Port (Internal App) <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="number"
                    required
                    min={1}
                    max={65535}
                    value={containerPort}
                    onChange={(e) => setContainerPort(e.target.value)}
                    placeholder="3000"
                    className="w-full px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <span className="text-[10px] text-gray-500">Port aplikasi (misal Next.js=3000, Web=80)</span>
                </div>
              </div>

              {/* 1-Click Preset Buttons */}
              <div className="space-y-1.5">
                <span className="text-[11px] font-medium text-gray-400">Rekomendasi Port Populer:</span>
                <div className="flex flex-wrap gap-2 text-xs">
                  {[
                    { label: 'Next.js / Node (3000:3000)', hp: '3000', cp: '3000' },
                    { label: 'FastAPI / Python (8000:8000)', hp: '8000', cp: '8000' },
                    { label: 'Web / PHP (8080:80)', hp: '8080', cp: '80' },
                    { label: 'Express (4000:4000)', hp: '4000', cp: '4000' },
                    { label: 'Flask (5000:5000)', hp: '5000', cp: '5000' },
                    { label: 'Standard HTTP (80:80)', hp: '80', cp: '80' },
                  ].map((preset) => (
                    <button
                      key={preset.label}
                      type="button"
                      onClick={() => applyPortPreset(preset.hp, preset.cp)}
                      className={`px-2.5 py-1 rounded-lg border text-xs transition-colors ${
                        hostPort === preset.hp && containerPort === preset.cp
                          ? 'bg-blue-600 text-white border-blue-600'
                          : 'border-border hover:bg-card text-gray-400 hover:text-foreground'
                      }`}
                    >
                      {preset.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Additional Port Mappings */}
              {additionalPorts.length > 0 && (
                <div className="space-y-2 pt-2 border-t border-border">
                  <span className="text-xs font-semibold text-foreground">Port Tambahan:</span>
                  {additionalPorts.map((ap, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <input
                        type="number"
                        placeholder="Host"
                        value={ap.host}
                        onChange={(e) => {
                          const copy = [...additionalPorts];
                          copy[idx].host = e.target.value;
                          setAdditionalPorts(copy);
                        }}
                        className="w-1/2 px-3 py-1.5 rounded-lg bg-background border border-border text-foreground font-mono text-xs"
                      />
                      <span className="text-gray-500">:</span>
                      <input
                        type="number"
                        placeholder="Container"
                        value={ap.container}
                        onChange={(e) => {
                          const copy = [...additionalPorts];
                          copy[idx].container = e.target.value;
                          setAdditionalPorts(copy);
                        }}
                        className="w-1/2 px-3 py-1.5 rounded-lg bg-background border border-border text-foreground font-mono text-xs"
                      />
                      <button
                        type="button"
                        onClick={() => setAdditionalPorts((prev) => prev.filter((_, i) => i !== idx))}
                        className="p-1.5 text-rose-500 hover:bg-rose-500/10 rounded"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <button
                type="button"
                onClick={() => setAdditionalPorts((prev) => [...prev, { host: '', container: '' }])}
                className="text-xs text-blue-500 hover:text-blue-400 flex items-center gap-1 font-medium"
              >
                <Plus className="w-3.5 h-3.5" /> Tambah Port Lain
              </button>
            </div>
          )}

          {/* STEP 3: ENVIRONMENT & DATABASE */}
          {currentStep === 3 && (
            <div className="space-y-5 animate-in fade-in duration-150">
              {/* PostgreSQL Auto-Database Provision Option */}
              <div className="p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/5 space-y-3">
                <label className="flex items-center gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={autoProvisionDb}
                    onChange={(e) => setAutoProvisionDb(e.target.checked)}
                    className="rounded border-border text-emerald-600 focus:ring-emerald-500 w-4 h-4"
                  />
                  <div className="flex items-center gap-1.5 font-semibold text-foreground text-xs">
                    <Database className="w-4 h-4 text-emerald-500" />
                    <span>Auto-Create & Auto-Connect Database PostgreSQL</span>
                    <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-500 font-bold">
                      REKOMENDASI
                    </span>
                  </div>
                </label>
                {autoProvisionDb && (
                  <div className="pl-6 space-y-2 text-xs">
                    <p className="text-gray-400 text-[11px]">
                      PSM akan otomatis membuat database di server PostgreSQL dan menginjeksi kredensial lengkap (
                      <code>DATABASE_URL</code>, <code>DB_CONNECTION=pgsql</code>, <code>DB_HOST</code>, dll.) ke container Docker.
                    </p>
                    <div>
                      <label className="block text-[11px] text-gray-400 mb-1">Custom Database Name (opsional):</label>
                      <input
                        type="text"
                        placeholder={`db_${(name || 'app').toLowerCase().replace(/[^a-z0-9_]/g, '_')}`}
                        value={customDbName}
                        onChange={(e) => setCustomDbName(e.target.value)}
                        className="w-full px-3 py-1.5 rounded-lg bg-background border border-border text-foreground font-mono text-xs"
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* Environment Variables Header */}
              <div className="flex items-center justify-between border-b border-border pb-2">
                <div>
                  <h3 className="text-xs font-bold text-foreground flex items-center gap-2">
                    <Key className="w-4 h-4 text-amber-500" />
                    <span>Environment Variables (.env)</span>
                  </h3>
                  <p className="text-[11px] text-gray-500">Semua variabel dienkripsi aman (AES-Fernet) saat disimpan.</p>
                </div>

                <div className="flex items-center gap-2 text-xs">
                  <button
                    type="button"
                    onClick={() => setShowSecrets(!showSecrets)}
                    className="px-2.5 py-1 rounded border border-border text-gray-400 hover:text-foreground flex items-center gap-1"
                  >
                    {showSecrets ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                    <span>{showSecrets ? 'Hide' : 'Show'}</span>
                  </button>

                  <div className="flex rounded-lg border border-border overflow-hidden">
                    <button
                      type="button"
                      onClick={() => {
                        if (envMode === 'raw') syncRawToTable(rawEnvText);
                        setEnvMode('table');
                      }}
                      className={`px-3 py-1 text-xs font-medium transition-colors ${
                        envMode === 'table' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-foreground'
                      }`}
                    >
                      Tabel
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (envMode === 'table') syncTableToRaw(envRows);
                        setEnvMode('raw');
                      }}
                      className={`px-3 py-1 text-xs font-medium transition-colors ${
                        envMode === 'raw' ? 'bg-blue-600 text-white' : 'text-gray-400 hover:text-foreground'
                      }`}
                    >
                      Paste .env
                    </button>
                  </div>
                </div>
              </div>

              {/* Env Mode: Table */}
              {envMode === 'table' ? (
                <div className="space-y-2">
                  <div className="max-h-56 overflow-y-auto space-y-2 pr-1">
                    {envRows.map((row, idx) => (
                      <div key={idx} className="flex items-center gap-2 text-xs">
                        <input
                          type="text"
                          placeholder="VARIABLE_NAME"
                          value={row.key}
                          onChange={(e) => updateEnvRow(idx, 'key', e.target.value)}
                          className="w-2/5 px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                        <span className="text-gray-500">=</span>
                        <input
                          type={showSecrets ? 'text' : 'password'}
                          placeholder="VALUE"
                          value={row.value}
                          onChange={(e) => updateEnvRow(idx, 'value', e.target.value)}
                          className="flex-1 px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                        <button
                          type="button"
                          onClick={() => removeEnvRow(idx)}
                          className="p-2 text-gray-400 hover:text-rose-500 hover:bg-rose-500/10 rounded transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>

                  <button
                    type="button"
                    onClick={addEnvRow}
                    className="text-xs text-blue-500 hover:text-blue-400 flex items-center gap-1 font-medium pt-1"
                  >
                    <Plus className="w-3.5 h-3.5" /> Tambah Baris Variabel
                  </button>
                </div>
              ) : (
                /* Env Mode: Raw Textarea Bulk Paste */
                <div className="space-y-2">
                  <textarea
                    rows={7}
                    placeholder={`NODE_ENV=production\nAPP_KEY=base64:...\nJWT_SECRET=mysecretkey\nAPI_URL=https://api.example.com`}
                    value={rawEnvText}
                    onChange={(e) => setRawEnvText(e.target.value)}
                    className="w-full px-3 py-2.5 rounded-lg bg-background border border-border text-foreground font-mono text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <p className="text-[11px] text-gray-500">
                    Tempel (paste) seluruh isi file <code>.env</code> Anda di sini. Baris yang diawali dengan <code>#</code> akan diabaikan.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* STEP 4: REVIEW & DEPLOY */}
          {currentStep === 4 && (
            <div className="space-y-5 animate-in fade-in duration-150">
              <div className="p-4 rounded-xl border border-blue-500/20 bg-blue-500/5 space-y-1">
                <div className="flex items-center gap-2 text-xs font-bold text-blue-500">
                  <Sparkles className="w-4 h-4" />
                  <span>Ringkasan Konfigurasi Deployment</span>
                </div>
                <p className="text-xs text-gray-400">
                  Periksa kembali detail sebelum Personal Server Manager membangun dan menjalankan container Docker Anda.
                </p>
              </div>

              {/* Summary Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div className="p-3.5 rounded-xl border border-border bg-background space-y-1">
                  <span className="text-gray-400 text-[11px] block">Project & Server</span>
                  <div className="font-bold text-foreground text-sm">{name}</div>
                  <div className="text-gray-400">
                    Host: <span className="text-foreground">{selectedServer?.name}</span> ({serverHost})
                  </div>
                </div>

                <div className="p-3.5 rounded-xl border border-border bg-background space-y-1">
                  <span className="text-gray-400 text-[11px] block">Sumber Aplikasi ({sourceType.toUpperCase()})</span>
                  {sourceType === 'git' ? (
                    <div>
                      <div className="font-mono text-foreground font-semibold truncate">{repositoryUrl}</div>
                      <div className="text-gray-400 font-mono text-[11px]">Branch: {branch || 'main'}</div>
                    </div>
                  ) : (
                    <div>
                      <div className="font-semibold text-foreground truncate">{zipFile ? zipFile.name : 'Arsip ZIP'}</div>
                      <div className="text-gray-400 text-[11px]">{zipFile ? formatBytes(zipFile.size) : 'Ready'}</div>
                    </div>
                  )}
                </div>

                <div className="p-3.5 rounded-xl border border-border bg-background space-y-1">
                  <span className="text-gray-400 text-[11px] block">Port Mapping Docker</span>
                  <div className="font-bold font-mono text-blue-500 text-sm">{compilePortMappings()}</div>
                  <div className="text-gray-400 text-[11px]">
                    URL:{' '}
                    <span className="text-foreground font-mono">
                      http://{serverHost}:{hostPort}
                    </span>
                  </div>
                </div>

                <div className="p-3.5 rounded-xl border border-border bg-background space-y-1">
                  <span className="text-gray-400 text-[11px] block">Environment & Database</span>
                  <div className="font-semibold text-foreground">
                    {compileEnvVars().length} Variabel .env Dikonfigurasi
                  </div>
                  <div className="text-emerald-500 text-[11px]">
                    {autoProvisionDb ? '✓ PostgreSQL Database Terhubung Otomatis' : 'Standalone Container'}
                  </div>
                </div>
              </div>

              {/* Progress Callout when deploying */}
              {deploying && (
                <div className="p-4 rounded-xl border border-blue-500/40 bg-blue-500/10 space-y-2 animate-pulse text-xs">
                  <div className="flex items-center gap-2 font-semibold text-blue-500">
                    <Rocket className="w-4 h-4 animate-spin" />
                    <span>{deployStatusText || 'Sedang memproses deployment...'}</span>
                  </div>
                  <p className="text-[11px] text-gray-400">
                    Harap tunggu sejenak, container Docker Anda sedang disiapkan dan log build akan terbuka otomatis.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-4 border-t border-border bg-card/80 backdrop-blur-sm flex items-center justify-between">
          <div>
            {currentStep > 1 && (
              <button
                type="button"
                onClick={() => setCurrentStep((prev) => (prev - 1) as any)}
                disabled={deploying}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-border text-gray-400 hover:text-foreground hover:bg-background text-xs font-medium transition-all"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Kembali</span>
              </button>
            )}
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={deploying}
              className="px-4 py-2 rounded-xl border border-border text-gray-400 hover:text-foreground hover:bg-background text-xs font-medium transition-all"
            >
              Batal
            </button>

            {currentStep < 4 ? (
              <button
                type="button"
                onClick={() => {
                  setErrorMsg('');
                  if (currentStep === 1) {
                    if (!name.trim()) {
                      setErrorMsg('Nama project wajib diisi.');
                      return;
                    }
                    if (sourceType === 'git' && !repositoryUrl.trim()) {
                      setErrorMsg('URL repository GitHub wajib diisi.');
                      return;
                    }
                    if (sourceType === 'upload' && !zipFile && !existingProject) {
                      setErrorMsg('Silakan pilih file ZIP project Anda.');
                      return;
                    }
                  }
                  setCurrentStep((prev) => (prev + 1) as any);
                }}
                className="flex items-center gap-1.5 px-5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md shadow-blue-600/20 transition-all"
              >
                <span>Lanjut</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleDeploy}
                disabled={deploying}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-bold shadow-lg shadow-blue-600/25 transition-all disabled:opacity-50"
              >
                <Rocket className={`w-4 h-4 ${deploying ? 'animate-bounce' : ''}`} />
                <span>{deploying ? 'Deploying ke Docker...' : '🚀 Deploy Project Sekarang'}</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

