import { useEffect, useMemo, useRef, useState } from "react";
import DOMPurify from "dompurify";
import { marked } from "marked";
// Deliberately a file rather than a string in here: it is meant to be
// written as prose and edited as prose. `?raw` hands it over as text and
// Vite rebuilds when it changes.
import { readCookie, writeCookie } from "../cookies";
import { api, PrepPlan, RemuxJob, StagedFile, TmdbCandidate } from "../api";

/** The right-hand panel for anything in a staging folder that isn't a film.
 *
 *  A staging folder is not just videos: it holds the subtitles you are about
 *  to embed, the release notes, the poster the uploader threw in, and the
 *  junk. Judging what to keep means being able to look at it, so whatever
 *  can be shown is shown and the rest at least describes itself. */
export function FileView({ area, file, play, onEnded }: {
  area: string;
  file: StagedFile;
  /** A song finished playing: the panel may start the next one. */
  onEnded?: () => void;
  /** Set when this file was double-clicked: start it playing. A new object
   *  per double-click, so a second one on the same file plays it again. */
  play?: { path: string } | null;
}) {
  const [text, setText] = useState<{ text: string; encoding: string } | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  useEffect(() => {
    if (play && play.path === file.path) audioRef.current?.play().catch(() => {});
  }, [play]);
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

      {/* A click only opens it; a double-click on the row plays it. */}
      {file.kind === "audio" && (
        <audio ref={audioRef} className="mv-fileaudio" src={api.prepRawUrl(area, file.path)} controls
               onEnded={onEnded} />
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
/** What the right-hand panel says while nothing is picked: how to use the
 *  tab that is open.
 *
 *  The texts are templates in ./help, one per kind of folder and language
 *  (`<name>.en.md`, `<name>.it.md`): "movies" for the film library,
 *  "workspace" for a folder with an inbox and an output, "output" for one
 *  with only an output. What makes each folder's text its own is its
 *  `description` in secrets.json's staging, filled in as
 *  `{{description}}`.
 *
 *  Templates take `{{name}}`, `{{description}}`, `{{inbox}}`, `{{output}}`,
 *  `{{user}}`, and
 *  blocks shown only when a flag is on (`{{#publish}}…{{/publish}}`) or off
 *  (`{{^publish}}…{{/publish}}`). The flags are what this user may do —
 *  `publish` (the publish permission) and `edit` (may change this folder) —
 *  so the text only describes what they can actually do. */
const HELP_FILES = import.meta.glob("./help/*.md", { query: "?raw", import: "default", eager: true }) as
  Record<string, string>;
type HelpLang = "en" | "it";
const HELP_LANG_COOKIE = "help_lang";

export interface HelpContext {
  template: string;
  vars: Record<string, string>;
  flags: Record<string, boolean>;
  /** The folder's description, per language. */
  description?: Record<string, string>;
}

function helpSource(template: string, lang: HelpLang): string {
  return HELP_FILES[`./help/${template}.${lang}.md`] ?? HELP_FILES[`./help/${template}.en.md`]
    ?? HELP_FILES[`./help/output.${lang}.md`] ?? "";
}

function renderTemplate(src: string, { vars, flags }: Pick<HelpContext, "vars" | "flags">): string {
  return src
    .replace(/\{\{([#^])(\w+)\}\}([\s\S]*?)\{\{\/\2\}\}/g,
      (_m, sign: string, key: string, body: string) => (!!flags[key] === (sign === "#") ? body : ""))
    .replace(/\{\{(\w+)\}\}/g, (_m, key: string) => vars[key] ?? "");
}

export function MoviesHome({ help }: { help: HelpContext }) {
  const [lang, setLangState] = useState<HelpLang>(
    () => (readCookie(HELP_LANG_COOKIE) === "it" ? "it" : "en"));
  const setLang = (l: HelpLang) => {
    setLangState(l);
    writeCookie(HELP_LANG_COOKIE, l);
  };
  const key = JSON.stringify(help);
  const html = useMemo(() => {
    const d = help.description ?? {};
    const description = d[lang] ?? d.en ?? Object.values(d)[0] ?? "";
    const md = renderTemplate(helpSource(help.template, lang),
                              { flags: help.flags, vars: { ...help.vars, description } });
    return DOMPurify.sanitize(marked.parse(md, { async: false, breaks: true }) as string);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, lang]);
  return (
    <div className="mv-home">
      <div className="mv-homelang">
        {(["en", "it"] as const).map((l) => (
          <button key={l} className={"ghost" + (lang === l ? " active" : "")} onClick={() => setLang(l)}>
            {l.toUpperCase()}
          </button>
        ))}
      </div>
      {/* eslint-disable-next-line react/no-danger */}
      <div className="markdown" dangerouslySetInnerHTML={{ __html: html }} />
    </div>
  );
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

  // With subtitles to generate the job runs in steps (each subtitle, then
  // the mux), and the bar says which one it is on.
  const step = running && (job!.steps ?? 0) > 1 && job!.step ? `${job!.step}/${job!.steps} · ` : "";
  const label = !running ? "" : step + (
    job!.phase === "generating"
      ? `${job!.step_label} subtitles${job!.detail ? `: ${job!.detail}` : ""}`
        + (job!.percent != null ? ` ${job!.percent}%` : "…")
      : job!.phase === "verifying" ? "checking…"
      : job!.phase === "tidying" ? "moving into place…"
      : `${(job!.steps ?? 0) > 1 ? "remuxing " : ""}${job!.percent ?? 0}%`);
  // Stopping is possible while generating subtitles or muxing: after that it
  // is moving files, and the server refuses to be interrupted there.
  const stoppable = running && ["generating", "muxing", ""].includes(job!.phase);

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

// 🎞 and 🖼 carry an invisible U+FE0F, for the reason given in App.tsx.
export const KIND_ICON: Record<string, string> = {
  video: "🎞️", image: "🖼️", audio: "🎵", subtitle: "💬", text: "📄", binary: "▪",
};

// ── the folder tree ──────────────────────────────────────────────────────
// A download is not tidy. The film may sit loose in the root, or three
// levels down beside a "Subs" folder, a sample and a screenshot gallery —
// so the listing arrives flat and the shape is rebuilt here from the paths,
// rather than the server deciding what the shape was allowed to be.

interface Node {
  file: StagedFile;
  children: Node[];
  /** While searching: something inside this folder matches, which is why
   *  it is shown — so it starts open, showing the matches. */
  hitInside?: boolean;
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
/** What a search leaves: the entries whose name matches, and the folders
 *  on the way to them. A folder that matches by its own name keeps all it
 *  holds — the search found the folder, so its contents are what you are
 *  looking for, not something to filter away. */
function filterTree(nodes: Node[], q: string): Node[] {
  if (!q) return nodes;
  const out: Node[] = [];
  for (const n of nodes) {
    const kids = filterTree(n.children, q);
    if (n.file.name.toLowerCase().includes(q)) {
      out.push({ ...n, hitInside: kids.length > 0 });
    } else if (kids.length) {
      out.push({ ...n, children: kids, hitInside: true });
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
/** The folder a row being dragged comes from — for drop targets outside
 *  the trees (the tab row), which cannot read the drag's data until the drop. */
export const draggedArea = (): string | null => currentDrag?.area ?? null;

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
  /** Create an empty folder called `name` inside `parent` ("" is the root). */
  mkdir: (parent: string, name: string) => void;
}

export function FileTree({
  area, files, query, activePath, activeMovieId, canEdit, onPick, marks, onPlay, actions,
  picked, onPicked, destinations, acceptsFrom, pickOnMove = true, loading = false,
}: {
  area: string;
  files: StagedFile[];
  /** The listing has not arrived yet: say so, rather than "Nothing here". */
  loading?: boolean;
  query: string;
  activePath: string | null;
  activeMovieId: string | null;
  canEdit: boolean;
  onPick: (f: StagedFile) => void;
  /** Files flagged with a note, by path — the music inbox's songs left for
   *  review, with why. A folder shows how many of its files are flagged. */
  marks?: Record<string, string>;
  /** A double-click on a file that plays (audio): open it and start it. */
  onPlay?: (f: StagedFile) => void;
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
  /** Whether stepping onto a file with the arrow keys opens it, as a click
   *  does (false: it is only highlighted, and Enter opens it — for pictures,
   *  which open full screen). */
  pickOnMove?: boolean;
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

  // While searching, folders open on their own — the ones something inside
  // matches — and a click opens or closes one on top of that. What was
  // clicked is forgotten with the search, and the tree goes back to how it
  // was left.
  const searchOpen = useMemo(() => {
    const out = new Set<string>();
    const walk = (list: Node[]) => {
      for (const n of list) {
        if (n.hitInside) { out.add(n.file.path); walk(n.children); }
      }
    };
    walk(shown);
    return out;
  }, [shown]);
  const [searchFlipped, setSearchFlipped] = useState<Set<string>>(new Set());
  useEffect(() => { setSearchFlipped(new Set()); }, [q]);
  const isOpenPath = (path: string) =>
    q ? searchOpen.has(path) !== searchFlipped.has(path) : expanded.has(path);

  // Rows in the order they are drawn, which is the order a shift-range runs
  // in: what you see between the two clicks, not what the tree holds.
  const visible = useMemo(() => {
    const out: StagedFile[] = [];
    const walk = (list: Node[]) => {
      for (const n of list) {
        out.push(n.file);
        if (n.file.kind === "folder" && isOpenPath(n.file.path)) walk(n.children);
      }
    };
    walk(shown);
    return out;
  }, [shown, expanded, q, searchOpen, searchFlipped]);
  // Where a shift-range starts: the last row clicked without shift.
  const anchor = useRef<string | null>(null);
  // The row the arrow keys are on: the last one clicked or stepped to.
  const [cursor, setCursor] = useState<string | null>(null);
  const treeRef = useRef<HTMLDivElement | null>(null);

  // `file` null: the menu of the tree's own background, which is about the
  // folder the tree shows rather than anything in it.
  const [menu, setMenu] = useState<{ x: number; y: number; file: StagedFile | null } | null>(null);
  // The only irreversible thing in this panel, so it takes two clicks: the
  // item arms itself first and says what it is about to take with it.
  const [armed, setArmed] = useState(false);
  // The menu's second page: the list of places "Move to" can send things.
  // Swapped in place rather than flown out to the side, because a flyout
  // from a menu opened near the right edge of the column has nowhere to go.
  const [choosing, setChoosing] = useState(false);
  const [editing, setEditing] = useState<{ path: string; value: string } | null>(null);
  // A folder being named before it exists: an input row inside `parent`.
  const [creating, setCreating] = useState<{ parent: string; value: string } | null>(null);
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

  /** Everything the tree is showing — all of it, or what a search left. */
  const allOn = shown.length > 0 && shown.every((n) => picked.has(n.file.path));
  // For the select-all row: how big everything shown is (a folder's size is
  // already what is under it), and how much of that is selected — each
  // picked thing once, not again for a picked folder's picked contents.
  const shownSize = shown.reduce((n, x) => n + (x.file.size || 0), 0);
  const pickedSize = useMemo(() => {
    if (!picked.size) return 0;
    let n = 0;
    for (const f of files) {
      if (!picked.has(f.path)) continue;
      const parts = f.path.split("/");
      let inside = false;
      for (let i = 1; i < parts.length && !inside; i++) inside = picked.has(parts.slice(0, i).join("/"));
      if (!inside) n += f.size || 0;
    }
    return n;
  }, [files, picked]);
  const toggleAll = () => {
    if (allOn) { onPicked(new Set()); return; }
    const next = new Set<string>();
    for (const n of shown) addFamily(next, n.file.path);
    onPicked(next);
  };

  // Escape lets go of the selection, the way it closes a menu.
  useEffect(() => {
    // With a menu open, Escape is the menu's: it closes that, nothing more.
    if (!picked.size || menu) return;
    const key = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (e.key === "Escape" && !t?.closest("input, textarea, select")) onPicked(new Set());
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [picked, onPicked, menu]);

  /** How many flagged files each folder holds, however deep. */
  const markCounts = useMemo(() => {
    const out = new Map<string, number>();
    for (const path of Object.keys(marks ?? {})) {
      const parts = path.split("/");
      for (let i = 1; i < parts.length; i++) {
        const folder = parts.slice(0, i).join("/");
        out.set(folder, (out.get(folder) ?? 0) + 1);
      }
    }
    return out;
  }, [marks]);

  const toggle = (path: string) =>
    (q ? setSearchFlipped : setExpanded)((prev) => {
      const next = new Set(prev);
      next.has(path) ? next.delete(path) : next.add(path);
      return next;
    });

  /** The arrow keys, like a file manager's: ↑ ↓ step through the rows as
   *  drawn, → opens a folder (or steps into it), ← closes it (or goes up to
   *  the folder a row is in), Enter opens what the cursor is on. */
  const onKey = (e: React.KeyboardEvent) => {
    if (editing || creating || menu || e.altKey || e.ctrlKey || e.metaKey) return;
    if ((e.target as HTMLElement).closest("input, textarea, select")) return;
    const at = cursor ?? activePath;
    const i = at ? visible.findIndex((v) => v.path === at) : -1;
    const cur = i >= 0 ? visible[i] : null;
    const moveTo = (f: StagedFile | undefined) => {
      if (!f) return;
      setCursor(f.path);
      anchor.current = f.path;
      if (f.kind !== "folder" && pickOnMove) onPick(f);
      requestAnimationFrame(() => {
        treeRef.current?.querySelector<HTMLElement>(`[data-path="${CSS.escape(f.path)}"]`)
          ?.scrollIntoView({ block: "nearest" });
      });
    };
    const isOpen = (f: StagedFile) => f.kind === "folder" && isOpenPath(f.path);
    switch (e.key) {
      case "ArrowDown": moveTo(visible[i + 1] ?? (i < 0 ? visible[0] : undefined)); break;
      case "ArrowUp": moveTo(i > 0 ? visible[i - 1] : visible[0]); break;
      case "Home": moveTo(visible[0]); break;
      case "End": moveTo(visible[visible.length - 1]); break;
      case "ArrowRight":
        if (!cur || cur.kind !== "folder") return;
        if (!isOpen(cur)) toggle(cur.path);
        else moveTo(visible[i + 1]?.folder === cur.path ? visible[i + 1] : undefined);
        break;
      case "ArrowLeft":
        if (!cur) return;
        if (isOpen(cur)) toggle(cur.path);
        else if (cur.folder) moveTo(visible.find((v) => v.path === cur.folder));
        break;
      case "Enter":
        if (!cur) return;
        cur.kind === "folder" ? toggle(cur.path) : onPick(cur);
        break;
      default:
        return;
    }
    e.preventDefault();
    e.stopPropagation();
  };

  const commitRename = () => {
    const edit = editing;
    setEditing(null);
    if (!edit) return;
    const name = edit.value.trim();
    const was = edit.path.split("/").pop() || "";
    if (name && name !== was) actions.rename(edit.path, name);
  };

  const commitCreate = () => {
    const c = creating;
    setCreating(null);
    const name = c?.value.trim();
    if (c && name) actions.mkdir(c.parent, name);
  };

  /** Start naming a new folder inside `parent`, opening it so the row shows. */
  const startCreate = (parent: string) => {
    if (parent) setExpanded((prev) => new Set(prev).add(parent));
    setCreating({ parent, value: "New folder" });
    setMenu(null);
  };

  const createRow = (parent: string, depth: number) =>
    creating?.parent === parent && (
      <div className="mv-node folder" style={{ paddingLeft: 6 + depth * 14 }}>
        {canEdit && <span className="mv-dot" style={{ visibility: "hidden" }} />}
        <span className="mv-twist" aria-hidden />
        <span className="mv-kind" aria-hidden>📁</span>
        <input
          className="mv-rename"
          autoFocus
          onFocus={(e) => e.currentTarget.select()}
          value={creating.value}
          onChange={(e) => setCreating({ parent, value: e.target.value })}
          onClick={(e) => e.stopPropagation()}
          onBlur={commitCreate}
          onKeyDown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); commitCreate(); }
            if (e.key === "Escape") { e.preventDefault(); setCreating(null); }
          }}
        />
      </div>
    );

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
    const open = folder && isOpenPath(f.path);
    const active = activePath === f.path || (!!f.movie_id && f.movie_id === activeMovieId);
    return (
      <div key={f.path} className="mv-branch">
        <div
          className={
            "mv-node" + (active ? " active" : "") + (folder ? " folder" : "") +
            (cursor === f.path && !active ? " cursor" : "") +
            (picked.has(f.path) ? " picked" : "") +
            (dropOn === f.path ? " dropping" : "")
          }
          style={{ paddingLeft: 6 + depth * 14 }}
          title={f.path}
          data-path={f.path}
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
            // While a selection is being made, every click goes on
            // selecting — anywhere on the row, not only on its dot — until
            // it is cleared (the bar's "clear", Escape, or unticking all).
            if (picked.size && canEdit) {
              tick(f.path);
              return;
            }
            anchor.current = f.path;
            setCursor(f.path);
            folder ? toggle(f.path) : onPick(f);
          }}
          onDoubleClick={() => {
            if (f.kind === "audio" && !editing && !picked.size) onPlay?.(f);
          }}
          onContextMenu={(e) => {
            e.preventDefault();
            // Not the background's menu too, which the tree would open next.
            e.stopPropagation();
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
          <span
            className="mv-twist"
            aria-hidden
            // The arrow always opens and closes — the one way to look inside
            // a folder while clicks on rows are ticking them.
            onClick={folder ? (e) => { e.stopPropagation(); toggle(f.path); } : undefined}
          >
            {folder ? (open ? "▾" : "▸") : ""}
          </span>
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
          {marks?.[f.path] && <span className="mv-mark" title={marks[f.path]}>?</span>}
          {folder && (markCounts.get(f.path) ?? 0) > 0 && (
            <span className="mv-mark" title="Songs in here left for you to check">
              {markCounts.get(f.path)} ?
            </span>
          )}
          <span className="mv-size">
            {folder ? `${f.children ?? 0} · ${fmtSize(f.size)}` : fmtSize(f.size)}
          </span>
        </div>
        {open && createRow(f.path, depth + 1)}
        {open && node.children.map((child) => row(child, depth + 1))}
      </div>
    );
  };

  return (
    <div
      ref={treeRef}
      // Focusable, so a click anywhere in it gives it the arrow keys.
      tabIndex={0}
      onKeyDown={onKey}
      className={"mv-tree" + (dropOn === "" ? " dropping" : "") + (picked.size ? " selecting" : "")}
      onDragOver={(e) => {
        if (!accept(e)) return;
        e.preventDefault();
        setDropOn("");
      }}
      onDragLeave={() => setDropOn((cur) => (cur === "" ? null : cur))}
      onDrop={(e) => drop(e, "")}
      onContextMenu={(e) => {
        e.preventDefault();
        setMenu({ x: e.clientX, y: e.clientY, file: null });
      }}
    >
      {shown.length > 0 && (
        <div className={"mv-node mv-selall" + (canEdit ? "" : " readonly")} onClick={canEdit ? toggleAll : undefined}
             title={canEdit ? (allOn ? "Unselect everything" : "Select everything shown here") : undefined}>
          {canEdit && <span className={"mv-dot" + (allOn ? " on" : "")} role="checkbox" aria-checked={allOn} />}
          <span className="mv-title">
            {!canEdit ? (q ? "Shown" : "Total")
              : allOn ? "Unselect all" : picked.size ? `Select all (${picked.size} selected)` : "Select all"}
          </span>
          <span className="mv-size" title={picked.size ? "selected of shown" : "everything shown here"}>
            {picked.size ? `${fmtSize(pickedSize)} of ${fmtSize(shownSize)}` : fmtSize(shownSize)}
          </span>
        </div>
      )}
      {createRow("", 0)}
      {shown.map((n) => row(n, 0))}
      {!shown.length && !creating && <p className="muted small">{loading ? "Reading the library…" : "Nothing here."}</p>}

      {menu && !menu.file && (
        <div className="mv-menu" style={{ left: menu.x, top: menu.y }}
             onClick={(e) => e.stopPropagation()}>
          <button
            disabled={!canEdit}
            title={canEdit ? "" : "Changing these folders needs the publish permission"}
            onClick={() => startCreate("")}
          >
            New folder
          </button>
        </div>
      )}

      {menu?.file && ((file: StagedFile) => {
        // Right-clicking a row that is part of a selection acts on the whole
        // selection — the file-manager rule — and says so, with a count,
        // so it is never a guess which of the two it meant.
        const roots = selectionRoots(picked);
        const many = picked.has(file.path) && roots.length > 1;
        const targets = many ? roots : [file.path];
        const what = many ? `${targets.length} items` : file.name;
        const locked = "Changing these folders needs the publish permission";
        return (
          <div className="mv-menu" style={{ left: menu.x, top: menu.y }}
               onClick={(e) => e.stopPropagation()}>
            <div className="mv-menuhead" title={many ? targets.join("\n") : file.path}>{what}</div>
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
                {!many && file.kind !== "folder" && (
                  <button onClick={() => { onPick(file); setMenu(null); }}>Open</button>
                )}
                {!many && file.kind === "folder" && (
                  <button
                    disabled={!canEdit}
                    title={canEdit ? "" : locked}
                    onClick={() => startCreate(file.path)}
                  >
                    New folder
                  </button>
                )}
                <button
                  disabled={!canEdit || many}
                  title={!canEdit ? locked : many ? "Rename one at a time" : ""}
                  onClick={() => { setEditing({ path: file.path, value: file.name }); setMenu(null); }}
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
                      : file.kind === "folder"
                        ? `Remove all (${file.children ?? 0} item${file.children === 1 ? "" : "s"})`
                        : "Remove file"}
                </button>
              </>
            )}
          </div>
        );
      })(menu.file)}
    </div>
  );
}

