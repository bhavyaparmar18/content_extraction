import type { Config } from "tailwindcss";
import forms from "@tailwindcss/forms";
import typography from "@tailwindcss/typography";

export default {
  darkMode: ["class", "[data-theme='dark']"],
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        app: "rgb(var(--bg-main-rgb) / <alpha-value>)",
        card: "rgb(var(--bg-card-rgb) / <alpha-value>)",
        "card-hover": "rgb(var(--bg-card-hover-rgb) / <alpha-value>)",
        sidebar: "rgb(var(--sidebar-bg-rgb) / <alpha-value>)",
        border: "var(--border)",
        primary: "rgb(var(--primary-rgb) / <alpha-value>)",
        "primary-dark": "var(--primary-dark)",
        "text-main": "rgb(var(--text-main-rgb) / <alpha-value>)",
        "text-muted": "rgb(var(--text-muted-rgb) / <alpha-value>)",
        warning: "rgb(var(--warning-rgb) / <alpha-value>)",
        danger: "rgb(var(--danger-rgb) / <alpha-value>)",
        info: "rgb(var(--info-rgb) / <alpha-value>)",
      },
      boxShadow: {
        panel: "0 16px 40px rgba(0,0,0,.26)",
        glow: "0 0 0 1px rgba(0,228,124,.16), 0 0 24px rgba(0,228,124,.08)",
      },
      spacing: {
        sidebar: "224px",
        "sidebar-collapsed": "72px",
        header: "64px",
      },
    },
  },
  plugins: [forms, typography],
} satisfies Config;
