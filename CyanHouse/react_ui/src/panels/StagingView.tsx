import { useEffect, useMemo, useRef, useState } from "react";
import DOMPurify from "dompurify";
import { marked } from "marked";
// Deliberately a file rather than a string in here: it is meant to be
// written as prose and edited as prose. `?raw` hands it over as text and
// Vite rebuilds when it changes.
import homeText from "./movies-home.md?raw";
import { api, PrepPlan, RemuxJob, StagedFile, TmdbCandidate } from "../api";

/** The right-hand panel for anything in a staging folder that isn't a film.
 *
 *  A staging folder is not just videos: it holds the subtitles you are about
 *  to embed, the release notes, the poster the uploader threw in, and the
 *  junk. Judging what to keep means being able to look at it, so whatever
 *  can be shown is shown and the rest at least describes itself. */
export function FileView({ area, file }: { area: string; file: StagedFile }) {
  const [text, setText] = useState<{ text: string; encoding: string } | null>(null);
  const [info, setInfo] = useState<Record<string, any> | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setText(null); setInfo(null); setError("");
    if (file.readable) {
      api.prepText(area, file.path).then(setText).catch((e) => setError(String(e)));
    } else if (file.kind !== "image") {
      api.prepInfo(area, file.path).then(setInfo).catch((e) => setError(String(e)));
    }
  }, [area, file.path]);

  return (
    <div className="mv-fileview">
      <h2 title={file.path}>{file.name}</h2>
      <p className="muted small">
        {file.folder || "(root)"} · {fmtSize(file.size)} · {file.kind}
        {text ? ` · ${text.encoding}` : ""}
      </p>
      {error && <p className="error small">{error}</p>}

      {file.kind === "image" && (
        <img className="mv-fileimg" src={api.prepRawUrl(area, file.path)} alt={file.name} />
      )}

      {text && <pre className="mv-filetext">{text.text}</pre>}

      {info && (
        <div className="mv-fileinfo">
          {/* Nothing to render, so say everything that can be said about it.
              A stray .sub or sample still reports a duration and streams. */}
          <dl>
            <dt>type</dt><dd>{String(info.suffix || "—")} ({String(info.kind)})</dd>
            <dt>size</dt><dd>{fmtSize(Number(info.size))}</dd>
            <dt>modified</dt><dd>{new Date(Number(info.modified) * 1000).toLocaleString()}</dd>
            {info.duration ? (<><dt>duration</dt><dd>{fmtDuration(Number(info.duration))}</dd></>) : null}
          </dl>
          {Array.isArray(info.streams) && info.streams.length > 0 && (
            <table className="mv-streams">
              <tbody>
                {info.streams.map((s: any, i: number) => (
                  <tr key={i}>
                    <td>{s.type}</td><td>{s.codec}</td>
                    <td>{s.language || ""}</td><td>{s.size || ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      {!file.readable && file.kind !== "image" && !info && !error && (
        <p className="muted small">Reading…</p>
      )}
    </div>
  );
}

/** What the right-hand panel shows when nothing is selected.
 *
 *  A document rather than a placeholder line: this is the panel's resting
 *  state, which makes it the one place in here with room to say something
 *  worth reading. Empty for now — the text lives in movies-home.md. */
export function MoviesHome() {
  const html = useMemo(() => {
    const raw = marked.parse(homeText, { async: false, breaks: true }) as string;
    return DOMPurify.sanitize(raw);
  }, []);
  if (!homeText.trim()) return <div className="mv-home empty" />;
  // eslint-disable-next-line react/no-danger
  return <div className="mv-home markdown" dangerouslySetInnerHTML={{ __html: html }} />;
}

/** Naming the film: what it is, and whether that is settled.
 *
 *  Kept separate from the commit below because they belong at opposite ends
 *  of the column — you decide what the film *is* before choosing what goes
 *  into it, and you press the button last. */
export function PrepIdentity({
  plan, onPlan,
}: {
  plan: PrepPlan;
  onPlan: (p: PrepPlan) => void;
}) {
  const [busy, setBusy] = useState("");
  const [candidates, setCandidates] = useState<TmdbCandidate[] | null>(null);
  const [suggested, setSuggested] = useState<number | null>(null);
  const [error, setError] = useState("");

  const identified = plan.tmdb_id != null && !!plan.target;

  /** Always opens the chooser, even on a confident match. Renaming a film is
   *  the one decision here with no downstream check on it, so it is made by
   *  a person looking at the alternatives, not by a heuristic. */
  const lookup = async () => {
    setBusy("Looking up…"); setError(""); setCandidates(null);
    try {
      const r = await api.prepIdentify(plan.title, plan.year);
      setSuggested(r.confident && r.match ? r.match.id : null);
      setCandidates(r.candidates);
    } catch (e) { setError(String(e).replace(/^Error:\s*/, "")); }
    finally { setBusy(""); }
  };

  const pick = (c: TmdbCandidate) => {
    onPlan({ ...plan, title: c.title, year: c.year, tmdb_id: c.id, target: c.name });
    setCandidates(null);
  };

  return (
    <div className="mv-prep">
      <h3>Prepare</h3>
      <div className="mv-prepname">
        <input value={plan.title} placeholder="title"
               onChange={(e) => onPlan({ ...plan, title: e.target.value, tmdb_id: null, target: "" })} />
        <input className="mv-year" value={plan.year} placeholder="year"
               onChange={(e) => onPlan({ ...plan, year: e.target.value, tmdb_id: null, target: "" })} />
        <button onClick={lookup} disabled={!!busy}>{busy || "Look up"}</button>
      </div>
      <p className={"mv-prepstatus " + (identified ? "ok" : "bad")}>
        <span aria-hidden>{identified ? "✔" : "✘"}</span>
        {identified ? (
          <>
            → {plan.target}
            <button className="ghost mv-clearname" title="Clear this match and search again"
                    onClick={() => onPlan({ ...plan, tmdb_id: null, target: "" })}>✕</button>
          </>
        ) : (
          <>Not identified — look it up before remuxing</>
        )}
      </p>
      {error && <p className="error small">{error}</p>}

      {candidates && (
        <div className="modal-backdrop" onClick={() => setCandidates(null)}>
          <div className="modal mv-chooser" onClick={(e) => e.stopPropagation()}>
            <h4>Which film is this?</h4>
            <p className="muted small">
              Searched “{plan.title}”{plan.year ? ` (${plan.year})` : ""} — most relevant first
            </p>
            <ul>
              {candidates.length === 0 && <li className="muted small">Nothing found.</li>}
              {candidates.map((c) => (
                <li key={c.id}>
                  <button className={c.id === suggested ? "suggested" : ""} onClick={() => pick(c)}>
                    {c.poster
                      ? <img src={c.poster} alt="" loading="lazy" />
                      : <span className="mv-noposter" aria-hidden>🎞</span>}
                    <span className="mv-choosetext">
                      <strong>{c.name}</strong>
                      {c.original_title && c.original_title !== c.title && (
                        <em>{c.original_title}</em>
                      )}
                      <span className="muted small">{c.overview || "No description."}</span>
                    </span>
                    {c.id === suggested && <span className="mv-suggested">best match</span>}
                  </button>
                </li>
              ))}
            </ul>
            <button className="ghost" onClick={() => setCandidates(null)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  );
}

/** What is being discarded, and the button that does it. Sits at the very
 *  bottom of the column: it is the last thing you do, and it is irreversible
 *  enough to deserve its own space. */
export function PrepCommit({
  area, plan, allowed, job, onChanged,
}: {
  area: string;
  plan: PrepPlan;
  /** Remuxing writes the output and clears the sources away — a change to
   *  the folders, so it needs the same permission as every other change. */
  allowed: boolean;
  /** This film's place in the server's queue, if it has one. The component
   *  keeps no progress of its own; it draws the job, so re-opening the film —
   *  or opening it in another browser — shows the same thing. */
  job: RemuxJob | null;
  /** Something about the queue changed; the panel re-reads it. */
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const dropped = plan.tracks.filter(
    (t) => t.type !== "video" && !t.cover_art && !t.language);
  const identified = plan.tmdb_id != null && !!plan.target;
  const blocked = plan.conflicts.length > 0;
  const running = job?.state === "running";
  const queued = job?.state === "queued";

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true); setError("");
    try { await fn(); onChanged(); }
    catch (e) { setError(String(e).replace(/^Error:\s*/, "")); }
    finally { setBusy(false); }
  };

  const label = !running ? "" : job!.phase === "verifying" ? "checking…"
    : job!.phase === "tidying" ? "moving into place…" : `${job!.percent ?? 0}%`;
  // Stopping is only possible while muxing: after that it is moving files,
  // and the server refuses to be interrupted there.
  const stoppable = running && (job!.phase === "muxing" || job!.phase === "");

  return (
    <div className="mv-commit">
      {dropped.length > 0 && (
        <p className="muted small">
          {dropped.length} track(s) without a language will be dropped:{" "}
          {dropped.map((t) => t.label).join(", ")}
        </p>
      )}
      {blocked && <p className="error small">{plan.conflicts.join("; ")}</p>}
      {error && <p className="error small">{error}</p>}
      <div className="mv-remuxrow">
        {/* The bar lives beside the button rather than above it — there is
            width to spare and nothing is displaced when it appears. */}
        <div className="mv-muxbar" data-busy={running || queued ? "true" : "false"}>
          {running && (
            <>
              <div className="mv-muxfill" style={{ width: `${job!.percent ?? 0}%` }} />
              <span className="mv-muxlabel">{label}</span>
            </>
          )}
          {queued && (
            <span className="mv-muxlabel muted">
              queued — {job!.position === 1 ? "next" : `#${job!.position} in line`}
            </span>
          )}
        </div>
        {running ? (
          <button className="mv-remux stop" disabled={busy || !stoppable || !allowed}
                  title={stoppable ? "Stop this remux — the source is left as it was"
                                   : "Finishing up — too late to stop"}
                  onClick={() => act(() => api.prepRemoveJob(job!.id))}>
            STOP
          </button>
        ) : queued ? (
          <button className="mv-remux" disabled={busy || !allowed}
                  title="Take it out of the queue"
                  onClick={() => act(() => api.prepRemoveJob(job!.id))}>
            UNQUEUE
          </button>
        ) : (
          <button
            className="mv-remux"
            onClick={() => act(() => api.prepExecute(area, plan))}
            disabled={!allowed || busy || blocked || !identified}
            title={!allowed ? "Remuxing needs the publish permission" : ""}
          >
            REMUX
          </button>
        )}
      </div>
    </div>
  );
}

export function fmtSize(bytes: number): string {
  if (!bytes) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  if (bytes < 1024 ** 4) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  return `${(bytes / 1024 ** 4).toFixed(2)} TB`;
}

function fmtDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor(seconds / 60) % 60;
  const s = Math.floor(seconds % 60);
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
           : `${m}:${String(s).padStart(2, "0")}`;
}

export const KIND_ICON: Record<string, string> = {
  video: "🎞", image: "🖼", subtitle: "💬", text: "📄", binary: "▪",
};

// ── the folder tree ──────────────────────────────────────────────────────
// A download is not tidy. The film may sit loose in the root, or three
// levels down beside a "Subs" folder, a sample and a screenshot gallery —
// so the listing arrives flat and the shape is rebuilt here from the paths,
// rather than the server deciding what the shape was allowed to be.

interface Node {
  file: StagedFile;
  children: Node[];
}

function buildTree(files: StagedFile[]): Node[] {
  const nodes = new Map<string, Node>();
  for (const f of files) nodes.set(f.path, { file: f, children: [] });
  const roots: Node[] = [];
  for (const f of files) {
    const node = nodes.get(f.path)!;
    // A parent that isn't in the listing (a truncated one, say) would
    // otherwise lose the whole subtree; showing it at the top is wrong but
    // visible, which is the better failure.
    const parent = f.folder ? nodes.get(f.folder) : undefined;
    (parent ? parent.children : roots).push(node);
  }
  const sort = (list: Node[]) => {
    list.sort((a, b) =>
      (a.file.kind === "folder" ? 0 : 1) - (b.file.kind === "folder" ? 0 : 1) ||
      a.file.name.localeCompare(b.file.name, undefined, { numeric: true, sensitivity: "base" }));
    for (const n of list) sort(n.children);
  };
  sort(roots);
  return roots;
}

/** Keeps a folder whose name matches, or that holds something matching —
 *  searching a tree for a file three levels down has to show the way to it. */
function filterTree(nodes: Node[], q: string): Node[] {
  if (!q) return nodes;
  const out: Node[] = [];
  for (const n of nodes) {
    const kids = filterTree(n.children, q);
    if (kids.length || n.file.name.toLowerCase().includes(q)) {
      out.push({ ...n, children: kids });
    }
  }
  return out;
}

/** What a drag is carrying. A private type so the player's own drop zone —
 *  which takes real files off the desktop — never mistakes one for the
 *  other. */
export const DRAG_TYPE = "application/x-cyanhouse-entry";

/** What is being dragged right now, if it started in one of these trees.
 *  A drop target has to decide *during* dragover whether it will take the
 *  drop, and browsers do not let dragover read the payload — only its type.
 *  Whether a tree accepts depends on which folder the drag came from (an
 *  inbox's output takes that inbox's things and nothing else), so the
 *  origin is kept here, set on dragstart and cleared on dragend. */
let currentDrag: { area: string; paths: string[] } | null = null;

/** The items a selection actually acts on: the topmost ones. Ticking a
 *  folder ticks everything in it, and moving the folder already carries its
 *  contents — acting on the children as well would try to move each of
 *  them a second time, from a place they have just left. */
export function selectionRoots(picked: Set<string>): string[] {
  return [...picked].filter((path) => {
    const parts = path.split("/");
    for (let i = parts.length - 1; i > 0; i--) {
      if (picked.has(parts.slice(0, i).join("/"))) return false;
    }
    return true;
  });
}

export interface TreeAction {
  /** Move these into the folder `to` of *this* tree's area ("" = its root).
   *  A list because dragging one of several selected rows moves all of them;
   *  `fromArea` because they may come from the other pane of a pair. */
  move: (paths: string[], to: string, fromArea: string) => void;
  rename: (path: string, name: string) => void;
  /** Delete these, in this tree's area. A list for the same reason `move`
   *  takes one: right-clicking a ticked row acts on everything ticked. */
  remove: (paths: string[]) => void;
  /** Move these into the root of another folder — the context menu's
   *  "Move to", the same destinations the selection bar offers. */
  moveTo: (paths: string[], toArea: string) => void;
  /** Files dragged in from the desktop, dropped on the folder `to`. */
  upload: (dt: DataTransfer, to: string) => void;
}

export function FileTree({
  area, files, query, activePath, activeMovieId, canEdit, onPick, actions,
  picked, onPicked, destinations, acceptsFrom,
}: {
  area: string;
  files: StagedFile[];
  query: string;
  activePath: string | null;
  activeMovieId: string | null;
  canEdit: boolean;
  onPick: (f: StagedFile) => void;
  actions: TreeAction;
  /** Ticked rows, by path. Held by the panel because the actions that
   *  consume them live under the tree, not in it. */
  picked: Set<string>;
  onPicked: (next: Set<string>) => void;
  /** Other folders a right-click can send things to. */
  destinations: { key: string; label: string }[];
  /** Which folders' entries may be dropped into this tree: "*" for any, or
   *  a list. An output a non-publisher cannot otherwise touch still takes
   *  drops from its own inbox — that is the one move they are allowed. */
  acceptsFrom: "*" | string[];
}) {
  const roots = useMemo(() => buildTree(files), [files]);
  const q = query.trim().toLowerCase();
  const shown = useMemo(() => filterTree(roots, q), [roots, q]);

  // Top level open, deeper closed: enough to see what a folder holds without
  // a wall of episodes from every series at once.
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const seeded = useRef(false);
  useEffect(() => {
    if (seeded.current || !files.length) return;
    seeded.current = true;
    setExpanded(new Set(files.filter((f) => f.kind === "folder" && !f.folder).map((f) => f.path)));
  }, [files]);

  // Rows in the order they are drawn, which is the order a shift-range runs
  // in: what you see between the two clicks, not what the tree holds.
  const visible = useMemo(() => {
    const out: StagedFile[] = [];
    const walk = (list: Node[]) => {
      for (const n of list) {
        out.push(n.file);
        if (n.file.kind === "folder" && (!!q || expanded.has(n.file.path))) walk(n.children);
      }
    };
    walk(shown);
    return out;
  }, [shown, expanded, q]);
  // Where a shift-range starts: the last row clicked without shift.
  const anchor = useRef<string | null>(null);

  const [menu, setMenu] = useState<{ x: number; y: number; file: StagedFile } | null>(null);
  // The only irreversible thing in this panel, so it takes two clicks: the
  // item arms itself first and says what it is about to take with it.
  const [armed, setArmed] = useState(false);
  // The menu's second page: the list of places "Move to" can send things.
  // Swapped in place rather than flown out to the side, because a flyout
  // from a menu opened near the right edge of the column has nowhere to go.
  const [choosing, setChoosing] = useState(false);
  const [editing, setEditing] = useState<{ path: string; value: string } | null>(null);
  const [dropOn, setDropOn] = useState<string | null>(null);

  useEffect(() => {
    if (!menu) return;
    setArmed(false);
    setChoosing(false);
    const close = () => setMenu(null);
    const key = (e: KeyboardEvent) => e.key === "Escape" && setMenu(null);
    window.addEventListener("click", close);
    window.addEventListener("scroll", close, true);
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("keydown", key);
    };
  }, [menu]);

  // Direct children of every folder, from the whole listing rather than
  // the drawn rows: ticking a folder takes everything in it, including what
  // is collapsed out of sight or filtered away by a search.
  const kids = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const f of files) {
      const list = map.get(f.folder) ?? [];
      list.push(f.path);
      map.set(f.folder, list);
    }
    return map;
  }, [files]);

  const descendants = (path: string): string[] => {
    const out: string[] = [];
    const stack = [...(kids.get(path) ?? [])];
    while (stack.length) {
      const p = stack.pop()!;
      out.push(p);
      stack.push(...(kids.get(p) ?? []));
    }
    return out;
  };

  /** Folders above `path`, nearest first. */
  const ancestors = (path: string): string[] => {
    const parts = path.split("/");
    const out: string[] = [];
    for (let i = parts.length - 1; i > 0; i--) out.push(parts.slice(0, i).join("/"));
    return out;
  };

  /** Tick a row the way a file manager does: with everything inside it,
   *  and then its parent too if that completes the parent. */
  const addFamily = (next: Set<string>, path: string) => {
    next.add(path);
    for (const d of descendants(path)) next.add(d);
    for (const a of ancestors(path)) {
      if ((kids.get(a) ?? []).every((c) => next.has(c))) next.add(a);
      else break;
    }
  };

  /** Tick or untick one row — what Ctrl-click and the dot both do.
   *  Unticking takes its contents with it, and every folder above it: a
   *  folder is only selected while all of it is. */
  const tick = (path: string) => {
    const next = new Set(picked);
    if (next.has(path)) {
      next.delete(path);
      for (const d of descendants(path)) next.delete(d);
      for (const a of ancestors(path)) next.delete(a);
    } else {
      addFamily(next, path);
    }
    anchor.current = path;
    onPicked(next);
  };

  const toggle = (path: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(path) ? next.delete(path) : next.add(path);
      return next;
    });

  const commitRename = () => {
    const edit = editing;
    setEditing(null);
    if (!edit) return;
    const name = edit.value.trim();
    const was = edit.path.split("/").pop() || "";
    if (name && name !== was) actions.rename(edit.path, name);
  };

  /** Where a drop on this row should put things: into a folder, or beside a
   *  file — dropping onto a file plainly means "next to this one". */
  const dropFolder = (f: StagedFile) => (f.kind === "folder" ? f.path : f.folder);

  /** Two different drags land here: a row being moved from one of these
   *  trees, and files coming in from the desktop. An upload needs this
   *  folder to be one you can change; a move needs it to accept things from
   *  wherever the drag started. */
  const accept = (e: React.DragEvent) => {
    if (e.dataTransfer.types.includes(DRAG_TYPE)) {
      const from = currentDrag?.area;
      return from !== undefined && (acceptsFrom === "*" || acceptsFrom.includes(from));
    }
    return canEdit && e.dataTransfer.types.includes("Files");
  };

  const drop = (e: React.DragEvent, to: string) => {
    e.preventDefault();
    e.stopPropagation();
    setDropOn(null);
    // Judged before the record is cleared — accept() reads it to know where
    // the drag came from, and with it gone every in-page drop was refused.
    const ok = accept(e);
    currentDrag = null;
    if (!ok) return;
    const raw = e.dataTransfer.getData(DRAG_TYPE);
    if (!raw) {
      // From outside the page: upload it into whatever folder it landed on.
      if (e.dataTransfer.types.includes("Files")) actions.upload(e.dataTransfer, to);
      return;
    }
    try {
      const from = JSON.parse(raw) as { area: string; paths: string[] };
      // From the other pane of a pair it is a move between folders, and
      // every path is a real move. Within this tree, one dropped on itself or
      // back where it already is would get a 409 from the server — a
      // complaint about a gesture that meant nothing — so those are dropped.
      const moving = from.area !== area ? (from.paths ?? []) : (from.paths ?? []).filter((path) => {
        const parent = path.split("/").slice(0, -1).join("/");
        return path !== to && parent !== to;
      });
      if (moving.length) actions.move(moving, to, from.area);
    } catch { /* not ours */ }
  };

  const row = (node: Node, depth: number) => {
    const f = node.file;
    const folder = f.kind === "folder";
    const open = folder && (!!q || expanded.has(f.path));
    const active = activePath === f.path || (!!f.movie_id && f.movie_id === activeMovieId);
    return (
      <div key={f.path} className="mv-branch">
        <div
          className={
            "mv-node" + (active ? " active" : "") + (folder ? " folder" : "") +
            (picked.has(f.path) ? " picked" : "") +
            (dropOn === f.path ? " dropping" : "")
          }
          style={{ paddingLeft: 6 + depth * 14 }}
          title={f.path}
          draggable={canEdit && !editing}
          onDragStart={(e) => {
            // Dragging one of several ticked rows takes all of them;
            // dragging an unticked row takes just it, and leaves the
            // selection alone.
            const paths = picked.has(f.path) && picked.size > 1 ? selectionRoots(picked) : [f.path];
            currentDrag = { area, paths };
            e.dataTransfer.setData(DRAG_TYPE, JSON.stringify({ area, paths }));
            e.dataTransfer.effectAllowed = "move";
          }}
          onDragEnd={() => { currentDrag = null; }}
          onDragOver={(e) => {
            if (!accept(e)) return;
            e.preventDefault();
            e.stopPropagation();
            e.dataTransfer.dropEffect = "move";
            setDropOn(f.path);
          }}
          onDragLeave={() => setDropOn((cur) => (cur === f.path ? null : cur))}
          onDrop={(e) => drop(e, dropFolder(f))}
          onClick={(e) => {
            // Ctrl/Cmd adds one, Shift takes everything between — the
            // gesture every file manager uses, so it needs no explaining.
            if ((e.metaKey || e.ctrlKey) && canEdit) {
              tick(f.path);
              return;
            }
            if (e.shiftKey && anchor.current && canEdit) {
              const from = visible.findIndex((v) => v.path === anchor.current);
              const to = visible.findIndex((v) => v.path === f.path);
              if (from >= 0 && to >= 0) {
                const [lo, hi] = from < to ? [from, to] : [to, from];
                const next = new Set(picked);
                for (const v of visible.slice(lo, hi + 1)) addFamily(next, v.path);
                onPicked(next);
                return;
              }
            }
            // A plain click is the old behaviour, and it drops the
            // selection: otherwise a tick left over from five minutes ago
            // quietly joins the next Delete.
            anchor.current = f.path;
            if (picked.size) onPicked(new Set());
            folder ? toggle(f.path) : onPick(f);
          }}
          onContextMenu={(e) => {
            e.preventDefault();
            setMenu({ x: e.clientX, y: e.clientY, file: f });
          }}
        >
          {/* Selecting without a keyboard: the same as Ctrl-click, for a
              mouse-only hand or a touch screen. Only offered to someone who
              can act on a selection — for anyone else it would tick things
              that nothing can then be done with. */}
          {canEdit && (
            <span
              className={"mv-dot" + (picked.has(f.path) ? " on" : "")}
              role="checkbox"
              aria-checked={picked.has(f.path)}
              title={picked.has(f.path) ? "Unselect" : "Select"}
              onClick={(e) => { e.stopPropagation(); tick(f.path); }}
            />
          )}
          <span className="mv-twist" aria-hidden>{folder ? (open ? "▾" : "▸") : ""}</span>
          <span className="mv-kind" aria-hidden>{folder ? (open ? "📂" : "📁") : KIND_ICON[f.kind] ?? "▪"}</span>
          {editing?.path === f.path ? (
            <input
              className="mv-rename"
              autoFocus
              value={editing.value}
              onChange={(e) => setEditing({ path: f.path, value: e.target.value })}
              onClick={(e) => e.stopPropagation()}
              onBlur={commitRename}
              onKeyDown={(e) => {
                if (e.key === "Enter") { e.preventDefault(); commitRename(); }
                if (e.key === "Escape") { e.preventDefault(); setEditing(null); }
              }}
            />
          ) : (
            <span className="mv-title">{f.name}</span>
          )}
          <span className="mv-size">
            {folder ? `${f.children ?? 0} · ${fmtSize(f.size)}` : fmtSize(f.size)}
          </span>
        </div>
        {open && node.children.map((child) => row(child, depth + 1))}
      </div>
    );
  };

  return (
    <div
      className={"mv-tree" + (dropOn === "" ? " dropping" : "")}
      onDragOver={(e) => {
        if (!accept(e)) return;
        e.preventDefault();
        setDropOn("");
      }}
      onDragLeave={() => setDropOn((cur) => (cur === "" ? null : cur))}
      onDrop={(e) => drop(e, "")}
    >
      {shown.map((n) => row(n, 0))}
      {!shown.length && <p className="muted small">Nothing here.</p>}

      {menu && (() => {
        // Right-clicking a row that is part of a selection acts on the whole
        // selection — the file-manager rule — and says so, with a count,
        // so it is never a guess which of the two it meant.
        const roots = selectionRoots(picked);
        const many = picked.has(menu.file.path) && roots.length > 1;
        const targets = many ? roots : [menu.file.path];
        const what = many ? `${targets.length} items` : menu.file.name;
        const locked = "Changing these folders needs the publish permission";
        return (
          <div className="mv-menu" style={{ left: menu.x, top: menu.y }}
               onClick={(e) => e.stopPropagation()}>
            <div className="mv-menuhead" title={many ? targets.join("\n") : menu.file.path}>{what}</div>
            {choosing ? (
              <>
                <button className="mv-menuback" onClick={() => setChoosing(false)}>‹ Move {what} to…</button>
                {destinations.length === 0 && <div className="mv-menunote">No other folders configured</div>}
                {destinations.map((d) => (
                  <button key={d.key} onClick={() => { actions.moveTo(targets, d.key); setMenu(null); }}>
                    {d.label}
                  </button>
                ))}
              </>
            ) : (
              <>
                {!many && menu.file.kind !== "folder" && (
                  <button onClick={() => { onPick(menu.file); setMenu(null); }}>Open</button>
                )}
                <button
                  disabled={!canEdit || many}
                  title={!canEdit ? locked : many ? "Rename one at a time" : ""}
                  onClick={() => { setEditing({ path: menu.file.path, value: menu.file.name }); setMenu(null); }}
                >
                  Rename
                </button>
                <button
                  disabled={!canEdit}
                  title={canEdit ? "" : locked}
                  onClick={() => setChoosing(true)}
                >
                  Move to…
                </button>
                <button onClick={() => { navigator.clipboard?.writeText(targets.join("\n")); setMenu(null); }}>
                  Copy path{many ? "s" : ""}
                </button>
                <button
                  className={"mv-remove" + (armed ? " armed" : "")}
                  disabled={!canEdit}
                  title={canEdit ? "Deletes it — there is no undo" : locked}
                  onClick={() => {
                    if (!armed) { setArmed(true); return; }
                    actions.remove(targets);
                    setMenu(null);
                  }}
                >
                  {armed
                    ? "Click again to confirm"
                    : many
                      ? `Remove ${targets.length} items`
                      : menu.file.kind === "folder"
                        ? `Remove all (${menu.file.children ?? 0} item${menu.file.children === 1 ? "" : "s"})`
                        : "Remove file"}
                </button>
              </>
            )}
          </div>
        );
      })()}
    </div>
  );
}

