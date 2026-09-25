import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ACCESS_RANK, api, FolderAccess, StagedFile } from "../api";
import { AccessBadge } from "./ShareDialog";

/** Tiles drawn at a time: a first screenful or two, then another batch
 *  whenever the end of what is drawn comes near — so ten thousand photos
 *  do not mean ten thousand tiles on the page at once. */
const BATCH = 150;
const GAP = 8;
/** A picture whose size the server does not know yet is laid out as this. */
const UNKNOWN_RATIO = 1.5;

/** `full`: the row spans the width (its tiles share out the last pixel of
 *  rounding); the last row of a folder does not, and keeps its tiles' sizes. */
type Row = { items: { file: StagedFile; index: number; w: number }[]; h: number; full: boolean };

/** Justified rows: pictures fill a row, left to right, until it is as wide
 *  as `width` at about `target` height; the row is then scaled to fit that
 *  width exactly. The last row keeps the target height rather than being
 *  stretched — unless `complete` is false (the folder is only partly drawn),
 *  when it is left out, so it does not change shape as more arrive. */
function justify(list: StagedFile[], width: number, target: number, complete: boolean): Row[] {
  const rows: Row[] = [];
  let cur: { file: StagedFile; index: number; r: number }[] = [];
  let sum = 0;
  const ratio = (f: StagedFile) => (f.width && f.height ? f.width / f.height : UNKNOWN_RATIO);
  list.forEach((file, index) => {
    const r = ratio(file);
    cur.push({ file, index, r });
    sum += r;
    const gaps = GAP * (cur.length - 1);
    if (sum * target + gaps >= width) {
      const h = (width - gaps) / sum;
      rows.push({ h, full: true, items: cur.map((c) => ({ file: c.file, index: c.index, w: c.r * h })) });
      cur = [];
      sum = 0;
    }
  });
  if (cur.length && complete) {
    rows.push({ h: target, full: false, items: cur.map((c) => ({ file: c.file, index: c.index, w: c.r * target })) });
  }
  return rows;
}

/** A folder shown as a card on the gallery's first layer: every picture
 *  under it (its subfolders' too), and the one on its cover. */
type Album = { path: string; name: string; count: number; albums: number; cover: StagedFile | null; depth: number };

const byName = (a: string, b: string) => a.localeCompare(b, undefined, { numeric: true });

/** The Images tab's default view. First the folders, as cards with a
 *  picture on the cover — ten thousand photos are not all put on one page —
 *  and inside one, its own subfolders the same way and then its pictures,
 *  in justified rows: left to right in name order, every picture of a row
 *  the same height and the row as wide as the page, none of them cropped.
 *  The rows are worked out from the pictures' sizes (the server knows them
 *  before any thumbnail loads), so nothing moves as they load, and loading
 *  more only adds rows underneath. A search looks through everything under
 *  the open folder and shows what matches folder by folder.
 *  A click opens the picture full screen (ImageViewer), where the arrows
 *  walk through the folder it was opened from.
 *
 *  The thumbnails are small copies made by the server (api/services/
 *  thumbs.py); the viewer shows the picture itself. Photos dropped on a
 *  folder's card, or on the open folder, from the computer are added to it;
 *  moving and renaming them is the Folders view's job. */
export function ImageGallery({ area, files, loading, query, size, folder: at, onFolder, onOpen, onUpload, onShare }: {
  area: string;
  files: StagedFile[];
  /** The listing has not arrived yet. */
  loading?: boolean;
  query: string;
  /** Row height and card width in pixels (the size slider). */
  size: number;
  /** The folder open ("" is the top), and a way to open another. */
  folder: string;
  onFolder: (folder: string) => void;
  onOpen: (list: StagedFile[], index: number) => void;
  /** Put what was dropped into `folder` ("" is the top) — it may hold
   *  whole folders. Absent for someone who may not. */
  onUpload?: (from: DataTransfer, folder: string) => void;
  /** Open an album's sharing — offered on the badge of albums this user
   *  may change (their own; for an admin, the ones nobody owns). */
  onShare?: (folder: string) => void;
}) {
  const q = query.trim().toLowerCase();
  // What a drag of files is over: a folder's card ("a:" + folder), a
  // section ("s:" + folder), or the space around them ("bg"). Kept apart
  // because the top folder's name is "" too, and dropping on one must not
  // light up everything.
  const [dropOn, setDropOn] = useState<string | null>(null);
  // Each folder's access, from the listing (the server attaches it).
  const accessOf = useMemo(() => {
    const m = new Map<string, FolderAccess>();
    for (const f of files) if (f.kind === "folder" && f.access) m.set(f.path, f.access);
    return m;
  }, [files]);
  const mayAdd = (folder: string) => {
    if (!folder) return true;
    const a = accessOf.get(folder);
    return !!a && ACCESS_RANK[a.level] >= ACCESS_RANK.add;
  };
  const dropProps = (folder: string, zone: string) => onUpload && mayAdd(folder) ? {
    onDragOver: (e: React.DragEvent) => {
      if (!e.dataTransfer.types.includes("Files")) return;
      e.preventDefault();
      e.stopPropagation();
      e.dataTransfer.dropEffect = "copy";
      setDropOn(zone);
    },
    onDragLeave: (e: React.DragEvent) => {
      if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDropOn((c) => (c === zone ? null : c));
    },
    onDrop: (e: React.DragEvent) => {
      if (!e.dataTransfer.types.includes("Files")) return;
      e.preventDefault();
      e.stopPropagation();
      setDropOn(null);
      onUpload(e.dataTransfer, folder);
    },
  } : {};

  const inside = (f: string) => at === "" || f === at || f.startsWith(at + "/");
  // The open folder's subfolders, as cards, and its own pictures.
  const [albums, direct] = useMemo(() => {
    const cards = new Map<string, Album>();
    const kids = new Map<string, Set<string>>();
    const own: StagedFile[] = [];
    for (const f of files) {
      if (f.kind !== "image" || !inside(f.folder)) continue;
      if (f.folder === at) { own.push(f); continue; }
      const rest = (at ? f.folder.slice(at.length + 1) : f.folder).split("/");
      const path = at ? `${at}/${rest[0]}` : rest[0];
      const depth = rest.length;
      const a = cards.get(path);
      if (!a) cards.set(path, { path, name: rest[0], count: 1, albums: 0, cover: f, depth });
      else {
        a.count++;
        // The cover: the first picture of the shallowest folder in it.
        if (!a.cover || depth < a.depth || (depth === a.depth && byName(f.path, a.cover.path) < 0)) {
          a.cover = f;
          a.depth = depth;
        }
      }
      if (rest.length > 1) {
        const k = kids.get(path) ?? new Set<string>();
        k.add(rest[1]);
        kids.set(path, k);
      }
    }
    // Folders with no pictures in them yet (a new album) are albums too.
    for (const f of files) {
      if (f.kind !== "folder" || !inside(f.path) || f.path === at) continue;
      const rest = (at ? f.path.slice(at.length + 1) : f.path).split("/");
      const path = at ? `${at}/${rest[0]}` : rest[0];
      if (!cards.has(path)) cards.set(path, { path, name: rest[0], count: 0, albums: 0, cover: null, depth: 99 });
      if (rest.length > 1) {
        const k = kids.get(path) ?? new Set<string>();
        k.add(rest[1]);
        kids.set(path, k);
      }
    }
    for (const [path, k] of kids) cards.get(path)!.albums = k.size;
    own.sort((a, b) => byName(a.name, b.name));
    return [[...cards.values()].sort((a, b) => byName(a.name, b.name)), own] as const;
  }, [files, at]);

  // Searching: what matches under the open folder, folder by folder.
  const sections = useMemo(() => {
    if (!q) return direct.length ? [[at, direct] as [string, StagedFile[]]] : [];
    const by = new Map<string, StagedFile[]>();
    for (const f of files) {
      if (f.kind !== "image" || !inside(f.folder)) continue;
      if (!f.path.toLowerCase().includes(q)) continue;
      const l = by.get(f.folder) ?? [];
      l.push(f);
      by.set(f.folder, l);
    }
    for (const l of by.values()) l.sort((a, b) => byName(a.name, b.name));
    // The open folder first, then the others by name.
    return [...by.entries()].sort(([a], [b]) => (a === at ? -1 : b === at ? 1 : byName(a, b)));
  }, [files, q, at, direct]);

  // The width the rows fill: the gallery's, less its padding.
  const box = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const measure = () => {
      const cs = getComputedStyle(el);
      setWidth(Math.floor(el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const dpr = Math.min(2, window.devicePixelRatio || 1);

  // Where each folder was scrolled to, so going back up lands where the
  // folder was left rather than at the top.
  const scrolled = useRef(new Map<string, number>());
  const go = (folder: string) => {
    if (box.current) scrolled.current.set(at, box.current.scrollTop);
    onFolder(folder);
  };
  useLayoutEffect(() => {
    if (box.current) box.current.scrollTop = scrolled.current.get(at) ?? 0;
  }, [at]);

  // How many tiles are drawn, over all the sections in order. Back to the
  // first batch when the search or the folder changes; a new photo
  // arriving does not.
  const [limit, setLimit] = useState(BATCH);
  useEffect(() => { setLimit(BATCH); }, [q, at]);
  const total = sections.reduce((n, [, list]) => n + list.length, 0);
  const more = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = more.current;
    if (!el || limit >= total) return;
    const io = new IntersectionObserver(
      (seen) => { if (seen.some((x) => x.isIntersecting)) setLimit((n) => n + BATCH); },
      { rootMargin: "1200px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [limit, total, sections]);
  let budget = limit;
  const drawn = sections.map(([folder, list]) => {
    const take = Math.max(0, Math.min(list.length, budget));
    budget -= take;
    return [folder, list, take] as const;
  }).filter(([, , take]) => take > 0)
    .map(([folder, list, take]) =>
      [folder, list, width > 0 ? justify(list.slice(0, take), width, size, take === list.length) : []] as const);

  const crumbs = at ? at.split("/") : [];
  // A new folder, here: offered where this user may add (image_access.py).
  const canCreate = !q && !!onUpload && mayAdd(at);
  const showAlbums = !q && (albums.length > 0 || canCreate);
  const picturesFirst = !!at && !q;
  const albumsBlock = showAlbums && (
    <>
      {picturesFirst && sections.length > 0 && (
        <header className="ig-head ig-folderhead">
          <h3>Folders</h3>
          <span className="ig-count">{albums.length}</span>
          <span className="ig-line" aria-hidden />
        </header>
      )}
      <div className="ig-albums" style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${size}px, 1fr))` }}>
            {albums.map((a) => (
              <button key={a.path} className={"ig-album" + (dropOn === "a:" + a.path ? " dropping" : "")}
                      title={a.path} onClick={() => go(a.path)} {...dropProps(a.path, "a:" + a.path)}>
                <span className="ig-cover">
                  {accessOf.get(a.path) && (
                    <AccessBadge access={accessOf.get(a.path)!} className="ig-albumaccess"
                                 onShare={onShare ? () => onShare(a.path) : undefined} />
                  )}
                  {a.cover
                    ? <AlbumCover src={api.prepThumbUrl(area, a.cover.path, Math.round(size * 1.5 * dpr), a.cover.modified)} />
                    : <span className="ig-broken ig-emptyalbum">📁</span>}
                </span>
                <span className="ig-albumname">{a.name}</span>
                <span className="ig-albumsub">
                  {a.count} {a.count === 1 ? "picture" : "pictures"}
                  {a.albums > 0 && ` · ${a.albums} ${a.albums === 1 ? "folder" : "folders"}`}
                </span>
              </button>
            ))}
            {canCreate && <NewAlbum area={area} folder={at} size={size} />}
          </div>
    </>
  );
  const pictures = (
    <>
      {!showAlbums && !sections.length && (
        <p className="muted small ig-empty">
          {loading ? "Reading the library…" : q ? "No pictures match." : "No pictures here yet."}
        </p>
      )}
      {drawn.map(([folder, list, rows]) => (
        <section key={folder} className={"ig-section" + (dropOn === "s:" + folder ? " dropping" : "")}
                 {...dropProps(folder, "s:" + folder)}>
          {(q || (showAlbums && !picturesFirst)) && (
            <header className="ig-head">
              <h3>{q ? (folder ? folder.split("/").pop() : "Pictures") : "Pictures here"}</h3>
              {q && folder.includes("/") && <span className="ig-path">{folder}</span>}
              <span className="ig-count">{list.length}</span>
              <span className="ig-line" aria-hidden />
            </header>
          )}
          <div className="ig-rows">
            {rows.map((row, r) => (
              <div key={r} className="ig-row" style={{ height: Math.round(row.h) }}>
                {row.items.map(({ file, index, w }) => (
                  <Tile key={file.path} file={file} width={w} grow={row.full}
                        src={api.prepThumbUrl(area, file.path, Math.round(w * dpr), file.modified)}
                        onClick={() => onOpen(list, index)} />
                ))}
              </div>
            ))}
          </div>
        </section>
      ))}
      {limit < total && <div ref={more} className="ig-more" aria-hidden />}
    </>
  );
  return (
    <div ref={box} className={"ig-scroll" + (at ? " nested" : "") + (dropOn === "bg" ? " dropping" : "")}
         {...dropProps(at, "bg")}>
      {at && (
        <nav className="ig-crumbs">
          <button className="ghost ig-crumb" onClick={() => go("")}>Pictures</button>
          {crumbs.map((c, i) => (
            <span key={i} className="ig-crumbpart">
              <span className="ig-sep" aria-hidden>›</span>
              {i < crumbs.length - 1
                ? <button className="ghost ig-crumb" onClick={() => go(crumbs.slice(0, i + 1).join("/"))}>{c}</button>
                : <span className="ig-here">{c}</span>}
            </span>
          ))}
          {accessOf.get(at) && (
            <AccessBadge access={accessOf.get(at)!} className="ig-crumbaccess"
                         onShare={onShare ? () => onShare(at) : undefined} />
          )}
        </nav>
      )}
      {/* Inside an album its own pictures come first and its folders after;
          at the top, where the albums are what you came for, the other way
          round. */}
      {picturesFirst ? <>{pictures}{albumsBlock}</> : <>{albumsBlock}{pictures}</>}
    </div>
  );
}

/** The last card of the albums: a new folder, here. Its name is typed on
 *  the card; the new folder is the maker's (image_access.claim), and it
 *  appears as soon as the listing is read again (the server says so). */
function NewAlbum({ area, folder }: { area: string; folder: string; size: number }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const create = async () => {
    const n = name.trim();
    if (!n) { setEditing(false); return; }
    setBusy(true);
    setError("");
    try {
      await api.prepMkdir(area, folder, n);
      setEditing(false);
      setName("");
    } catch (e) {
      setError(String(e).replace(/^Error:\s*/, ""));
    } finally {
      setBusy(false);
    }
  };
  if (!editing) {
    return (
      <button className="ig-album ig-newalbum" onClick={() => setEditing(true)} title="Make a new folder here">
        <span className="ig-cover"><span className="ig-newplus" aria-hidden>＋</span></span>
        <span className="ig-albumname">New folder</span>
        <span className="ig-albumsub">{folder ? `in ${folder.split("/").pop()}` : "an album of your own"}</span>
      </button>
    );
  }
  return (
    <div className="ig-album ig-newalbum editing">
      <span className="ig-cover"><span className="ig-newplus" aria-hidden>📁</span></span>
      <input className="ig-newname" autoFocus placeholder="Folder name" value={name} disabled={busy}
             onChange={(e) => setName(e.target.value)}
             onBlur={() => { if (!name.trim()) setEditing(false); }}
             onKeyDown={(e) => {
               if (e.key === "Enter") { e.preventDefault(); create(); }
               if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setEditing(false); setName(""); }
             }} />
      <span className={"ig-albumsub" + (error ? " error" : "")}>{error || (busy ? "Creating…" : "Enter to create · Esc to cancel")}</span>
    </div>
  );
}

function AlbumCover({ src }: { src: string }) {
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");
  return state === "error" ? <span className="ig-broken">🖼️</span> : (
    <img className={state} src={src} alt="" loading="lazy" decoding="async" draggable={false}
         onLoad={() => setState("ok")} onError={() => setState("error")} />
  );
}

function Tile({ file, src, width, grow, onClick }: {
  file: StagedFile; src: string; width: number; grow: boolean; onClick: () => void;
}) {
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");
  // Its place in the row is fixed before the thumbnail arrives: nothing
  // moves when it does.
  return (
    <button className={"ig-tile " + state} onClick={onClick} title={file.name}
            style={{ flex: grow ? `${width} 1 0` : `0 0 ${Math.round(width)}px` }}>
      {state !== "error" ? (
        <img src={src} alt={file.name} loading="lazy" decoding="async" draggable={false}
             onLoad={() => setState("ok")} onError={() => setState("error")} />
      ) : (
        <span className="ig-broken">{file.name.split(".").pop()?.toUpperCase()}</span>
      )}
      <span className="ig-caption">{file.name.replace(/\.[^.]+$/, "")}</span>
    </button>
  );
}

/** A picture full screen, over everything. ← → (or the side arrows, or a
 *  swipe) step through `list`; Esc, the ✕ or a click beside the picture
 *  closes it. The neighbours are loaded ahead, so stepping is instant. */
export function ImageViewer({ area, list, index, onIndex, onClose }: {
  area: string;
  list: StagedFile[];
  index: number;
  onIndex: (i: number) => void;
  onClose: () => void;
}) {
  const file = list[index];
  const [loaded, setLoaded] = useState(false);
  const [touch, setTouch] = useState<number | null>(null);
  const go = (d: number) => {
    const i = index + d;
    if (i >= 0 && i < list.length) onIndex(i);
  };

  useEffect(() => { setLoaded(false); }, [file?.path]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft") go(-1);
      else if (e.key === "ArrowRight") go(1);
      else return;
      e.preventDefault();
      e.stopPropagation();
    };
    // Capture: the page's own arrow keys (turning cover pages) wait.
    window.addEventListener("keydown", key, true);
    return () => window.removeEventListener("keydown", key, true);
  });
  // The neighbours, ahead of time.
  useEffect(() => {
    for (const d of [-1, 1]) {
      const n = list[index + d];
      if (n) new Image().src = api.prepRawUrl(area, n.path);
    }
  }, [area, list, index]);

  if (!file) return null;
  return (
    <div className="iv-overlay" onClick={onClose}
         onTouchStart={(e) => setTouch(e.touches[0].clientX)}
         onTouchEnd={(e) => {
           if (touch === null) return;
           const dx = e.changedTouches[0].clientX - touch;
           if (Math.abs(dx) > 50) go(dx < 0 ? 1 : -1);
           setTouch(null);
         }}>
      <div className="iv-top" onClick={(e) => e.stopPropagation()}>
        <span className="iv-name" title={file.path}>{file.name}</span>
        <span className="iv-meta">
          {file.folder || "Pictures"} · {fmtSize(file.size)} · {index + 1} / {list.length}
        </span>
        <a className="iv-btn" href={api.prepRawUrl(area, file.path)} target="_blank" rel="noreferrer"
           title="Open the original in a new tab">↗</a>
        <button className="iv-btn" onClick={onClose} title="Close (Esc)">✕</button>
      </div>
      {!loaded && <span className="mv-ring iv-spin" aria-hidden />}
      <img key={file.path} className={"iv-img" + (loaded ? " in" : "")} src={api.prepRawUrl(area, file.path)}
           alt={file.name} onLoad={() => setLoaded(true)} onClick={(e) => e.stopPropagation()} draggable={false} />
      {index > 0 && (
        <button className="iv-nav prev" title="Previous (←)" onClick={(e) => { e.stopPropagation(); go(-1); }}>‹</button>
      )}
      {index < list.length - 1 && (
        <button className="iv-nav next" title="Next (→)" onClick={(e) => { e.stopPropagation(); go(1); }}>›</button>
      )}
    </div>
  );
}

function fmtSize(n: number): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(n / 1e3))} KB`;
}
