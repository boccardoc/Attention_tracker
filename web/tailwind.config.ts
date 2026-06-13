import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0a0c10",
        panel: "#12151c",
        panel2: "#171b24",
        edge: "#262c38",
        muted: "#8b93a7",
        accent: "#5eead4",
        early: "#22c55e",
        froth: "#f43f5e",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
