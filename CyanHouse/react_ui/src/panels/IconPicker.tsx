import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useBackToClose } from "../backClose";
import { useT } from "../i18n";
import { usePhone } from "../narrow";
import { Floating } from "./Floating";
import { Icon } from "./icons";

// The two icon sets a category can take its icon from, packed by
// scripts/icon-sets.mjs into one file each under public/: fetched the first
// time something needs one, and kept for the page's life (and by the
// browser's cache).
//   line:  Tabler's outline icons (tabler.io, MIT), drawn in currentColor;
//          stored by bare name ("pig-money").
//   color: Microsoft's Fluent Emoji, flat (MIT), in their own colours;
//          stored as "fluent:<name>" ("fluent:money-bag").
// Or a picture of one's own (uploaded): shrunk here to a small PNG and
// stored whole, as its data: URL.
type IconSet = "line" | "color";
type IconEntry = { name: string; category: string; tags: string; svg: string };

const FILES: Record<IconSet, string> = { line: "tabler-icons.json", color: "fluent-icons.json" };
const FLUENT = "fluent:";

const loading: Partial<Record<IconSet, Promise<Map<string, IconEntry>>>> = {};

function loadSet(set: IconSet): Promise<Map<string, IconEntry>> {
  // Under the app's base (/ui/ behind nginx), not the site's root.
  return loading[set] ??= fetch(import.meta.env.BASE_URL + FILES[set])
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
    .then((d: { icons: [string, string, string, string][] }) =>
      new Map(d.icons.map(([name, category, tags, svg]) => [name, { name, category, tags, svg }])))
    .catch((e) => { delete loading[set]; throw e; });   // a later call tries again
}

function useIconSet(set: IconSet | null): Map<string, IconEntry> | null {
  const [icons, setIcons] = useState<{ set: IconSet; map: Map<string, IconEntry> } | null>(null);
  useEffect(() => {
    if (!set) return;
    let alive = true;
    loadSet(set).then((map) => alive && setIcons({ set, map })).catch(() => {});
    return () => { alive = false; };
  }, [set]);
  return icons && icons.set === set ? icons.map : null;
}

const TABLER_NAME = /^[a-z0-9-]+$/;

/** Which set a stored icon comes from and its name there; null for anything
 *  else (an emoji typed before the picker existed). */
function parse(icon: string): { set: IconSet; name: string } | null {
  if (icon.startsWith(FLUENT)) return { set: "color", name: icon.slice(FLUENT.length) };
  if (TABLER_NAME.test(icon)) return { set: "line", name: icon };
  return null;
}

// An uploaded picture: drawn into a square this big (kept whole, centred,
// see-through around it) and stored as a PNG data: URL.
const IMAGE = "data:image/";
const IMAGE_SIZE = 96;
function shrink(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const k = IMAGE_SIZE / Math.max(img.naturalWidth, img.naturalHeight);
      const w = Math.max(1, Math.round(img.naturalWidth * k)), h = Math.max(1, Math.round(img.naturalHeight * k));
      const c = document.createElement("canvas");
      c.width = c.height = IMAGE_SIZE;
      c.getContext("2d")!.drawImage(img, (IMAGE_SIZE - w) / 2, (IMAGE_SIZE - h) / 2, w, h);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL("image/png"));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("not an image")); };
    img.src = url;
  });
}

const keyOf = (set: IconSet, name: string) => (set === "color" ? FLUENT + name : name);

/** `fit` (a colour icon shown beside text): the view framed on what is
 *  actually drawn, a square around its middle — Fluent's emojis sit higher
 *  or lower in their 32px box from one to the next, so beside a line of
 *  text they'd look out of line. */
function Svg({ set, svg, fit = false }: { set: IconSet; svg: string; fit?: boolean }) {
  const ref = useRef<SVGSVGElement>(null);
  const [view, setView] = useState("0 0 32 32");
  useLayoutEffect(() => {
    if (!fit || set !== "color" || !ref.current) return;
    const b = ref.current.getBBox();
    if (!b.width || !b.height) return;   // not laid out (hidden): keep the box
    const size = Math.max(b.width, b.height) * 1.04;
    setView(`${b.x + b.width / 2 - size / 2} ${b.y + b.height / 2 - size / 2} ${size} ${size}`);
  }, [fit, set, svg]);
  return set === "line" ? (
    <svg className="cat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
         strokeLinecap="round" strokeLinejoin="round" aria-hidden dangerouslySetInnerHTML={{ __html: svg }} />
  ) : (
    <svg ref={ref} className="cat-icon" viewBox={view} aria-hidden dangerouslySetInnerHTML={{ __html: svg }} />
  );
}

/** A stored icon, drawn from its set; an old emoji shows as it is. */
export function CatIcon({ icon }: { icon: string }) {
  const parsed = parse(icon);
  const icons = useIconSet(parsed?.set ?? null);
  if (!icon) return null;
  if (icon.startsWith(IMAGE)) return <img className="cat-icon" src={icon} alt="" />;
  if (!parsed) return <span className="cat-icon">{icon}</span>;
  return <Svg set={parsed.set} svg={icons?.get(parsed.name)?.svg ?? ""} fit />;
}

// The groups a budget mostly needs, shown first (in this order), before all the others.
const STARTERS: Record<IconSet, string[]> = {
  line: ["Currencies", "E-commerce", "Buildings", "Vehicles", "Food", "Health", "Sport", "Devices"],
  color: ["Objects", "Food & Drink", "Travel & Places", "Activities", "Animals & Nature", "Symbols"],
};
// The grid draws this many icons at a time and the next batch as its end
// scrolls into view, so even Tabler's five thousand open at once.
const BATCH = 300;

/** A button showing the current icon; tapped, a box with the two sets
 *  (line / colour), a search over the shown one (names, tags and groups),
 *  and a grid of every match — the whole set when nothing is typed. */
export function IconPicker({ value, onChange }: { value: string; onChange: (icon: string) => void }) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const [set, setSet] = useState<IconSet>(() => parse(value)?.set ?? "color");
  const [query, setQuery] = useState("");
  const icons = useIconSet(open ? set : null);
  const [limit, setLimit] = useState(BATCH);
  const phone = usePhone();
  const box = useRef<HTMLSpanElement>(null);
  const full = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLSpanElement>(null);
  const grid = useRef<HTMLSpanElement>(null);
  const end = useRef<HTMLSpanElement>(null);
  useBackToClose(() => setOpen(false), open);
  useEffect(() => {
    if (!open) return;
    const down = (e: PointerEvent) => {
      const at = e.target as Node;
      if (!box.current?.contains(at) && !full.current?.contains(at) && !pop.current?.contains(at)) setOpen(false);
    };
    document.addEventListener("pointerdown", down);
    return () => document.removeEventListener("pointerdown", down);
  }, [open]);

  const matches = useMemo(() => {
    if (!icons) return [];
    const all = [...icons.values()];
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) {
      const starters = STARTERS[set];
      const rank = (e: IconEntry) => { const i = starters.indexOf(e.category); return i < 0 ? starters.length : i; };
      return all.sort((a, b) => rank(a) - rank(b));   // stable: each group keeps its own order
    }
    const hay = (e: IconEntry) => `${e.name} ${e.tags} ${e.category}`.toLowerCase();
    return all.filter((e) => words.every((w) => hay(e).includes(w)))
      // a hit in the name before one only in the tags
      .sort((a, b) => Number(!a.name.includes(words[0])) - Number(!b.name.includes(words[0])));
  }, [icons, query, set]);

  // A new search or set starts again from the top, one batch in.
  useEffect(() => {
    setLimit(BATCH);
    grid.current?.scrollTo({ top: 0 });
  }, [query, set]);
  useEffect(() => {
    const el = end.current;
    if (!el || limit >= matches.length) return;
    const seen = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) setLimit((n) => n + BATCH);
    }, { root: grid.current, rootMargin: "200px" });
    seen.observe(el);
    return () => seen.disconnect();
  }, [limit, matches.length]);

  const pick = (icon: string) => { onChange(icon); setOpen(false); };
  const current = parse(value);
  const content = <>
    <span className="icon-picker-sets">
      {(["color", "line"] as IconSet[]).map((s) => (
        <button type="button" key={s} className={s === set ? "active" : ""} onClick={() => setSet(s)}>
          {t(s === "color" ? "fin_icon_color" : "fin_icon_line")}
        </button>
      ))}
    </span>
    <span className="icon-picker-head">
      <input value={query} placeholder={t("fin_icon_search")} onChange={(e) => setQuery(e.target.value)} />
      {/* A picture of one's own, then no icon at all. */}
      <label className="icon-picker-tool" title={t("fin_icon_upload")} aria-label={t("fin_icon_upload")}>
        <Icon name="upload" size={18} className="" />
        <input type="file" accept="image/*" hidden onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) shrink(file).then(pick).catch(() => {});
        }} />
      </label>
      <button type="button" className="ghost icon-picker-tool" title={t("fin_icon_none")} aria-label={t("fin_icon_none")}
              onClick={() => pick("")}>
        <Icon name="close" size={18} className="" />
      </button>
    </span>
    {!icons ? <span className="muted">{t("loading")}</span> : (
      <span className="icon-picker-grid" ref={grid}>
        {matches.slice(0, limit).map((e) => (
          <button type="button" key={e.name} title={e.name}
                  className={current?.set === set && current.name === e.name ? "active" : ""}
                  onClick={() => pick(keyOf(set, e.name))}>
            <Svg set={set} svg={e.svg} />
          </button>
        ))}
        {limit < matches.length && <span className="icon-picker-end" ref={end} />}
      </span>
    )}
  </>;

  return (
    <span className="icon-picker" ref={box}>
      <button type="button" ref={btn} className={"ghost icon-picker-btn" + (open ? " active" : "")}
              title={!value ? t("fin_icon_none") : value.startsWith(IMAGE) ? t("fin_icon_uploaded") : value} onClick={() => setOpen(!open)}>
        {value ? <CatIcon icon={value} /> : <span className="muted">—</span>}
      </button>
      {open && !phone && <Floating anchor={btn} ref={pop} className="icon-picker-pop" maxHeight={460}>{content}</Floating>}
      {/* On a phone: the whole screen, its way back a bar named as the field. */}
      {open && phone && createPortal(
        <div className="modal-backdrop settings-full" ref={full}>
          <div className="settings-full-page icon-picker-full">
            <button type="button" className="ghost back-bar" onClick={() => setOpen(false)}>
              <Icon name="left" size={16} className="back-bar-arrow" />
              <span className="back-bar-name">{t("fin_icon")}</span>
            </button>
            <span className="icon-picker-pop">{content}</span>
          </div>
        </div>,
        document.body,
      )}
    </span>
  );
}
