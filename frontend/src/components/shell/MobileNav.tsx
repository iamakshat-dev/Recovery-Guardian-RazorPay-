import { useState } from "react";
import { NAV_ITEMS } from "./navigation";

interface MobileNavProps {
  activeSection: string;
  onNavigate: (id: string) => void;
}

export function MobileNav({ activeSection, onNavigate }: MobileNavProps) {
  const [open, setOpen] = useState(false);

  return (
    <header className="flex items-center justify-between border-b border-border bg-bg-surface px-4 py-3 md:hidden">
      <div className="font-mono text-xs font-semibold tracking-wide text-text-primary">
        RECOVERY GUARDIAN
      </div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls="mobile-nav-menu"
        aria-label={open ? "Close navigation menu" : "Open navigation menu"}
        onClick={() => setOpen((prev) => !prev)}
        className="rounded border border-border px-3 py-1.5 text-xs text-text-secondary transition-colors duration-150 hover:text-text-primary"
      >
        {open ? "Close" : "Menu"}
      </button>

      {open ? (
        <nav
          id="mobile-nav-menu"
          aria-label="Sections"
          className="absolute left-0 right-0 top-[49px] z-20 border-b border-border bg-bg-surface p-3"
        >
          <ul className="space-y-0.5">
            {NAV_ITEMS.map((item) => {
              const isActive = item.id === activeSection;
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    disabled={!item.enabled}
                    aria-current={isActive ? "page" : undefined}
                    onClick={() => {
                      if (!item.enabled) return;
                      onNavigate(item.id);
                      setOpen(false);
                    }}
                    className={[
                      "flex w-full items-center justify-between rounded px-3 py-2 text-left text-sm",
                      item.enabled
                        ? isActive
                          ? "bg-bg-surface2 text-text-primary"
                          : "text-text-secondary hover:bg-bg-surface2"
                        : "cursor-not-allowed text-text-muted/60",
                    ].join(" ")}
                  >
                    {item.label}
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
      ) : null}
    </header>
  );
}
