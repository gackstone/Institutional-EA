import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@institutional-ea/cloud-contract": path.resolve(
        __dirname,
        "../../packages/cloud-contract/src/index.ts"
      ),
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
