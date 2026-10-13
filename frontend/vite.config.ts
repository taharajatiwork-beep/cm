import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(frontendRoot, "..");
const kitRoot = path.join(repoRoot, "assets", "sotoodeh-brand-kit");
const fallbackRoot = path.join(frontendRoot, "src", "brand", "fallback");
const hasKit = fs.existsSync(path.join(kitRoot, "code", "fonts.css"));
const brandCodeDir = hasKit ? path.join(kitRoot, "code") : path.join(fallbackRoot, "code");
const brandAssetsDir = hasKit ? path.join(kitRoot, "assets") : path.join(fallbackRoot, "assets");

function brandImage(name: "symbol" | "wordmark"): string {
  const png = path.join(brandAssetsDir, `sotoodeh-${name}.png`);
  if (fs.existsSync(png)) return png;
  return path.join(fallbackRoot, "assets", `sotoodeh-${name}.svg`);
}

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@brand-code": brandCodeDir,
      "@brand-symbol": brandImage("symbol"),
      "@brand-wordmark": brandImage("wordmark"),
    },
  },
  server: {
    port: 5173,
    fs: {
      allow: [frontendRoot, path.resolve(frontendRoot, "..")],
    },
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY || "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
