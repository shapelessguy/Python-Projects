// Food service client — self-contained module. The only shared touch-points
// are the auth 401 hook and the version poll (see ../api.ts `food` field).
import { onAuthFailed } from "../auth";

export interface Dish {
  id: number;
  name: string;
  category: string;
  rating: number;
  image: string;
  url: string;
  has_text: boolean;
  instructions: string;
  ingredients: string;
}

export interface FoodData {
  dishes: Dish[];
  categories: string[];
  version: number;
}

export interface ImageHit {
  url: string;
  thumbnail: string;
  title: string;
  source: string;
}

export interface DishInput {
  name: string;
  category: string;
  rating: number;
  image_url?: string | null;
  url?: string;
  instructions?: string;
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

  remove: (id: number) =>
    f(`/api/food/dishes/${id}`, { method: "DELETE" }).then(j<FoodData>),

  searchImages: (q: string, num = 60) =>
    f(`/api/food/image-search?q=${encodeURIComponent(q)}&num=${num}`).then(
      j<{ images: ImageHit[] }>,
    ),
};
