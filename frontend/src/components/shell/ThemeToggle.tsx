import { useTheme } from "../../lib/useTheme";

/**
 * A single, quiet toggle -- not a settings menu. Persists to
 * localStorage and updates the `data-theme` attribute synchronously
 * (see lib/theme.ts); no page reload, no flash.
 */
export function ThemeToggle() {
  const [theme, setTheme] = useTheme();
  const isLight = theme === "light";

  return (
    <button
      type="button"
      onClick={() => setTheme(isLight ? "dark" : "light")}
      aria-pressed={isLight}
      className="flex items-center gap-1.5 rounded border border-border px-2.5 py-1.5 font-mono text-[11px] uppercase tracking-wider text-text-secondary transition-colors duration-150 hover:border-text-muted hover:text-text-primary"
    >
      <span aria-hidden="true" className="text-sm leading-none">
        {isLight ? "○" : "●"}
      </span>
      {isLight ? "Light" : "Dark"}
    </button>
  );
}
