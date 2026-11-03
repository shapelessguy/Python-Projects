// Food service client — self-contained module. The only shared touch-points
// are the auth 401 hook and the version poll (see ../api.ts `food` field).
import { onAuthFailed } from "../auth";

export interface Dish {
  id: number;
  /** In English; name_tr / instructions_tr hold the other languages that
   *  have them (lang -> text). */
  name: string;
  name_tr?: Record<string, string>;
  category: string;
  rating: number;
  image: string;
  url: string;
  instructions: string;
  instructions_tr?: Record<string, string>;
  ingredients: string;
  /** Its facts, filled by the recipe import, editable (null: not known). */
  facts: DishFacts;
  /** The instructions' photos: "N" -> stored image file, for {{photo:N}}. */
  photos: Record<string, string>;
  /** The recipe import: its state, and whether the linked recipe is the one
   *  imported (false for a recipe linked but never imported). */
  import: DishImport;
}

export type Difficulty = "very_easy" | "easy" | "medium" | "hard" | "very_hard" | "";

export interface DishFacts {
  prep_min: number | null;
  cook_min: number | null;
  total_min: number | null;
  difficulty: Difficulty;
  /** The recipe site's own rating and comments: shown, not edited. */
  source_rating: string;
  source_rating_count: string;
  source_comments: string;
}

export interface DishImport {
  state?: "running" | "done" | "failed";
  /** While running: queued, fetching, reading, translating. */
  stage?: string;
  /** What failed (a failed import keeps what did work). */
  errors?: string[];
  imported: boolean;
}

/** An ingredient's conversion between two of mass, volume and pieces, as
 *  entered: a_qty a_unit = b_qty b_unit ("1 tbsp = 12 g"). */
export interface Conversion {
  a_qty: number;
  a_unit: string;
  b_qty: number;
  b_unit: string;
}

/** One ingredient of the list: its optional conversions, and how many
 *  dishes use it. */
export interface CatalogIngredient {
  id: number;
  /** In English; `names` holds the other languages that have one. */
  name: string;
  names: Record<string, string>;
  uses: number;
  conversions: Conversion[];
}

export type Macro = "mass" | "volume" | "count";

/** A unit a recipe line may be written in ("" is a count of pieces), and
 *  how many of its macro-category's base unit (g, ml, piece) it is. */
export interface UnitDef {
  unit: string;
  macro: Macro;
  factor: number;
}

export interface FoodData {
  dishes: Dish[];
  categories: string[];
  /** category -> lang -> its name there. */
  category_tr?: Record<string, Record<string, string>>;
  ingredients: CatalogIngredient[];
  units: UnitDef[];
  version: number;
}

/** One shopping-list line: an ingredient's total, in parts when some of its
 *  amounts don't convert to the others ("200 g + 3"); `approximate` when a
 *  recipe gave it no amount. */
export interface GroceryLine {
  key: string;
  name: string;
  parts: { amount: string; unit: string }[];
  approximate: boolean;
}

export interface ImageHit {
  url: string;
  thumbnail: string;
  title: string;
  source: string;
}

/** One GialloZafferano search result, with the facts its card shows ("" for
 *  one it doesn't): rating "4,3", comments "160", difficulty in Italian
 *  ("Facile"), time "4 h 40 min", kcal "772". */
export interface RecipeHit {
  url: string;
  title: string;
  image: string;
  category: string;
  description: string;
  rating: string;
  comments: string;
  difficulty: string;
  time: string;
  kcal: string;
}

/** What a fetched recipe page's schema.org data says (food.py,
 *  _recipe_summary); "" / [] / {} where the page has nothing. Times are
 *  ISO 8601 durations ("PT280M"). */
export interface RecipeSummary {
  url: string;
  name: string;
  image: string;
  description: string;
  category: string;
  cuisine: string;
  yield: string;
  prep_time: string;
  cook_time: string;
  total_time: string;
  ingredients: string[];
  steps: string[];
  nutrition: Record<string, string>;
  rating: string;
  rating_count: string;
  comments: string;
  author: string;
  publisher: string;
}

/** One step of a recipe page's preparation: its text -- photo N it points
 *  at written "{{photo:N}}" -- and its photos, each with the numbers it
 *  shows (one, or several for a strip of them). */
export interface RecipeStep {
  text: string;
  images: { steps: number[]; url: string }[];
}

export interface DishInput {
  name: string;
  category: string;
  rating: number;
  image_url?: string | null;
  /** An uploaded image, as a data: URL (JPEG / PNG / WebP / GIF). */
  image_data?: string;
  url?: string;
  instructions?: string;
  /** The language name / category / instructions are written in; the server
   *  translates them into the others before saving. */
  lang?: string;
  prep_min?: number | null;
  cook_min?: number | null;
  total_min?: number | null;
  difficulty?: Difficulty;
  ingredients?: string;
}

async function j<T>(r: Response): Promise<T> {
  if (r.status === 401) {
    onAuthFailed();
    throw new Error("401 — not signed in");
  }
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text()}`);
  return r.json() as Promise<T>;
}

const JSON_HEADERS = { "content-type": "application/json" };

// Ratings are per-user; never serve one user's cached dish list to another.
const f = (url: string, init: RequestInit = {}) =>
  fetch(url, { cache: "no-store", ...init });

/** URL for a stored dish image filename. */
export const dishImageUrl = (file: string) =>
  `/api/food/images/${encodeURIComponent(file)}`;

export const foodApi = {
  list: () => f("/api/food/dishes").then(j<FoodData>),

  create: (body: DishInput) =>
    f("/api/food/dishes", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }).then(j<FoodData>),

  patch: (id: number, body: Partial<DishInput>) =>
    f(`/api/food/dishes/${id}`, {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }).then(j<FoodData>),

  /** Import (again) the recipe a dish links to; it runs on its own, the
   *  dish's `import` tells how it goes. */
  importRecipe: (id: number) =>
    f(`/api/food/dishes/${id}/import`, { method: "POST" }).then(j<FoodData>),

  remove: (id: number) =>
    f(`/api/food/dishes/${id}`, { method: "DELETE" }).then(j<FoodData>),

  /** Rename an ingredient of the list (into another: they merge), or set
   *  all of its conversions. */
  patchIngredient: (id: number, body: { name?: string; conversions?: Conversion[] }) =>
    f(`/api/food/ingredients/${id}`, {
      method: "PATCH",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    }).then(j<FoodData>),

  removeIngredient: (id: number) =>
    f(`/api/food/ingredients/${id}`, { method: "DELETE" }).then(j<FoodData>),

  /** The shopping list for these dishes (id -> how much, in its yield's unit). */
  grocery: (items: Record<number, number>) =>
    f("/api/food/grocery", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ items }),
    }).then(j<{ lines: GroceryLine[] }>),

  /** A page of GialloZafferano's search results. */
  recipeSearch: (q: string, page = 1) =>
    f(`/api/food/recipe-search?q=${encodeURIComponent(q)}&page=${page}`).then(
      j<{ results: RecipeHit[]; next_page: number | null }>,
    ),

  /** Fetch a recipe page; the server keeps it (HTML and metadata). */
  recipePage: (url: string) =>
    f("/api/food/recipe-page", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ url }),
    }).then(j<{ recipe: RecipeSummary }>),

  /** A recipe page as the server keeps it (fetched first if it isn't yet). */
  getRecipePage: (url: string) =>
    f(`/api/food/recipe-page?url=${encodeURIComponent(url)}`).then(
      j<{ recipe: RecipeSummary; preparation: RecipeStep[]; fetched_at: string }>,
    ),

  searchImages: (q: string, num = 60) =>
    f(`/api/food/image-search?q=${encodeURIComponent(q)}&num=${num}`).then(
      j<{ images: ImageHit[] }>,
    ),
};
