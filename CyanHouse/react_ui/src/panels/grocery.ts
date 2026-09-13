// Grocery list state — which dishes are on it and how many times each is
// being made. Purely a client-side convenience (never sent to the backend),
// persisted in its own cookie so it survives reloads, mirroring the pattern
// ../auth.ts already uses for the login credential.
const COOKIE = "grocery_list";
const MAX_AGE = 60 * 60 * 24 * 7; // 7 days

export type GroceryList = Record<number, number>; // dish id -> quantity

export function loadGroceryList(): GroceryList {
  try {
    const raw = readCookie(COOKIE);
    if (!raw) return {};
    const parsed = JSON.parse(decodeURIComponent(raw)) as unknown;
    if (!parsed || typeof parsed !== "object") return {};
    const out: GroceryList = {};
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      const id = Number(k);
      const qty = Number(v);
      if (Number.isFinite(id) && Number.isInteger(qty) && qty > 0) out[id] = qty;
    }
    return out;
  } catch {
    return {};
  }
}

export function saveGroceryList(list: GroceryList): void {
  const value = encodeURIComponent(JSON.stringify(list));
  document.cookie =
    `${COOKIE}=${value}; path=/; max-age=${MAX_AGE}; SameSite=Strict` +
    (location.protocol === "https:" ? "; Secure" : "");
}

// Which shopping-list lines (keyed "name::unit", see FoodPanel's
// computeGroceryTotals) have been ticked off -- separate cookie since it
// churns independently of which dishes/quantities are selected.
const CHECKED_COOKIE = "grocery_checked";

export function loadCheckedIngredients(): Set<string> {
  try {
    const raw = readCookie(CHECKED_COOKIE);
    if (!raw) return new Set();
    const parsed = JSON.parse(decodeURIComponent(raw)) as unknown;
    if (Array.isArray(parsed)) return new Set(parsed.filter((x): x is string => typeof x === "string"));
  } catch {
    /* ignore */
  }
  return new Set();
}

export function saveCheckedIngredients(keys: Set<string>): void {
  const value = encodeURIComponent(JSON.stringify([...keys]));
  document.cookie =
    `${CHECKED_COOKIE}=${value}; path=/; max-age=${MAX_AGE}; SameSite=Strict` +
    (location.protocol === "https:" ? "; Secure" : "");
}

function readCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return m ? m[1] : null;
}
