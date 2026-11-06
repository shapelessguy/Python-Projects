import type React from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import DOMPurify from "dompurify";
import { marked } from "marked";
import { useVersionPoll } from "../api";
import {
  CatalogIngredient,
  Category,
  Dish,
  DishInput,
  Conversion,
  DishFacts,
  Difficulty,
  FoodData,
  GroceryLine,
  ImageHit,
  Macro,
  RecipeHit,
  RecipeStep,
  RecipeSummary,
  SplitPart,
  UnitDef,
  dishImageUrl,
  dishSmallUrl,
  foodApi,
} from "./food";
import { SizeSlider } from "./SizeSlider";
import { Key, useT } from "../i18n";
import {
  GroceryList,
  Bought,
  CheckedIngredients,
  loadCheckedIngredients,
  loadGroceryList,
  saveCheckedIngredients,
  saveGroceryList,
} from "./grocery";
import { createPortal } from "react-dom";
import { useBackToClose } from "../backClose";
import { ConfirmDialog } from "../ConfirmDialog";
import { usePhone } from "../narrow";
import { useDragScroll } from "../dragScroll";

function stars(rating: number): string {
  const full = Math.max(0, Math.min(Math.round(rating), 10));
  return full ? "★".repeat(full) + ` (${full})` : "—";
}

function ratingShort(rating: number): string {
  const full = Math.max(0, Math.min(Math.round(rating), 10));
  return full ? `★ ${full}` : "—";
}

/** An ingredient's name in the UI's language, English until it has one. */
const ingredientName = (c: CatalogIngredient, lang: string) => (lang !== "en" && c.names?.[lang]) || c.name;

/** A dish's name in the UI's language, English until it has one. */
const dishName = (d: Dish, lang: string) => d.name_tr?.[lang] || d.name;

/** A shopping-list line's amounts, as what was bought when it is ticked. */
const boughtOf = (line: GroceryLine): Bought =>
  Object.fromEntries(line.parts.map((p) => [p.macro, p.base]));

/** Whether what was bought still covers `line`: every part at most as much
 *  as was bought in its macro. A line with no amounts ("to taste") always
 *  is. A part from an older server, without its base, can't be compared
 *  and doesn't count against. */
const covers = (bought: Bought, line: GroceryLine) =>
  line.parts.every((p) => p.base === undefined || (bought[p.macro] ?? -1) >= p.base - 1e-6);

/** Lower case, accents dropped: "Caffè" is found by "caffe". */
const fold = (s: string) => s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();

/** The open / loaded sets' key for a category's group: its id ("" for the
 *  uncategorised), so a rename keeps it open. */
const groupKey = (c: Category | null) => (c ? String(c.id) : "");

// null is the dishes with no category, shown last.
const byCategoryOf = (data: FoodData, cat: Category | null) =>
  data.dishes.filter((d) => d.category_id === (cat?.id ?? null));
const categoryGroups = (data: FoodData) => [
  ...data.categories,
  ...(data.dishes.some((d) => d.category_id === null) ? [null] : []),
].filter((c) => byCategoryOf(data, c).length > 0);

const LONG_PRESS_MS = 500;

/** A long press (touch) or a right click (mouse) on an element:
 *  `press(onLong, onClick)` gives the handlers to spread on it. The click a
 *  long press ends with is swallowed, so it doesn't also count as a tap. One
 *  timer for every element -- only one is ever being pressed. */
function useLongPress() {
  const timer = useRef<number | undefined>(undefined);
  const fired = useRef(false);
  const origin = useRef<[number, number]>([0, 0]);
  const cancel = () => { window.clearTimeout(timer.current); timer.current = undefined; };
  return (onLong: () => void, onClick?: () => void) => ({
    onPointerDown: (e: React.PointerEvent) => {
      fired.current = false;
      if (e.pointerType === "mouse") return;
      origin.current = [e.clientX, e.clientY];
      cancel();
      timer.current = window.setTimeout(() => { timer.current = undefined; fired.current = true; onLong(); }, LONG_PRESS_MS);
    },
    // A finger that moves is scrolling, not pressing.
    onPointerMove: (e: React.PointerEvent) => {
      if (timer.current !== undefined
          && Math.hypot(e.clientX - origin.current[0], e.clientY - origin.current[1]) > 10) cancel();
    },
    onPointerUp: cancel,
    onPointerCancel: cancel,
    // Right click -- and Android's own long press, which may beat the timer.
    onContextMenu: (e: React.MouseEvent) => {
      e.preventDefault();
      cancel();
      if (!fired.current) { fired.current = true; onLong(); }
    },
    onClick: () => {
      if (fired.current) { fired.current = false; return; }
      onClick?.();
    },
  });
}
/** What a dish's yield counts ("persone"), in `lang` -- English until it has it. */
const yieldUnit = (d: Dish, lang: string) =>
  (lang !== "en" && d.yield_unit_tr?.[lang]) || parseIngredients(d.ingredients).unit;

/** Renders LLM-generated markdown as HTML. The source text ultimately comes
 *  from a scraped third-party webpage via an LLM prompt, so it's untrusted —
 *  sanitize before it ever touches the DOM. */
function MarkdownView({ text, photos }: { text: string; photos?: Record<string, string> }) {
  const html = useMemo(() => {
    // {{ref:N}}, the text's mention of photo N, reads as its number;
    // {{photo:N}} is the photo itself, put where it stands (withPhotos).
    const marked_ = text
      // A line of photos above a step is a block of its own: a list may
      // start right under a paragraph only at 1.
      .replace(/^((?:\{\{photo:\d+\}\}[ \t]*)+)\n(?!\n)/gm, "$1\n\n")
      .replace(/\{\{ref:(\d+)\}\}/g, '<span class="photo-badge">$1</span>')
      .replace(/\{\{photo:(\d+)\}\}/g, '<span class="photo-slot" data-photo="$1"></span>');
    const raw = marked.parse(marked_, { async: false, breaks: true }) as string;
    const clean = DOMPurify.sanitize(raw);
    return clean.includes("photo-slot") ? withPhotos(clean, photos ?? {}) : clean;
  }, [text, photos]);
  // eslint-disable-next-line react/no-danger
  return <div className="dish-info-body markdown" dangerouslySetInnerHTML={{ __html: html }} />;
}

/** Sanitized instructions HTML with each {{photo:N}} slot as photo N --
 *  side by side with the slots next to it, a paragraph of nothing but
 *  photos becoming their row; captioned with its number unless a strip of
 *  several. A slot with no photo (one that couldn't be downloaded) goes. */
function withPhotos(html: string, photos: Record<string, string>): string {
  const doc = new DOMParser().parseFromString(`<div>${html}</div>`, "text/html");
  const root = doc.body.firstElementChild as HTMLElement;
  const shared = new Map<string, number>();  // file -> how many numbers show it
  for (const f of Object.values(photos)) shared.set(f, (shared.get(f) ?? 0) + 1);
  const isBlank = (n: Node | null) => n?.nodeType === Node.TEXT_NODE && !n.textContent?.trim()
    || (n as Element | null)?.tagName === "BR";
  for (const slot of [...root.querySelectorAll<HTMLElement>(".photo-slot")]) {
    const n = slot.dataset.photo ?? "";
    const file = photos[n];
    if (!file) { slot.remove(); continue; }
    const fig = doc.createElement("figure");
    const img = doc.createElement("img");
    img.src = dishImageUrl(file);
    img.loading = "lazy";
    fig.appendChild(img);
    if (shared.get(file) === 1) {
      const cap = doc.createElement("figcaption");
      cap.textContent = n;
      fig.appendChild(cap);
    }
    let prev = slot.previousSibling;
    while (prev && isBlank(prev)) prev = prev.previousSibling;
    if ((prev as Element | null)?.classList?.contains("recipe-viewer-photos")) {
      prev!.appendChild(fig);
      slot.remove();
    } else {
      const grid = doc.createElement("div");
      grid.className = "recipe-viewer-photos";
      grid.appendChild(fig);
      slot.replaceWith(grid);
    }
  }
  for (const grid of root.querySelectorAll(".recipe-viewer-photos")) {
    if (grid.children.length === 1) grid.classList.add("single");
    const p = grid.parentElement!;
    if (p.tagName === "P" && [...p.childNodes].every((n) => n === grid || isBlank(n))) p.replaceWith(grid);
  }
  return root.innerHTML;
}

// Zoom = target card (column) width in px; image height tracks it.
const ZOOM_MIN = 110; // phone-sized; the footer's buttons wrap below 160px (styles.css)
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
  const { t, lang } = useT();
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
  // The category whose name is being edited in its heading.
  const [renaming, setRenaming] = useState<number | null>(null);
  const [zoom, setZoom] = useState<number>(loadZoom);
  const [editingIngredients, setEditingIngredients] = useState<Dish | null>(null);
  // The dish whose recipe import is being watched (ImportProgress).
  const [watching, setWatching] = useState<number | null>(null);
  const [showCatalog, setShowCatalog] = useState(false);
  const [groceryList, setGroceryList] = useState<GroceryList>(() => loadGroceryList());
  const [groceryMode, setGroceryMode] = useState(false);
  const [pendingSelection, setPendingSelection] = useState<Set<number>>(() => new Set());
  const [checkedIngredients, setCheckedIngredients] = useState<CheckedIngredients>(() => loadCheckedIngredients());
  // Phone: categories are chips, one open at a time, and the grocery list is
  // a full-screen sheet opened from 🛒 rather than a block atop the dishes.
  const phone = usePhone();
  const [showGrocery, setShowGrocery] = useState(false);
  const [query, setQuery] = useState("");
  const press = useLongPress();
  // .panel.food scrolls; .food-top (heading, chips) sticks at its top.
  const scrollRef = useRef<HTMLDivElement>(null);
  const topRef = useRef<HTMLDivElement>(null);
  const groupsRef = useRef<HTMLDivElement>(null);
  // Where a touch on the dishes started: a sideways swipe changes category.
  const swipeFrom = useRef<[number, number] | null>(null);

  const toggleCategory = useCallback((cat: string) => {
    setExpanded((s) => {
      const n = new Set(s);
      n.has(cat) ? n.delete(cat) : n.add(cat);
      return n;
    });
    setEverOpened((s) => (s.has(cat) ? s : new Set(s).add(cat)));
  }, []);

  // A chip: that category alone, remembered for next time. If the page is
  // scrolled into the dishes, back to the top of them, so the new category
  // starts at its first row.
  const selectCategory = useCallback((cat: string) => {
    setExpanded(new Set([cat]));
    setEverOpened((s) => (s.has(cat) ? s : new Set(s).add(cat)));
    try {
      localStorage.setItem("foodCat", cat);
    } catch {
      /* ignore */
    }
    const panel = scrollRef.current, top = topRef.current, groups = groupsRef.current;
    if (panel && top && groups) {
      const gap = groups.getBoundingClientRect().top - top.getBoundingClientRect().bottom;
      if (gap < 0) panel.scrollTop += gap;
    }
  }, []);

  // Chips always show a category: the last one picked, else the first.
  useEffect(() => {
    if (!phone || !data || query) return;
    const keys = categoryGroups(data).map(groupKey);
    if (keys.some((k) => expanded.has(k))) return;
    let saved: string | null = null;
    try {
      saved = localStorage.getItem("foodCat");
    } catch {
      /* ignore */
    }
    const pick = saved !== null && keys.includes(saved) ? saved : keys[0];
    if (pick !== undefined) selectCategory(pick);
  }, [phone, data, query, expanded, selectCategory]);

  const markLoaded = useCallback(
    (cat: string) => setImgLoaded((s) => (s.has(cat) ? s : new Set(s).add(cat))),
    [],
  );
  // Each open category's images loaded so far, of how many: a bar at the
  // right of its heading until they all are.
  const [imgProgress, setImgProgress] = useState<Record<string, [number, number]>>({});
  const reportProgress = useCallback(
    (cat: string, done: number, total: number) => setImgProgress((p) => {
      const was = p[cat];
      return was && was[0] === done && was[1] === total ? p : { ...p, [cat]: [done, total] };
    }),
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
      return d;
    }).catch((e) => { setError(serverMessage(e)); return null; });

  // Checked-off shopping-list lines (bought) survive changes to the
  // selection -- a dish added or removed, a quantity stepped -- since what
  // is already in the bag stays bought. Only clearing the list as a whole
  // starts them over.
  const resetChecked = () => {
    setCheckedIngredients(new Map());
    saveCheckedIngredients(new Map());
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
    setGroceryMode(false);
    if (phone && Object.keys(next).length) setShowGrocery(true);
  };
  const setGroceryQty = (id: number, qty: number) => {
    setGroceryList((gl) => {
      const next = { ...gl, [id]: Math.max(1, qty) };
      saveGroceryList(next);
      return next;
    });
  };
  const removeFromGrocery = (id: number) => {
    setGroceryList((gl) => {
      const next = { ...gl };
      delete next[id];
      saveGroceryList(next);
      return next;
    });
  };
  const clearGroceryList = () => {
    setGroceryList({});
    saveGroceryList({});
    resetChecked();
    setShowGrocery(false);
  };
  // Ticking a line keeps what it asks for now as what was bought.
  const toggleChecked = (line: GroceryLine) =>
    setCheckedIngredients((s) => {
      const n = new Map(s);
      n.has(line.key) ? n.delete(line.key) : n.set(line.key, boughtOf(line));
      saveCheckedIngredients(n);
      return n;
    });
  // A new shopping list (the selection or a quantity changed): a ticked line
  // that now needs more than was bought, of any of its parts, is unticked --
  // less, or the same, stays bought. Legacy ticks (no amounts) take the
  // line's amounts as bought. Lines not on the list keep their tick.
  const reconcileChecked = useCallback((lines: GroceryLine[]) =>
    setCheckedIngredients((s) => {
      let n: CheckedIngredients | null = null;
      for (const line of lines) {
        if (!s.has(line.key)) continue;
        const bought = s.get(line.key);
        if (bought && covers(bought, line)) continue;
        n ??= new Map(s);
        if (bought) n.delete(line.key);
        else n.set(line.key, boughtOf(line));
      }
      if (!n) return s;
      saveCheckedIngredients(n);
      return n;
    }), []);

  if (error && !data)
    return (
      <div className="panel">
        <p className="error">{error}</p>
      </div>
    );
  // Loading: the heading as it will be, a bar running at its right -- the
  // page doesn't jump when the dishes come.
  if (!data)
    return (
      <div className="panel food">
        <div className="food-main">
          <div className="food-head">
            <h2>{t("food_dishes")}</h2>
            <div className="load-bar indeterminate" role="progressbar" aria-label={t("loading")} title={t("loading")}>
              <div className="load-bar-fill" />
            </div>
          </div>
        </div>
      </div>
    );

  const byCategory = (cat: Category | null) => byCategoryOf(data, cat);
  const groups = categoryGroups(data);
  // Searching shows every category with a match, open, and only the matches.
  const q = fold(query.trim());
  const searching = q !== "";
  const matches = (d: Dish) =>
    [d.name, ...Object.values(d.name_tr ?? {})].some((n) => n && fold(n).includes(q));
  const chips = phone && !searching;
  // Phone: a sideways swipe over the dishes goes to the next / previous
  // category, as the chips run (no wrapping round). Mostly sideways and long
  // enough, so a scroll down the dishes is never one.
  const swipe = chips ? {
    onTouchStart: (e: React.TouchEvent) => {
      swipeFrom.current = e.touches.length === 1 ? [e.touches[0].clientX, e.touches[0].clientY] : null;
    },
    onTouchEnd: (e: React.TouchEvent) => {
      const from = swipeFrom.current;
      swipeFrom.current = null;
      if (!from) return;
      const dx = e.changedTouches[0].clientX - from[0], dy = e.changedTouches[0].clientY - from[1];
      if (Math.abs(dx) < 60 || Math.abs(dx) < 2 * Math.abs(dy)) return;
      const keys = groups.map(groupKey);
      const at = keys.findIndex((k) => expanded.has(k));
      const next = keys[at + (dx < 0 ? 1 : -1)];
      if (at >= 0 && next !== undefined) selectCategory(next);
    },
  } : {};
  const groceryCount = Object.keys(groceryList).length;
  const onGroceryButton = () => (phone && groceryCount ? setShowGrocery(true) : enterGroceryMode());
  const renameEditor = (c: Category) => (
    <CategoryNameEdit
      initial={c.tr[lang] || c.name}
      onCancel={() => setRenaming(null)}
      onSave={(name) => foodApi.renameCategory(c.id, name, lang)
        .then((d) => { apply(d); setRenaming(null); })
        .catch((e) => setError(serverMessage(e)))}
    />
  );
  // Long press / right click on a category's name renames it.
  const renamable = (c: Category | null) => Boolean(c) && !groceryMode && renaming !== c?.id;
  const groupLabel = (c: Category | null) => (c ? c.tr[lang] || c.name : t("food_uncategorised"));
  const groupProgress = (cat: string, open: boolean) => {
    const progress = imgProgress[cat];
    return open && !imgLoaded.has(cat) && progress && progress[1] > 0 && progress[0] < progress[1] ? progress : null;
  };
  const groceryProps = {
    dishes: data.dishes,
    catalog: data.ingredients ?? [],
    version: data.version,
    list: groceryList,
    onQtyChange: setGroceryQty,
    onRemove: removeFromGrocery,
    onClear: clearGroceryList,
    checked: checkedIngredients,
    onToggleChecked: toggleChecked,
    onLines: reconcileChecked,
  };

  return (
    <div className="panel food" ref={scrollRef}>
      <div
        className={"food-main" + (chips ? " food--chips" : "")}
        style={{ "--dish-col": `${zoom}px` } as React.CSSProperties}
      >
        <div className="food-top" ref={topRef}>
          <div className="food-head">
            <h2>{t("food_dishes")}</h2>
            <input type="search" className="food-search" placeholder={t("food_search")} aria-label={t("food_search")}
                   value={query} onChange={(e) => setQuery(e.target.value)}
                   onKeyDown={(e) => { if (e.key === "Escape") setQuery(""); }} />
            <label className="food-zoom" title={t("food_card_size")}>
              <span aria-hidden>🔍</span>
              <SizeSlider min={ZOOM_MIN} max={ZOOM_MAX} step={10} value={zoom} title={t("food_card_size")} onChange={setZoom} />
            </label>
            {groceryMode ? (
              <>
                <span className="muted small food-selected">{t("food_selected", { n: pendingSelection.size })}</span>
                <button className="active" onClick={confirmSelection}>{t("done")}</button>
                <button className="ghost" onClick={cancelSelection}>{t("cancel")}</button>
              </>
            ) : (
              <>
                {/* The words go on a phone (.btn-text), leaving the icons. */}
                <button className="ghost" title={t("food_ingredients")} onClick={() => setShowCatalog(true)}>
                  🥕<span className="btn-text"> {t("food_ingredients")}</span>
                </button>
                <button className="ghost food-grocery-btn" title={t("food_grocery")} onClick={onGroceryButton}>
                  🛒<span className="btn-text"> {t("food_grocery")}</span>
                  {phone && groceryCount > 0 && <span className="food-badge">{groceryCount}</span>}
                </button>
                <button className="active" title={t("food_add_dish")} onClick={() => setEditing("new")}>
                  +<span className="btn-text"> {t("food_add_dish")}</span>
                </button>
              </>
            )}
          </div>
          {chips && (
            <ChipStrip>
              {groups.map((c) => {
                const cat = groupKey(c);
                const isOpen = expanded.has(cat);
                const progress = groupProgress(cat, isOpen);
                if (c && renaming === c.id)
                  return <span className="food-chip renaming" key={cat}>{renameEditor(c)}</span>;
                return (
                  <button key={cat} className={"food-chip" + (isOpen ? " active" : " ghost")}
                          title={c && !groceryMode ? t("food_rename_hint") : undefined}
                          {...press(() => renamable(c) && setRenaming(c!.id), () => selectCategory(cat))}>
                    {groupLabel(c)}
                    <span className="food-chip-n">{byCategory(c).length}</span>
                    {progress && (
                      <span className="food-chip-bar" role="progressbar" aria-valuemin={0} aria-valuemax={progress[1]}
                            aria-valuenow={progress[0]} title={t("food_loading_images", { done: progress[0], total: progress[1] })}>
                        <span className="load-bar-fill" style={{ width: `${(progress[0] / progress[1]) * 100}%` }} />
                      </span>
                    )}
                  </button>
                );
              })}
            </ChipStrip>
          )}
        </div>
        {error && <p className="error small">{error}</p>}

        {!groceryMode && !phone && <GroceryPanel {...groceryProps} onEdit={enterGroceryMode} />}

        {groups.length === 0 && (
          <p className="muted">{t("food_no_dishes")}</p>
        )}
        {searching && !data.dishes.some(matches) && (
          <p className="muted">{t("food_no_matches")}</p>
        )}

        <div ref={groupsRef} className="food-groups" {...swipe}>
          {groups.map((c) => {
            const cat = groupKey(c);
            const all = byCategory(c).sort((a, b) => b.rating - a.rating);
            const dishes = searching ? all.filter(matches) : all;
            if (!dishes.length) return null;
            const isOpen = searching || expanded.has(cat);
            const progress = groupProgress(cat, isOpen);
            return (
              <section className={"food-group" + (isOpen ? " open" : "")} key={cat || "-"}>
                <h3
                  className="food-group-head"
                  title={c && !groceryMode ? t("food_rename_hint") : undefined}
                  {...press(() => renamable(c) && setRenaming(c!.id), () => !searching && toggleCategory(cat))}
                >
                  <span className="chevron">{isOpen ? "▾" : "▸"}</span>
                  {c && renaming === c.id ? renameEditor(c) : (
                    <>
                      {groupLabel(c)}
                      <span className="muted"> ({dishes.length})</span>
                    </>
                  )}
                  {progress && (
                    <span className="load-bar" role="progressbar" aria-valuemin={0} aria-valuemax={progress[1]}
                          aria-valuenow={progress[0]} title={t("food_loading_images", { done: progress[0], total: progress[1] })}>
                      <span className="load-bar-fill" style={{ width: `${(progress[0] / progress[1]) * 100}%` }} />
                    </span>
                  )}
                </h3>
                {/* Searching mounts just the matches' cards, and only an
                    opened category may call itself loaded -- a search
                    through it has not loaded all its pictures. */}
                {(everOpened.has(cat) || searching) && (
                  <CategoryGrid
                    dishes={dishes}
                    collapsed={!isOpen}
                    loaded={imgLoaded.has(cat)}
                    onAllLoaded={() => { if (!searching) markLoaded(cat); }}
                    onProgress={(done, total) => reportProgress(cat, done, total)}
                    onEdit={setEditing}
                    onRate={(id, rating) => mutate(foodApi.patch(id, { rating }))}
                    onEditIngredients={setEditingIngredients}
                    onWatchImport={setWatching}
                    groceryMode={groceryMode}
                    selection={pendingSelection}
                    onToggleSelect={toggleSelect}
                  />
                )}
              </section>
            );
          })}
        </div>
      </div>

      {phone && showGrocery && !groceryMode && (
        <GrocerySheet onClose={() => setShowGrocery(false)}>
          <GroceryPanel {...groceryProps} onClose={() => setShowGrocery(false)}
                        onEdit={() => { setShowGrocery(false); enterGroceryMode(); }} />
        </GrocerySheet>
      )}

      {editing && (
        <DishForm
          dish={editing === "new" ? null : editing}
          categories={data.categories}
          onCancel={() => setEditing(null)}
          onDelete={(id) => {
            setEditing(null);
            mutate(foodApi.remove(id));
          }}
          onSubmit={(body) => {
            const editedId = editing === "new" ? null : editing.id;
            return mutate(
              editing === "new"
                ? foodApi.create(body as DishInput)
                : foodApi.patch(editing.id, body),
            ).then((d) => {
              // A recipe linked, new or changed: its import runs -- watch it.
              if (!d) return;
              const saved = editedId !== null ? d.dishes.find((x) => x.id === editedId)
                : d.dishes.reduce<Dish | undefined>((a, x) => (!a || x.id > a.id ? x : a), undefined);
              if (saved?.import.state === "running") setWatching(saved.id);
            });
          }}
          onImport={(id) => {
            setEditing(null);
            foodApi.importRecipe(id).then((d) => { apply(d); setWatching(id); }).catch((e) => setError(serverMessage(e)));
          }}
        />
      )}

      {watching !== null && data.dishes.some((d) => d.id === watching) && (
        <ImportProgress
          // Opened afresh when it comes to the sub-recipes: all ticked.
          key={`${watching}-${data.dishes.find((d) => d.id === watching)!.import.state}`}
          dish={data.dishes.find((d) => d.id === watching)!}
          dishes={data.dishes}
          onChoose={(id, keep) => foodApi.chooseSplit(id, keep).then(apply).catch((e) => setError(serverMessage(e)))}
          onClose={() => setWatching(null)}
          onOpen={(d) => { setWatching(null); setEditingIngredients(d); }}
          onRetry={(id) => foodApi.importRecipe(id).then(apply).catch((e) => setError(serverMessage(e)))}
        />
      )}

      {showCatalog && (
        <IngredientCatalog items={data.ingredients ?? []} units={data.units ?? []} dishes={data.dishes}
                           onOpenDish={setEditingIngredients} onChanged={apply} onClose={() => setShowCatalog(false)} />
      )}

      {editingIngredients && (
        <IngredientsEditor
          // The dish as it is now -- and opened afresh when an import of it
          // ends, so what it brought is what is edited.
          key={`${editingIngredients.id}-${data.dishes.find((d) => d.id === editingIngredients.id)?.import.state ?? ""}`}
          dish={data.dishes.find((d) => d.id === editingIngredients.id) ?? editingIngredients}
          dishes={data.dishes}
          onRetryImport={(id) => foodApi.importRecipe(id).then((d) => { apply(d); setWatching(id); })
            .catch((e) => setError(serverMessage(e)))}
          catalog={data.ingredients ?? []}
          units={data.units ?? []}
          onCancel={() => setEditingIngredients(null)}
          onSaved={(d) => {
            apply(d);
            setEditingIngredients(null);
          }}
        />
      )}
    </div>
  );
}

function GrocerySummary({
  items,
  checked,
  onToggle,
  catalog,
}: {
  items: GroceryLine[];
  checked: CheckedIngredients;
  onToggle: (line: GroceryLine) => void;
  catalog: CatalogIngredient[];
}) {
  const { t, lang } = useT();
  const byName = new Map(catalog.map((c) => [c.name, c]));
  if (!items.length) return null;
  return (
    <div className="grocery-summary">
      <h4>{t("food_shopping_list")}</h4>
      <ul className="grocery-summary-list">
        {items.map((it) => (
          <li key={it.key}>
            <label>
              <input
                type="checkbox"
                checked={checked.has(it.key)}
                onChange={() => onToggle(it)}
              />
              <span className="grocery-summary-name">
                {byName.has(it.name) ? ingredientName(byName.get(it.name)!, lang) : it.name}
              </span>
              {it.parts.length > 0 && (
                <span className="grocery-summary-amount">
                  {it.parts.map((p) => p.amount + (p.unit ? ` ${unitLabel(t, p.unit)}` : "")).join(" + ")}
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
 *  worked out by the server (food.py, grocery): every dish's ingredients
 *  scaled to the quantity picked for it and added up, converted where the
 *  ingredient's conversions allow. Asked again when the selection or the
 *  catalogue (`version`) changes. */
function GroceryPanel({
  dishes,
  catalog,
  version,
  list,
  onQtyChange,
  onRemove,
  onEdit,
  onClear,
  checked,
  onToggleChecked,
  onLines,
  onClose,
}: {
  dishes: Dish[];
  catalog: CatalogIngredient[];
  version: number;
  list: GroceryList;
  onQtyChange: (id: number, qty: number) => void;
  onRemove: (id: number) => void;
  onEdit: () => void;
  onClear: () => void;
  checked: CheckedIngredients;
  onToggleChecked: (line: GroceryLine) => void;
  /** Every new shopping list, to check the ticks against. */
  onLines: (lines: GroceryLine[]) => void;
  /** In the phone's sheet: a ✕ to close it. */
  onClose?: () => void;
}) {
  const { t, lang } = useT();
  const byId = new Map(dishes.map((d) => [d.id, d]));
  const entries = Object.entries(list)
    .map(([id, qty]) => ({ dish: byId.get(Number(id)), qty }))
    .filter((e): e is { dish: Dish; qty: number } => Boolean(e.dish));

  const [totals, setTotals] = useState<GroceryLine[]>([]);
  const listKey = JSON.stringify(list);
  useEffect(() => {
    let live = true;
    foodApi.grocery(list).then((r) => { if (live) { setTotals(r.lines); onLines(r.lines); } })
      .catch(() => live && setTotals([]));
    return () => { live = false; };
  }, [listKey, version]);  // eslint-disable-line react-hooks/exhaustive-deps

  if (!entries.length) return null;

  return (
    <section className="grocery-panel">
      <div className="grocery-panel-head">
        <h3>🛒 {t("food_grocery_list")}</h3>
        <div className="row-actions">
          <button type="button" className="ghost" onClick={onEdit}>
            {t("food_edit_selection")}
          </button>
          <button type="button" className="ghost danger" onClick={onClear}>
            {t("clear")}
          </button>
          {onClose && <button type="button" className="ghost" title={t("close")} onClick={onClose}>✕</button>}
        </div>
      </div>
      <div className="grocery-items">
        {entries.map(({ dish, qty }) => {
          const unit = yieldUnit(dish, lang);
          return (
            <div className="grocery-item" key={dish.id}>
              <span className="grocery-item-name">{dishName(dish, lang)}</span>
              <QuantityStepper value={qty} unit={unit} onChange={(n) => onQtyChange(dish.id, n)} />
              <button
                type="button"
                className="glyph-btn"
                title={t("food_remove_from_list")}
                onClick={() => onRemove(dish.id)}
              >
                🗑
              </button>
            </div>
          );
        })}
      </div>
      <GrocerySummary items={totals} checked={checked} onToggle={onToggleChecked} catalog={catalog} />
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

/** A category's name, edited in place in its heading: Enter or ✓ saves --
 *  the other languages follow, translated on the server -- Esc or ✕ leaves
 *  it as it was. */
function CategoryNameEdit({ initial, onSave, onCancel }: {
  initial: string;
  onSave: (name: string) => Promise<unknown>;
  onCancel: () => void;
}) {
  const { t } = useT();
  const [text, setText] = useState(initial);
  const [saving, setSaving] = useState(false);
  const save = () => {
    const name = text.trim();
    if (!name || name === initial) return onCancel();
    setSaving(true);
    onSave(name).finally(() => setSaving(false));
  };
  return (
    <span className="food-cat-rename" onClick={(e) => e.stopPropagation()}>
      <input value={text} autoFocus disabled={saving} onChange={(e) => setText(e.target.value)}
             onKeyDown={(e) => { if (e.key === "Enter") save(); else if (e.key === "Escape") onCancel(); }} />
      <button className="ghost" title={saving ? t("food_translating") : t("save")} disabled={saving} onClick={save}>
        {saving ? <span className="mv-ring btn-ring" aria-hidden /> : "✓"}
      </button>
      <button className="ghost" title={t("cancel")} disabled={saving} onClick={onCancel}>✕</button>
    </span>
  );
}

/** The phone's category chips, in a row that also scrolls by wheel and
 *  mouse drag -- phone mode holds on a short desktop window too. Its own
 *  component so the ref exists when the hook runs (the row mounts later
 *  than the panel). */
function ChipStrip({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useDragScroll(ref);
  // The open one in sight -- a swipe may have gone to a chip off the edge.
  useEffect(() => {
    const strip = ref.current, chip = strip?.querySelector<HTMLElement>(".food-chip.active");
    if (!strip || !chip) return;
    const l = chip.offsetLeft - strip.offsetLeft, r = l + chip.offsetWidth;
    if (l < strip.scrollLeft) strip.scrollTo({ left: l - 8, behavior: "smooth" });
    else if (r > strip.scrollLeft + strip.clientWidth)
      strip.scrollTo({ left: r - strip.clientWidth + 8, behavior: "smooth" });
  });
  return <div className="food-chips" ref={ref}>{children}</div>;
}

/** The phone's grocery list: the whole screen, closed by its ✕ or Back. */
function GrocerySheet({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  useBackToClose(onClose);
  return createPortal(<div className="grocery-sheet">{children}</div>, document.body);
}

/** One category's cards, telling how many of their images have loaded (or
 *  errored) -- the parent's bar by its heading -- until they all have. Once
 *  done it calls `onAllLoaded` and the parent stops passing `loaded={false}`,
 *  so re-opening the category is bar-free. Stays mounted while collapsed so
 *  images are never re-fetched. */
function CategoryGrid({
  dishes,
  collapsed,
  loaded,
  onAllLoaded,
  onProgress,
  onEdit,
  onRate,
  onEditIngredients,
  onWatchImport,
  groceryMode,
  selection,
  onToggleSelect,
}: {
  dishes: Dish[];
  collapsed: boolean;
  loaded: boolean;
  onAllLoaded: () => void;
  onProgress: (done: number, total: number) => void;
  onEdit: (d: Dish) => void;
  onRate: (id: number, rating: number) => void;
  onEditIngredients: (d: Dish) => void;
  onWatchImport: (id: number) => void;
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
  useEffect(() => { if (!loaded) onProgress(done, total); }, [loaded, done, total]);  // eslint-disable-line react-hooks/exhaustive-deps

  const onImgSettled = (id: number) => {
    if (settled.current.has(id)) return;
    settled.current.add(id);
    setDone((n) => n + 1);
  };

  return (
    <>
      <div className="dish-grid" hidden={collapsed}>
        {dishes.map((d) => (
          <DishCard
            key={d.id}
            dish={d}
            onEdit={() => onEdit(d)}
            onRate={(n) => onRate(d.id, n)}
            onImgSettled={() => onImgSettled(d.id)}
            onEditIngredients={() => onEditIngredients(d)}
            onWatchImport={() => onWatchImport(d.id)}
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
  onEdit,
  onRate,
  onImgSettled,
  onEditIngredients,
  onWatchImport,
  groceryMode,
  selected,
  onToggleSelect,
}: {
  dish: Dish;
  onEdit: () => void;
  onRate: (rating: number) => void;
  onImgSettled?: () => void;
  onEditIngredients: () => void;
  onWatchImport: () => void;
  groceryMode: boolean;
  selected: boolean;
  onToggleSelect: () => void;
}) {
  const { t, lang } = useT();
  const name = dishName(dish, lang);
  const eligibleForGrocery = Boolean(dish.ingredients);
  // Where the rating's popup opens: below the card's stars.
  const [ratingAt, setRatingAt] = useState<DOMRect | null>(null);
  const img = dish.image ? (
    <img
      // No loading="lazy": the category itself is the lazy boundary
      // (images mount only after you open it), and the loading bar needs
      // every image in the category to actually start loading.
      src={dishSmallUrl(dish.image)}
      alt={name}
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
        title={eligibleForGrocery ? undefined : t("food_no_ingredients_yet")}
      >
        <div className="dish-card-img">
          {img}
          <div className="dish-card-select-mark" aria-hidden>
            {selected ? "☑" : "☐"}
          </div>
        </div>
        <div className="dish-card-foot">
          <div className="meta">
            <div className="dish-name" title={name}>
              {name}
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
        title={t("food_ingredients_and_instructions")}
      >
        {img}
      </button>
      {(dish.import.state === "running" || dish.import.state === "choosing" || dish.import.state === "failed") && (
        <button
          type="button"
          className={"dish-card-import " + dish.import.state}
          title={dish.import.state === "failed" ? (dish.import.errors ?? []).join("\n") : undefined}
          onClick={onWatchImport}
        >
          {dish.import.state === "running"
            ? <><span className="mv-ring btn-ring" aria-hidden />{t("food_importing")}</>
            : dish.import.state === "choosing" ? <>? {t("food_split_suggested")}</>
            : <>⚠ {t("food_import_failed")}</>}
        </button>
      )}
      <div className="dish-card-foot">
        <div className="meta">
          <div className="dish-name" title={name}>
            {name}
          </div>
          <button type="button" className="dish-stars" title={`${t("food_rating")} ${stars(dish.rating)}`}
                  onClick={(e) => setRatingAt(e.currentTarget.getBoundingClientRect())}>
            {ratingShort(dish.rating)}
          </button>
        </div>
        {ratingAt && (
          <RatingPopup at={ratingAt} value={dish.rating}
                       onPick={(n) => { setRatingAt(null); if (n !== dish.rating) onRate(n); }}
                       onClose={() => setRatingAt(null)} />
        )}
        <div className="acts">
          <button className="ghost" title={t("edit")} onClick={onEdit}>
            ✎
          </button>
        </div>
      </div>
    </div>
  );
}

interface IngredientRow {
  name: string;
  quantity: string;
  unit: string;
  /** Another dish used as this ingredient (its id; 0 while none is picked):
   *  then `quantity` is its grams, `name` and `unit` unused. */
  dish?: number;
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
      dishes?: Record<string, { quantity?: unknown; position?: unknown }>;
    };
    const entries = Object.entries(data.ingredients ?? {});
    const rows: IngredientRow[] = entries.map(([name, v]) => ({
      name,
      quantity: String(v?.quantity ?? ""),
      unit: String(v?.unit ?? ""),
    }));
    // The dishes it uses, each at its place among the ingredients.
    Object.entries(data.dishes ?? {})
      .map(([id, v]) => ({ at: Number(v?.position), row: { name: "", quantity: String(v?.quantity ?? ""), unit: "", dish: Number(id) } }))
      .sort((a, b) => a.at - b.at)
      .forEach(({ at, row }) => rows.splice(Math.min(at, rows.length), 0, row));
    return { quantity: String(data.quantity ?? ""), unit: String(data.unit ?? ""), rows };
  } catch {
    return { quantity: "", unit: "", rows: [] };
  }
}

// A name as typed, in any language ("Zwiebel", "olio d'oliva"); the server
// turns it into the list's English one (food.py, _TYPED_NAME_RE).
const TYPED_NAME_RE = /^\p{L}+(?:[ '’-]\p{L}+)*$/u;
const PLAIN_NUMBER_RE = /^\d+(?:\.\d+)?$/;

/** Same shape rules as the backend's _validate_ingredients_json, applied
 *  per-field since the editor keeps quantity/unit apart. null = valid. */
function rowError(r: IngredientRow): Key | null {
  const name = r.name.trim();
  const qty = r.quantity.trim();
  if (r.dish !== undefined) return PLAIN_NUMBER_RE.test(qty) && Number(qty) > 0 ? null : "food_dish_qty_invalid";
  if (name && !TYPED_NAME_RE.test(name)) return "food_name_invalid";
  if (qty && !PLAIN_NUMBER_RE.test(qty)) return "food_qty_invalid";
  return null;
}

/** What the server said, from a failed foodApi call (already translated). */
function serverMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

type T = ReturnType<typeof useT>["t"];

/** The units whose name is said differently in each language; "" is a
 *  count of pieces. The rest (g, kg, ml, l...) read the same everywhere. */
const UNIT_KEYS: Record<string, Key> = {
  "": "unit_pieces", tsp: "unit_tsp", tbsp: "unit_tbsp", cup: "unit_cup",
  glass: "unit_glass", "coffee cup": "unit_coffee_cup",
};
const unitLabel = (t: T, u: string) => (u in UNIT_KEYS ? t(UNIT_KEYS[u]) : u);
/** What a closed unit picker shows: an icon for the kitchen measures,
 *  the symbol itself for the metric ones (g, kg, ml...), short already.
 *  Filled shapes on a 24-unit grid; the outlined bits (a handle, steam)
 *  say so themselves. */
const LINE = { fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" } as const;
const UNIT_ICONS: Record<string, React.ReactNode> = {
  "": <><circle cx="7" cy="16.5" r="3.5" /><circle cx="17" cy="16.5" r="3.5" /><circle cx="12" cy="7.5" r="3.5" /></>,
  // the same spoon, small and big
  tsp: <><ellipse cx="12" cy="10" rx="3.2" ry="4" /><rect x="11.1" y="13" width="1.8" height="8" rx="0.9" /></>,
  tbsp: <><ellipse cx="12" cy="7" rx="4.6" ry="5.6" /><rect x="10.8" y="11.5" width="2.4" height="11" rx="1.2" /></>,
  cup: <><path d="M3 6h13v8.5A5.5 5.5 0 0 1 10.5 20h-2A5.5 5.5 0 0 1 3 14.5z" /><path {...LINE} d="M16 8.5h1.5a3 3 0 0 1 0 6H16" /></>,
  glass: <><path {...LINE} strokeLinejoin="round" d="M5.5 3h13l-1.8 18H7.3z" /><path d="M6.6 11h10.8l-1 9H7.6z" /></>,
  "coffee cup": <><path d="M5 10h11v3.5a4.5 4.5 0 0 1-4.5 4.5h-2A4.5 4.5 0 0 1 5 13.5z" /><path {...LINE} d="M16 11.5h1a2 2 0 0 1 0 4h-1" /><rect x="2.5" y="19.5" width="17" height="2" rx="1" /><path {...LINE} strokeWidth={1.6} d="M9 2.5c-1 1.3 1 2.2 0 4.5M12.5 2.5c-1 1.3 1 2.2 0 4.5" /></>,
};
function UnitIcon({ unit }: { unit: string }) {
  if (!(unit in UNIT_ICONS)) return <>{unit}</>;
  return <svg className="unit-icon" viewBox="0 0 24 24" fill="currentColor">{UNIT_ICONS[unit]}</svg>;
}

const MACRO_KEYS: Record<Macro, Key> = { mass: "macro_mass", volume: "macro_volume", count: "macro_count" };

/** The unit picker of a recipe line: every unit, grouped by macro-category.
 *  Closed, it shows the unit's icon over the select (whose own text is
 *  hidden); open, the full names. */
function UnitSelect({ units, value, onChange, macro }: {
  units: UnitDef[];
  value: string;
  onChange: (u: string) => void;
  /** Only this category's units, ungrouped. */
  macro?: Macro;
}) {
  const { t } = useT();
  const of = (m: Macro) => units.filter((u) => u.macro === m);
  const option = (u: UnitDef) => <option key={u.unit} value={u.unit}>{unitLabel(t, u.unit)}</option>;
  return (
    <span className="unit-select" title={unitLabel(t, value)}>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {macro ? of(macro).map(option) : (["mass", "volume", "count"] as Macro[]).map((m) => (
          <optgroup key={m} label={t(MACRO_KEYS[m])}>{of(m).map(option)}</optgroup>
        ))}
      </select>
      <span className="unit-select-label" aria-hidden><UnitIcon unit={value} /></span>
    </span>
  );
}

/** The three conversions an ingredient can have, each written with its
 *  left side in `a` and its right side in `b` ("1 tbsp = 12 g"). */
const PAIRS: { a: Macro; b: Macro; aUnit: string; bUnit: string }[] = [
  { a: "count", b: "mass", aUnit: "", bUnit: "g" },
  { a: "count", b: "volume", aUnit: "", bUnit: "ml" },
  { a: "volume", b: "mass", aUnit: "tbsp", bUnit: "g" },
];

interface ConvDraft { a_qty: string; a_unit: string; b_qty: string; b_unit: string }

/** An ingredient's conversions as the three rows of PAIRS, empty where it
 *  has none -- a stored one may be written either way round. */
function convDrafts(convs: Conversion[], units: UnitDef[]): ConvDraft[] {
  const macro = new Map(units.map((u) => [u.unit, u.macro]));
  return PAIRS.map((p) => {
    for (const c of convs) {
      const [ma, mb] = [macro.get(c.a_unit), macro.get(c.b_unit)];
      if (ma === p.a && mb === p.b) return { a_qty: String(c.a_qty), a_unit: c.a_unit, b_qty: String(c.b_qty), b_unit: c.b_unit };
      if (ma === p.b && mb === p.a) return { a_qty: String(c.b_qty), a_unit: c.b_unit, b_qty: String(c.a_qty), b_unit: c.a_unit };
    }
    return { a_qty: "", a_unit: p.aUnit, b_qty: "", b_unit: p.bUnit };
  });
}

/** The ingredient list: every ingredient the recipes use, each with its
 *  optional conversions between mass, volume and pieces -- what lets the
 *  shopping list add up recipes that measure it differently
 *  (api/services/food.py). Renaming one into another merges them. */
function IngredientCatalog({ items, units, dishes, onOpenDish, onChanged, onClose }: {
  items: CatalogIngredient[];
  units: UnitDef[];
  dishes: Dish[];
  /** A dish of an ingredient's list, opened over this one. */
  onOpenDish: (d: Dish) => void;
  onChanged: (d: FoodData) => void;
  onClose: () => void;
}) {
  useBackToClose(onClose);
  const { t, tn } = useT();
  const [query, setQuery] = useState("");
  const [names, setNames] = useState<Record<number, string>>({});
  // The ingredient whose conversions are open, and their rows as typed.
  const [converting, setConverting] = useState<{ id: number; drafts: ConvDraft[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The ingredient whose dishes are shown, and each ingredient's dishes
  // (by its list name, as the dishes' ingredients have it).
  const [showingDishes, setShowingDishes] = useState<number | null>(null);
  const dishesOf = useMemo(() => {
    const m = new Map<string, Dish[]>();
    for (const d of dishes) {
      for (const r of parseIngredients(d.ingredients).rows) if (r.dish === undefined) m.set(r.name, [...(m.get(r.name) ?? []), d]);
    }
    return m;
  }, [dishes]);
  // A rename into another ingredient's name, waiting to be confirmed.
  const [merging, setMerging] = useState<{ message: string; yes: () => void; no: () => void } | null>(null);

  const run = (p: Promise<FoodData>) => {
    setBusy(true);
    setError(null);
    return p.then((d) => { onChanged(d); return true; })
      .catch((e) => { setError(serverMessage(e)); return false; })
      .finally(() => setBusy(false));
  };
  const { lang: uiLang } = useT();
  // Names are shown and edited in the UI's language only: German keeps its
  // capitals, the others are lowercase. The server has the other languages
  // follow when the edit makes it another thing to buy.
  const typed = (v: string) => (uiLang === "de" ? v : v.toLowerCase());
  const forget = (id: number) => setNames((n) => { const { [id]: _, ...rest } = n; return rest; });
  const rename = (it: CatalogIngredient) => {
    const was = ingredientName(it, uiLang);
    const to = typed((names[it.id] ?? was).trim().replace(/\s+/g, " "));
    if (!to || to === was) return forget(it.id);
    const send = () =>
      run(foodApi.patchIngredient(it.id, { name: to, lang: uiLang })).then((ok) => ok && forget(it.id));
    const into = items.find((o) => o.id !== it.id && ingredientName(o, uiLang).toLowerCase() === to.toLowerCase());
    if (into) setMerging({ message: t("food_merge_confirm", { a: was, b: ingredientName(into, uiLang), n: it.uses }),
                           yes: send, no: () => forget(it.id) });
    else send();
  };
  const setDraft = (i: number, patch: Partial<ConvDraft>) =>
    setConverting((c) => c && { ...c, drafts: c.drafts.map((d, j) => (j === i ? { ...d, ...patch } : d)) });
  const saveConversions = (id: number, drafts: ConvDraft[]) => {
    const filled = drafts.filter((d) => d.a_qty.trim() || d.b_qty.trim());
    if (filled.some((d) => !(Number(d.a_qty) > 0 && Number(d.b_qty) > 0))) {
      setError(t("food_conversion_incomplete"));
      return;
    }
    const conversions = filled.map((d) => ({
      a_qty: Number(d.a_qty), a_unit: d.a_unit, b_qty: Number(d.b_qty), b_unit: d.b_unit,
    }));
    run(foodApi.patchIngredient(id, { conversions })).then((ok) => ok && setConverting(null));
  };
  const q = query.trim().toLowerCase();
  const shown = items
    .filter((it) => ingredientName(it, uiLang).toLowerCase().includes(q))
    .sort((a, b) => ingredientName(a, uiLang).localeCompare(ingredientName(b, uiLang), uiLang));

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal dish-info" onClick={(e) => e.stopPropagation()}>
        <h4>{t("food_ingredients")}</h4>
        <p className="muted small">{t("food_catalog_intro")}</p>
        <input placeholder={t("food_catalog_search", { n: items.length })} value={query} onChange={(e) => setQuery(e.target.value)} />
        <div className="dish-info-scroll">
          <div className="ingredients-rows">
            {shown.map((it) => (
              <div key={it.id}>
                <div className="ingredients-row catalog-row">
                  <input
                    value={names[it.id] ?? ingredientName(it, uiLang)}
                    onChange={(e) => setNames((n) => ({ ...n, [it.id]: typed(e.target.value) }))}
                    onBlur={() => rename(it)}
                    onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
                    disabled={busy}
                  />
                  <button type="button" className={"ghost" + (it.conversions.length ? " active" : "")} disabled={busy}
                          title={t("food_conversions")}
                          onClick={() => setConverting(converting?.id === it.id ? null
                            : { id: it.id, drafts: convDrafts(it.conversions, units) })}>
                    ⇄{it.conversions.length ? ` ${it.conversions.length}` : ""}
                  </button>
                  <button type="button" className={"ghost catalog-uses" + (showingDishes === it.id ? " active" : "")}
                          disabled={!it.uses} title={`${t("food_dishes_using_it")}: ${tn("food_uses", it.uses)}`}
                          onClick={() => setShowingDishes(showingDishes === it.id ? null : it.id)}>
                    🍽 {it.uses}
                  </button>
                  <button type="button" className="glyph-btn" disabled={busy || it.uses > 0}
                          title={it.uses ? t("food_in_use") : t("remove")}
                          onClick={() => run(foodApi.removeIngredient(it.id))}>
                    🗑
                  </button>
                </div>
                {showingDishes === it.id && (
                  <div className="ingredients-conversions catalog-dishes">
                    {[...(dishesOf.get(it.name) ?? [])]
                      .sort((a, b) => dishName(a, uiLang).localeCompare(dishName(b, uiLang), uiLang))
                      .map((d) => (
                        <button type="button" key={d.id} className="ghost catalog-dish" onClick={() => onOpenDish(d)}>
                          {d.image ? <img src={dishSmallUrl(d.image)} alt="" loading="lazy" /> : <span className="catalog-dish-blank">🍽</span>}
                          {dishName(d, uiLang)}
                        </button>
                      ))}
                  </div>
                )}
                {converting?.id === it.id && (
                  <div className="ingredients-conversions">
                    {PAIRS.map((p, i) => {
                      const d = converting.drafts[i];
                      return (
                        <div className="ingredients-conversion" key={i}>
                          <input inputMode="decimal" placeholder={t("qty")} value={d.a_qty}
                                 onChange={(e) => setDraft(i, { a_qty: e.target.value })} />
                          {p.a === "count" ? <span className="muted small">{t("unit_pieces")}</span>
                            : <UnitSelect units={units} macro={p.a} value={d.a_unit} onChange={(u) => setDraft(i, { a_unit: u })} />}
                          <span>=</span>
                          <input inputMode="decimal" placeholder={t("qty")} value={d.b_qty}
                                 onChange={(e) => setDraft(i, { b_qty: e.target.value })} />
                          <UnitSelect units={units} macro={p.b} value={d.b_unit} onChange={(u) => setDraft(i, { b_unit: u })} />
                        </div>
                      );
                    })}
                    <div className="row-actions">
                      <button type="button" disabled={busy} onClick={() => saveConversions(it.id, converting.drafts)}>
                        {t("food_save_conversions")}
                      </button>
                      <button type="button" className="ghost" onClick={() => setConverting(null)}>{t("cancel")}</button>
                    </div>
                  </div>
                )}
              </div>
            ))}
            {items.length === 0 && (
              <p className="muted small">{t("food_catalog_empty")}</p>
            )}
          </div>
        </div>
        {error && <p className="error small">{error}</p>}
        <div className="row-actions">
          <button type="button" className="active" onClick={onClose}>{t("done")}</button>
        </div>
      </div>
      {merging && (
        <ConfirmDialog message={merging.message}
                       onYes={() => { setMerging(null); merging.yes(); }}
                       onNo={() => { setMerging(null); merging.no(); }} />
      )}
    </div>
  );
}

/** One dish's ingredients, by hand. Typing a name offers the ingredient
 *  list's; a name not in it is a new ingredient, which joins the list when
 *  the dish is saved. Each amount is in any unit of `units`. */
function IngredientsEditor({
  dish,
  dishes,
  catalog,
  units,
  onCancel,
  onSaved,
  onRetryImport,
}: {
  dish: Dish;
  dishes: Dish[]; // all of them: the yield units already in use
  catalog: CatalogIngredient[];
  units: UnitDef[];
  onRetryImport: (dishId: number) => void;
  onCancel: () => void;
  onSaved: (d: FoodData) => void;
}) {
  useBackToClose(onCancel);
  const { t, lang } = useT();
  // Ingredients are shown and typed in the UI's language: a name as shown
  // goes back as the list's (English) one; any other is checked against
  // the list by the server on save.
  const shown = useMemo(() => new Map(catalog.map((c) => [c.name, ingredientName(c, lang)])), [catalog, lang]);
  const listed = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of catalog) { m.set(c.name.toLowerCase(), c.name); m.set(ingredientName(c, lang).toLowerCase(), c.name); }
    return m;
  }, [catalog, lang]);
  const known = { has: (typed: string) => listed.has(typed.toLowerCase()) };
  // The instructions in the UI's language, English until it has them.
  const shownIns = (lang !== "en" && dish.instructions_tr?.[lang]) || dish.instructions;
  const initial = useMemo(() => parseIngredients(dish.ingredients), [dish.ingredients]);
  const [quantity, setQuantity] = useState(initial.quantity);
  // The yield's unit as shown, in the UI's language; sent back as the
  // English one unless it is changed (then it is translated on save).
  const shownUnit = useMemo(() => yieldUnit(dish, lang), [dish, lang]);
  const [unit, setUnit] = useState(shownUnit);
  // A yield unit some dish already has is picked; typing one is only for a
  // new one (or a dish with none yet). Shown in the UI's language.
  const yieldUnits = useMemo(() => {
    const shown = new Set<string>();
    for (const d of dishes) { const u = yieldUnit(d, lang); if (u) shown.add(u); }
    return [...shown].sort((a, b) => a.localeCompare(b));
  }, [dishes, lang]);
  const [newUnit, setNewUnit] = useState(() => !yieldUnits.includes(shownUnit));
  // Its field is focused only when "New unit…" is picked, not on opening.
  const [unitPicked, setUnitPicked] = useState(false);
  // A row with no amount has no unit yet; grams until one is picked.
  const [rows, setRows] = useState<IngredientRow[]>(
    () => initial.rows.map((r) => ({ ...r, name: shown.get(r.name) ?? r.name, unit: r.quantity.trim() ? r.unit : "g" })));
  // The dishes it can use: ones whose weight is known (what grams of them
  // are scaled by), and not this one or one using it, however far down --
  // the server refuses those too (food.py, _check_components).
  const usable = useMemo(() => {
    const uses = new Map(dishes.map((d) => [d.id, parseIngredients(d.ingredients).rows.flatMap((r) => (r.dish ? [r.dish] : []))]));
    const reaches = (from: number, seen = new Set<number>()): boolean =>
      from === dish.id || (!seen.has(from) && (seen.add(from), (uses.get(from) ?? []).some((c) => reaches(c, seen))));
    return dishes
      .filter((d) => (d.weight_g ?? 0) > 0)
      .filter((d) => !reaches(d.id))
      .sort((a, b) => dishName(a, lang).localeCompare(dishName(b, lang), lang));
  }, [dishes, dish.id, lang]);
  const dishById = useMemo(() => new Map(dishes.map((d) => [d.id, d])), [dishes]);
  // The instructions, below the ingredients: shown rendered, or -- with
  // nothing to show yet, or after Edit -- as the Markdown being written.
  const [insEditing, setInsEditing] = useState(!shownIns);
  const [insText, setInsText] = useState(shownIns);
  const [saving, setSaving] = useState(false);
  // Saving changed instructions waits for them to be translated into the
  // other languages (food.py, _translate) -- seconds, not a blink.
  const [translating, setTranslating] = useState(false);
  const [facts, setFacts] = useState<DishFacts>(dish.facts);
  // Names not in the list are checked against it on save (a typo becomes
  // the list's ingredient) -- a second or two.
  const [checking, setChecking] = useState(false);
  // A save was tried with something missing or wrong: it is marked red.
  const [tried, setTried] = useState(false);
  // The yield is needed once there are ingredients: a number, and what it
  // counts in words ("persone", "Personen").
  const used = (r: IngredientRow) => (r.dish === undefined ? !!r.name.trim() : r.dish > 0);
  const hasRows = rows.some(used);
  const yieldBad = {
    quantity: hasRows && !PLAIN_NUMBER_RE.test(quantity.trim()),
    unit: hasRows && !/^\p{L}+(?:[ '’-]\p{L}+)*$/u.test(unit.trim()),
  };
  const [error, setError] = useState<string | null>(null);

  const updateRow = (i: number, patch: Partial<IngredientRow>) =>
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  const removeRow = (i: number) => setRows((rs) => rs.filter((_, idx) => idx !== i));
  const addRow = () => setRows((rs) => [...rs, { name: "", quantity: "", unit: "g" }]);
  const addDishRow = () => setRows((rs) => [...rs, { name: "", quantity: "", unit: "", dish: 0 }]);
  const lower = (s: string) => s.toLowerCase();

  /** The ingredients as they would be saved. */
  const build = (rs: IngredientRow[]) => {
    const ingredients: Record<string, { quantity: string; unit: string }> = {};
    // The dishes used, each with its place among all the lines (an
    // ingredient written twice is one line).
    const comps: Record<string, { quantity: string; position: number }> = {};
    let at = 0;
    for (const r of rs) {
      if (r.dish !== undefined) {
        if (r.dish > 0 && !(r.dish in comps)) comps[r.dish] = { quantity: r.quantity.trim(), position: at++ };
        continue;
      }
      const typed = r.name.trim();
      if (!typed) continue;
      const name = listed.get(typed.toLowerCase()) ?? typed;
      const qty = r.quantity.trim();
      if (!(name in ingredients)) at++;
      ingredients[name] = { quantity: qty, unit: qty ? r.unit : "" };
    }
    // No rows left -> clear the field entirely (an empty {} would fail the
    // backend's "non-empty object" check, and isn't what "cleared" means).
    const payload = at
      ? JSON.stringify({ quantity: quantity.trim(), unit: unit.trim() === shownUnit ? initial.unit : unit.trim(),
                         ingredients, dishes: comps })
      : "";
    return payload;
  };
  // What opening changed nothing would save: only sent when it differs.
  const unchanged = useMemo(() => build(initial.rows.map((r) => ({ ...r, name: shown.get(r.name) ?? r.name }))), [initial]);  // eslint-disable-line react-hooks/exhaustive-deps

  const save = () => {
    setError(null);
    const payload = build(rows);
    const body: Partial<DishInput> = {};
    if (payload !== unchanged || quantity !== initial.quantity || unit !== shownUnit) {
      // The backend's own checks (_validate_ingredients_json), made here:
      // what's missing or wrong is marked red, said in one line.
      const named = rows.filter(used);
      const todo = [
        yieldBad.quantity && t("food_need_yield_quantity"),
        yieldBad.unit && t("food_need_yield_unit"),
        named.some((r) => rowError(r) === "food_dish_qty_invalid") && t("food_dish_qty_invalid"),
        named.some((r) => rowError(r) === "food_qty_invalid") && t("food_qty_invalid"),
        named.some((r) => rowError(r) === "food_name_invalid") && t("food_name_invalid"),
      ].filter(Boolean);
      if (todo.length) {
        setTried(true);
        setError(todo.join(" "));
        return;
      }
      body.ingredients = payload;
      body.lang = lang; // the yield's unit is written in it
    }
    if (insText !== shownIns) {
      body.instructions = insText;
      body.lang = lang;
    }
    for (const k of ["prep_min", "cook_min", "total_min", "difficulty"] as const) {
      if (facts[k] !== dish.facts[k]) Object.assign(body, { [k]: facts[k] });
    }
    if (!Object.keys(body).length) { onCancel(); return; }
    setSaving(true);
    foodApi
      .patch(dish.id, body)
      .then(onSaved)
      .catch((e) => setError(serverMessage(e)))
      .finally(() => { setSaving(false); setTranslating(false); setChecking(false); });
    setTranslating((body.instructions !== undefined && body.instructions.trim() !== "")
      || (body.ingredients !== undefined && unit.trim() !== shownUnit));
    setChecking(body.ingredients !== undefined && rows.some((r) => r.dish === undefined && r.name.trim() && !known.has(r.name.trim())));
  };

  return (
    <div className="modal-backdrop">
      <div className="modal dish-info" onClick={(e) => e.stopPropagation()}>
        <h4>{dishName(dish, lang)}</h4>
        <div className="dish-info-scroll">
          {dish.import.state === "running" && (
            <p className="muted small"><span className="mv-ring btn-ring" aria-hidden />{t("food_importing")}</p>
          )}
          {dish.import.state === "failed" && (
            <div className="import-failed small">
              ⚠ {t("food_import_failed")}: {(dish.import.errors ?? []).join("; ")}{" "}
              <button type="button" className="ghost" onClick={() => onRetryImport(dish.id)}>{t("food_retry")}</button>
            </div>
          )}
          <section className="dish-section">
          <div className="dish-section-head"><h5>{t("food_ingredients")}</h5></div>
          <div className="ingredients-top">
            <span className="muted small">{t("food_serves")}</span>
            <input value={quantity} onChange={(e) => setQuantity(e.target.value)} placeholder={t("food_quantity_placeholder")}
                   aria-label={t("food_quantity")} className={"yield-qty" + (tried && yieldBad.quantity ? " invalid" : "")} />
            {newUnit ? (
              <span className="dish-form-newcat">
                <input value={unit} onChange={(e) => setUnit(lang === "de" ? e.target.value : lower(e.target.value))}
                       placeholder={t("food_unit_placeholder")} autoFocus={unitPicked}
                       aria-label={t("food_unit")} className={tried && yieldBad.unit ? "invalid" : ""} />
                {yieldUnits.length > 0 && (
                  <button type="button" className="ghost" title={t("cancel")}
                          onClick={() => { setNewUnit(false); setUnit(yieldUnits.includes(shownUnit) ? shownUnit : yieldUnits[0]); }}>
                    ✕
                  </button>
                )}
              </span>
            ) : (
              <select value={unit} aria-label={t("food_unit")} className={tried && yieldBad.unit ? "invalid" : ""}
                      onChange={(e) => {
                        if (e.target.value === "\0new") { setNewUnit(true); setUnitPicked(true); setUnit(""); } else setUnit(e.target.value);
                      }}>
                {yieldUnits.map((u) => <option key={u} value={u}>{u}</option>)}
                <option value={"\0new"}>{t("food_unit_new")}</option>
              </select>
            )}
          </div>
          <datalist id="food-ingredient-names">
            {catalog.map((c) => <option key={c.name} value={ingredientName(c, lang)} />)}
          </datalist>
          <div className="ingredients-rows">
            {rows.map((r, i) => {
              const err = used(r) ? rowError(r) : null;
              if (r.dish !== undefined) {
                const picked = dishById.get(r.dish);
                // Its own dish, and the usable ones no other line has.
                const choices = usable.filter((d) => d.id === r.dish || !rows.some((o) => o.dish === d.id));
                if (picked && !choices.includes(picked)) choices.unshift(picked);
                return (
                  <div key={i} className={"ingredients-row dish-row" + (err && tried ? " invalid" : "")}>
                    <select value={r.dish} onChange={(e) => updateRow(i, { dish: Number(e.target.value) })}
                            aria-label={t("food_pick_dish")}>
                      <option value={0} disabled>{t("food_pick_dish")}</option>
                      {choices.map((d) => <option key={d.id} value={d.id}>🍽 {dishName(d, lang)}</option>)}
                    </select>
                    <input
                      value={r.quantity}
                      inputMode="decimal"
                      onChange={(e) => updateRow(i, { quantity: e.target.value })}
                      placeholder={t("qty")}
                    />
                    <span className="dish-row-unit muted small">g</span>
                    <button type="button" className="glyph-btn" title={t("remove")} onClick={() => removeRow(i)}>
                      🗑
                    </button>
                  </div>
                );
              }
              return (
                <div key={i}>
                  <div className={"ingredients-row" + (err && tried ? " invalid" : "")}>
                    <input
                      value={r.name}
                      list="food-ingredient-names"
                      onChange={(e) => updateRow(i, { name: e.target.value })}
                      placeholder={t("food_name_placeholder")}
                    />
                    <input
                      value={r.quantity}
                      onChange={(e) => updateRow(i, { quantity: e.target.value })}
                      placeholder={t("qty")}
                    />
                    <UnitSelect units={units} value={r.unit} onChange={(u) => updateRow(i, { unit: u })} />
                    <button type="button" className="glyph-btn" title={t("remove")} onClick={() => removeRow(i)}>
                      🗑
                    </button>
                  </div>
                  {r.name.trim() && !known.has(r.name.trim()) && (
                    <div className="ingredients-row-note">{t("food_new_ingredient")}</div>
                  )}
                </div>
              );
            })}
          </div>
          <div className="ingredients-add">
            <button type="button" className="ghost add-btn" onClick={addRow}>
              {t("food_add_ingredient")}
            </button>
            {usable.length > 0 && (
              <button type="button" className="ghost add-btn" onClick={addDishRow}>
                {t("food_add_component")}
              </button>
            )}
          </div>
          </section>

          <FactsEditor facts={facts} onChange={setFacts} />

          <section className="dish-section">
          <div className="dish-section-head">
            <h5>{t("food_instructions")}</h5>
            {!insEditing && (
              <button type="button" className="ghost small-btn" onClick={() => setInsEditing(true)}>✎ {t("edit")}</button>
            )}
          </div>
          {insEditing ? (
            <textarea
              className="dish-info-edit"
              value={insText}
              disabled={saving}
              onChange={(e) => setInsText(e.target.value)}
              rows={10}
              placeholder={t("food_instructions_placeholder")}
            />
          ) : (
            <MarkdownView text={shownIns} photos={dish.photos} />
          )}
          </section>
        </div>
        {error && <p className="error small">{error}</p>}
        <div className="row-actions">
          <button type="button" className="active" onClick={save} disabled={saving}>
            {(translating || checking) && <span className="mv-ring btn-ring" aria-hidden />}
            {translating ? t("food_translating") : checking ? t("food_checking_ingredients") : saving ? t("saving") : t("save")}
          </button>
          <button type="button" className="ghost" onClick={onCancel} disabled={saving}>
            {t("cancel")}
          </button>
        </div>
      </div>
    </div>
  );
}

const DIFFICULTY_KEYS: Record<Exclude<Difficulty, "">, Key> = {
  very_easy: "food_difficulty_very_easy", easy: "food_difficulty_easy", medium: "food_difficulty_medium",
  hard: "food_difficulty_hard", very_hard: "food_difficulty_very_hard",
};

/** A dish's facts, editable: times and difficulty; the recipe
 *  site's rating shown as it is. */
function FactsEditor({ facts, onChange }: { facts: DishFacts; onChange: (f: DishFacts) => void }) {
  const { t } = useT();
  const num = (v: string) => (v.trim() === "" || !(Number(v) >= 0) ? null : Number(v));
  const set = (patch: Partial<DishFacts>) => onChange({ ...facts, ...patch });
  return (
    <section className="dish-section">
      <div className="dish-section-head"><h5>{t("food_facts")}</h5></div>
      <div className="facts-grid">
        {(["prep_min", "cook_min", "total_min"] as const).map((k) => (
          <label key={k}>
            {t(`food_${k}` as Key)}
            <input inputMode="numeric" placeholder="min" value={facts[k] ?? ""}
                   onChange={(e) => set({ [k]: num(e.target.value) === null ? null : Math.round(num(e.target.value)!) })} />
          </label>
        ))}
        <label className="facts-wide">
          {t("food_difficulty")}
          <select value={facts.difficulty} onChange={(e) => set({ difficulty: e.target.value as Difficulty })}>
            <option value="">—</option>
            {Object.entries(DIFFICULTY_KEYS).map(([d, key]) => <option key={d} value={d}>{t(key)}</option>)}
          </select>
        </label>
      </div>
      {facts.source_rating && (
        <p className="muted small">
          {t("food_source_rating", { rating: facts.source_rating, count: facts.source_rating_count || "?" })}
        </p>
      )}
    </section>
  );
}

const IMPORT_STAGES = ["fetching", "splitting", "reading", "translating"] as const;
const STAGE_KEYS: Record<(typeof IMPORT_STAGES)[number], Key> = {
  fetching: "food_stage_fetching", splitting: "food_stage_splitting", reading: "food_stage_reading",
  translating: "food_stage_translating",
};

/** A dish's recipe import as it goes -- the stages, ticked off -- closing
 *  when it is done; a failure stays, to open the dish or retry. The import
 *  goes on when it is closed. */
function ImportProgress({ dish, dishes, onClose, onOpen, onRetry, onChoose }: {
  dish: Dish;
  dishes: Dish[];
  onClose: () => void;
  onOpen: (d: Dish) => void;
  onRetry: (id: number) => void;
  /** Its sub-recipes picked (by their place in import.parts). */
  onChoose: (id: number, keep: number[]) => Promise<unknown>;
}) {
  useBackToClose(onClose);
  const { t, lang } = useT();
  const { state, stage, errors, parts = [] } = dish.import;
  const at = IMPORT_STAGES.indexOf(stage as (typeof IMPORT_STAGES)[number]);
  // The sub-recipes to make dishes of: all of them until unticked.
  const [keep, setKeep] = useState<Set<number>>(() => new Set(parts.map((_, i) => i)));
  const [sending, setSending] = useState(false);
  const partName = (p: SplitPart) => {
    const there = p.existing ? dishes.find((d) => d.id === p.existing) : undefined;
    return there ? dishName(there, lang) : (lang !== "en" && p.name_tr[lang]) || p.name;
  };
  const toggle = (i: number) => setKeep((k) => { const n = new Set(k); if (n.has(i)) n.delete(i); else n.add(i); return n; });
  // Done is shown on the dish itself: the window just goes. A failure stays.
  useEffect(() => { if (state === "done") onClose(); }, [state]);  // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="modal-backdrop picker" onClick={onClose}>
      <div className="modal import-progress" onClick={(e) => e.stopPropagation()}>
        <h4>{dishName(dish, lang)}</h4>
        <ul className="import-stages">
          {IMPORT_STAGES.map((s, i) => {
            const going = state === "running" || state === "choosing";
            const done = state === "done" || state === "failed" || (going && i < at);
            const now = going && i === at;
            return (
              <li key={s} className={done ? "done" : now ? "now" : ""}>
                {done ? "✓" : now && state === "choosing" ? "?" : now ? <span className="mv-ring btn-ring" aria-hidden /> : "○"}{" "}
                {t(STAGE_KEYS[s])}
              </li>
            );
          })}
        </ul>
        {state === "choosing" && (
          <div className="import-split">
            <p className="muted small">{t("food_split_intro")}</p>
            <label className="import-split-main">
              <input type="checkbox" checked disabled /> {dishName(dish, lang)} <span className="muted small">({t("food_split_main")})</span>
            </label>
            {parts.map((p, i) => (
              <label key={i}>
                <input type="checkbox" checked={keep.has(i)} disabled={sending} onChange={() => toggle(i)} />{" "}
                {partName(p)}{" "}
                <span className="muted small">({p.existing ? t("food_split_existing") : t("food_split_secondary")})</span>
              </label>
            ))}
          </div>
        )}
        {state === "failed" && (
          <div className="import-failed small">⚠ {t("food_import_failed")}: {(errors ?? []).join("; ")}</div>
        )}
        <div className="row-actions">
          {state === "failed" && <button type="button" className="active" onClick={() => onOpen(dish)}>{t("food_open_dish")}</button>}
          {state === "failed" && <button type="button" onClick={() => onRetry(dish.id)}>{t("food_retry")}</button>}
          {state === "choosing" && (
            <button type="button" className="active" disabled={sending}
                    onClick={() => { setSending(true); onChoose(dish.id, [...keep].sort()).finally(() => setSending(false)); }}>
              {sending && <span className="mv-ring btn-ring" aria-hidden />}
              {keep.size ? t("food_split_do") : t("food_split_keep_whole")}
            </button>
          )}
          <button type="button" className="ghost" onClick={onClose}>{t("close")}</button>
        </div>
      </div>
    </div>
  );
}

/** A new dish, or an existing one's name, category, url, rating and
 *  image. Name and category are shown and written in the UI's language; a
 *  changed one is translated into the others before it is saved (the
 *  spinner), so only a changed one is sent. */
function DishForm({
  dish,
  categories,
  onCancel,
  onDelete,
  onSubmit,
  onImport,
}: {
  dish: Dish | null;
  categories: Category[];
  onCancel: () => void;
  onDelete: (dishId: number) => void;
  onSubmit: (body: Partial<DishInput>) => Promise<unknown>;
  /** Import the recipe the dish already links to (never imported yet). */
  onImport: (dishId: number) => void;
}) {
  useBackToClose(onCancel);
  const { t, lang } = useT();
  const catName = (c: Category) => c.tr[lang] || c.name;
  const initialName = dish ? dishName(dish, lang) : "";
  const dishCategory = categories.find((c) => c.id === dish?.category_id);
  const initialCategory = dishCategory ? catName(dishCategory) : "";
  const [name, setName] = useState(initialName);
  const [category, setCategory] = useState(initialCategory);
  const [rating, setRating] = useState(dish?.rating ?? 7);
  // A category of the list is picked; typing one is only for a new one.
  const [newCategory, setNewCategory] = useState(false);
  const [saving, setSaving] = useState<"saving" | "translating" | null>(null);
  // The recipe the dish comes from: its page's url, and -- once one is
  // picked from the search here -- what the page says (the server keeps the
  // page itself).
  const [recipeUrl, setRecipeUrl] = useState(dish?.url ?? "");
  const [recipe, setRecipe] = useState<RecipeSummary | null>(null);
  const [findingRecipe, setFindingRecipe] = useState(false);
  const [viewingRecipe, setViewingRecipe] = useState(false);
  // undefined = keep existing image; string = newly picked URL to download.
  const [pickedUrl, setPickedUrl] = useState<string | undefined>(undefined);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [uploadError, setUploadError] = useState(false);

  const preview = pickedUrl
    ? pickedUrl
    : dish?.image
      ? dishImageUrl(dish.image)
      : null;

  const [askReplace, setAskReplace] = useState(false);
  const [askDelete, setAskDelete] = useState(false);
  const [recipeMenu, setRecipeMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!recipeMenu) return;
    const away = (e: PointerEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setRecipeMenu(false);
    };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [recipeMenu]);
  const canImport = Boolean(dish && recipeUrl && recipeUrl === dish.url && !dish.import.imported
    && dish.import.state !== "running");
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    // A new recipe for a dish that has ingredients or instructions replaces
    // them (its import): asked first.
    if (dish && recipeUrl.trim() && recipeUrl.trim() !== dish.url && (dish.ingredients || dish.instructions)) {
      setAskReplace(true);
      return;
    }
    save();
  };
  const save = () => {
    const body: Partial<DishInput> = { rating, url: recipeUrl.trim(), lang };
    if (!dish || name.trim() !== initialName) body.name = name.trim();
    if (!dish || category.trim() !== initialCategory) body.category = category.trim();
    // An upload is a data: URL; anything else was picked from the search.
    if (pickedUrl?.startsWith("data:")) body.image_data = pickedUrl;
    else if (pickedUrl !== undefined) body.image_url = pickedUrl;
    setSaving(body.name !== undefined || body.category ? "translating" : "saving");
    onSubmit(body).finally(() => setSaving(null));
  };

  return (
    <div className="modal-backdrop">
      <form
        className="modal dish-form"
        onClick={(e) => e.stopPropagation()}
        onSubmit={submit}
      >
        <h4>{dish ? t("food_edit_dish") : t("food_new_dish")}</h4>

        <div className="dish-form-recipe">
          <span className="dish-form-label">{t("food_recipe")}</span>
          {recipeUrl ? (
            <div className="recipe-row" ref={menuRef}>
              <button type="button" className="recipe-row-main" title={t("food_show_recipe")}
                      onClick={() => setViewingRecipe(true)}>
                <span aria-hidden>📖</span>
                <span className="recipe-row-text">
                  {recipe?.name && <strong>{recipe.name}</strong>}
                  <span className="muted small">{t("food_recipe_from", { site: siteOf(recipeUrl) })}</span>
                </span>
              </button>
              <a href={recipeUrl} target="_blank" rel="noopener noreferrer" title={t("food_open_recipe", { url: recipeUrl })}>↗</a>
              <button type="button" className="recipe-row-more" title={t("more")} aria-expanded={recipeMenu}
                      onClick={() => setRecipeMenu((o) => !o)}>⋯</button>
              {recipeMenu && (
                <div className="recipe-row-menu">
                  <button type="button" onClick={() => { setRecipeMenu(false); setFindingRecipe(true); }}>
                    {t("food_change_recipe")}
                  </button>
                  {canImport && (
                    <button type="button" onClick={() => { setRecipeMenu(false); onImport(dish!.id); }}>
                      {t("food_import_recipe")}
                    </button>
                  )}
                  <button type="button" className="danger"
                          onClick={() => { setRecipeMenu(false); setRecipeUrl(""); setRecipe(null); }}>
                    {t("remove")}
                  </button>
                </div>
              )}
            </div>
          ) : (
            <button type="button" onClick={() => setFindingRecipe(true)}>📖 {t("food_find_recipe")}</button>
          )}
        </div>

        <label>
          {t("name")}
          {/* Focused for a new dish only: opening one to edit pops no keyboard. */}
          <input value={name} onChange={(e) => setName(e.target.value)} autoFocus={!dish} />
        </label>

        <label>
          {t("food_category")}
          {newCategory ? (
            <span className="dish-form-newcat">
              <input
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder={t("food_category_placeholder")}
                autoFocus
              />
              <button type="button" className="ghost" title={t("cancel")}
                      onClick={() => { setNewCategory(false); setCategory(initialCategory); }}>
                ✕
              </button>
            </span>
          ) : (
            <select
              value={category}
              onChange={(e) => {
                if (e.target.value === "\0new") {
                  setNewCategory(true);
                  setCategory("");
                } else setCategory(e.target.value);
              }}
            >
              {/* None: one of the list is chosen for it on save. */}
              <option value="">{t("food_category_auto")}</option>
              {categories.map((c) => (
                <option key={c.id} value={catName(c)}>{catName(c)}</option>
              ))}
              <option value={"\0new"}>{t("food_category_new")}</option>
            </select>
          )}
        </label>


        <div className="dish-form-rating">
          <span className="dish-form-label">{t("food_rating")}</span>
          <StarRating value={rating} onChange={setRating} />
        </div>

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
              {preview ? t("food_change_image") : t("food_pick_image")}
            </button>
            <label className="dish-form-upload">
              {t("food_upload_image")}
              <input
                type="file"
                accept="image/*"
                hidden
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";  // the same file again is a change too
                  if (!file) return;
                  setUploadError(false);
                  shrinkImage(file)
                    .then(setPickedUrl)
                    .catch((err) => {
                      console.error("image upload:", file.name, file.type, file.size, err);
                      setUploadError(true);
                    });
                }}
              />
            </label>
            {uploadError && <span className="error small">{t("food_upload_failed")}</span>}
            {pickedUrl !== undefined && (
              <button
                type="button"
                className="ghost"
                onClick={() => setPickedUrl(undefined)}
              >
                {t("food_reset")}
              </button>
            )}
          </div>
        </div>

        <div className="dish-form-actions">
          {dish && (
            <button type="button" className="ghost danger dish-form-delete" disabled={saving !== null}
                    onClick={() => setAskDelete(true)}>
              🗑 {t("delete")}
            </button>
          )}
          <button type="submit" className="active" disabled={!name.trim() || saving !== null}>
            {saving === "translating" && <span className="mv-ring btn-ring" aria-hidden />}
            {saving === "translating" ? t("food_translating") : saving ? t("saving") : dish ? t("save") : t("create")}
          </button>
          <button type="button" className="ghost" onClick={onCancel} disabled={saving !== null}>
            {t("cancel")}
          </button>
        </div>
      </form>

      {viewingRecipe && <RecipeViewer url={recipeUrl} onClose={() => setViewingRecipe(false)} />}

      {findingRecipe && (
        <RecipeSearch
          initialQuery={name.trim()}
          onClose={() => setFindingRecipe(false)}
          onPicked={(r) => {
            setFindingRecipe(false);
            setRecipe(r);
            setRecipeUrl(r.url);
            // Fill in what is still empty: the name, and the image.
            if (!name.trim()) setName(r.name);
            if (r.image && !dish?.image && pickedUrl === undefined) setPickedUrl(r.image);
          }}
        />
      )}

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
      {askDelete && dish && (
        <ConfirmDialog message={t("food_delete_confirm", { name: dishName(dish, lang) })} yesLabel={t("delete")} danger
                       onYes={() => { setAskDelete(false); onDelete(dish.id); }}
                       onNo={() => setAskDelete(false)} />
      )}
      {askReplace && (
        <ConfirmDialog message={t("food_replace_confirm")}
                       onYes={() => { setAskReplace(false); save(); }}
                       onNo={() => setAskReplace(false)} />
      )}
    </div>
  );
}

// The recipe sites searched (recipe_sites.py), by their domains.
const SITE_NAMES: [RegExp, string][] = [
  [/(^|\.)giallozafferano\.it$/, "GialloZafferano"],
  [/(^|\.)chefkoch\.de$/, "Chefkoch"],
  [/(^|\.)bbcgoodfood\.com$/, "BBC Good Food"],
];

/** The site a recipe url is on: a searched one by name, else its host
 *  ("www." off); the url itself if it isn't one. */
function siteOf(url: string): string {
  try {
    const host = new URL(url).hostname.replace(/^www\./, "");
    return SITE_NAMES.find(([re]) => re.test(host))?.[1] ?? host;
  } catch {
    return url;
  }
}

/** 0-10 as ten stars: a click sets it, a click on the star it already is
 *  clears it. */
/** The rating of a dish, picked on its card: its stars in a small popup
 *  just below `at` (kept on the screen), drawn on the page's body. A star
 *  is the rating, the one it has already clears it; a tap outside or Back
 *  leaves it as it was. */
function RatingPopup({ at, value, onPick, onClose }: {
  at: DOMRect;
  value: number;
  onPick: (n: number) => void;
  onClose: () => void;
}) {
  useBackToClose(onClose);
  const width = Math.min(320, window.innerWidth - 16);
  const left = Math.max(8, Math.min(at.left, window.innerWidth - width - 8));
  const below = at.bottom + 6 + 52 < window.innerHeight;
  return createPortal(
    <div className="rating-popup-backdrop" onClick={onClose}>
      <div className="rating-popup" onClick={(e) => e.stopPropagation()}
           style={{ left, width, ...(below ? { top: at.bottom + 6 } : { bottom: window.innerHeight - at.top + 6 }) }}>
        <StarRating value={value} onChange={onPick} />
      </div>
    </div>,
    document.body,
  );
}

function StarRating({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  const [hover, setHover] = useState(0);
  const shown = hover || value;
  return (
    <span className="star-rating" onMouseLeave={() => setHover(0)} role="radiogroup">
      {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
        <button
          type="button"
          key={n}
          className={n <= shown ? "on" : ""}
          aria-label={String(n)}
          aria-checked={n === value}
          role="radio"
          onMouseEnter={() => setHover(n)}
          onClick={() => onChange(n === value ? 0 : n)}
        >
          ★
          <span className="star-num">{n}</span>
        </button>
      ))}
    </span>
  );
}

/** A picked photo as a JPEG data: URL, its long side at most 1600 px -- a
 *  phone's photo is several MB, and the API takes at most 1 MB a request. */
function shrinkImage(file: File, max = 1600): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      const scale = Math.min(1, max / Math.max(img.width, img.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      canvas.getContext("2d")?.drawImage(img, 0, 0, canvas.width, canvas.height);
      resolve(canvas.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("the browser could not decode it")); };
    img.src = url;
  });
}

/** The recipe a dish comes from: its name (once picked here) and site, a
 *  link to the page. */
function RecipeLink({ url, name }: { url: string; name?: string }) {
  const { t } = useT();
  return (
    <a className="recipe-link" href={url} target="_blank" rel="noopener noreferrer">
      {name && <strong>{name}</strong>}
      <span className="muted small">{t("food_recipe_from", { site: siteOf(url) })}</span>
    </a>
  );
}

/** "PT280M" -> "4 h 40 min"; "" for what isn't an ISO 8601 duration. */
function fmtDuration(iso: string): string {
  const m = /^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?/.exec(iso);
  if (!m || !(m[1] || m[2] || m[3])) return "";
  const mins = Number(m[1] ?? 0) * 1440 + Number(m[2] ?? 0) * 60 + Number(m[3] ?? 0);
  const h = Math.floor(mins / 60), min = mins % 60;
  return [h ? `${h} h` : "", min ? `${min} min` : ""].filter(Boolean).join(" ");
}

/** "carbohydrateContent" -> "carbohydrate", "saturatedFatContent" -> "saturated fat". */
const nutrientName = (key: string) =>
  key.replace(/Content$/, "").replace(/([A-Z])/g, " $1").toLowerCase();

/** A step's text with its {{ref:N}} mentions as the numbers on the photos. */
function StepText({ text }: { text: string }) {
  return (
    <>
      {text.split(/\n\n+/).map((para, i) => (
        <p key={i}>
          {para.split(/(\{\{ref:\d+\}\})/).map((part, j) => {
            const n = /^\{\{ref:(\d+)\}\}$/.exec(part);
            return n ? <span key={j} className="photo-badge">{n[1]}</span> : part;
          })}
        </p>
      ))}
    </>
  );
}

/** A dish's recipe as the server keeps it: what its page says, the
 *  ingredients as written there, and the preparation, every step with its
 *  photos in order -- to check it was fetched right. */
function RecipeViewer({ url, onClose }: { url: string; onClose: () => void }) {
  useBackToClose(onClose);
  const { t } = useT();
  const [page, setPage] = useState<{ recipe: RecipeSummary; preparation: RecipeStep[]; fetched_at: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    foodApi.getRecipePage(url).then((p) => live && setPage(p)).catch((e) => live && setError(serverMessage(e)));
    return () => { live = false; };
  }, [url]);

  const r = page?.recipe;
  const facts = r ? [
    r.rating && `★ ${r.rating}${r.rating_count ? ` (${r.rating_count})` : ""}`,
    r.comments && t("food_comments", { n: r.comments }),
    r.yield && t("food_yield", { n: r.yield }),
    fmtDuration(r.prep_time) && t("food_prep", { t: fmtDuration(r.prep_time) }),
    fmtDuration(r.cook_time) && t("food_cook", { t: fmtDuration(r.cook_time) }),
    fmtDuration(r.total_time) && t("food_total", { t: fmtDuration(r.total_time) }),
  ].filter(Boolean) : [];
  return (
    <div className="modal-backdrop picker" onClick={onClose}>
      <div className="modal recipe-viewer" onClick={(e) => e.stopPropagation()}>
        <div className="recipe-viewer-head">
          <h4>{r?.name ?? t("food_recipe")}</h4>
          <button type="button" className="ghost" onClick={onClose}>{t("close")}</button>
        </div>
        <div className="dish-info-scroll">
          {!page && !error && <p className="muted">{t("loading")}</p>}
          {error && <p className="error small">{error}</p>}
          {r && page && (
            <>
              <RecipeLink url={url} />
              {r.image && <img className="recipe-viewer-cover" src={r.image} alt="" />}
              {r.description && <p className="muted small">{r.description}</p>}
              {facts.length > 0 && <p className="small">{facts.join(" · ")}</p>}
              {Object.keys(r.nutrition).length > 0 && (
                <p className="muted small">
                  {Object.entries(r.nutrition).map(([k, v]) => `${nutrientName(k)} ${v}`).join(" · ")}
                </p>
              )}
              <h5>{t("food_ingredients")}</h5>
              <ul className="recipe-viewer-ingredients">
                {r.ingredients.map((line, i) => <li key={i}>{line}</li>)}
              </ul>
              <h5>{t("food_preparation")}</h5>
              {page.preparation.map((step, i) => (
                <div className="recipe-viewer-step" key={i}>
                  <span className="recipe-viewer-step-num">{i + 1}</span>
                  {step.images.length > 0 && (
                    <div className={"recipe-viewer-photos" + (step.images.length === 1 ? " single" : "")}>
                      {step.images.map((img, j) => (
                        <figure key={j}>
                          <img src={img.url} alt="" loading="lazy" />
                          {/* A strip of photos has their numbers printed in it already. */}
                          {img.steps.length === 1 && <figcaption>{img.steps[0]}</figcaption>}
                        </figure>
                      ))}
                    </div>
                  )}
                  <StepText text={step.text} />
                </div>
              ))}
              <p className="muted small">{t("food_fetched_at", { when: page.fetched_at })}</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

const HIT_DIFFICULTY: Record<string, Key> = {
  very_easy: "food_difficulty_very_easy", easy: "food_difficulty_easy", medium: "food_difficulty_medium",
  hard: "food_difficulty_hard", very_hard: "food_difficulty_very_hard",
};
const SHOWN_FIRST = 20; // the best results shown; More shows the rest

/** Search the recipe sites and pick a recipe: its page is fetched and kept
 *  by the server, and what it says comes back to fill the dish form in. */
function RecipeSearch({ initialQuery, onPicked, onClose }: {
  initialQuery: string;
  onPicked: (r: RecipeSummary) => void;
  onClose: () => void;
}) {
  useBackToClose(onClose);
  const { t } = useT();
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<RecipeHit[]>([]);
  const [shown, setShown] = useState(SHOWN_FIRST);
  const [failed, setFailed] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [fetching, setFetching] = useState<string | null>(null); // the url being fetched
  const [error, setError] = useState<string | null>(null);

  const run = (q: string) => {
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    setSearched(true);
    setResults([]);
    setFailed([]);
    foodApi
      .recipeSearch(q.trim())
      .then((r) => {
        setResults(r.results);
        setShown(SHOWN_FIRST);
        setFailed(Object.keys(r.failed));
      })
      .catch((e) => setError(serverMessage(e)))
      .finally(() => setLoading(false));
  };
  const pick = (hit: RecipeHit) => {
    if (fetching) return;
    setFetching(hit.url);
    setError(null);
    foodApi
      .recipePage(hit.url)
      .then((r) => onPicked(r.recipe))
      .catch((e) => setError(serverMessage(e)))
      .finally(() => setFetching(null));
  };

  return (
    <div className="modal-backdrop picker">
      <div className="modal image-picker" onClick={(e) => e.stopPropagation()}>
        <form className="picker-search" onSubmit={(e) => { e.preventDefault(); run(query); }}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("food_recipe_search_placeholder")}
            autoFocus
          />
          <button type="submit">{t("search")}</button>
          <button type="button" className="ghost" onClick={onClose}>{t("close")}</button>
        </form>
        {error && <p className="error small">{error}</p>}
        {!searched && <p className="muted small">{t("food_recipe_search_hint")}</p>}
        {failed.length > 0 && <p className="muted small">{t("food_sites_failed", { sites: failed.join(", ") })}</p>}
        <div className="picker-grid">
          {results.slice(0, shown).map((hit) => (
            <button
              type="button"
              key={hit.url}
              className={"picker-cell recipe-cell" + (fetching === hit.url ? " fetching" : "")}
              title={hit.description}
              disabled={fetching !== null}
              onClick={() => pick(hit)}
            >
              {hit.image ? <img src={hit.image} alt="" loading="lazy" /> : <span className="dish-card-img-empty">🍽</span>}
              <span className="recipe-cell-caption">
                <span className="recipe-cell-title">
                  {fetching === hit.url && <span className="mv-ring btn-ring" aria-hidden />}
                  {hit.title}
                </span>
                <span className="recipe-cell-cat">{[hit.site, hit.category].filter(Boolean).join(" · ")}</span>
                <span className="recipe-cell-facts">
                  {[
                    hit.rating && `★ ${hit.rating}${hit.votes ? ` (${hit.votes})` : ""}`,
                    hit.comments && `💬 ${hit.comments}`,
                    HIT_DIFFICULTY[hit.difficulty] && t(HIT_DIFFICULTY[hit.difficulty]),
                    hit.time && `⏱ ${hit.time}`,
                    hit.kcal && `${hit.kcal} kcal`,
                  ].filter(Boolean).join(" · ")}
                </span>
              </span>
            </button>
          ))}
        </div>
        {loading && <p className="muted">{t("food_searching")}</p>}
        {searched && !loading && !error && results.length === 0 && <p className="muted">{t("food_no_results")}</p>}
        {shown < results.length && !loading && (
          <div className="row-actions">
            <button type="button" className="ghost" onClick={() => setShown(results.length)}>{t("food_more_results")}</button>
          </div>
        )}
      </div>
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
  useBackToClose(onClose);
  const { t } = useT();
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
            placeholder={t("food_image_search_placeholder")}
            autoFocus
          />
          <button type="submit">{t("search")}</button>
          <button type="button" className="ghost" onClick={onClose}>
            {t("close")}
          </button>
        </form>

        {loading && <p className="muted">{t("food_searching")}</p>}
        {error && <p className="error small">{error}</p>}
        {!searched && !loading && (
          <p className="muted small">
            {t("food_search_hint").split("{search}").map((part, i) => (
              <span key={i}>{i > 0 && <strong>{t("search")}</strong>}{part}</span>
            ))}
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
          <p className="muted">{t("food_no_results")}</p>
        )}
      </div>
    </div>
  );
}
