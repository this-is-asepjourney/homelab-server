'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  LayoutDashboard,
  Server,
  FolderGit2,
  Rocket,
  Activity,
  HardDrive,
  History,
  Settings,
  Sun,
  Moon,
  LogOut,
  Menu,
  X,
  ShieldCheck,
  ChevronRight,
  Terminal,
  Boxes,
  Bell,
  AlertTriangle,
  Network,
} from 'lucide-react';
import { useTheme } from './theme-provider';
import { api, getAuthToken } from '../lib/api';

interface NavItem {
  name: string;
  href: string;
  icon: React.ElementType;
}

const navItems: NavItem[] = [
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { name: 'Servers', href: '/servers', icon: Server },
  { name: 'App Store', href: '/templates', icon: Boxes },
  { name: 'Projects', href: '/projects', icon: FolderGit2 },
  { name: 'Deployments', href: '/deployments', icon: Rocket },
  { name: 'Monitoring', href: '/monitoring', icon: Activity },
  { name: 'Network', href: '/network', icon: Network },
  { name: 'Storage', href: '/storage', icon: HardDrive },
  { name: 'Activity Log', href: '/activity', icon: History },
  { name: 'Settings', href: '/settings', icon: Settings },
];

export function LayoutShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { theme, resolvedTheme, setTheme } = useTheme();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [user, setUser] = useState<any>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [alertsOpen, setAlertsOpen] = useState(false);

  useEffect(() => {
    // If on login page, don't show shell
    if (pathname === '/login') return;

    const token = getAuthToken();
    if (!token) {
      router.push('/login');
      return;
    }

    const savedUser = localStorage.getItem('psm_user');
    if (savedUser) {
      try {
        setUser(JSON.parse(savedUser));
      } catch (_) {}
    }

    api.me()
      .then((u) => setUser(u))
      .catch(() => {
        // Continue with local user or login redirect
      });

    // Load recent alerts
    api.getRecentAlerts()
      .then((a) => setAlerts(a))
      .catch(() => {});
  }, [pathname, router]);

  if (pathname === '/login') {
    return <>{children}</>;
  }

  const toggleTheme = () => {
    setTheme(resolvedTheme === 'dark' ? 'light' : 'dark');
  };

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar Desktop */}
      <aside className="hidden md:flex flex-col w-64 border-r border-border bg-card/60 backdrop-blur-md">
        {/* App Title */}
        <div className="flex items-center gap-3 h-16 px-6 border-b border-border">
          <div className="p-2 rounded-lg bg-blue-600 text-white shadow-md shadow-blue-500/20">
            <Terminal className="w-5 h-5" />
          </div>
          <div>
            <h1 className="font-bold text-sm tracking-tight text-foreground">PSM Control Plane</h1>
            <p className="text-xs text-muted-foreground text-gray-500 dark:text-gray-400">v0.1.0 MVP</p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href || (item.href !== '/dashboard' && pathname.startsWith(item.href));
            return (
              <Link
                key={item.name}
                href={item.href}
                className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-blue-600/10 text-blue-600 dark:bg-blue-500/15 dark:text-blue-400 font-semibold'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-100 dark:hover:bg-gray-800/60'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-blue-600 dark:text-blue-400' : ''}`} />
                {item.name}
              </Link>
            );
          })}
        </nav>

        {/* User & Homelab Status */}
        <div className="p-4 border-t border-border bg-card/40">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400">Homelab Connected</span>
            </div>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gray-200 dark:bg-gray-800 text-gray-600 dark:text-gray-400">
              LAN
            </span>
          </div>

          <div className="flex items-center justify-between pt-2 border-t border-border/50">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold text-xs uppercase shadow-sm">
                {user?.name ? user.name[0] : 'A'}
              </div>
              <div className="text-left">
                <p className="text-xs font-medium text-foreground truncate max-w-[100px]">{user?.name || 'Administrator'}</p>
                <p className="text-[10px] text-gray-500 capitalize">{user?.role || 'owner'}</p>
              </div>
            </div>
            <button
              onClick={() => api.logout()}
              title="Logout"
              className="p-1.5 text-gray-400 hover:text-rose-500 hover:bg-rose-500/10 rounded-md transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Header */}
        <header className="h-16 border-b border-border flex items-center justify-between px-6 bg-card/40 backdrop-blur-sm z-10">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setMobileOpen(!mobileOpen)}
              className="md:hidden p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>

            {/* Breadcrumb path */}
            <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
              <span className="font-medium text-foreground capitalize">
                {pathname.split('/')[1] || 'Dashboard'}
              </span>
              {pathname.split('/')[2] && (
                <>
                  <ChevronRight className="w-4 h-4" />
                  <span className="text-blue-500 font-mono text-xs">{pathname.split('/')[2]}</span>
                </>
              )}
            </div>
          </div>

          {/* Quick controls */}
          <div className="flex items-center gap-3">
            <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-xs font-medium">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Control Plane Active</span>
            </div>

            {/* Alerts & Notifications Bell */}
            <div className="relative">
              <button
                onClick={() => setAlertsOpen(!alertsOpen)}
                className="relative p-2 rounded-lg border border-border text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                title="System Alerts"
              >
                <Bell className="w-4 h-4" />
                {alerts.length > 0 && (
                  <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-rose-500 text-[10px] font-bold text-white shadow-sm">
                    {alerts.length > 9 ? '9+' : alerts.length}
                  </span>
                )}
              </button>

              {/* Alerts Dropdown */}
              {alertsOpen && (
                <div className="absolute right-0 mt-2 w-80 rounded-xl border border-border bg-card shadow-2xl overflow-hidden z-50 text-xs">
                  <div className="flex items-center justify-between p-3 border-b border-border bg-background/60">
                    <span className="font-bold text-foreground">Notifications & Alerts</span>
                    {alerts.length > 0 && (
                      <button
                        onClick={async () => {
                          await api.clearAlerts();
                          setAlerts([]);
                        }}
                        className="text-[11px] text-blue-500 hover:underline"
                      >
                        Clear All
                      </button>
                    )}
                  </div>
                  <div className="max-h-72 overflow-y-auto divide-y divide-border">
                    {alerts.length === 0 ? (
                      <div className="p-4 text-center text-gray-500 text-xs">
                        No active system alerts. All nodes healthy!
                      </div>
                    ) : (
                      alerts.map((alt) => (
                        <div key={alt.id} className="p-3 hover:bg-gray-500/5 transition-colors space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-foreground truncate">{alt.title}</span>
                            <span className="text-[10px] text-gray-400 font-mono">
                              {new Date(alt.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </span>
                          </div>
                          <p className="text-[11px] text-gray-400 line-clamp-2">{alt.description}</p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Theme Toggle Button */}
            <button
              onClick={toggleTheme}
              className="p-2 rounded-lg border border-border text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
              title={`Switch to ${resolvedTheme === 'dark' ? 'Light' : 'Dark'} Mode`}
            >
              {resolvedTheme === 'dark' ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-slate-700" />}
            </button>
          </div>
        </header>

        {/* Page Content scrollable */}
        <main className="flex-1 overflow-y-auto p-6 bg-background">
          {children}
        </main>
      </div>
    </div>
  );
}

