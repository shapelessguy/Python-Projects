import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

// Ports come from the project root (one dir up), read directly so this works
// regardless of where `npm run dev` is invoked from. secrets.json is the one
// place every part of the stack reads its config from (api/config.py and
// android_ui/app/build.gradle.kts both do the same) -- .env is only still
// honoured for anyone who kept one from before that consolidation.
function loadRoot(): Record<string, string> {
  const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
  const out: Record<string, string> = {};
  try {
    for (const line of readFileSync(resolve(root, ".env"), "utf8").split(/\r?\n/)) {
      const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
      if (m) out[m[1]] = m[2].replace(/#.*$/, "").trim();
    }
  } catch {
    /* no .env — secrets.json below is the normal case */
  }
  try {
    const json = JSON.parse(readFileSync(resolve(root, "secrets.json"), "utf8"));
    for (const [k, v] of Object.entries(json)) {
      if (k !== "users" && v != null) out[k] = String(v);
    }
  } catch {
    /* no secrets.json — fall through to the defaults below */
  }
  return out;
}

const env = loadRoot();
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
