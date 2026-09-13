import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import DOMPurify from "dompurify";
import { marked } from "marked";
import { useVersionPoll } from "../api";
import {
  Dish,
  DishInput,
  FoodData,
  ImageHit,
  dishImageUrl,
  foodApi,
} from "./food";
import {
  GroceryList,
  loadCheckedIngredients,
  loadGroceryList,
  saveCheckedIngredients,
  saveGroceryList,
} from "./grocery";

function stars(rating: number): string {
  const full = Math.max(0, Math.min(Math.round(rating), 10));
  return full ? "★".repeat(full) + ` (${full})` : "—";
}

function ratingShort(rating: number): string {
  const full = Math.max(0, Math.min(Math.round(rating), 10));
  return full ? `★ ${full}` : "—";
}

/** Renders LLM-generated markdown as HTML. The source text ultimately comes
 *  from a scraped third-party webpage via an LLM prompt, so it's untrusted —
 *  sanitize before it ever touches the DOM. */
function MarkdownView({ text }: { text: string }) {
  const html = useMemo(() => {
    const raw = marked.parse(text, { async: false, breaks: true }) as string;
    return DOMPurify.sanitize(raw);
  }, [text]);
  // eslint-disable-next-line react/no-danger
  return <div className="dish-info-body markdown" dangerouslySetInnerHTML={{ __html: html }} />;
}

// Zoom = target card (column) width in px; image height tracks it.
const ZOOM_MIN = 190; // was 140 -- too narrow left no room for the footer's icon buttons
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
  const [editingIngredients, setEditingIngredients] = useState<Dish | null>(null);
  const [editingInstructions, setEditingInstructions] = useState<Dish | null>(null);
  const [groceryList, setGroceryList] = useState<GroceryList>(() => loadGroceryList());
  const [groceryMode, setGroceryMode] = useState(false);
  const [pendingSelection, setPendingSelection] = useState<Set<number>>(() => new Set());
  const [checkedIngredients, setCheckedIngredients] = useState<Set<string>>(() => loadCheckedIngredients());

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

  // Checked-off shopping-list lines are only meaningful for the exact
  // selection/quantities that produced them -- any change to either
  // (a dish added/removed, a quantity stepped) changes the totals, so a
  // checkmark from before could now be sitting against a different amount
  // or a different set of ingredients entirely. Wipe it rather than carry
  // stale checks forward.
  const resetChecked = () => {
    setCheckedIngredients(new Set());
    saveCheckedIngredients(new Set());
  };

  // Drop grocery-list entries for dishes that got deleted, or whose
  // ingredients got cleared out from under it -- otherwise a stale id could
  // sit in the cookie forever pointing at nothing.
  useEffect(() => {
    if (!data) return;
    const eligible = new Set(data.dishes.filter((d) => d.ingredients).map((d) => d.id));
    setGroceryList((gl) => {
      const next: GroceryList = {};
      let changed = false;
      for (const [id, qty] of Object.entries(gl)) {
        if (eligible.has(Number(id))) next[Number(id)] = qty;
        else changed = true;
      }
      if (!changed) return gl;
      saveGroceryList(next);
      resetChecked();
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const enterGroceryMode = () => {
    setPendingSelection(new Set(Object.keys(groceryList).map(Number)));
    setGroceryMode(true);
  };
  const cancelSelection = () => setGroceryMode(false);
  const toggleSelect = (id: number) =>
    setPendingSelection((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  const confirmSelection = () => {
    const next: GroceryList = {};
    for (const id of pendingSelection) {
      if (groceryList[id] !== undefined) {
        next[id] = groceryList[id];
        continue;
      }
      // Default a newly-added dish to its own recipe quantity (e.g. "4"
      // servings) rather than an arbitrary 1 -- that's the no-scaling
      // starting point; stepping it changes how much of every ingredient
      // gets pulled into the summary below.
      const dish = data?.dishes.find((d) => d.id === id);
      const base = dish ? Number(parseIngredients(dish.ingredients).quantity) : NaN;
      next[id] = Number.isFinite(base) && base > 0 ? base : 1;
    }
    setGroceryList(next);
    saveGroceryList(next);
    resetChecked();
    setGroceryMode(false);
  };
  const setGroceryQty = (id: number, qty: number) => {
    setGroceryList((gl) => {
      const next = { ...gl, [id]: Math.max(1, qty) };
      saveGroceryList(next);
      return next;
    });
    resetChecked();
  };
  const removeFromGrocery = (id: number) => {
    setGroceryList((gl) => {
      const next = { ...gl };
      delete next[id];
      saveGroceryList(next);
      return next;
    });
    resetChecked();
  };
  const clearGroceryList = () => {
    setGroceryList({});
    saveGroceryList({});
    resetChecked();
  };
  const toggleChecked = (key: string) =>
    setCheckedIngredients((s) => {
      const n = new Set(s);
      n.has(key) ? n.delete(key) : n.add(key);
      saveCheckedIngredients(n);
      return n;
    });

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
          {groceryMode ? (
            <>
              <span className="muted small">{pendingSelection.size} selected</span>
              <button className="active" onClick={confirmSelection}>Done</button>
              <button className="ghost" onClick={cancelSelection}>Cancel</button>
            </>
          ) : (
            <>
              <button className="ghost" onClick={enterGroceryMode}>🛒 Grocery</button>
              <button className="active" onClick={() => setEditing("new")}>
                + Add dish
              </button>
            </>
          )}
        </div>
        {error && <p className="error small">{error}</p>}

        {!groceryMode && (
          <GroceryPanel
            dishes={data.dishes}
            list={groceryList}
            onQtyChange={setGroceryQty}
            onRemove={removeFromGrocery}
            onEdit={enterGroceryMode}
            onClear={clearGroceryList}
            checked={checkedIngredients}
            onToggleChecked={toggleChecked}
          />
        )}

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
                  onEditIngredients={setEditingIngredients}
                  onEditInstructions={setEditingInstructions}
                  groceryMode={groceryMode}
                  selection={pendingSelection}
                  onToggleSelect={toggleSelect}
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

      {editingIngredients && (
        <IngredientsEditor
          dish={editingIngredients}
          onCancel={() => setEditingIngredients(null)}
          onSaved={(d) => {
            apply(d);
            setEditingIngredients(null);
          }}
        />
      )}

      {editingInstructions && (
        <InstructionsEditor
          dish={editingInstructions}
          onCancel={() => setEditingInstructions(null)}
          onSaved={(d) => {
            apply(d);
            setEditingInstructions(null);
          }}
        />
      )}
    </div>
  );
}

/** One line in the shopping list: an ingredient name, optionally split by
 *  unit when two recipes measure it differently (grams vs a bare count,
 *  say) -- those can't be added together. `approximate` marks a line where
 *  some OTHER recipe also uses this ingredient but didn't give an amount at
 *  all, so the true total is at least this much. */
interface GroceryTotal {
  key: string; // "name::unit" -- also the sum key for same-name-same-unit amounts
  name: string;
  unit: string;
  amount: number | null; // null only when every contributor gave no quantity
  approximate: boolean;
}

function computeGroceryTotals(dishes: Dish[], list: GroceryList): GroceryTotal[] {
  // First pass: per ingredient name, sum same-unit amounts and separately
  // note whether *any* contributor gave no quantity at all.
  const byName = new Map<string, { byUnit: Map<string, number>; hasUnspecified: boolean }>();
  for (const [idStr, targetQty] of Object.entries(list)) {
    const dish = dishes.find((d) => d.id === Number(idStr));
    if (!dish) continue;
    const parsed = parseIngredients(dish.ingredients);
    const baseQty = Number(parsed.quantity);
    // No sane base to scale from (missing/zero/non-numeric) -> take the
    // recipe's amounts as-is rather than blow up on a division by zero.
    const factor = Number.isFinite(baseQty) && baseQty > 0 ? targetQty / baseQty : 1;
    for (const row of parsed.rows) {
      const name = row.name.trim();
      if (!name) continue;
      const unit = row.unit.trim();
      const entry = byName.get(name) ?? { byUnit: new Map<string, number>(), hasUnspecified: false };
      byName.set(name, entry);
      if (!row.quantity.trim()) {
        entry.hasUnspecified = true;
        continue;
      }
      entry.byUnit.set(unit, (entry.byUnit.get(unit) ?? 0) + Number(row.quantity) * factor);
    }
  }
  // Second pass: one output row per (name, unit) that actually has an
  // amount; a same-named contributor with no quantity attaches "+" to all
  // of them instead of becoming its own unmerged, number-less row.
  const totals: GroceryTotal[] = [];
  for (const [name, { byUnit, hasUnspecified }] of byName) {
    if (byUnit.size === 0) {
      totals.push({ key: `${name}::`, name, unit: "", amount: null, approximate: false });
      continue;
    }
    for (const [unit, amount] of byUnit) {
      totals.push({ key: `${name}::${unit}`, name, unit, amount, approximate: hasUnspecified });
    }
  }
  return totals.sort((a, b) => a.name.localeCompare(b.name));
}

function formatAmount(n: number): string {
  // Scaling can produce e.g. 166.66666...; round to something worth reading.
  const r = Math.round(n * 100) / 100;
  return String(r);
}

function GrocerySummary({
  items,
  checked,
  onToggle,
}: {
  items: GroceryTotal[];
  checked: Set<string>;
  onToggle: (key: string) => void;
}) {
  if (!items.length) return null;
  return (
    <div className="grocery-summary">
      <h4>Shopping list</h4>
      <ul className="grocery-summary-list">
        {items.map((it) => (
          <li key={it.key}>
            <label>
              <input
                type="checkbox"
                checked={checked.has(it.key)}
                onChange={() => onToggle(it.key)}
              />
              <span className="grocery-summary-name">{it.name}</span>
              {it.amount !== null && (
                <span className="grocery-summary-amount">
                  {formatAmount(it.amount)}
                  {it.unit ? ` ${it.unit}` : ""}
                  {it.approximate ? "+" : ""}
                </span>
              )}
            </label>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The persistent grocery list -- shown above the dish groups whenever it
 *  has anything in it: one row per selected dish with a quantity picker
 *  (in that dish's own recipe unit), then the combined shopping list below,
 *  every dish's ingredients scaled to the quantity picked for it and summed
 *  wherever two entries share the same ingredient name and unit. */
function GroceryPanel({
  dishes,
  list,
  onQtyChange,
  onRemove,
  onEdit,
  onClear,
  checked,
  onToggleChecked,
}: {
  dishes: Dish[];
  list: GroceryList;
  onQtyChange: (id: number, qty: number) => void;
  onRemove: (id: number) => void;
  onEdit: () => void;
  onClear: () => void;
  checked: Set<string>;
  onToggleChecked: (key: string) => void;
}) {
  const byId = new Map(dishes.map((d) => [d.id, d]));
  const entries = Object.entries(list)
    .map(([id, qty]) => ({ dish: byId.get(Number(id)), qty }))
    .filter((e): e is { dish: Dish; qty: number } => Boolean(e.dish));

  if (!entries.length) return null;

  const totals = computeGroceryTotals(dishes, list);

  return (
    <section className="grocery-panel">
      <div className="grocery-panel-head">
        <h3>🛒 Grocery list</h3>
        <div className="row-actions">
          <button type="button" className="ghost" onClick={onEdit}>
            Edit selection
          </button>
          <button type="button" className="ghost danger" onClick={onClear}>
            Clear
          </button>
        </div>
      </div>
      <div className="grocery-items">
        {entries.map(({ dish, qty }) => {
          const unit = parseIngredients(dish.ingredients).unit;
          return (
            <div className="grocery-item" key={dish.id}>
              <span className="grocery-item-name">{dish.name}</span>
              <QuantityStepper value={qty} unit={unit} onChange={(n) => onQtyChange(dish.id, n)} />
              <button
                type="button"
                className="ghost danger"
                title="Remove from list"
                onClick={() => onRemove(dish.id)}
              >
                🗑
              </button>
            </div>
          );
        })}
      </div>
      <GrocerySummary items={totals} checked={checked} onToggle={onToggleChecked} />
    </section>
  );
}

function QuantityStepper({
  value,
  unit,
  onChange,
  min = 1,
}: {
  value: number;
  unit?: string;
  onChange: (n: number) => void;
  min?: number;
}) {
  return (
    <div className="qty-stepper">
      <button
        type="button"
        className="ghost"
        onClick={() => onChange(Math.max(min, value - 1))}
        disabled={value <= min}
      >
        −
      </button>
      <span className="qty-value">
        {value}
        {unit ? ` ${unit}` : ""}
      </span>
      <button type="button" className="ghost" onClick={() => onChange(value + 1)}>
        +
      </button>
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
  onEditIngredients,
  onEditInstructions,
  groceryMode,
  selection,
  onToggleSelect,
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
  onEditIngredients: (d: Dish) => void;
  onEditInstructions: (d: Dish) => void;
  groceryMode: boolean;
  selection: Set<number>;
  onToggleSelect: (id: number) => void;
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
            onEditIngredients={() => onEditIngredients(d)}
            onEditInstructions={() => onEditInstructions(d)}
            groceryMode={groceryMode}
            selected={selection.has(d.id)}
            onToggleSelect={() => onToggleSelect(d.id)}
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
  onEditIngredients,
  onEditInstructions,
  groceryMode,
  selected,
  onToggleSelect,
}: {
  dish: Dish;
  armed: boolean;
  onEdit: () => void;
  onArm: () => void;
  onCancelArm: () => void;
  onDelete: () => void;
  onImgSettled?: () => void;
  onEditIngredients: () => void;
  onEditInstructions: () => void;
  groceryMode: boolean;
  selected: boolean;
  onToggleSelect: () => void;
}) {
  const processed = Boolean(dish.instructions || dish.ingredients);
  const eligibleForGrocery = Boolean(dish.ingredients);
  const img = dish.image ? (
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
  );

  if (groceryMode) {
    // A simplified, read-only card: the whole thing is the toggle, so none
    // of the normal per-dish actions (edit/delete/instructions/ingredients)
    // are reachable here -- avoids them firing alongside a selection toggle.
    return (
      <div
        className={
          "dish-card grocery-select" +
          (eligibleForGrocery ? "" : " ineligible") +
          (selected ? " selected" : "")
        }
        onClick={eligibleForGrocery ? onToggleSelect : undefined}
        title={eligibleForGrocery ? undefined : "No ingredients yet — can't add to a grocery list"}
      >
        <div className="dish-card-img">
          {img}
          <div className="dish-card-select-mark" aria-hidden>
            {selected ? "☑" : "☐"}
          </div>
        </div>
        <div className="dish-card-foot">
          <div className="meta">
            <div className="dish-name" title={dish.name}>
              {dish.name}
            </div>
            <div className="dish-stars" title={stars(dish.rating)}>
              {ratingShort(dish.rating)}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="dish-card">
      <button
        type="button"
        className="dish-card-img clickable"
        onClick={onEditIngredients}
        title={dish.ingredients ? "Edit ingredients" : "Add ingredients"}
      >
        {img}
      </button>
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
              {dish.url && !processed && (
                <span
                  className={"dish-status-dot " + (dish.has_text ? "ok" : "bad")}
                  title={dish.has_text ? "Recipe text saved" : "Recipe text not fetched yet"}
                />
              )}
              <button
                className="ghost"
                title={dish.instructions ? "Edit instructions" : "Add instructions"}
                onClick={onEditInstructions}
              >
                📄
              </button>
              {dish.url && (
                <button
                  className="ghost"
                  title={`Open recipe: ${dish.url}`}
                  onClick={() => window.open(dish.url, "_blank", "noopener,noreferrer")}
                >
                  🔗
                </button>
              )}
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

function InstructionsEditor({
  dish,
  onCancel,
  onSaved,
}: {
  dish: Dish;
  onCancel: () => void;
  onSaved: (d: FoodData) => void;
}) {
  // Nothing to look at yet -> go straight to editing; otherwise show the
  // rendered result first, with an explicit Edit step.
  const [mode, setMode] = useState<"view" | "edit">(dish.instructions ? "view" : "edit");
  const [text, setText] = useState(dish.instructions);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = () => {
    setSaving(true);
    setError(null);
    foodApi
      .patch(dish.id, { instructions: text })
      .then(onSaved)
      .catch((e) => setError(String(e)))
      .finally(() => setSaving(false));
  };

  return (
    <div className="modal-backdrop">
      <div className="modal dish-info" onClick={(e) => e.stopPropagation()}>
        <h4>{dish.name} — Instructions</h4>
        {mode === "edit" ? (
          <textarea
            className="dish-info-edit"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={12}
            placeholder="Write the steps in Markdown…"
            autoFocus
          />
        ) : (
          <MarkdownView text={dish.instructions} />
        )}
        {error && <p className="error small">{error}</p>}
        <div className="row-actions">
          {mode === "edit" ? (
            <>
              <button type="button" className="active" onClick={save} disabled={saving}>
                {saving ? "Saving…" : "Save"}
              </button>
              <button
                type="button"
                className="ghost"
                onClick={() => {
                  setText(dish.instructions);
                  if (dish.instructions) setMode("view");
                  else onCancel();
                }}
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              <button type="button" className="active" onClick={() => setMode("edit")}>
                Edit
              </button>
              <button type="button" className="ghost" onClick={onCancel}>
                Close
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

interface IngredientRow {
  name: string;
  quantity: string;
  unit: string;
}

// Each ingredient is stored as its own {quantity, unit} object server-side
// (see api/services/food.py's _validate_ingredients_json) specifically so
// the editor never has to parse/split a combined "<number><unit>" string.
function parseIngredients(raw: string): { quantity: string; unit: string; rows: IngredientRow[] } {
  if (!raw.trim()) return { quantity: "", unit: "", rows: [] };
  try {
    const data = JSON.parse(raw) as {
      quantity?: unknown;
      unit?: unknown;
      ingredients?: Record<string, { quantity?: unknown; unit?: unknown }>;
    };
    const entries = Object.entries(data.ingredients ?? {});
    const rows = entries.map(([name, v]) => ({
      name,
      quantity: String(v?.quantity ?? ""),
      unit: String(v?.unit ?? ""),
    }));
    return { quantity: String(data.quantity ?? ""), unit: String(data.unit ?? ""), rows };
  } catch {
    return { quantity: "", unit: "", rows: [] };
  }
}

const LOWER_WORD_RE = /^[a-z]+(?: [a-z]+)*$/;
const PLAIN_NUMBER_RE = /^\d+(?:\.\d+)?$/;

/** Same shape rules as the backend's _validate_ingredients_json, applied
 *  per-field since the editor keeps quantity/unit apart. null = valid. */
function rowError(r: IngredientRow): string | null {
  const name = r.name.trim();
  const qty = r.quantity.trim();
  const unit = r.unit.trim();
  if (name && !LOWER_WORD_RE.test(name)) return "name must be lowercase letters only";
  if (qty && !PLAIN_NUMBER_RE.test(qty)) return "quantity must be a number, or left blank";
  if (unit && !LOWER_WORD_RE.test(unit)) return "unit must be lowercase letters only";
  if (unit && !qty) return "a unit needs a quantity";
  return null;
}

function IngredientsEditor({
  dish,
  onCancel,
  onSaved,
}: {
  dish: Dish;
  onCancel: () => void;
  onSaved: (d: FoodData) => void;
}) {
  const initial = useMemo(() => parseIngredients(dish.ingredients), [dish.ingredients]);
  const [quantity, setQuantity] = useState(initial.quantity);
  const [unit, setUnit] = useState(initial.unit);
  const [rows, setRows] = useState<IngredientRow[]>(initial.rows);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateRow = (i: number, patch: Partial<IngredientRow>) =>
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  const removeRow = (i: number) => setRows((rs) => rs.filter((_, idx) => idx !== i));
  const addRow = () => setRows((rs) => [...rs, { name: "", quantity: "", unit: "" }]);
  const lower = (s: string) => s.toLowerCase();

  const save = () => {
    setError(null);
    // Mirrors the backend's own checks (see _validate_ingredients_json) so a
    // bad row is flagged before a round trip, not just via whatever error
    // text a failed PATCH happens to return.
    const bad = rows.filter((r) => r.name.trim() && rowError(r));
    if (bad.length) {
      setError("Fix the highlighted ingredient(s) before saving.");
      return;
    }
    const ingredients: Record<string, { quantity: string; unit: string }> = {};
    for (const r of rows) {
      const name = r.name.trim();
      if (!name) continue;
      ingredients[name] = { quantity: r.quantity.trim(), unit: r.unit.trim() };
    }
    // No rows left -> clear the field entirely (an empty {} would fail the
    // backend's "non-empty object" check, and isn't what "cleared" means).
    const payload = Object.keys(ingredients).length
      ? JSON.stringify({ quantity: quantity.trim(), unit: unit.trim(), ingredients })
      : "";
    setSaving(true);
    foodApi
      .patch(dish.id, { ingredients: payload })
      .then(onSaved)
      .catch((e) => setError(String(e)))
      .finally(() => setSaving(false));
  };

  return (
    <div className="modal-backdrop">
      <div className="modal dish-info" onClick={(e) => e.stopPropagation()}>
        <h4>{dish.name} — Ingredients</h4>
        <div className="dish-info-scroll">
          <div className="ingredients-top">
            <label>
              Quantity
              <input value={quantity} onChange={(e) => setQuantity(e.target.value)} placeholder="e.g. 4" />
            </label>
            <label>
              Unit
              <input value={unit} onChange={(e) => setUnit(lower(e.target.value))} placeholder="e.g. persons" />
            </label>
          </div>
          <div className="ingredients-rows">
            {rows.map((r, i) => {
              const err = r.name.trim() ? rowError(r) : null;
              return (
                <div key={i}>
                  <div className={"ingredients-row" + (err ? " invalid" : "")}>
                    <input
                      value={r.name}
                      onChange={(e) => updateRow(i, { name: lower(e.target.value) })}
                      placeholder="name"
                    />
                    <input
                      value={r.quantity}
                      onChange={(e) => updateRow(i, { quantity: e.target.value })}
                      placeholder="qty"
                    />
                    <input
                      value={r.unit}
                      onChange={(e) => updateRow(i, { unit: lower(e.target.value) })}
                      placeholder="unit"
                    />
                    <button type="button" className="ghost danger" title="Remove" onClick={() => removeRow(i)}>
                      🗑
                    </button>
                  </div>
                  {err && <div className="ingredients-row-error">{err}</div>}
                </div>
              );
            })}
          </div>
          <button type="button" className="ghost" onClick={addRow}>
            + Add ingredient
          </button>
        </div>
        {error && <p className="error small">{error}</p>}
        <div className="row-actions">
          <button type="button" className="active" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
          <button type="button" className="ghost" onClick={onCancel}>
            Cancel
          </button>
        </div>
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
  const [recipeUrl, setRecipeUrl] = useState(dish?.url ?? "");
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
      url: recipeUrl.trim(),
    };
    if (pickedUrl !== undefined) body.image_url = pickedUrl;
    onSubmit(body);
  };

  return (
    <div className="modal-backdrop">
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
          Recipe URL
          <input
            type="url"
            value={recipeUrl}
            onChange={(e) => setRecipeUrl(e.target.value)}
            placeholder="https://…"
          />
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
    <div className="modal-backdrop picker">
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
