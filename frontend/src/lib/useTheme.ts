import { useEffect, useState } from "react";
import { applyTheme, persistTheme, resolveTheme, type Theme } from "./theme";

/**
 * React-side view of the current theme. index.html's inline script has
 * already applied the resolved theme before this ever runs (no-flash);
 * this hook just reads that same resolution so the toggle button's
 * initial label/state matches what is already painted.
 */
export function useTheme(): [Theme, (next: Theme) => void] {
  const [theme, setThemeState] = useState<Theme>(() => resolveTheme());

  useEffect(() => {
    // Keep in sync if the OS-level preference changes while no explicit
    // choice has been stored (matches index.html's resolution order).
    const media = window.matchMedia("(prefers-color-scheme: light)");
    function handleChange() {
      const stored = window.localStorage.getItem("recovery-guardian:theme");
      if (stored === "dark" || stored === "light") return;
      const next = resolveTheme();
      applyTheme(next);
      setThemeState(next);
    }
    media.addEventListener("change", handleChange);
    return () => media.removeEventListener("change", handleChange);
  }, []);

  function setTheme(next: Theme) {
    persistTheme(next);
    setThemeState(next);
  }

  return [theme, setTheme];
}
