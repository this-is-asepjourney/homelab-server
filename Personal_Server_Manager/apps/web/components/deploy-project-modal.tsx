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
  Check,
  Copy,
  Layers,
  FileCode,
  ExternalLink,
  FileText,
  Sparkles,
  HelpCircle,
  AlertCircle,
  Loader2,
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

const RESERVED_SYSTEM_PORTS: Record<number, string> = {
  53: 'CoreDNS (:53)',
  80: 'Nginx Ingress Router (:80)',
  1883: 'Mosquitto MQTT (:1883)',
  3000: 'PSM Web Internal (:3000)',
  3001: 'Grafana Utama (:3001)',
  3002: 'Uptime Kuma (:3002)',
  3005: 'PSM Console Web (:3005)',
  3306: 'MySQL Server (:3306)',
  5001: 'Homelab Registry (:5001)',
  5432: 'PostgreSQL Server (:5432)',
  8000: 'PAP Core Central API Gateway (:8000)',
  8001: 'PAP Core Web UI (:8001)',
  8080: 'Vaultwarden Password Manager (:8080)',
  8081: 'Apache Web Server (:8081)',
  8086: 'InfluxDB TSDB (:8086)',
  8088: 'HeatpressHub Web (:8088)',
  9001: 'Prometheus Server (:9001)',
  9090: 'Cockpit Admin Console (:9090)',
};

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

  // Step 2: Ports & Local DNS
  const [hostPort, setHostPort] = useState('3100');
  const [containerPort, setContainerPort] = useState('3000');
  const [recommendedPort, setRecommendedPort] = useState(3100);
  const [reservedPorts, setReservedPorts] = useState<Record<number, string>>(RESERVED_SYSTEM_PORTS);
  const [additionalPorts, setAdditionalPorts] = useState<Array<{ host: string; container: string }>>([]);
  const [domain, setDomain] = useState(existingProject?.domain || '');

  // Step 3: Environment & Flexible DB
  const [dbType, setDbType] = useState<'postgres' | 'mysql' | 'sqlite' | 'none'>(existingProject?.db_type || 'postgres');
  const [userHasCustomizedDb, setUserHasCustomizedDb] = useState(false);
  const [envMode, setEnvMode] = useState<'table' | 'raw'>('table');
  const [envRows, setEnvRows] = useState<Array<{ key: string; value: string; isSecret?: boolean }>>([
    { key: 'NODE_ENV', value: 'production', isSecret: false },
  ]);
  const [rawEnvText, setRawEnvText] = useState('');
  const [autoProvisionDb, setAutoProvisionDb] = useState(existingProject?.db_type ? existingProject.db_type !== 'none' : true);
  const [customDbName, setCustomDbName] = useState(existingProject?.db_name || '');
  const [showSecrets, setShowSecrets] = useState(false);

  // Submission
  const [deploying, setDeploying] = useState(false);
  const [deployStatusText, setDeployStatusText] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  // Dockerfile Setup Assistant state
  const [showDockerfilePreview, setShowDockerfilePreview] = useState(false);
  const [previewDockerfile, setPreviewDockerfile] = useState('');
  const [previewDockerignore, setPreviewDockerignore] = useState('');
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [copiedPreview, setCopiedPreview] = useState(false);
  const [previewSubTab, setPreviewSubTab] = useState<'dockerfile' | 'dockerignore'>('dockerfile');

  const handleOpenDockerfilePreview = async () => {
    try {
      setLoadingPreview(true);
      setShowDockerfilePreview(true);
      const res = await api.generateDockerfilePreview({
        framework,
        port: parseInt(containerPort, 10) || 3000,
        project_name: name || 'my-app',
      });
      if (res && res.dockerfile) {
        setPreviewDockerfile(res.dockerfile);
        setPreviewDockerignore(res.dockerignore || '');
      }
    } catch (e: any) {
      setPreviewDockerfile(`# Error: ${e.message}`);
    } finally {
      setLoadingPreview(false);
    }
  };

  // Auto-discover next available free port on target server
  useEffect(() => {
    let mounted = true;
    api.getNextAvailablePort().then((res) => {
      if (mounted && res && res.recommended_host_port) {
        setRecommendedPort(res.recommended_host_port);
        if (res.reserved_ports) {
          setReservedPorts({ ...RESERVED_SYSTEM_PORTS, ...res.reserved_ports });
        }
        if (!existingProject && (hostPort === '3000' || hostPort === '3100')) {
          setHostPort(String(res.recommended_host_port));
        }
      }
    });
    return () => {
      mounted = false;
    };
  }, []);

  // Initialize from existing project if supplied
  useEffect(() => {
    if (existingProject) {
      setName(existingProject.name || '');
      setServerId(existingProject.server_id || servers[0]?.id || '');
      setFramework(existingProject.framework || 'Next.js');
      setSourceType(existingProject.source_type || 'git');
      setRepositoryUrl(existingProject.repository_url || '');
      setBranch(existingProject.branch || 'main');
      if (existingProject.domain) setDomain(existingProject.domain);
      if (existingProject.db_type) {
        setDbType(existingProject.db_type);
        setAutoProvisionDb(existingProject.db_type !== 'none');
      }
      if (existingProject.db_name) setCustomDbName(existingProject.db_name);

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
  // Realtime port conflict detection
  const currentHpNum = parseInt(hostPort.trim(), 10);
  const rawPortConflict = !isNaN(currentHpNum) ? reservedPorts[currentHpNum] : null;
  // If editing an existing project, using its own active port is completely valid and NOT a conflict!
  const isSelfProjectPort = Boolean(
    existingProject &&
    rawPortConflict &&
    (
      rawPortConflict.toLowerCase().includes((existingProject.name || '').toLowerCase()) ||
      (existingProject.port_mappings && existingProject.port_mappings.includes(String(currentHpNum)))
    )
  );
  const portConflictReason = isSelfProjectPort ? null : rawPortConflict;
  const serverHost = selectedServer?.hostname || 'localhost';

  // Quick port presets
  const applyPortPreset = (hp: string, cp: string) => {
    setHostPort(hp);
    setContainerPort(cp);
  };

  // Change framework presets with non-conflicting host port
  const handleFrameworkChange = (fw: string) => {
    setFramework(fw);
    const safeHp = String(recommendedPort || '3100');
    if (fw === 'Next.js' || fw === 'Node.js' || fw === 'React / Vite') {
      applyPortPreset(safeHp, '3000');
    } else if (fw === 'FastAPI' || fw === 'Django / Python') {
      applyPortPreset(safeHp, '8000');
      if (!userHasCustomizedDb && !existingProject) setDbType('postgres');
    } else if (fw === 'Laravel' || fw === 'PHP') {
      applyPortPreset(safeHp, '8080');
      if (!userHasCustomizedDb && !existingProject) setDbType('mysql');
    } else if (fw === 'Flask') {
      applyPortPreset(safeHp, '5000');
    } else if (fw === 'Static HTML') {
      applyPortPreset(safeHp, '80');
      if (!userHasCustomizedDb && !existingProject) setDbType('none');
    }
  };

  // Auto-name detection from Git URL or ZIP
  const handleNameInput = (val: string) => {
    setName(val);
    if (!existingProject && (!domain || domain.endsWith('.homelab') || domain.endsWith('.fa.local'))) {
      const slug = val.toLowerCase().replace(/[^a-z0-9_-]/g, '-').replace(/^-+|-+$/g, '');
      setDomain(slug ? `${slug}.homelab` : '');
    }
  };

  const handleRepoUrlChange = (url: string) => {
    let cleanUrl = url.trim();
    if (cleanUrl.includes('/tree/')) {
      const parts = cleanUrl.split('/tree/');
      cleanUrl = parts[0].replace(/\/+$/, '');
      const extractedBranch = parts[1]?.replace(/^\/+|\/+$/g, '').split('/')[0];
      if (extractedBranch) {
        setBranch(extractedBranch);
      }
    }
    setRepositoryUrl(cleanUrl);
    if (!name || name === 'my-app') {
      try {
        const clean = cleanUrl.replace(/\.git$/, '');
        const segs = clean.split('/');
        const last = segs[segs.length - 1];
        if (last) {
          const cleanName = last.toLowerCase().replace(/[^a-z0-9_-]/g, '-');
          setName(cleanName);
          if (!domain) setDomain(`${cleanName}.homelab`);
        }
      } catch (_) {}
    }
  };

  const handleZipFileChange = (file: File | null) => {
    setZipFile(file);
    if (file && (!name || name === 'my-app')) {
      const base = file.name.replace(/\.zip$/i, '');
      const cleanName = base.toLowerCase().replace(/[^a-z0-9_-]/g, '-');
      setName(cleanName);
      if (!domain) setDomain(`${cleanName}.homelab`);
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
    if (portConflictReason) {
      setErrorMsg(`Port host ${hostPort} bentrok dengan ${portConflictReason}. Silakan ganti port atau klik 'Gunakan Port Aman :${recommendedPort}'.`);
      setCurrentStep(2);
      return;
    }

    try {
      setDeploying(true);
      const portString = compilePortMappings();
      const envVariables = compileEnvVars();

      // If existing project: update project configuration & trigger redeployment
      if (existingProject) {
        setDeployStatusText('Menyimpan perubahan konfigurasi & menyiapkan rilis baru...');
        try {
          await api.updateProject(existingProject.id, {
            name: name.trim() || undefined,
            framework,
            repository_url: sourceType === 'git' ? (repositoryUrl.trim() || undefined) : undefined,
            branch: sourceType === 'git' ? (branch || 'main') : undefined,
            domain: domain.trim() || undefined,
            db_type: dbType,
            port_mappings: portString,
            db_name: customDbName.trim() || undefined,
          });
        } catch (_) {}

        if (envVariables && envVariables.length > 0) {
          try {
            await api.updateProjectEnvironment(existingProject.id, envVariables);
          } catch (_) {}
        }

        setDeployStatusText('Meluncurkan container release baru di server...');
        if (sourceType === 'upload' && zipFile) {
          const dep = await api.uploadZipDeployment(existingProject.id, zipFile, portString, envVariables, dbType);
          onClose();
          if (onSuccess) onSuccess(dep);
          router.push(`/deployments/${dep.id}`);
        } else if (sourceType === 'upload' && !zipFile) {
          const dep = await api.redeployProject(existingProject.id);
          onClose();
          if (onSuccess) onSuccess(dep);
          router.push(`/deployments/${dep.id}`);
        } else {
          const dep = await api.triggerGitDeployment(existingProject.id, branch || 'main', portString, envVariables, dbType);
          onClose();
          if (onSuccess) onSuccess(dep);
          router.push(`/deployments/${dep.id}`);
        }
        return;
      }

      // Creating a new project flow
      setDeployStatusText('Creating project record, local DNS route & Docker configuration...');
      const cleanSlug = name.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '-').replace(/^-+|-+$/g, '');
      const finalDomain = domain.trim() || (cleanSlug ? `${cleanSlug}.homelab` : 'app.homelab');

      const created = await api.createProject({
        server_id: serverId,
        name: name.trim(),
        framework,
        source_type: sourceType,
        repository_url: sourceType === 'git' ? repositoryUrl.trim() : null,
        branch: sourceType === 'git' ? branch || 'main' : null,
        port_mappings: portString,
        domain: finalDomain,
        db_type: dbType,
        auto_provision_db: dbType !== 'none' && autoProvisionDb,
        database_name: customDbName.trim() || null,
        environment_variables: envVariables,
        auto_deploy: sourceType === 'git',
      });

      if (sourceType === 'upload' && zipFile) {
        setDeployStatusText('Uploading ZIP archive & initiating Docker build...');
        const dep = await api.uploadZipDeployment(created.id, zipFile, portString, envVariables, dbType);
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
                <span>{existingProject ? `Edit & Deploy Ulang • ${name || existingProject.name}` : 'Deploy Project ke Docker'}</span>
                <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-500/10 text-blue-500 border border-blue-500/20 uppercase tracking-wide">
                  {existingProject ? 'Redeploy Mode' : 'Fast Docker Pipeline'}
                </span>
              </h2>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {existingProject
                  ? 'Sesuaikan konfigurasi repositori, port, database engine, atau environment variables lalu luncurkan rilis baru.'
                  : 'Langkah mudah deploy container via Git atau ZIP dengan port mapping & environment variables.'}
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

          {deploying ? (
            <div className="py-8 px-4 flex flex-col items-center justify-center text-center space-y-6 animate-in fade-in duration-200">
              <div className="relative">
                <div className="w-20 h-20 rounded-3xl bg-gradient-to-tr from-blue-600/20 to-indigo-600/20 border border-blue-500/30 flex items-center justify-center shadow-xl shadow-blue-500/10">
                  <Rocket className="w-10 h-10 animate-bounce text-blue-500" />
                </div>
                <div className="absolute -bottom-1 -right-1 p-1.5 bg-card rounded-full border border-border shadow-md">
                  <Loader2 className="w-4 h-4 text-indigo-500 animate-spin" />
                </div>
              </div>

              <div className="space-y-1.5 max-w-md">
                <h3 className="text-base font-bold text-foreground">
                  Menginisialisasi Deployment ke Docker
                </h3>
                <p className="text-xs text-gray-400">
                  {deployStatusText || 'Sedang menyiapkan container & pipeline build...'}
                </p>
              </div>

              {/* Informative Step Tracker */}
              <div className="w-full max-w-md bg-background/80 border border-border rounded-2xl p-4 text-xs space-y-3 text-left shadow-inner">
                <div className="flex items-center justify-between text-[11px] font-mono">
                  <span className="text-gray-400">Proses Pipeline Inisiasi</span>
                  <span className="text-blue-500 font-bold flex items-center gap-1">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Sedang Berjalan
                  </span>
                </div>

                <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                  <div className="h-full bg-gradient-to-r from-blue-500 via-indigo-500 to-cyan-400 rounded-full animate-pulse w-4/5" />
                </div>

                <div className="space-y-2 pt-1 text-[11px]">
                  <div className="flex items-center gap-2 text-emerald-500">
                    <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                    <span>Verifikasi port host :{hostPort} & port container :{containerPort} (Lolos)</span>
                  </div>
                  <div className="flex items-center gap-2 text-emerald-500">
                    <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                    <span>Konfigurasi environment & database auto-wiring (Tersiap)</span>
                  </div>
                  <div className="flex items-center gap-2 text-blue-400 font-medium">
                    <Loader2 className="w-3.5 h-3.5 shrink-0 animate-spin text-blue-500" />
                    <span>{deployStatusText || 'Mendaftarkan job ke worker agent Docker...'}</span>
                  </div>
                  <div className="flex items-center gap-2 text-gray-500">
                    <div className="w-3.5 h-3.5 rounded-full border border-gray-600 flex items-center justify-center text-[9px] text-gray-400">4</div>
                    <span>Streaming log langsung pada layar deployment console</span>
                  </div>
                </div>
              </div>

              <div className="text-[11px] text-gray-500 flex items-center gap-1.5 font-mono">
                <Sparkles className="w-3.5 h-3.5 text-blue-400" />
                <span>Otomatis berpindah ke live terminal stream begitu container mulai di-build...</span>
              </div>
            </div>
          ) : (
            <>
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
                    onChange={(e) => handleNameInput(e.target.value)}
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
                  <div className="flex items-center justify-between mb-1">
                    <label className="block text-xs font-medium text-foreground">Framework / Stack Preset</label>
                    <button
                      type="button"
                      onClick={handleOpenDockerfilePreview}
                      className="text-xs text-indigo-400 hover:text-indigo-300 font-medium flex items-center gap-1 transition-colors"
                    >
                      <Eye className="w-3.5 h-3.5" />
                      <span>Preview Dockerfile ({framework})</span>
                    </button>
                  </div>
                  <select
                    value={framework}
                    onChange={(e) => handleFrameworkChange(e.target.value)}
                    className="w-full px-3 py-2 rounded-lg bg-background border border-border text-foreground text-xs"
                  >
                    <option value="Next.js">Next.js (Port 3000 — Multi-stage Standalone)</option>
                    <option value="React / Vite">React / Vite / Vue (Port 80 — SPA Nginx Alpine)</option>
                    <option value="Node.js">Node.js / Express / NestJS (Port 3000)</option>
                    <option value="FastAPI">Python FastAPI / Uvicorn (Port 8000)</option>
                    <option value="Django / Python">Python Django / Gunicorn (Port 8000)</option>
                    <option value="Laravel">Laravel / PHP (Port 8080)</option>
                    <option value="Flask">Python Flask (Port 5000)</option>
                    <option value="Go">Go / Golang (Port 8080 — Ultra-light Alpine)</option>
                    <option value="Static HTML">Static HTML / Nginx (Port 80)</option>
                    <option value="Docker Compose">Docker Compose (Stack Specification)</option>
                  </select>
                  <div className="mt-2.5 p-3 rounded-lg border border-indigo-500/20 bg-indigo-500/5 flex items-center justify-between gap-3 text-[11px]">
                    <div className="flex items-center gap-2 text-gray-300">
                      <FileCode className="w-4 h-4 text-indigo-400 shrink-0" />
                      <span>
                        PSM otomatis menambahkan Dockerfile multi-stage production & .dockerignore untuk <strong>{framework}</strong>.
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={handleOpenDockerfilePreview}
                      className="px-2.5 py-1 rounded bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/30 font-medium whitespace-nowrap transition-colors flex items-center gap-1"
                    >
                      <Eye className="w-3 h-3" />
                      <span>Lihat Dockerfile</span>
                    </button>
                  </div>
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

              {/* Primary Port Inputs & Auto-Allocator */}
              <div className="space-y-2">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-xs font-medium text-foreground">
                        Host Port (Port Server) <span className="text-rose-500">*</span>
                      </label>
                      <button
                        type="button"
                        onClick={() => setHostPort(String(recommendedPort))}
                        className="text-[10px] text-blue-400 hover:text-blue-300 font-semibold flex items-center gap-1"
                        title="Pilih port yang dijamin bebas"
                      >
                        <Sparkles className="w-3 h-3" /> Auto-Bebas :{recommendedPort}
                      </button>
                    </div>
                    <input
                      type="number"
                      required
                      min={1}
                      max={65535}
                      value={hostPort}
                      onChange={(e) => setHostPort(e.target.value)}
                      placeholder={String(recommendedPort)}
                      className={`w-full px-3 py-2 rounded-lg bg-background border text-foreground font-mono text-sm focus:outline-none focus:ring-2 ${
                        portConflictReason
                          ? 'border-rose-500/80 focus:ring-rose-500'
                          : 'border-border focus:ring-blue-500'
                      }`}
                    />
                    <span className="text-[10px] text-gray-500">Port yang dibuka di server Ubuntu Anda</span>
                    {isSelfProjectPort && (
                      <div className="text-[11px] text-emerald-400 flex items-center gap-1 mt-1 font-medium">
                        <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                        <span>Port {hostPort} adalah port aktif milik project ini (aman digunakan).</span>
                      </div>
                    )}
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

                {/* Conflict Alert Box */}
                {portConflictReason && (
                  <div className="p-3 rounded-xl border border-rose-500/40 bg-rose-500/10 text-rose-300 text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-2 animate-in fade-in">
                    <div className="flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
                      <span>
                        Port Host <b>{hostPort}</b> sudah dipakai oleh <b>{portConflictReason}</b>!
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setHostPort(String(recommendedPort))}
                      className="px-2.5 py-1 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs shrink-0 flex items-center gap-1 shadow-sm self-start sm:self-auto"
                    >
                      <Sparkles className="w-3.5 h-3.5" /> Gunakan Port Aman :{recommendedPort}
                    </button>
                  </div>
                )}
              </div>

              {/* Local DNS & Virtual Host Configuration */}
              <div className="p-4 rounded-xl border border-indigo-500/30 bg-indigo-500/5 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs font-bold text-indigo-400">
                    <Globe className="w-4 h-4" />
                    <span>🌐 Local DNS & Virtual Host Routing (Port 80)</span>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] bg-indigo-500/10 text-indigo-400 font-semibold border border-indigo-500/20">
                    CoreDNS + Ingress Router
                  </span>
                </div>
                <p className="text-xs text-gray-400">
                  Aplikasi otomatis di-routing tanpa perlu memasukkan port di browser. Siap diakses via LAN & Tailscale.
                </p>
                <div>
                  <label className="block text-xs font-medium text-foreground mb-1">
                    Domain Lokal Aplikasi:
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      placeholder="nama-project.homelab"
                      value={domain}
                      onChange={(e) => setDomain(e.target.value)}
                      className="flex-1 px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                    <div className="flex gap-1 shrink-0">
                      <button
                        type="button"
                        onClick={() => {
                          const slug = (name || 'app').toLowerCase().replace(/[^a-z0-9_-]/g, '-').replace(/^-+|-+$/g, '');
                          setDomain(`${slug || 'app'}.homelab`);
                        }}
                        className="px-2 py-1.5 rounded text-[11px] border border-border bg-card hover:bg-background text-gray-400 hover:text-foreground font-mono"
                      >
                        .homelab
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          const slug = (name || 'app').toLowerCase().replace(/[^a-z0-9_-]/g, '-').replace(/^-+|-+$/g, '');
                          setDomain(`${slug || 'app'}.fa.local`);
                        }}
                        className="px-2 py-1.5 rounded text-[11px] border border-border bg-card hover:bg-background text-gray-400 hover:text-foreground font-mono"
                      >
                        .fa.local
                      </button>
                    </div>
                  </div>
                  <span className="text-[10px] text-gray-500 mt-1 block">
                    URL Akses Browser: <span className="text-indigo-400 font-mono">http://{domain || `${name || 'app'}.homelab`}</span>
                  </span>
                </div>
              </div>

              {/* 1-Click Preset Buttons (Safe Non-Colliding Presets) */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-medium text-gray-400">Rekomendasi Port Bebas Konflik:</span>
                  <span className="text-[10px] text-emerald-400 font-semibold">✨ Host Port Aman Otomatis</span>
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  {[
                    { label: `Next.js / Node (:${recommendedPort} -> :3000)`, hp: String(recommendedPort), cp: '3000' },
                    { label: `FastAPI / Python (:${recommendedPort} -> :8000)`, hp: String(recommendedPort), cp: '8000' },
                    { label: `PHP / Laravel (:${recommendedPort} -> :80)`, hp: String(recommendedPort), cp: '80' },
                    { label: `Express (:${recommendedPort} -> :4000)`, hp: String(recommendedPort), cp: '4000' },
                    { label: `Python Flask (:${recommendedPort} -> :5000)`, hp: String(recommendedPort), cp: '5000' },
                    { label: `Vite / React (:${recommendedPort} -> :80)`, hp: String(recommendedPort), cp: '80' },
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
              {/* Flexible Multi-Database Provision Option */}
              <div className="p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/5 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs font-bold text-emerald-500">
                    <Database className="w-4 h-4" />
                    <span>Flexible Database Engine (Multi-DB)</span>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-500 font-bold border border-emerald-500/20">
                    Auto-Provisioning
                  </span>
                </div>
                <p className="text-xs text-gray-400">
                  Pilih database untuk project Anda. PSM otomatis membuatkan schema/database baru dan menginjeksi variabel kredensial.
                </p>

                {/* DB Engine Radio Cards */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                  {[
                    { id: 'postgres', label: 'PostgreSQL', desc: 'Port 5432 (Shared Host)', badge: 'Default' },
                    { id: 'mysql', label: 'MySQL', desc: 'Port 3306 (Shared Host)', badge: 'Fleksibel' },
                    { id: 'sqlite', label: 'SQLite', desc: 'Embedded (/data/sqlite)', badge: 'Ringan' },
                    { id: 'none', label: 'Stateless', desc: 'Tanpa Database Server', badge: 'Worker/UI' },
                  ].map((engine) => (
                    <button
                      key={engine.id}
                      type="button"
                      onClick={() => {
                        setDbType(engine.id as any);
                        setUserHasCustomizedDb(true);
                        setAutoProvisionDb(engine.id !== 'none');
                      }}
                      className={`p-3 rounded-xl border text-left flex flex-col justify-between transition-all ${
                        dbType === engine.id
                          ? 'border-emerald-500 bg-emerald-500/10 text-foreground ring-1 ring-emerald-500'
                          : 'border-border bg-card/60 hover:bg-card text-gray-400 hover:text-foreground'
                      }`}
                    >
                      <div className="flex items-center justify-between w-full mb-1">
                        <span className="font-bold text-xs text-foreground">{engine.label}</span>
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-background/80 text-emerald-400 border border-emerald-500/20 font-mono">
                          {engine.badge}
                        </span>
                      </div>
                      <span className="text-[10px] text-gray-500">{engine.desc}</span>
                    </button>
                  ))}
                </div>

                {/* DB Details (for PostgreSQL & MySQL) */}
                {(dbType === 'postgres' || dbType === 'mysql') && (
                  <div className="pl-2 space-y-2 text-xs pt-2 border-t border-border/50">
                    <div className="flex items-center justify-between">
                      <label className="text-[11px] text-gray-400 font-medium">
                        Custom Database Name (opsional):
                      </label>
                      <span className="text-[10px] text-emerald-400 font-mono">
                        {dbType === 'postgres' ? 'Auto: DATABASE_URL & DB_CONNECTION=pgsql' : 'Auto: MYSQL_URL, DB_HOST & DB_PASSWORD'}
                      </span>
                    </div>
                    <input
                      type="text"
                      placeholder={`db_${(name || 'app').toLowerCase().replace(/[^a-z0-9_]/g, '_')}`}
                      value={customDbName}
                      onChange={(e) => setCustomDbName(e.target.value)}
                      className="w-full px-3 py-1.5 rounded-lg bg-background border border-border text-foreground font-mono text-xs focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    />
                  </div>
                )}

                {dbType === 'sqlite' && (
                  <div className="text-[11px] text-gray-400 bg-background/50 p-2.5 rounded-lg border border-border">
                    📁 Database SQLite akan otomatis disimpan di <code>/data/sqlite/{name || 'app'}.db</code> dan diinjeksikan sebagai <code>DATABASE_URL=sqlite:////data/sqlite/...</code>.
                  </div>
                )}

                {dbType === 'none' && (
                  <div className="text-[11px] text-gray-400 bg-background/50 p-2.5 rounded-lg border border-border">
                    ⚡ Project stateless tanpa provisioning database. Container akan dijalankan murni dengan environment variables di bawah.
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
                  <span className="text-gray-400 text-[11px] block">Local DNS & Database</span>
                  <div className="font-semibold text-foreground flex items-center gap-1.5">
                    <span className="text-indigo-400 font-mono text-[11px]">http://{domain || `${name || 'app'}.homelab`}</span>
                  </div>
                  <div className="text-emerald-500 text-[11px]">
                    {dbType !== 'none' ? `✓ Database ${dbType.toUpperCase()} Terhubung Otomatis` : 'Standalone Stateless Container'}
                  </div>
                </div>

                <div className="p-3.5 rounded-xl border border-indigo-500/20 bg-indigo-500/5 sm:col-span-2 flex items-center justify-between text-xs">
                  <div>
                    <span className="text-indigo-400 text-[11px] font-semibold flex items-center gap-1.5">
                      <FileCode className="w-3.5 h-3.5" />
                      <span>Docker Build Strategy (PaaS Standard)</span>
                    </span>
                    <div className="text-gray-300 text-xs mt-0.5">
                      Otomatis multi-stage build, non-root user ({framework}), dan proteksi context <code>.dockerignore</code>.
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={handleOpenDockerfilePreview}
                    className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors flex items-center gap-1.5 shrink-0"
                  >
                    <Eye className="w-3.5 h-3.5" />
                    <span>Lihat Dockerfile</span>
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
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
                <span>
                  {deploying
                    ? (deployStatusText || 'Memproses deployment...')
                    : existingProject
                    ? '🚀 Simpan & Deploy Ulang ke Server'
                    : '🚀 Deploy Project Sekarang'}
                </span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Dockerfile Preview Modal */}
      {showDockerfilePreview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-card border border-border rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between p-4 border-b border-border bg-background">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                  <FileCode className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="font-bold text-sm text-foreground">Dockerfile Setup Assistant</h4>
                  <p className="text-[11px] text-gray-500">Preview Dockerfile multi-stage production untuk stack {framework}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowDockerfilePreview(false)}
                className="p-1.5 rounded-lg text-gray-400 hover:text-foreground hover:bg-card transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-4 flex-1 overflow-y-auto space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setPreviewSubTab('dockerfile')}
                    className={`px-3 py-1 rounded-lg text-xs font-mono font-medium ${
                      previewSubTab === 'dockerfile'
                        ? 'bg-indigo-600/15 text-indigo-400 border border-indigo-500/30'
                        : 'text-gray-400 hover:text-foreground'
                    }`}
                  >
                    Dockerfile
                  </button>
                  <button
                    type="button"
                    onClick={() => setPreviewSubTab('dockerignore')}
                    className={`px-3 py-1 rounded-lg text-xs font-mono font-medium ${
                      previewSubTab === 'dockerignore'
                        ? 'bg-indigo-600/15 text-indigo-400 border border-indigo-500/30'
                        : 'text-gray-400 hover:text-foreground'
                    }`}
                  >
                    .dockerignore
                  </button>
                </div>

                <button
                  type="button"
                  onClick={() => {
                    const text = previewSubTab === 'dockerfile' ? previewDockerfile : previewDockerignore;
                    navigator.clipboard.writeText(text);
                    setCopiedPreview(true);
                    setTimeout(() => setCopiedPreview(false), 2000);
                  }}
                  className="px-2.5 py-1 rounded-md border border-border text-xs text-gray-300 hover:text-foreground hover:bg-background flex items-center gap-1 transition-colors"
                >
                  {copiedPreview ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copiedPreview ? 'Tersalin' : 'Salin Kode'}</span>
                </button>
              </div>

              <div className="relative rounded-xl border border-border bg-[#0d1117] p-3.5 overflow-x-auto text-xs font-mono text-gray-300 max-h-[380px]">
                {loadingPreview ? (
                  <div className="py-12 text-center text-gray-500">Memuat konfigurasi Dockerfile...</div>
                ) : (
                  <pre className="leading-relaxed whitespace-pre font-mono">
                    {previewSubTab === 'dockerfile' ? previewDockerfile : previewDockerignore}
                  </pre>
                )}
              </div>
            </div>

            <div className="p-3 border-t border-border bg-background flex justify-end">
              <button
                type="button"
                onClick={() => setShowDockerfilePreview(false)}
                className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold"
              >
                Tutup Preview
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

