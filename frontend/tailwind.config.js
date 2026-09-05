/** @type {import('tailwindcss').Config} */

// Each entry reads a CSS custom property defined in src/index.css (see
// that file's module comment for the full token rationale). The
// `rgb(var(--x) / <alpha-value>)` pattern is what lets Tailwind's
// opacity-modifier syntax (`bg-safety/40`, `text-warning`, ...) keep
// working — Tailwind substitutes `<alpha-value>` with the modifier at
// build time. Every existing component class name is preserved
// (`bg`, `border`, `text.primary/secondary/muted`, `safety`, `warning`,
// `critical`, `info`) — only the underlying value now resolves through
// the theme token layer instead of a fixed hex, so toggling
// `[data-theme]` on <html> reskins the whole app without per-component
// changes.
function withOpacity(variable) {
  return `rgb(var(${variable}) / <alpha-value>)`;
}

export default {
  // Theming is done entirely through the CSS custom properties in
  // src/index.css (`:root` = dark, `[data-theme="light"]` override) --
  // no `dark:` Tailwind variant is used anywhere, so darkMode is left
  // at its default.
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: withOpacity("--color-bg"),
          surface: withOpacity("--color-surface"),
          surface2: withOpacity("--color-surface-raised"),
          subtle: withOpacity("--color-surface-subtle"),
        },
        border: {
          DEFAULT: withOpacity("--color-border"),
        },
        text: {
          primary: withOpacity("--color-text-primary"),
          secondary: withOpacity("--color-text-secondary"),
          muted: withOpacity("--color-text-muted"),
        },
        // "safety" keeps its existing name (BLOCK_RECONCILE, zero
        // duplicate-risk) -- it is the product's one reserved safety
        // color, never reused as a generic "positive" accent elsewhere.
        safety: {
          DEFAULT: withOpacity("--color-success"),
          glow: "rgb(var(--color-success) / 0.12)",
        },
        warning: withOpacity("--color-warning"),
        critical: withOpacity("--color-danger"),
        info: withOpacity("--color-info"),
        accent: withOpacity("--color-accent"),
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
      },
      borderRadius: {
        DEFAULT: "8px",
        lg: "12px",
      },
      transitionTimingFunction: {
        "guardian-out": "cubic-bezier(0.16, 1, 0.3, 1)",
      },
    },
  },
  plugins: [],
};
