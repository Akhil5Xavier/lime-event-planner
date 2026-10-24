import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 127.0.0.1, not localhost: Node 17+ resolves localhost to ::1 but uvicorn listens on IPv4.
      "/api": "http://127.0.0.1:8000",
    },
  },
});
