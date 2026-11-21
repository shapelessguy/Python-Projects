import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

// The page's server is CyanManager itself (gui/web.py), on WEB_PORT from
// CyanManager's .env. `npm run dev` proxies the API to it.
function webPort(): string {
  const env = resolve(dirname(fileURLToPath(import.meta.url)), "..", ".env");
  try {
    for (const line of readFileSync(env, "utf8").split(/\r?\n/)) {
      const m = line.match(/^\s*WEB_PORT\s*=\s*(\d+)/);
      if (m) return m[1];
    }
  } catch {
    /* no .env: the default below */
  }
  return "8000";
}

const target = `http://localhost:${webPort()}`;

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5174,
    proxy: { "/api": target, "/icons": target },
  },
});
