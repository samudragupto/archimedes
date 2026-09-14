import type { Config } from "tailwindcss";

/**
 * Design tokens follow the shadcn convention (CSS variables in globals.css),
 * so components/ui reads like standard shadcn output. The accent is a deep
 * "solicitation ink" blue; tier badge colors are defined as dedicated tokens
 * (tier-nano green / tier-super blue / tier-ultra purple / tier-tavily orange)
 * because they are a core part of the product's visual language: every LLM
 * call in the UI is labeled with the model that made it.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        secondary: { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
        destructive: { DEFAULT: "hsl(var(--destructive))", foreground: "hsl(var(--destructive-foreground))" },
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        tier: {
          nano: "hsl(var(--tier-nano))",
          super: "hsl(var(--tier-super))",
          ultra: "hsl(var(--tier-ultra))",
          tavily: "hsl(var(--tier-tavily))",
        },
      },
      borderRadius: { lg: "var(--radius)", md: "calc(var(--radius) - 2px)", sm: "calc(var(--radius) - 4px)" },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "Helvetica Neue", "sans-serif"],
        serif: ["Georgia", "Cambria", "Times New Roman", "serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      keyframes: {
        "pulse-soft": { "0%, 100%": { opacity: "1" }, "50%": { opacity: "0.55" } },
      },
      animation: { "pulse-soft": "pulse-soft 1.8s ease-in-out infinite" },
    },
  },
  plugins: [],
};
export default config;
