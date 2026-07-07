import { reactRouter } from "@react-router/dev/vite";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// Proxy /api to the FastAPI backend (dashboard/api, uvicorn). Point MONITOR_API
// at the tunnelled VM port (default http://localhost:8888).
const MONITOR_API = process.env.MONITOR_API ?? "http://localhost:8888";

export default defineConfig({
  plugins: [tailwindcss(), reactRouter()],
  resolve: {
    tsconfigPaths: true,
  },
  server: {
    proxy: {
      "/api": { target: MONITOR_API, changeOrigin: true },
    },
  },
});
