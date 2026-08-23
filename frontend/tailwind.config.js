/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "#080A0D",
          surface: "#101318",
          surface2: "#151A20",
        },
        border: {
          DEFAULT: "#252B33",
        },
        text: {
          primary: "#F3F5F7",
          secondary: "#9AA3AE",
          // #68717D (the Milestone 1 spec value) fails WCAG AA contrast
          // (3.88:1) against the darkest surface (#080A0D) at the small
          // text sizes this token is actually used at — found by the
          // Milestone 2 axe-core audit. Lightened to #7B8794 (5.10:1),
          // which still reads as clearly muted relative to `secondary`
          // and `primary`. Every other Milestone 1 color is unchanged.
          muted: "#7B8794",
        },
        safety: {
          DEFAULT: "#22C55E",
          glow: "rgba(34, 197, 94, 0.12)",
        },
        warning: "#F59E0B",
        critical: "#EF4444",
        info: "#60A5FA",
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
