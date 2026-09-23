import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { MovieItem } from "../api";

/** The film library as pages of covers, turned with the arrows.
 *
 *  A page is exactly as many covers as fit the space it is given — as many
 *  columns as the width takes, as many rows as the height takes — so there is
 *  never a scrollbar, and changing the cover size or the window re-lays the
 *  pages out. The covers are Plex's own posters (api/routers/movies.py,
 *  /poster); a film Plex has none for shows its name in an empty frame.
 *
 *  What is remembered is the first film on the page rather than the page
 *  number, so resizing keeps you where you were instead of throwing you onto
 *  whatever page now has that number. */

/** Room under each cover for its name. */
const CAPTION = 22;

function posterUrl(m: MovieItem, px: number): string {
  return "/api/movies/poster?" + new URLSearchParams({ id: m.id, w: String(px), v: m.poster ?? "" });
}

export function CoverBook({
  items, size, selectedId, onPick, active, resetKey,
}: {
  items: MovieItem[];
  /** Cover width in CSS pixels. */
  size: number;
  selectedId: string | null;
  onPick: (m: MovieItem) => void;
  /** Whether the book is on screen — the arrow keys are only its while it is. */
  active: boolean;
  /** Going back to the first page whenever this changes (the search text). */
  resetKey: string;
}) {
  const pageRef = useRef<HTMLDivElement | null>(null);
  const [box, setBox] = useState({ w: 0, h: 0 });
  const [first, setFirst] = useState(() => Math.max(0, items.findIndex((m) => m.id === selectedId)));
  const [dir, setDir] = useState<"next" | "prev" | "">("");
  const [broken, setBroken] = useState<Set<string>>(new Set());

  useLayoutEffect(() => {
    const el = pageRef.current;
    if (!el) return;
    const measure = () => setBox({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const gap = Math.max(10, Math.round(size * 0.1));
  const cols = Math.max(1, Math.floor((box.w + gap) / (size + gap)));
  const rows = Math.max(1, Math.floor((box.h + gap) / (size * 1.5 + CAPTION + gap)));
  const per = cols * rows;
  const pages = Math.max(1, Math.ceil(items.length / per));
  const page = Math.min(pages - 1, Math.floor(first / per));
  const shown = items.slice(page * per, page * per + per);
  // Plex scales the poster; ask for the size it is drawn at on this screen,
  // rounded so neighbouring slider positions share the browser's cache.
  const px = Math.min(1000, Math.ceil((size * (window.devicePixelRatio || 1)) / 100) * 100);

  const lastReset = useRef(resetKey);
  useEffect(() => {
    if (lastReset.current === resetKey) return;
    lastReset.current = resetKey;
    setFirst(0); setDir("");
  }, [resetKey]);

  const go = (to: number) => {
    const p = Math.max(0, Math.min(pages - 1, to));
    if (p === page) return;
    setDir(p > page ? "next" : "prev");
    setFirst(p * per);
  };

  // Arrow keys turn the page — unless something that uses them has focus.
  const goRef = useRef(go);
  goRef.current = go;
  const pageNow = useRef(page);
  pageNow.current = page;
  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.closest("input, select, textarea, video, iframe") || t.isContentEditable)) return;
      const p = pageNow.current;
      const to = e.key === "ArrowRight" || e.key === "PageDown" ? p + 1
        : e.key === "ArrowLeft" || e.key === "PageUp" ? p - 1
        : e.key === "Home" ? 0
        : e.key === "End" ? Infinity
        : null;
      if (to === null) return;
      e.preventDefault();
      goRef.current(to);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active]);

  // The pages either side are fetched ahead, so turning one shows covers
  // rather than empty frames filling in.
  useEffect(() => {
    for (const m of [...items.slice((page + 1) * per, (page + 2) * per),
                     ...items.slice(Math.max(0, page - 1) * per, page * per)]) {
      if (m.poster) new Image().src = posterUrl(m, px);
    }
  }, [items, page, per, px]);

  // A swipe turns the page on a touch screen.
  const touchX = useRef<number | null>(null);

  return (
    <div className="mv-book">
      <button className="mv-turn" disabled={page === 0} onClick={() => go(page - 1)}
              title="Previous page (←)">‹</button>
      <div
        className="mv-bookpage"
        ref={pageRef}
        onTouchStart={(e) => { touchX.current = e.touches[0].clientX; }}
        onTouchEnd={(e) => {
          if (touchX.current === null) return;
          const dx = e.changedTouches[0].clientX - touchX.current;
          touchX.current = null;
          if (Math.abs(dx) > 50) go(dx < 0 ? page + 1 : page - 1);
        }}
      >
        {box.w > 0 && (
          <div
            key={`${page}/${per}`}
            className={"mv-covers" + (dir ? ` turn-${dir}` : "")}
            style={{
              gridTemplateColumns: `repeat(${cols}, ${size}px)`,
              gridTemplateRows: `repeat(${rows}, ${Math.round(size * 1.5) + CAPTION}px)`,
              columnGap: gap,
            }}
          >
            {shown.map((m) => (
              <button
                key={m.id}
                className={"mv-cover" + (selectedId === m.id ? " active" : "")}
                title={m.title}
                onClick={() => onPick(m)}
              >
                <span className="mv-coverart">
                  {m.poster && !broken.has(m.id) ? (
                    <img src={posterUrl(m, px)} alt="" draggable={false}
                         onError={() => setBroken((b) => new Set(b).add(m.id))} />
                  ) : (
                    <span className="mv-coverblank">{m.title}</span>
                  )}
                </span>
                <span className="mv-covertitle">{m.title}</span>
              </button>
            ))}
          </div>
        )}
        {!items.length && <p className="muted small mv-bookempty">No matches.</p>}
      </div>
      <button className="mv-turn" disabled={page >= pages - 1} onClick={() => go(page + 1)}
              title="Next page (→)">›</button>
      <div className="mv-bookfoot muted small">
        {items.length ? `${page * per + 1}–${Math.min(items.length, page * per + per)} of ${items.length}` : ""}
        <span className="mv-bookpages">page {page + 1} / {pages}</span>
      </div>
    </div>
  );
}
