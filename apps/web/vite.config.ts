import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    allowedHosts: [".cloudspaces.litng.ai", "localhost", "127.0.0.1"],
  },
  preview: {
    host: "0.0.0.0",
    allowedHosts: [".cloudspaces.litng.ai", "localhost", "127.0.0.1"],
  },
});
