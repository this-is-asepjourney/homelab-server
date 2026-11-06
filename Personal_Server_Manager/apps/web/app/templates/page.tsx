'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
  Boxes,
  ShieldCheck,
  ShieldAlert,
  Network,
  Cloud,
  Database,
  Activity,
  Box,
  Rocket,
  Search,
  Filter,
  CheckCircle,
  ExternalLink,
  X,
  Server as ServerIcon,
  Layers,
  Sparkles,
} from 'lucide-react';
import { api } from '../../lib/api';

const ICON_MAP: Record<string, React.ElementType> = {
  ShieldCheck,
  ShieldAlert,
  Network,
  Cloud,
  Database,
  Activity,
  Box,
};

export default function TemplatesPage() {
  const router = useRouter();
  const [templates, setTemplates] = useState<any[]>([]);
  const [servers, setServers] = useState<any[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>('All');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  // Deploy Modal State
  const [deployModal, setDeployModal] = useState<{
    open: boolean;
    template: any | null;
    projectName: string;
    targetServerId: string;
    port: string;
    envVars: Record<string, string>;
  }>({
    open: false,
    template: null,
    projectName: '',
    targetServerId: '',
    port: '',
    envVars: {},
  });

  const [deploying, setDeploying] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const [tmpls, srvs] = await Promise.all([
          api.getTemplates(),
          api.getServers(),
        ]);
        setTemplates(tmpls);
        setServers(srvs);
      } catch (err) {
        console.error('Failed to load templates or servers', err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const categories = ['All', 'Security', 'Networking', 'Database', 'Monitoring', 'Management'];

  const filtered = templates.filter((t) => {
    const matchesCategory = selectedCategory === 'All' || t.category === selectedCategory;
    const matchesSearch =
      t.name.toLowerCase().includes(search.toLowerCase()) ||
      t.description.toLowerCase().includes(search.toLowerCase());
    return matchesCategory && matchesSearch;
  });

  const handleOpenDeploy = (template: any) => {
    const defaultServer = servers.length > 0 ? servers[0].id : '';
    setDeployModal({
      open: true,
      template,
      projectName: template.id,
      targetServerId: defaultServer,
      port: template.default_port > 0 ? String(template.default_port) : '',
      envVars: { ...(template.environment_variables || {}) },
    });
  };

  const handleConfirmDeploy = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!deployModal.template || !deployModal.targetServerId) {
      alert('Please select a target server.');
      return;
    }

    try {
      setDeploying(true);
      const res = await api.deployTemplate({
        server_id: deployModal.targetServerId,
        template_id: deployModal.template.id,
        project_name: deployModal.projectName,
        port: deployModal.port ? parseInt(deployModal.port, 10) : undefined,
        environment_variables: deployModal.envVars,
      });

      setDeployModal({ ...deployModal, open: false });
      router.push(`/projects/${res.project_id}`);
    } catch (err: any) {
      alert(err.message || 'Deployment dispatch failed');
    } finally {
      setDeploying(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight text-foreground">Homelab App Store</h1>
            <span className="px-2.5 py-0.5 rounded-full bg-blue-500/10 text-blue-500 text-xs font-semibold flex items-center gap-1 border border-blue-500/20">
              <Sparkles className="w-3 h-3" /> 1-Click Stacks
            </span>
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Production-ready self-hosted apps and container stacks preconfigured for homelab servers.
          </p>
        </div>

        {/* Search */}
        <div className="relative w-full sm:w-72">
          <Search className="w-4 h-4 text-gray-400 absolute left-3 top-3" />
          <input
            type="text"
            placeholder="Search applications..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-lg bg-card border border-border text-foreground text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {/* Category Tabs */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 border-b border-border text-xs">
        {categories.map((cat) => (
          <button
            key={cat}
            onClick={() => setSelectedCategory(cat)}
            className={`px-3.5 py-1.5 rounded-lg font-medium whitespace-nowrap transition-colors ${
              selectedCategory === cat
                ? 'bg-blue-600 text-white font-semibold'
                : 'text-gray-400 hover:text-foreground hover:bg-card'
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Templates Grid */}
      {loading ? (
        <div className="p-12 text-center text-gray-500 text-sm">Loading curated homelab stacks...</div>
      ) : filtered.length === 0 ? (
        <div className="p-12 text-center text-gray-500 text-sm">No applications found matching your criteria.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {filtered.map((tmpl) => {
            const Icon = ICON_MAP[tmpl.icon] || Boxes;
            return (
              <div
                key={tmpl.id}
                className="group p-5 rounded-xl border border-border bg-card shadow-sm hover:border-blue-500/40 hover:shadow-md transition-all flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="p-2.5 rounded-lg bg-blue-500/10 text-blue-500 border border-blue-500/20 group-hover:bg-blue-500 group-hover:text-white transition-colors">
                      <Icon className="w-5 h-5" />
                    </div>
                    {tmpl.badge && (
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-gray-500/10 text-gray-400 border border-border uppercase tracking-wider">
                        {tmpl.badge}
                      </span>
                    )}
                  </div>

                  <h3 className="font-bold text-sm text-foreground mb-1 group-hover:text-blue-500 transition-colors">
                    {tmpl.name}
                  </h3>
                  <span className="text-[11px] font-mono text-gray-400 block mb-2">{tmpl.category}</span>
                  <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-3 leading-relaxed mb-4">
                    {tmpl.description}
                  </p>
                </div>

                <div className="pt-3 border-t border-border flex items-center justify-between text-xs">
                  <span className="font-mono text-gray-400 text-[11px]">
                    {tmpl.default_port > 0 ? `Port :${tmpl.default_port}` : 'Tunnel'}
                  </span>
                  <button
                    onClick={() => handleOpenDeploy(tmpl)}
                    className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium text-xs shadow-sm transition-all"
                  >
                    <Rocket className="w-3.5 h-3.5" />
                    <span>1-Click Deploy</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Deploy Modal */}
      {deployModal.open && deployModal.template && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <form
            onSubmit={handleConfirmDeploy}
            className="w-full max-w-lg rounded-xl border border-border bg-card shadow-2xl overflow-hidden text-xs"
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-border bg-background/50">
              <div className="flex items-center gap-2">
                <Rocket className="w-4 h-4 text-blue-500" />
                <h3 className="font-bold text-sm text-foreground">
                  Deploy {deployModal.template.name}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setDeployModal({ ...deployModal, open: false })}
                className="text-gray-400 hover:text-foreground"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-4 max-h-[75vh] overflow-y-auto">
              <div>
                <label className="block text-gray-400 font-medium mb-1">Target Homelab Node</label>
                <select
                  required
                  value={deployModal.targetServerId}
                  onChange={(e) => setDeployModal({ ...deployModal, targetServerId: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-background border border-border text-foreground"
                >
                  {servers.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.hostname || s.id}) - {s.status}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-gray-400 font-medium mb-1">Project & Stack Name</label>
                <input
                  type="text"
                  required
                  value={deployModal.projectName}
                  onChange={(e) => setDeployModal({ ...deployModal, projectName: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono"
                />
              </div>

              {deployModal.template.default_port > 0 && (
                <div>
                  <label className="block text-gray-400 font-medium mb-1">Host Exposed Port</label>
                  <input
                    type="number"
                    value={deployModal.port}
                    onChange={(e) => setDeployModal({ ...deployModal, port: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-background border border-border text-foreground font-mono"
                    placeholder="e.g. 8080"
                  />
                  <p className="text-[11px] text-gray-500 mt-1">
                    Port to access this application from your LAN / Tailscale network.
                  </p>
                </div>
              )}

              {/* Environment Variables */}
              {Object.keys(deployModal.envVars).length > 0 && (
                <div className="space-y-2 pt-2 border-t border-border">
                  <label className="block text-gray-400 font-medium">Environment Configuration</label>
                  {Object.entries(deployModal.envVars).map(([k, v]) => (
                    <div key={k} className="flex items-center gap-2">
                      <span className="w-1/3 font-mono text-[11px] text-gray-300 truncate">{k}</span>
                      <input
                        type="text"
                        value={v}
                        onChange={(e) =>
                          setDeployModal({
                            ...deployModal,
                            envVars: { ...deployModal.envVars, [k]: e.target.value },
                          })
                        }
                        className="w-2/3 px-2.5 py-1.5 rounded bg-background border border-border text-foreground font-mono text-[11px]"
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-2.5 px-5 py-3 border-t border-border bg-background/50">
              <button
                type="button"
                onClick={() => setDeployModal({ ...deployModal, open: false })}
                className="px-3.5 py-1.5 rounded-lg border border-border text-gray-400 hover:text-foreground font-medium"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={deploying}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-medium shadow-md shadow-blue-600/20 disabled:opacity-50"
              >
                <Rocket className="w-3.5 h-3.5" />
                <span>{deploying ? 'Deploying Stack...' : 'Deploy to Docker'}</span>
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

