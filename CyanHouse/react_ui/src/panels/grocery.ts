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

// Which shopping-list lines (keyed by the line's `key`) have been ticked off,
// each with how much was bought: macro -> amount in its base unit, the line's
// totals when it was ticked. A later selection that needs more than that of
// any part unticks it (FoodPanel). null: ticked before amounts were kept,
// taken as the line's amounts the next time it is seen. Separate cookie
// since it churns independently of which dishes/quantities are selected.
const CHECKED_COOKIE = "grocery_checked";

export type Bought = Record<string, number>;
export type CheckedIngredients = Map<string, Bought | null>;

export function loadCheckedIngredients(): CheckedIngredients {
  const out: CheckedIngredients = new Map();
  try {
    const raw = readCookie(CHECKED_COOKIE);
    if (!raw) return out;
    const parsed = JSON.parse(decodeURIComponent(raw)) as unknown;
    if (Array.isArray(parsed)) {
      for (const k of parsed) if (typeof k === "string") out.set(k, null);
    } else if (parsed && typeof parsed === "object") {
      for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
        if (!v || typeof v !== "object") { out.set(k, null); continue; }
        const bought: Bought = {};
        for (const [m, n] of Object.entries(v as Record<string, unknown>))
          if (typeof n === "number" && Number.isFinite(n)) bought[m] = n;
        out.set(k, bought);
      }
    }
  } catch {
    /* ignore */
  }
  return out;
}

export function saveCheckedIngredients(checked: CheckedIngredients): void {
  const value = encodeURIComponent(JSON.stringify(Object.fromEntries(checked)));
  document.cookie =
    `${CHECKED_COOKIE}=${value}; path=/; max-age=${MAX_AGE}; SameSite=Strict` +
    (location.protocol === "https:" ? "; Secure" : "");
}

function readCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return m ? m[1] : null;
}
