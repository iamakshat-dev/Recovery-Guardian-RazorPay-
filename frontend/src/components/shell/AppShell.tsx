import { useRef, useState, type ReactNode } from "react";
import { MobileNavOverlay } from "./MobileNavOverlay";
import { TopNav } from "./TopNav";

interface AppShellProps {
  activeSection: string;
  onNavigate: (id: string) => void;
  children: ReactNode;
}

/**
 * Top-navigation product shell (Visual System Phase E), replacing the
 * Milestone 1 sidebar layout. The mobile hamburger trigger's ref lives
 * here so MobileNavOverlay can return focus to it on close -- the two
 * components share it rather than each guessing at the DOM.
 */
export function AppShell({ activeSection, onNavigate, children }: AppShellProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const menuTriggerRef = useRef<HTMLButtonElement>(null);

  function handleNavigate(id: string) {
    onNavigate(id);
    setMobileMenuOpen(false);
  }

  return (
    <div className="flex min-h-screen flex-col bg-bg text-text-primary">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-bg-surface2 focus:px-4 focus:py-2 focus:text-sm"
      >
        Skip to main content
      </a>

      <TopNav
        activeSection={activeSection}
        onNavigate={handleNavigate}
        onOpenMobileMenu={() => setMobileMenuOpen((v) => !v)}
        mobileMenuOpen={mobileMenuOpen}
        menuTriggerRef={menuTriggerRef}
      />

      <MobileNavOverlay
        activeSection={activeSection}
        onNavigate={handleNavigate}
        open={mobileMenuOpen}
        onClose={() => setMobileMenuOpen(false)}
        triggerRef={menuTriggerRef}
      />

      <main id="main-content" className="min-w-0 flex-1">
        {children}
      </main>

      <footer className="border-t border-border px-4 py-3 md:px-8">
        <p className="mx-auto max-w-[1400px] font-mono text-[10px] leading-relaxed text-text-muted">
          model root-cause-logreg-calibrated-v1 · policy rules-v1
        </p>
      </footer>
    </div>
  );
}
