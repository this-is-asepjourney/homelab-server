import type { Metadata } from 'next';
import './globals.css';
import { ThemeProvider } from '../components/theme-provider';
import { LayoutShell } from '../components/layout-shell';

export const metadata: Metadata = {
  title: 'Personal Server Manager (PSM)',
  description: 'Self-hosted Multi-Server Management Platform',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen antialiased bg-background text-foreground">
        <ThemeProvider>
          <LayoutShell>{children}</LayoutShell>
        </ThemeProvider>
      </body>
    </html>
  );
}

