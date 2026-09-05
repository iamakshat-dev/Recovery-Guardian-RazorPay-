import { NAV_ITEMS } from "./navigation";
import { ThemeToggle } from "./ThemeToggle";

interface TopNavProps {
  activeSection: string;
  onNavigate: (id: string) => void;
  onOpenMobileMenu: () => void;
  mobileMenuOpen: boolean;
  menuTriggerRef: React.RefObject<HTMLButtonElement>;
}

/**
 * Persistent top navigation (Visual System Phase E), replacing the
 * Milestone 1 sidebar. `sticky top-0` keeps it visible while scrolling
 * without pinning the whole page (no scroll hijacking). The active
 * indicator is a single underline bar driven by `aria-current="page"`
 * plus a CSS-only transition -- no animation library, no JS-computed
 * position.
 */
export function TopNav({ activeSection, onNavigate, onOpenMobileMenu, mobileMenuOpen, menuTriggerRef }: TopNavProps) {
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-bg/95 backdrop-blur supports-[backdrop-filter]:bg-bg/80">
      <div className="mx-auto flex h-14 max-w-[1400px] items-center justify-between gap-4 px-4 md:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <span className="whitespace-nowrap font-mono text-[13px] font-semibold tracking-wide text-text-primary">
            RECOVERY GUARDIAN
          </span>
          <span className="hidden items-center gap-1.5 lg:flex">
            <span
              aria-hidden="true"
              className="h-1.5 w-1.5 rounded-full bg-safety shadow-[0_0_6px_rgb(var(--color-success)/0.6)]"
            />
            <span className="font-mono text-[10px] uppercase tracking-wider text-text-muted">System Verified</span>
          </span>
        </div>

        <nav aria-label="Sections" className="hidden flex-1 justify-center lg:flex">
          <ul className="flex items-center gap-0.5">
            {NAV_ITEMS.map((item) => {
              const isActive = item.id === activeSection;
              return (
                <li key={item.id} className="relative">
                  <button
                    type="button"
                    disabled={!item.enabled}
                    aria-current={isActive ? "page" : undefined}
                    onClick={() => item.enabled && onNavigate(item.id)}
                    className={[
                      "relative whitespace-nowrap rounded px-2.5 py-1.5 font-mono text-[12px] uppercase tracking-wide transition-colors duration-150",
                      item.enabled
                        ? isActive
                          ? "text-text-primary"
                          : "text-text-secondary hover:text-text-primary"
                        : "cursor-not-allowed text-text-muted/60",
                    ].join(" ")}
                  >
                    {item.label}
                    <span
                      aria-hidden="true"
                      className={[
                        "absolute inset-x-2 -bottom-[1px] h-[2px] rounded-full bg-accent transition-transform duration-200 ease-guardian-out",
                        isActive ? "scale-x-100" : "scale-x-0",
                      ].join(" ")}
                    />
                    {!item.enabled ? (
                      <span className="ml-1 font-mono text-[9px] normal-case tracking-normal text-text-muted/70">
                        Soon
                      </span>
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="flex items-center gap-2">
          <div className="hidden lg:block">
            <ThemeToggle />
          </div>
          <button
            ref={menuTriggerRef}
            type="button"
            aria-expanded={mobileMenuOpen}
            aria-controls="mobile-nav-overlay"
            aria-label={mobileMenuOpen ? "Close navigation menu" : "Open navigation menu"}
            onClick={onOpenMobileMenu}
            className="rounded border border-border px-3 py-1.5 text-xs text-text-secondary transition-colors duration-150 hover:text-text-primary lg:hidden"
          >
            {mobileMenuOpen ? "Close" : "Menu"}
          </button>
        </div>
      </div>
    </header>
  );
}
