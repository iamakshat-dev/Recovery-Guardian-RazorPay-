export type Theme = "dark" | "light";

const STORAGE_KEY = "recovery-guardian:theme";

/**
 * Theme persistence + system-preference resolution (Visual System Phase
 * D). The actual first-paint decision lives in index.html's inline
 * script (it must run before React mounts, and before the stylesheet
 * paints, to avoid a flash of the wrong theme) -- this module re-reads
 * the SAME storage key and applies the SAME resolution order, so a
 * later call from React (e.g. the toggle button reading the current
 * state) can never disagree with what index.html already painted.
 */
export function getStoredTheme(): Theme | null {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored === "dark" || stored === "light" ? stored : null;
  } catch {
    // Private browsing / storage blocked -- fall through to system
    // preference, never crash the app over a theme preference.
    return null;
  }
}

export function getSystemTheme(): Theme {
  try {
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  } catch {
    return "dark";
  }
}

export function resolveTheme(): Theme {
  return getStoredTheme() ?? getSystemTheme();
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}

export function persistTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Persistence is a convenience, not a requirement -- the theme
    // still applies for this page view even if it can't be saved.
  }
  applyTheme(theme);
}
