import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// In development the FastAPI backend runs on :8000; Vite proxies /api to it.
// In production `uv run titan3d serve` serves the built dist/ and the API together.
export default defineConfig({
  plugins: [tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } },
  },
  build: { target: "es2023", chunkSizeWarningLimit: 900 },
});
