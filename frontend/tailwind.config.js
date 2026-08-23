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
          muted: "#68717D",
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
