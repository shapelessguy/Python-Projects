// The server answers in English. The messages a user can meet are the
// srv_* keys, whose English text is the server's own word for word, {x}
// standing for the parts that vary; a message is matched against those and
// said again in the picked language, the varying parts translated in turn
// (a "could not fetch the recipe: {e}" carries another message). Anything
// unmatched is shown as it came.
import { translate, type Key } from "./i18n";
import { en } from "./i18n/en";

interface Pattern { key: Key; names: string[]; re: RegExp; literal: number }

const PATTERNS: Pattern[] = (Object.keys(en) as Key[])
  .filter((k) => k.startsWith("srv_") && !k.startsWith("srv_ui_"))
  .map((key) => {
    const parts = en[key].split(/\{(\w+)\}/);
    const names = parts.filter((_, i) => i % 2 === 1);
    const literals = parts.filter((_, i) => i % 2 === 0);
    const re = new RegExp(
      "^" + literals.map((l) => l.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("([\\s\\S]+?)") + "$");
    return { key, names, re, literal: literals.join("").length };
  })
  // The most specific first: "not permitted to see that folder" before
  // "not permitted to {what}".
  .sort((a, b) => b.literal - a.literal);

/** A server message in the picked language. */
export function serverText(text: string, depth = 0): string {
  const trimmed = text.trim();
  if (!trimmed || depth > 3) return text;
  for (const p of PATTERNS) {
    const m = p.re.exec(trimmed);
    if (!m) continue;
    const vars: Record<string, string> = {};
    p.names.forEach((n, i) => { vars[n] = serverText(m[i + 1], depth + 1); });
    return translate(p.key, vars);
  }
  return text;
}

/** What a failed response says: its `detail` (FastAPI), in the picked
 *  language, else its status. */
export function responseText(status: number, body: string): string {
  let detail: unknown = body;
  try { detail = JSON.parse(body).detail ?? body; } catch { /* plain text */ }
  if (Array.isArray(detail)) {
    // A request the server's model refused: each problem's own message.
    detail = detail.map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : JSON.stringify(d))).join("; ");
  }
  const text = typeof detail === "string" ? detail : JSON.stringify(detail);
  // An HTML page is a proxy's (nginx) error, not something to show.
  if (!text.trim() || /^\s*</.test(text)) return translate("srv_ui_status", { status });
  return serverText(text);
}

/** A failed API call: `message` is what to show, already translated. */
export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
    // So String(e) is the message alone, without an "Error: " in front.
    this.name = "";
  }
}

/** The ApiError of a failed response. */
export async function apiError(r: Response): Promise<ApiError> {
  return new ApiError(r.status, responseText(r.status, await r.text().catch(() => "")));
}
