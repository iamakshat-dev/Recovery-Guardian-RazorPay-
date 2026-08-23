import type { ReactNode } from "react";
import { MobileNav } from "./MobileNav";
import { Sidebar } from "./Sidebar";

interface AppShellProps {
  activeSection: string;
  onNavigate: (id: string) => void;
  children: ReactNode;
}

export function AppShell({ activeSection, onNavigate, children }: AppShellProps) {
  return (
    <div className="flex min-h-screen flex-col bg-bg text-text-primary md:flex-row">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-bg-surface2 focus:px-4 focus:py-2 focus:text-sm"
      >
        Skip to main content
      </a>
      <MobileNav activeSection={activeSection} onNavigate={onNavigate} />
      <Sidebar activeSection={activeSection} onNavigate={onNavigate} />
      <main id="main-content" className="min-w-0 flex-1">
        {children}
      </main>
    </div>
  );
}
