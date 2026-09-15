import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

// Ports come from .env at the project root (one dir up) — read it directly so it works
// regardless of where `npm run dev` is invoked from.
function loadDotenv(): Record<string, string> {
  const path = resolve(dirname(fileURLToPath(import.meta.url)), "..", ".env");
  const out: Record<string, string> = {};
  try {
    for (const line of readFileSync(path, "utf8").split(/\r?\n/)) {
      const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
      if (m) out[m[1]] = m[2].replace(/#.*$/, "").trim();
    }
  } catch {
    /* no .env — use defaults */
  }
  return out;
}

const env = loadDotenv();
const apiPort = env.API_PORT || "8000";
const webPort = Number(env.WEB_PORT || 5173);

// eslint-disable-next-line no-console
console.log(`[vite] dev server :${webPort}  ->  proxy /api -> http://localhost:${apiPort}`);

export default defineConfig({
  base: "/ui/",
  plugins: [react()],
  server: {
    port: webPort,
    proxy: {
      "/api": {
        target: env.API_URL || `http://localhost:${apiPort}`,
        changeOrigin: true,
      },
    },
  },
  build: { outDir: "dist" },
});
