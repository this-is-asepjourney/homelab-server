'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Terminal, Lock, Mail, ArrowRight, ShieldCheck, Loader2 } from 'lucide-react';
import { api } from '../../lib/api';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('admin@psm.local');
  const [password, setPassword] = useState('Admin12345!');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await api.login(email, password);
      router.push('/dashboard');
    } catch (err: any) {
      setError(err.message || 'Login failed. Please check credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-slate-950 to-slate-900 p-4">
      <div className="w-full max-w-md bg-slate-900/80 border border-slate-800 rounded-2xl shadow-2xl p-8 backdrop-blur-xl">
        {/* Brand header */}
        <div className="flex flex-col items-center text-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-blue-600 flex items-center justify-center text-white mb-4 shadow-lg shadow-blue-500/30">
            <Terminal className="w-6 h-6" />
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Personal Server Manager</h1>
          <p className="text-sm text-slate-400 mt-1">Homelab & Multi-Server Control Plane</p>
        </div>

        {/* Demo credentials hint */}
        <div className="mb-6 p-3 rounded-lg bg-blue-500/10 border border-blue-500/20 text-xs text-blue-300 flex items-start gap-2.5">
          <ShieldCheck className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
          <div>
            <span className="font-semibold text-blue-200">Default Credentials:</span>
            <div className="font-mono mt-0.5 text-[11px] text-blue-300">
              admin@psm.local / Admin12345!
            </div>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-xs text-rose-300">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">Email Address</label>
            <div className="relative">
              <Mail className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full pl-9 pr-4 py-2.5 rounded-lg bg-slate-800/80 border border-slate-700 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all"
                placeholder="admin@psm.local"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">Password</label>
            <div className="relative">
              <Lock className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pl-9 pr-4 py-2.5 rounded-lg bg-slate-800/80 border border-slate-700 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all"
                placeholder="••••••••••••"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-2 py-2.5 px-4 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium flex items-center justify-center gap-2 shadow-lg shadow-blue-600/30 transition-all disabled:opacity-50"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Authenticating...</span>
              </>
            ) : (
              <>
                <span>Sign In to Control Plane</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </form>

        <div className="mt-8 pt-4 border-t border-slate-800 text-center">
          <p className="text-xs text-slate-500">
            Self-hosted Control Plane v0.1.0 • Protected by Argon2id
          </p>
        </div>
      </div>
    </div>
  );
}

