import { useCallback, useEffect, useRef, useState } from "react";
import { useVersionPoll } from "../api";
import {
  Dish,
  DishInput,
  FoodData,
  ImageHit,
  dishImageUrl,
  foodApi,
} from "./food";

function stars(rating: number): string {
  const full = Math.max(0, Math.min(Math.round(rating), 10));
  return full ? "★".repeat(full) + ` (${full})` : "—";
}

function ratingShort(rating: number): string {
  const full = Math.max(0, Math.min(Math.round(rating), 10));
  return full ? `★ ${full}` : "—";
}

// Zoom = target card (column) width in px; image height tracks it.
const ZOOM_MIN = 140;
const ZOOM_MAX = 460;
const ZOOM_DEFAULT = 240;

function loadZoom(): number {
  try {
    const v = Number(localStorage.getItem("foodZoom"));
    if (v >= ZOOM_MIN && v <= ZOOM_MAX) return v;
  } catch {
    /* private mode / blocked storage */
  }
  return ZOOM_DEFAULT;
}

export function FoodPanel() {
  const { food } = useVersionPoll();
  const [data, setData] = useState<FoodData | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Categories start collapsed; `expanded` holds the ones the user has opened,
  // `everOpened` gates whether a category's <img> nodes are mounted at all
  // (so nothing downloads until you open it), `imgLoaded` marks the ones whose
  // images have all finished — those skip the loading bar next time.
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [everOpened, setEverOpened] = useState<Set<string>>(() => new Set());
  const [imgLoaded, setImgLoaded] = useState<Set<string>>(() => new Set());
  const [editing, setEditing] = useState<Dish | "new" | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [zoom, setZoom] = useState<number>(loadZoom);

  const toggleCategory = useCallback((cat: string) => {
    setExpanded((s) => {
      const n = new Set(s);
      n.has(cat) ? n.delete(cat) : n.add(cat);
      return n;
    });
    setEverOpened((s) => (s.has(cat) ? s : new Set(s).add(cat)));
  }, []);

  const markLoaded = useCallback(
    (cat: string) => setImgLoaded((s) => (s.has(cat) ? s : new Set(s).add(cat))),
    [],
  );
  const appliedVersion = useRef(-1);
  const seenFood = useRef(0);

  useEffect(() => {
    try {
      localStorage.setItem("foodZoom", String(zoom));
    } catch {
      /* ignore */
    }
  }, [zoom]);

  const apply = useCallback((d: FoodData) => {
    setData(d);
    appliedVersion.current = d.version;
    setError(null);
  }, []);

  const load = useCallback(() => {
    foodApi.list().then(apply).catch((e) => setError(String(e)));
  }, [apply]);

  useEffect(() => load(), [load]);

  // Refetch only when the poll reports a food version we have not applied
  // ourselves (a change from another client). Mirrors PersonalPanel.
  useEffect(() => {
    if (food === seenFood.current) return;
    seenFood.current = food;
    if (data && food !== appliedVersion.current) load();
  }, [food, data, load]);

  const mutate = (p: Promise<FoodData>) =>
    p.then((d) => {
      apply(d);
      setEditing(null);
    }).catch((e) => setError(String(e)));

  if (error && !data)
    return (
      <div className="panel">
        <p className="error">{error}</p>
      </div>
    );
  if (!data)
    return (
      <div className="panel">
        <p className="muted">Loading…</p>
      </div>
    );

  const byCategory = (cat: string) =>
    data.dishes.filter((d) => (d.category || "Uncategorised") === cat);
  const groups = [
    ...data.categories,
    ...(data.dishes.some((d) => !d.category) ? ["Uncategorised"] : []),
  ].filter((c) => byCategory(c).length > 0);

  return (
    <div className="panel food">
      <div
        className="food-main"
        style={{ "--dish-col": `${zoom}px` } as React.CSSProperties}
      >
        <div className="food-head">
          <h2>Dishes</h2>
          <label className="food-zoom" title="Card size">
            <span aria-hidden>🔍</span>
            <input
              type="range"
              min={ZOOM_MIN}
              max={ZOOM_MAX}
              step={10}
              value={zoom}
              onChange={(e) => setZoom(Number(e.target.value))}
            />
          </label>
          <button className="active" onClick={() => setEditing("new")}>
            + Add dish
          </button>
        </div>
        {error && <p className="error small">{error}</p>}

        {groups.length === 0 && (
          <p className="muted">No dishes yet — add your first one.</p>
        )}

        {groups.map((cat) => {
          const dishes = byCategory(cat).sort((a, b) => b.rating - a.rating);
          const isOpen = expanded.has(cat);
          return (
            <section className="food-group" key={cat}>
              <h3
                className="food-group-head"
                onClick={() => toggleCategory(cat)}
              >
                <span className="chevron">{isOpen ? "▾" : "▸"}</span>
                {cat}
                <span className="muted"> ({dishes.length})</span>
              </h3>
              {everOpened.has(cat) && (
                <CategoryGrid
                  dishes={dishes}
                  collapsed={!isOpen}
                  loaded={imgLoaded.has(cat)}
                  onAllLoaded={() => markLoaded(cat)}
                  confirmDelete={confirmDelete}
                  onEdit={setEditing}
                  onArm={setConfirmDelete}
                  onCancelArm={() => setConfirmDelete(null)}
                  onDelete={(id) => {
                    setConfirmDelete(null);
                    mutate(foodApi.remove(id));
                  }}
                />
              )}
            </section>
          );
        })}
      </div>

      {editing && (
        <DishForm
          dish={editing === "new" ? null : editing}
          categories={data.categories}
          onCancel={() => setEditing(null)}
          onSubmit={(body) =>
            mutate(
              editing === "new"
                ? foodApi.create(body)
                : foodApi.patch(editing.id, body),
            )
          }
        />
      )}
    </div>
  );
}

/** One category's cards + a progress bar shown until every image in it has
 *  loaded (or errored). Once done it calls `onAllLoaded` and the parent stops
 *  passing `loaded={false}`, so re-opening the category is bar-free. Stays
 *  mounted while collapsed so images are never re-fetched. */
function CategoryGrid({
  dishes,
  collapsed,
  loaded,
  onAllLoaded,
  confirmDelete,
  onEdit,
  onArm,
  onCancelArm,
  onDelete,
}: {
  dishes: Dish[];
  collapsed: boolean;
  loaded: boolean;
  onAllLoaded: () => void;
  confirmDelete: number | null;
  onEdit: (d: Dish) => void;
  onArm: (id: number) => void;
  onCancelArm: () => void;
  onDelete: (id: number) => void;
}) {
  const total = dishes.filter((d) => d.image).length;
  const settled = useRef<Set<number>>(new Set());
  const [done, setDone] = useState(0);

  useEffect(() => {
    if (!loaded && done >= total) onAllLoaded();
  }, [loaded, done, total, onAllLoaded]);

  const onImgSettled = (id: number) => {
    if (settled.current.has(id)) return;
    settled.current.add(id);
    setDone((n) => n + 1);
  };

  const showBar = !collapsed && !loaded && total > 0 && done < total;

  return (
    <>
      {showBar && (
        <div className="cat-loading" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}>
          <span className="cat-loading-label muted small">
            Loading images… {done}/{total}
          </span>
          <div className="cat-loading-track">
            <div
              className="cat-loading-fill"
              style={{ width: `${(done / total) * 100}%` }}
            />
          </div>
        </div>
      )}
      <div className="dish-grid" hidden={collapsed}>
        {dishes.map((d) => (
          <DishCard
            key={d.id}
            dish={d}
            armed={confirmDelete === d.id}
            onEdit={() => onEdit(d)}
            onArm={() => onArm(d.id)}
            onCancelArm={onCancelArm}
            onDelete={() => onDelete(d.id)}
            onImgSettled={() => onImgSettled(d.id)}
          />
        ))}
      </div>
    </>
  );
}

function DishCard({
  dish,
  armed,
  onEdit,
  onArm,
  onCancelArm,
  onDelete,
  onImgSettled,
}: {
  dish: Dish;
  armed: boolean;
  onEdit: () => void;
  onArm: () => void;
  onCancelArm: () => void;
  onDelete: () => void;
  onImgSettled?: () => void;
}) {
  return (
    <div className="dish-card">
      <div className="dish-card-img">
        {dish.image ? (
          <img
            // No loading="lazy": the category itself is the lazy boundary
            // (images mount only after you open it), and the loading bar needs
            // every image in the category to actually start loading.
            src={dishImageUrl(dish.image)}
            alt={dish.name}
            ref={(el) => {
              // Cached images can be `complete` before onLoad would fire.
              if (el && el.complete) onImgSettled?.();
            }}
            onLoad={() => onImgSettled?.()}
            onError={() => onImgSettled?.()}
          />
        ) : (
          <span className="dish-card-img-empty">🍽</span>
        )}
      </div>
      <div className={"dish-card-foot" + (armed ? " armed" : "")}>
        {armed ? (
          <>
            <span className="confirm-label">Delete “{dish.name}”?</span>
            <div className="acts">
              <button className="danger" onClick={onDelete}>
                Delete
              </button>
              <button className="ghost" onClick={onCancelArm}>
                Cancel
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="meta">
              <div className="dish-name" title={dish.name}>
                {dish.name}
              </div>
              <div className="dish-stars" title={stars(dish.rating)}>
                {ratingShort(dish.rating)}
              </div>
            </div>
            <div className="acts">
              <button className="ghost" title="Edit" onClick={onEdit}>
                ✎
              </button>
              <button className="ghost danger" title="Delete" onClick={onArm}>
                🗑
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function DishForm({
  dish,
  categories,
  onCancel,
  onSubmit,
}: {
  dish: Dish | null;
  categories: string[];
  onCancel: () => void;
  onSubmit: (body: DishInput) => void;
}) {
  const [name, setName] = useState(dish?.name ?? "");
  const [category, setCategory] = useState(dish?.category ?? "");
  const [rating, setRating] = useState(dish?.rating ?? 7);
  // undefined = keep existing image; string = newly picked URL to download.
  const [pickedUrl, setPickedUrl] = useState<string | undefined>(undefined);
  const [pickerOpen, setPickerOpen] = useState(false);

  const preview = pickedUrl
    ? pickedUrl
    : dish?.image
      ? dishImageUrl(dish.image)
      : null;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    const body: DishInput = {
      name: name.trim(),
      category: category.trim(),
      rating,
    };
    if (pickedUrl !== undefined) body.image_url = pickedUrl;
    onSubmit(body);
  };

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <form
        className="modal dish-form"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h4>{dish ? "Edit dish" : "New dish"}</h4>

        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </label>

        <label>
          Category
          <input
            list="food-categories"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="e.g. Pasta"
          />
          <datalist id="food-categories">
            {categories.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </label>

        <label>
          Rating: <strong>{rating}</strong> {stars(rating)}
          <input
            type="range"
            min={0}
            max={10}
            value={rating}
            onChange={(e) => setRating(Number(e.target.value))}
          />
        </label>

        <div className="dish-form-image">
          <div className="dish-thumb">
            {preview ? (
              <img src={preview} alt="" />
            ) : (
              <span className="dish-thumb-empty">🍽</span>
            )}
          </div>
          <div className="col">
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
            >
              {preview ? "Change image…" : "Pick image…"}
            </button>
            {pickedUrl !== undefined && (
              <button
                type="button"
                className="ghost"
                onClick={() => setPickedUrl(undefined)}
              >
                Reset
              </button>
            )}
          </div>
        </div>

        <div className="row-actions">
          <button type="submit" className="active" disabled={!name.trim()}>
            {dish ? "Save" : "Create"}
          </button>
          <button type="button" className="ghost" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </form>

      {pickerOpen && (
        <ImagePicker
          initialQuery={name.trim() || category.trim()}
          onClose={() => setPickerOpen(false)}
          onPick={(url) => {
            setPickedUrl(url);
            setPickerOpen(false);
          }}
        />
      )}
    </div>
  );
}

function ImagePicker({
  initialQuery,
  onPick,
  onClose,
}: {
  initialQuery: string;
  onPick: (url: string) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<ImageHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  const run = (q: string) => {
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    setSearched(true);
    foodApi
      .searchImages(q.trim(), 60)
      .then((r) => setResults(r.images))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  return (
    <div className="modal-backdrop picker" onClick={onClose}>
      <div className="modal image-picker" onClick={(e) => e.stopPropagation()}>
        <form
          className="picker-search"
          onSubmit={(e) => {
            e.preventDefault();
            run(query);
          }}
        >
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search for an image…"
            autoFocus
          />
          <button type="submit">Search</button>
          <button type="button" className="ghost" onClick={onClose}>
            Close
          </button>
        </form>

        {loading && <p className="muted">Searching…</p>}
        {error && <p className="error small">{error}</p>}
        {!searched && !loading && (
          <p className="muted small">
            Type a search term and press <strong>Search</strong>.
          </p>
        )}

        <div className="picker-grid">
          {results.map((hit, i) => (
            <button
              type="button"
              key={hit.url + i}
              className="picker-cell"
              title={hit.title || hit.source}
              onClick={() => onPick(hit.url)}
            >
              <img src={hit.thumbnail} alt={hit.title} loading="lazy" />
            </button>
          ))}
        </div>
        {searched && !loading && !error && results.length === 0 && (
          <p className="muted">No results.</p>
        )}
      </div>
    </div>
  );
}
