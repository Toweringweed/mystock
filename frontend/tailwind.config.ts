import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        up: "#ef5350",
        down: "#26a69a",
        accent: "#58a6ff",
        card: "#161b22",
      },
    },
  },
  plugins: [],
};

export default config;
