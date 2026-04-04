import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    // Слушаем все интерфейсы — иначе с другого устройства / по IP фронт не откроется
    host: true,
    port: 5173,
    strictPort: false,
    allowedHosts: [
      "hedy-disconcerted-junie.ngrok-free.dev",
      ".ngrok-free.dev",
    ],
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: true,
    port: 4173,
    allowedHosts: [
      "hedy-disconcerted-junie.ngrok-free.dev",
      ".ngrok-free.dev",
    ],
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
