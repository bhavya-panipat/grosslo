import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: {
          DEFAULT: "#000000",
          deep: "#050505",
        },
        surface: {
          DEFAULT: "#0a0a0a",
          raised: "#111111",
        },
        border: {
          DEFAULT: "rgba(255, 255, 255, 0.08)",
          strong: "rgba(255, 255, 255, 0.14)",
        },
        gold: {
          DEFAULT: "#D4AF37",
          bright: "#F3BA2F",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        "inner-edge": "inset 0 1px 0 0 rgba(255, 255, 255, 0.06)",
        "bevel": "0 1px 0 0 rgba(255, 255, 255, 0.9) inset, 0 1px 2px 0 rgba(0, 0, 0, 0.4)",
        "glow-gold": "0 0 40px -8px rgba(212, 175, 55, 0.35)",
      },
      backgroundImage: {
        "radial-warm": "radial-gradient(ellipse at center, rgba(243, 186, 47, 0.16) 0%, rgba(212, 175, 55, 0.06) 35%, transparent 70%)",
      },
    },
  },
  plugins: [],
};

export default config;
