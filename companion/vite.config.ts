import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig({
  envDir: path.resolve(__dirname, ".."),
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@institutional-ea/cloud-contract": path.resolve(__dirname, "../packages/cloud-contract/src/index.ts"),
    },
  },
  base: "./",
  server: {
    port: 5173,
    strictPort: true,
    watch: {
      ignored: ["**/release/**", "**/dist/**"],
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
