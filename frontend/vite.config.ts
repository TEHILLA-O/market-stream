import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const api = process.env.MARKETSTREAM_API ?? "http://127.0.0.1:8000";
console.log(`[marketstream] proxying /api and /ws to ${api}`);

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": api,
      "/healthz": api,
      "/ws": { target: api.replace(/^http/, "ws"), ws: true },
    },
  },
});
