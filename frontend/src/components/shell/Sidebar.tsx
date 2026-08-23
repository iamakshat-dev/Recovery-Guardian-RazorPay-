import { NAV_ITEMS } from "./navigation";

interface SidebarProps {
  activeSection: string;
  onNavigate: (id: string) => void;
}

export function Sidebar({ activeSection, onNavigate }: SidebarProps) {
  return (
    <aside
      aria-label="Primary navigation"
      className="hidden shrink-0 flex-col border-r border-border bg-bg-surface md:flex md:w-60"
    >
      <div className="px-5 py-6">
        <div className="font-mono text-[13px] font-semibold leading-tight tracking-wide text-text-primary">
          RECOVERY
          <br />
          GUARDIAN
        </div>
        <div className="mt-4 flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="h-1.5 w-1.5 rounded-full bg-safety shadow-[0_0_6px_rgba(34,197,94,0.6)]"
          />
          <span className="font-mono text-[10px] uppercase tracking-wider text-text-muted">
            System Verified
          </span>
        </div>
      </div>

      <nav aria-label="Sections" className="flex-1 px-3 pb-6">
        <ul className="space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const isActive = item.id === activeSection;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  disabled={!item.enabled}
                  aria-current={isActive ? "page" : undefined}
                  onClick={() => item.enabled && onNavigate(item.id)}
                  className={[
                    "flex w-full items-center justify-between rounded px-3 py-2 text-left text-sm transition-colors duration-150",
                    item.enabled
                      ? isActive
                        ? "bg-bg-surface2 text-text-primary"
                        : "text-text-secondary hover:bg-bg-surface2 hover:text-text-primary"
                      : "cursor-not-allowed text-text-muted/60",
                  ].join(" ")}
                >
                  <span className="flex items-center gap-2">
                    {isActive ? (
                      <span aria-hidden="true" className="h-1 w-1 rounded-full bg-info" />
                    ) : (
                      <span aria-hidden="true" className="h-1 w-1 rounded-full bg-transparent" />
                    )}
                    {item.label}
                  </span>
                  {!item.enabled ? (
                    <span className="font-mono text-[9px] uppercase tracking-wider text-text-muted/70">
                      Soon
                    </span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="border-t border-border px-5 py-4">
        <p className="font-mono text-[10px] leading-relaxed text-text-muted">
          model root-cause-logreg-calibrated-v1
          <br />
          policy rules-v1
        </p>
      </div>
    </aside>
  );
}
