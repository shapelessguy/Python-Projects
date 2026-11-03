// UI language: the supported languages, the one picked (per browser, in
// localStorage), and t() / tn() to read a string of it. Adding a language
// is one entry in LANGUAGES and its dictionary file.
import { useCallback, useSyncExternalStore } from "react";
import { de } from "./de";
import { en, type Dict } from "./en";
import { it } from "./it";

export const LANGUAGES: { code: string; name: string; dict: Dict }[] = [
  { code: "en", name: "English", dict: en },
  { code: "it", name: "Italiano", dict: it },
  { code: "de", name: "Deutsch", dict: de },
];

export type Key = keyof Dict;
/** The keys with a plural form: "food_uses" for food_uses_one / food_uses_other. */
export type PluralKey = { [K in Key]: K extends `${infer B}_one` ? B : never }[Key];

const STORAGE_KEY = "lang";
const supported = (code: string | null | undefined) =>
  LANGUAGES.some((l) => l.code === code) ? (code as string) : null;

function initial(): string {
  try {
    const saved = supported(localStorage.getItem(STORAGE_KEY));
    if (saved) return saved;
  } catch {
    /* private mode / blocked storage */
  }
  return supported(navigator.language?.slice(0, 2)) ?? "en";
}

let current = initial();
const listeners = new Set<() => void>();

export function setLanguage(code: string): void {
  if (!supported(code) || code === current) return;
  current = code;
  try {
    localStorage.setItem(STORAGE_KEY, code);
  } catch {
    /* ignore */
  }
  listeners.forEach((l) => l());
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useLanguage(): string {
  return useSyncExternalStore(subscribe, () => current);
}

/** The picked language's strings: t("food_selected", { n: 3 }), and
 *  tn("food_uses", 3) for a plural (n is filled in as {n}). */
export function useT() {
  const lang = useLanguage();
  const dict = LANGUAGES.find((l) => l.code === lang)?.dict ?? en;
  const t = useCallback(
    (key: Key, vars?: Record<string, string | number>) =>
      (dict[key] ?? en[key]).replace(/\{(\w+)\}/g, (m, v) => (vars && v in vars ? String(vars[v]) : m)),
    [dict],
  );
  const tn = useCallback(
    (key: PluralKey, n: number, vars?: Record<string, string | number>) =>
      t(`${key}_${n === 1 ? "one" : "other"}` as Key, { n, ...vars }),
    [t],
  );
  return { t, tn, lang };
}

/** The language picker. */
export function LanguageSelect() {
  const { t, lang } = useT();
  return (
    <select value={lang} title={t("language")} aria-label={t("language")} onChange={(e) => setLanguage(e.target.value)}>
      {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
    </select>
  );
}
