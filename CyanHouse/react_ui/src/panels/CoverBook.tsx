import { useEffect, useLayoutEffect, useRef, useState } from "react";

/** A library as pages of covers, turned with the arrows: the films (Plex's
 *  posters), and the Music tab's artists.
 *
 *  A page is exactly as many covers as fit the space it is given — as many
 *  columns as the width takes, as many rows as the height takes — so there is
 *  never a scrollbar, and changing the cover size or the window re-lays the
 *  pages out. Only one page of covers is loaded at a time (and the pages
 *  either side, ahead), which is what keeps a big library quick. An item
 *  with no picture shows its name in an empty frame.
 *
 *  What is remembered is the first film on the page rather than the page
 *  number, so resizing keeps you where you were instead of throwing you onto
 *  whatever page now has that number. */

/** Room under each cover for its name (and a second line, when there is one). */
const CAPTION = 22;
const SUBCAPTION = 16;

export function CoverBook<T extends { id: string; title: string }>({
  items, size, selectedId, onPick, active, resetKey, art, sub, aspect = 1.5, round = false,
}: {
  items: T[];
  /** Cover width in CSS pixels. */
  size: number;
  /** An item's picture at about `px` pixels wide, or null for none. */
  art: (item: T, px: number) => string | null;
  /** A second, quieter line under the name. */
  sub?: (item: T) => string;
  /** Height over width: 1.5 for a film poster, 1 for a square. */
  aspect?: number;
  /** Round pictures (artists) rather than rectangles. */
  round?: boolean;
  selectedId: string | null;
  onPick: (m: T) => void;
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
  const caption = CAPTION + (sub ? SUBCAPTION : 0);
  const rows = Math.max(1, Math.floor((box.h + gap) / (size * aspect + caption + gap)));
  const per = cols * rows;
  const pages = Math.max(1, Math.ceil(items.length / per));
  const page = Math.min(pages - 1, Math.floor(first / per));
  const shown = items.slice(page * per, page * per + per);
  // The server scales the picture; ask for the size it is drawn at on this
  // screen, rounded so neighbouring slider positions share the browser's cache.
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
      const url = art(m, px);
      if (url) new Image().src = url;
    }
  }, [items, page, per, px]);

  // A swipe turns the page on a touch screen.
  const touchX = useRef<number | null>(null);

  return (
    <div className={"mv-book" + (round ? " round" : "")}>
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
              gridTemplateRows: `repeat(${rows}, ${Math.round(size * aspect) + caption}px)`,
              columnGap: gap,
            }}
          >
            {shown.map((m) => {
              const url = art(m, px);
              return (
                <button
                  key={m.id}
                  className={"mv-cover" + (selectedId === m.id ? " active" : "")}
                  title={m.title}
                  onClick={() => onPick(m)}
                >
                  <span className="mv-coverart" style={{ aspectRatio: `1 / ${aspect}` }}>
                    {url && !broken.has(m.id) ? (
                      <img src={url} alt="" draggable={false}
                           onError={() => setBroken((b) => new Set(b).add(m.id))} />
                    ) : (
                      <span className="mv-coverblank">{m.title}</span>
                    )}
                  </span>
                  <span className="mv-covertitle">{m.title}</span>
                  {sub && <span className="mv-coversub">{sub(m)}</span>}
                </button>
              );
            })}
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
