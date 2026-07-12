import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The UI talks to the API at a same-origin `/api` prefix. In dev, Vite proxies
// `/api/*` to the FastAPI server (default http://localhost:8000), stripping the
// prefix so the engine's clean routes (/classify, /triage, …) are unchanged. In
// production, nginx does the same rewrite (see web/ui/nginx.conf).
const API_TARGET = process.env.VITE_API_PROXY || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
