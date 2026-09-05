import { useEffect, useRef } from "react";
import { NAV_ITEMS } from "./navigation";
import { ThemeToggle } from "./ThemeToggle";

interface MobileNavOverlayProps {
  activeSection: string;
  onNavigate: (id: string) => void;
  open: boolean;
  onClose: () => void;
  triggerRef: React.RefObject<HTMLButtonElement>;
}

const FOCUSABLE_SELECTOR = 'button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';

/**
 * Full-height mobile navigation overlay (Visual System Phase E/§12).
 * Traps focus while open, closes on Escape, and returns focus to the
 * trigger button on close -- the three behaviors a hamburger menu must
 * get right to be usable by keyboard, not just touch.
 */
export function MobileNavOverlay({ activeSection, onNavigate, open, onClose, triggerRef }: MobileNavOverlayProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const wasOpen = useRef(false);

  useEffect(() => {
    if (open) {
      const first = panelRef.current?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
      first?.focus();
      wasOpen.current = true;
    } else if (wasOpen.current) {
      triggerRef.current?.focus();
      wasOpen.current = false;
    }
  }, [open, triggerRef]);

  useEffect(() => {
    if (!open) return;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== "Tab") return;

      const focusable = panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
      if (!focusable || focusable.length === 0) return;
      const list = Array.from(focusable);
      const first = list[0];
      const last = list[list.length - 1];

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      id="mobile-nav-overlay"
      ref={panelRef}
      role="dialog"
      aria-modal="true"
      aria-label="Navigation menu"
      className="fixed inset-0 top-14 z-20 flex flex-col bg-bg lg:hidden"
    >
      <nav aria-label="Sections" className="flex-1 overflow-y-auto px-4 py-4">
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
                    onClose();
                  }}
                  className={[
                    "flex w-full items-center justify-between rounded px-3 py-3 text-left text-base",
                    item.enabled
                      ? isActive
                        ? "bg-bg-surface2 text-text-primary"
                        : "text-text-secondary hover:bg-bg-surface2"
                      : "cursor-not-allowed text-text-muted/60",
                  ].join(" ")}
                >
                  {item.label}
                  {!item.enabled ? (
                    <span className="font-mono text-[9px] uppercase tracking-wider text-text-muted/70">Soon</span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="border-t border-border px-4 py-4">
        <ThemeToggle />
      </div>
    </div>
  );
}
