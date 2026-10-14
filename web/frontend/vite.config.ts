import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { renderSeo } from "./seo.config";

/**
 * One app, two static heads: dist/index.html (en) and dist/ru/index.html (ru), so crawlers
 * see the right language per URL. The dev server picks the language from the request path.
 */
function seoPages(): Plugin {
  let outDir = "dist";
  return {
    name: "bs-seo-pages",
    configResolved(c) { outDir = resolve(c.root, c.build.outDir); },
    transformIndexHtml(html, ctx) {
      // in build the markers stay until writeBundle, which renders both languages
      if (!ctx.server) return html;
      return renderSeo(html, /^\/ru(\/|$|\?)/.test(ctx.originalUrl ?? "") ? "ru" : "en");
    },
    writeBundle() {
      const template = readFileSync(resolve(outDir, "index.html"), "utf8");
      writeFileSync(resolve(outDir, "index.html"), renderSeo(template, "en"));
      mkdirSync(resolve(outDir, "ru"), { recursive: true });
      writeFileSync(resolve(outDir, "ru/index.html"), renderSeo(template, "ru"));
    },
  };
}

export default defineConfig({
  plugins: [react(), seoPages()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
  optimizeDeps: { exclude: ["onnxruntime-web"] },
  build: { target: "es2022" },
});
