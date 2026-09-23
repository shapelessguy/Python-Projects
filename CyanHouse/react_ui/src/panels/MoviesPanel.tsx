import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, MovieInfo, MovieItem, MovieTrack, MovieSource, PrepPlan, RemuxJob, StagedFile } from "../api";
import { FileView, FileTree, MoviesHome, PrepIdentity, PrepCommit, DRAG_TYPE, fmtSize, selectionRoots } from "./StagingView";
import { useVersionPoll, useVisibility } from "../api";
import { entriesFrom, walkEntries, useUploads } from "../uploads";

/** The stream is a transcode piped into a fragmented MP4: no byte ranges, no
 *  index, so the browser can't seek it and `video.duration` is meaningless.
 *  Seeking is therefore a *server* operation -- a new request at `t=`, which
 *  restarts ffmpeg there -- and everything this player displays is
 *  `offset + video.currentTime` measured against the duration ffprobe
 *  reported. That's also why the native controls are off: they'd offer a
 *  scrub bar that can't work. See api/services/movies.py. */

/** Per-track delay in milliseconds, keyed by MovieTrack.key, kept per film.
 *  Positive pushes the track later, negative earlier — the same sense a
 *  desktop player uses. Persisted only so that a page reload in the middle of
 *  hunting an offset doesn't throw the number away. */
type Delays = Record<string, number>;

const DELAY_KEY = "movies.delays";

function loadDelays(movieId: string): Delays {
  try {
    return JSON.parse(localStorage.getItem(`${DELAY_KEY}.${movieId}`) || "{}");
  } catch {
    return {};
  }
}

function saveDelays(movieId: string, delays: Delays) {
  try {
    const kept = Object.fromEntries(Object.entries(delays).filter(([, v]) => v));
    if (Object.keys(kept).length) {
      localStorage.setItem(`${DELAY_KEY}.${movieId}`, JSON.stringify(kept));
    } else {
      localStorage.removeItem(`${DELAY_KEY}.${movieId}`);
    }
  } catch {
    /* private mode / disabled storage */
  }
}

interface Playing {
  movie: MovieItem;
  /** Source timestamp the current ffmpeg was started at. */
  offset: number;
  audio: number;
  /** null = no subtitles (they're burned in, so this is a server-side choice). */
  sub: number | null;
  height: number;
  src: string;
}

const HEIGHT_LABEL: Record<number, string> = {
  // 0 is the stream-copy rung: the file's own video, no re-encoding, so also
  // its own resolution and bitrate. Only offered when the server says the
  // codec is one browsers actually decode.
  0: "Original",
  360: "360p",
  480: "480p",
  720: "720p",
  1080: "1080p",
};

/** Subtitles are burned into the picture, which means decoding and
 *  re-encoding it — the one thing the Original rung doesn't do. Picking one
 *  excludes the other, so whichever the user just chose wins and the panel
 *  says what it moved. */
const SUBS_NEED_TRANSCODE = "Subtitles are burned in, so Original switched to 360p.";
const ORIGINAL_NEEDS_NO_SUBS = "Original sends the file untouched, so subtitles went off.";

function fmt(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) seconds = 0;
  const s = Math.floor(seconds % 60);
  const m = Math.floor(seconds / 60) % 60;
  const h = Math.floor(seconds / 3600);
  const pad = (n: number) => String(n).padStart(2, "0");
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

/** What a pane with nothing ticked in it is handed — one shared empty set, so
 *  the other pane re-renders only when its own selection actually changes. */
const NO_PICK: Set<string> = new Set();

function gb(bytes: number): string {
  return `${(bytes / 1e9).toFixed(1)} GB`;
}

export function MoviesPanel() {
  // One id per mounted panel: the backend keys its live transcodes on it, so
  // a seek can kill the stream it seeked away from instead of leaving two
  // ffmpegs fighting over the GPU.
  const sid = useRef(Math.random().toString(36).slice(2) + Date.now().toString(36));
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);

  // Which tab is open: "" for the film library, or the name of a staging
  // area — which shows its inbox and its output together, or just the one
  // it has (the series library is an area with only an output).
  const [tab, setTab] = useState("");
  // The folder the right-hand panel's content comes from. With a staging
  // area open that is one of *two* folders, so it is set by whichever pane
  // was clicked in, not by the tab.
  const [source, setSource] = useState("");
  const [sources, setSources] = useState<MovieSource[]>([]);
  const [languages, setLanguages] = useState<{ code: string; name: string }[]>([]);
  // One listing per visible pane, keyed by source key.
  const [listings, setListings] = useState<Record<string, StagedFile[]>>({});
  const [paneErrors, setPaneErrors] = useState<Record<string, string>>({});
  const [plans, setPlans] = useState<Record<string, PrepPlan>>({});
  const [viewFile, setViewFile] = useState<StagedFile | null>(null);
  const [prepNote, setPrepNote] = useState("");
  // Rearranging happens in the left column and has to be answered there:
  // `prepNote` lives inside the player, which is replaced wholesale by the
  // file viewer — exactly what is on screen while you are renaming things.
  const [treeNote, setTreeNote] = useState<{ text: string; bad: boolean } | null>(null);
  // Ticked rows, by path, and the pane they were ticked in. One pane at a
  // time: a selection spanning an inbox and an output would make "delete
  // these" mean two different folders at once.
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [pickedArea, setPickedArea] = useState("");
  const [bulkTo, setBulkTo] = useState("");
  const [bulkBusy, setBulkBusy] = useState("");
  // Same two-click confirm the context menu uses; disarms whenever the
  // selection changes, so it can never carry over to a different set.
  const [armedDelete, setArmedDelete] = useState(false);
  // Which upload batch is expanded to show its files. One at a time: the
  // tray is a status line, not a second file browser.
  const [openBatch, setOpenBatch] = useState("");
  const [space, setSpace] = useState<
    { name: string; mount: string; path: string; total: number; free: number } | null>(null);
  const versions = useVersionPoll();
  const { permissions } = useVisibility();
  // Which tab a drag is currently hovering, so it can say so.
  const [dropTab, setDropTab] = useState("");
  // The server's remux queue — running whether or not this page is open.
  // Held here only to draw it; the server is the record.
  const [jobs, setJobs] = useState<RemuxJob[]>([]);
  const [queueOpen, setQueueOpen] = useState(false);
  const running = jobs.find((j) => j.state === "running") ?? null;
  const waiting = jobs.filter((j) => j.state === "queued");
  const busyQueue = !!running || waiting.length > 0;

  /** The tabs: one per library, one per staging area. An area is its inbox
   *  and its output together — either may be missing — and opening it shows
   *  both, the work waiting above the work done. */
  const groups = useMemo(() => {
    const out: { key: string; label: string; todo?: MovieSource; done?: MovieSource }[] = [];
    const at = new Map<string, number>();
    for (const x of sources) {
      // The libraries have no pair; they key on their own source key.
      const key = x.kind === "inbox" || x.kind === "output" ? x.group : x.key;
      let i = at.get(key);
      if (i === undefined) {
        i = out.length;
        at.set(key, i);
        out.push({ key, label: x.kind === "inbox" || x.kind === "output" ? x.group : x.label });
      }
      if (x.role === "todo") out[i].todo = x;
      else out[i].done = x;
    }
    return out;
  }, [sources]);

  /** The folders the open tab shows, top to bottom. Empty for the film
   *  library, which is a flat list of films rather than a tree. */
  const panes = useMemo(() => {
    if (tab === "") return [] as MovieSource[];
    const g = groups.find((x) => x.key === tab);
    return [g?.todo, g?.done].filter(Boolean) as MovieSource[];
  }, [groups, tab]);
  const paneKeys = panes.map((x) => x.key).join("|");
  const inbox = panes.find((x) => x.kind === "inbox");

  const [movies, setMovies] = useState<MovieItem[]>([]);
  const [listError, setListError] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<MovieItem | null>(null);
  const [info, setInfo] = useState<MovieInfo | null>(null);
  const [infoError, setInfoError] = useState("");
  const [playing, setPlaying] = useState<Playing | null>(null);
  const [position, setPosition] = useState(0);
  const [scrub, setScrub] = useState<number | null>(null);
  const [paused, setPaused] = useState(false);
  const [buffering, setBuffering] = useState(false);
  const [volume, setVolume] = useState(1);
  const [streamError, setStreamError] = useState("");
  // The stream ended before the film did: either ffmpeg died, or the server
  // reaped a transcode that had been paused long enough to look abandoned.
  // The element can't be resumed after that -- pressing play starts a new
  // one from the same position instead.
  const [dead, setDead] = useState(false);
  const [note, setNote] = useState("");
  // Whether `note` is a complaint or a confirmation — the same line carries
  // both, and a rejected upload should not read like a success.
  const [noteBad, setNoteBad] = useState(false);
  const [subBusy, setSubBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [delays, setDelays] = useState<Delays>({});
  // What is in the boxes while they're being typed in. Kept apart from
  // `delays` so a half-typed "-" or "12" never restarts the transcode --
  // nothing leaves here until blur or Enter.
  const [draft, setDraft] = useState<Record<string, string>>({});
  const fileRef = useRef<HTMLInputElement | null>(null);

  // Defaults for the *next* start, editable before anything is playing.
  const [audio, setAudio] = useState(0);
  const [sub, setSub] = useState<number | null>(null);
  const [height, setHeight] = useState(360);

  useEffect(() => {
    api.movies().then(setMovies).catch((e) => setListError(String(e)));
  }, []);

  // Which folders exist is configuration, and configuration changes: it is
  // re-read on the same counter the listings use, so correcting a path in
  // secrets.json moves the tabs rather than waiting for a page reload.
  useEffect(() => {
    api.prepAreas()
      .then((r) => { setSources(r.sources); setLanguages(r.languages); })
      .catch(() => {});
  }, [versions.prep]);

  /** Re-read every visible pane. Both at once because a move between them
   *  changes both, and a half-updated pair shows a file in two places. */
  const loadPanes = useCallback(async (keys: string[]) => {
    const results = await Promise.all(keys.map((k) =>
      api.prepFiles(k)
        .then((r) => ({ k, files: r.files, error: "" }))
        .catch((e) => ({ k, files: [] as StagedFile[], error: String(e).replace(/^Error:\s*/, "") }))));
    setListings(Object.fromEntries(results.map((r) => [r.k, r.files])));
    setPaneErrors(Object.fromEntries(results.filter((r) => r.error).map((r) => [r.k, r.error])));
    return Object.fromEntries(results.map((r) => [r.k, r.files])) as Record<string, StagedFile[]>;
  }, []);

  // The backend watches the staging folders and bumps `prep` when they
  // change, so this refetches on a real change rather than on a timer.
  useEffect(() => {
    if (!paneKeys) return;
    let alive = true;
    setListError("");
    loadPanes(paneKeys.split("|")).catch(() => {});
    // Only an inbox has films waiting to be prepared; an output's films are
    // already done, so there is no plan to fetch for them.
    if (!inbox) { setPlans({}); return () => { alive = false; }; }
    api.prepScan(inbox.key)
      .then((r) => {
        if (!alive) return;
        // A film being edited right now keeps the local copy: the server's
        // copy is at most one save behind it, and taking the server's would
        // undo the last keystroke.
        setPlans((mine) => {
          const next: Record<string, PrepPlan> = {};
          for (const p of r.films) {
            if (!p.movie_id) continue;
            next[p.movie_id] = unsaved.current.has(p.movie_id) && mine[p.movie_id]
              ? mine[p.movie_id] : p;
          }
          return next;
        });
      })
      .catch(() => {});
    return () => { alive = false; };
  }, [paneKeys, inbox?.key, versions.prep, loadPanes]);

  // Kept next to the search box because "can I still put a 40 GB remux
  // here?" is a question you ask in front of the folder. Refetched on the
  // same signal the listing uses, so a delete or a remux moves the number.
  // For a pair it is the inbox's disk — where the next download lands.
  useEffect(() => {
    let alive = true;
    api.prepSpace(panes[0]?.key ?? "")
      .then((r) => alive && setSpace(r))
      .catch(() => alive && setSpace(null));
    return () => { alive = false; };
  }, [paneKeys, versions.prep]);

  // Asked for whenever the folders change — queueing, starting and finishing
  // a remux all bump that counter, so a remux queued from another browser
  // shows up here too — and then followed once a second while anything is
  // running or waiting.
  // Plans with a save still to go out, by movie id — kept safe from being
  // overwritten by a refetch until the server has them.
  const unsaved = useRef(new Set<string>());
  const saveTimers = useRef(new Map<string, number>());
  const saveNow = (plan: PrepPlan): Promise<void> => {
    const id = plan.movie_id!;
    return api.prepSavePlan(plan.area!, plan)
      .then(() => undefined)
      .catch((e) => setPrepNote(`Could not save: ${String(e).replace(/^Error:\s*/, "")}`))
      .finally(() => {
        // Another edit may have been scheduled while this one was in the
        // air; the film stays protected until that one has gone too.
        if (!saveTimers.current.has(id)) unsaved.current.delete(id);
      });
  };
  const scheduleSave = (plan: PrepPlan) => {
    const id = plan.movie_id;
    if (!id || !plan.area) return;
    unsaved.current.add(id);
    window.clearTimeout(saveTimers.current.get(id));
    saveTimers.current.set(id, window.setTimeout(() => {
      saveTimers.current.delete(id);
      saveNow(plan);
    }, 300));
  };
  /** Send anything still waiting — before Remux all, which works from what
   *  the server has saved, not from what is on this screen. */
  const flushSaves = async () => {
    const pending = [...saveTimers.current.keys()];
    const sends = pending.map((id) => {
      window.clearTimeout(saveTimers.current.get(id));
      saveTimers.current.delete(id);
      const plan = plans[id];
      return plan ? saveNow(plan) : Promise.resolve();
    });
    await Promise.all(sends);
  };

  const loadJobs = useCallback(() => {
    api.prepJobs().then((r) => setJobs(r.jobs)).catch(() => {});
  }, []);
  useEffect(loadJobs, [versions.prep, loadJobs]);
  useEffect(() => {
    if (!busyQueue) return;
    const t = window.setInterval(loadJobs, 1000);
    return () => window.clearInterval(t);
  }, [busyQueue, loadJobs]);

  const stop = useCallback(() => {
    setPlaying(null);
    setBuffering(false);
    setStreamError("");
    setDead(false);
    api.movieStop(sid.current);
  }, []);

  // A transcode outlives the page unless someone says so: the generator on
  // the server only unwinds when the connection drops, and a backgrounded
  // tab can hold one open for a while.
  useEffect(() => {
    const id = sid.current;
    const bye = () => api.movieStop(id);
    window.addEventListener("pagehide", bye);
    return () => {
      window.removeEventListener("pagehide", bye);
      bye();
    };
  }, []);

  const switchTab = (next: string) => {
    // Re-clicking the tab you are already on would clear the lists without
    // refetching them: the effect that reloads keys off the panes changing,
    // so nothing would bring the files back.
    if (next === tab) return;
    stop();
    setTab(next);
    const g = groups.find((x) => x.key === next);
    setSource(g?.todo?.key ?? g?.done?.key ?? next);
    setSelected(null); setInfo(null); setViewFile(null);
    setListings({}); setPaneErrors({}); setPlans({});
    setPrepNote(""); setQuery(""); setTreeNote(null); setSpace(null);
    setPicked(new Set()); setPickedArea(""); setBulkTo("");
  };

  // Who may change what — the same rule as may_change / may_move in
  // api/routers/prep.py, which is what actually enforces it; this only keeps
  // the panel from offering what the server would refuse.
  //
  // A staging area with an inbox is a workspace: its two folders, the work
  // waiting and the work done, are open to anyone — rename, delete, upload,
  // reorganise, remux, and move between the two. Everything past that
  // needs the publish permission.
  const publisher = !!permissions.publish;
  /** The workspace a folder belongs to, or null for the shelf. */
  const workspaceOf = (key: string): string | null => {
    const x = sources.find((s) => s.key === key);
    if (!x) return null;
    if (x.kind === "inbox") return x.key;
    if (x.kind === "output" && sources.some((s) => s.kind === "inbox" && s.group === x.group)) return x.group;
    return null;
  };
  /** Both folders of a workspace. */
  const workspaceFolders = (ws: string) =>
    sources.filter((s) => s.group === ws && (s.kind === "inbox" || s.kind === "output")).map((s) => s.key);
  const canEditArea = (area: string) => publisher || workspaceOf(area) !== null;
  /** Which folders' entries may be dropped into `area`. */
  const acceptsFrom = (area: string): "*" | string[] => {
    if (publisher) return "*";
    const ws = workspaceOf(area);
    return ws ? workspaceFolders(ws) : [];
  };

  /** Re-read the panes after something moved, was renamed or was deleted,
   *  and follow whatever the right-hand panel was showing to its new path —
   *  the file is the same file, and having it vanish because it was renamed
   *  is exactly the wrong answer. `now` is null when it is simply gone. */
  const afterRearrange = async (
    was: string, now: string | null, fromArea: string, toArea: string,
  ) => {
    const moved = (path: string) => path === was || path.startsWith(was + "/");
    const follow = (path: string) => (now === null ? null : now + path.slice(was.length));

    // Its id encodes its path, so a film that moved is no longer addressable
    // under the id being streamed.
    const playingPath = (listings[fromArea] ?? []).find((f) => f.movie_id === selected?.id)?.path;
    if (playingPath && moved(playingPath)) { stop(); setSelected(null); setInfo(null); }

    const fresh = await loadPanes(panes.map((x) => x.key));
    if (viewFile && source === fromArea && moved(viewFile.path)) {
      const to = follow(viewFile.path);
      const next = to !== null ? (fresh[toArea] ?? []).find((f) => f.path === to) : undefined;
      // Followed into the other pane: the right panel now reads from there.
      if (next) setSource(toArea);
      setViewFile(next ?? null);
    }
  };

  // A finished upload puts a file in a folder being looked at, so the
  // listings have to catch up. The backend bumps its counter too, but that
  // is a poll away and this is instant.
  const refreshListing = useCallback(() => {
    if (paneKeys) loadPanes(paneKeys.split("|")).catch(() => {});
  }, [paneKeys, loadPanes]);
  const uploads = useUploads(refreshListing);

  useEffect(() => { setArmedDelete(false); }, [picked]);

  // When a remux finishes, the film it was for is gone from the inbox — its
  // sources are in the trash and the result is in the output. Anything still
  // showing it would be showing a file that is no longer there.
  /** Queue every ready film in an inbox, and say which were left out and
   *  why — a film not yet identified is the usual one. */
  const remuxAll = async (area: string) => {
    setTreeNote(null);
    try {
      await flushSaves();
      const r = await api.prepRemuxAll(area);
      loadJobs();
      const left = r.skipped.map((x) => `${x.folder} (${x.reason.replace(`${x.folder}: `, "")})`);
      say(`Queued ${r.queued.length} film${r.queued.length === 1 ? "" : "s"}` +
          (left.length ? `. Not queued: ${left.join("; ")}` : ""),
          r.queued.length === 0 && left.length > 0);
    } catch (e) { failed(e); }
  };

  const failedCount = jobs.filter((j) => j.state === "failed").length;
  const phaseText = (j: RemuxJob) =>
    j.phase === "verifying" ? `Checking ${j.target}`
      : j.phase === "tidying" ? `Moving ${j.target}`
      : `Remuxing ${j.target}`;

  // The menu closes on any click outside it, or Escape — like the tree's.
  useEffect(() => {
    if (!queueOpen) return;
    const close = () => setQueueOpen(false);
    const key = (e: KeyboardEvent) => e.key === "Escape" && setQueueOpen(false);
    window.addEventListener("click", close);
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener("click", close); window.removeEventListener("keydown", key); };
  }, [queueOpen]);

  const lastRunning = useRef<string | null>(null);
  useEffect(() => {
    const was = lastRunning.current;
    lastRunning.current = running?.id ?? null;
    if (!was || was === running?.id) return;
    const ended = jobs.find((j) => j.id === was);
    if (ended?.state === "done" && selected?.id === ended.movie_id) {
      stop(); setSelected(null); setInfo(null);
    }
    if (paneKeys) loadPanes(paneKeys.split("|")).catch(() => {});
  }, [running?.id, jobs]);

  const say = (text: string, bad = false) => setTreeNote({ text, bad });
  const failed = (e: unknown) => say(String(e).replace(/^Error:\s*/, ""), true);

  const labelOf = (key: string) => sources.find((x) => x.key === key)?.label ?? key;

  /** What a pane's tree can do, bound to that pane's folder. Moves take the
   *  area they come *from* separately, because the two panes of a pair are
   *  two folders and dragging between them is the whole point of showing
   *  them together. */
  const actionsFor = (area: string) => ({
    move: (paths: string[], to: string, fromArea: string) =>
      moveMany(fromArea, paths, area, to,
               fromArea === area ? (to || "the top level") : `${labelOf(area)}${to ? " / " + to : ""}`),
    rename: async (path: string, name: string) => {
      setTreeNote(null);
      try {
        const r = await api.prepRename(area, path, name);
        say(`Renamed to ${r.name}`);
        await afterRearrange(path, r.new_path, area, area);
      } catch (e) { failed(e); }
    },
    upload: (dt: DataTransfer, to: string) => {
      // Read *before* any await: the DataTransfer is emptied the moment the
      // drop handler returns, and an entry taken from it afterwards is null.
      const entries = entriesFrom(dt);
      setTreeNote(null);
      walkEntries(entries, dt).then((found) => {
        if (!found.length) { say("Nothing usable in that drop", true); return; }
        uploads.add(found, area, to);
        const bytes = found.reduce((n, p) => n + p.file.size, 0);
        say(`Uploading ${found.length} file${found.length === 1 ? "" : "s"} ` +
            `(${fmtSize(bytes)}) → ${labelOf(area)}${to ? " / " + to : ""}`);
      }).catch((e) => failed(e));
    },
    remove: (paths: string[]) => deletePaths(area, paths),
    moveTo: (paths: string[], toArea: string) =>
      moveMany(area, paths, toArea, "", labelOf(toArea)),
  });

  /** Where a right-click in `area` can send things: every other folder that
   *  exists, or — without the publish permission — the other half of the
   *  same workspace. */
  const destinationsFor = (area: string) => {
    const ws = workspaceOf(area);
    return sources
      .filter((x) => x.ready && x.key !== area)
      .filter((x) => publisher || (ws !== null && workspaceOf(x.key) === ws))
      .map((x) => ({ key: x.key, label: x.label }));
  };

  /** Dropping onto a tab moves the thing into that tab's folder — its inbox
   *  for a staging area, since that is where incoming work goes. */
  const dropOnTab = async (e: React.DragEvent, target: MovieSource) => {
    e.preventDefault();
    setDropTab("");
    const raw = e.dataTransfer.getData(DRAG_TYPE);
    if (!raw) return;
    let from: { area: string; paths: string[] };
    try {
      from = JSON.parse(raw);
    } catch { return; }
    if (from.area === target.key) return;
    await moveMany(from.area, from.paths ?? [], target.key, "", target.label);
  };

  /** Delete these. Sequential for the same reason moving is: each one can
   *  fail on its own terms, and you should be told which. */
  const deletePaths = async (area: string, paths: string[]) => {
    setArmedDelete(false);
    setTreeNote(null);
    setBulkBusy("Deleting…");
    let gone = 0;
    let files = 0;
    let bytes = 0;
    const problems: string[] = [];
    let last = "";
    for (const path of paths) {
      try {
        const r = await api.prepDelete(area, path);
        gone += 1; files += r.files; bytes += r.size; last = path;
      } catch (e) {
        problems.push(String(e).replace(/^Error:\s*/, ""));
      }
    }
    setBulkBusy("");
    setPicked(new Set());
    if (last) await afterRearrange(last, null, area, area);
    const head = paths.length === 1 && gone === 1
      ? `Deleted ${paths[0].split("/").pop()} — ${files} file${files === 1 ? "" : "s"}, ${fmtSize(bytes)} freed`
      : `Deleted ${gone} of ${paths.length} — ${files} file${files === 1 ? "" : "s"}, ${fmtSize(bytes)} freed`;
    say(problems.length ? `${head}. ${problems[0]}` : head, gone === 0);
  };

  /** One move per item, sequentially: they are renames on a filesystem, the
   *  failures are per-item (a name already taken at the destination), and a
   *  batch that stops at the first one would leave you guessing which of
   *  twenty files actually went. */
  const moveMany = async (
    fromArea: string, paths: string[], toArea: string, to: string, label: string,
  ) => {
    setTreeNote(null);
    setBulkBusy("Moving…");
    let moved = 0;
    let last: { was: string; now: string } | null = null;
    const problems: string[] = [];
    for (const path of paths) {
      try {
        const r = await api.prepMovePath(fromArea, path, toArea, to);
        moved += 1;
        last = { was: path, now: r.new_path };
      } catch (e) {
        problems.push(String(e).replace(/^Error:\s*/, ""));
      }
    }
    setBulkBusy("");
    setPicked(new Set());
    if (last) await afterRearrange(last.was, last.now, fromArea, toArea);
    else if (!problems.length) return;
    const head = `Moved ${moved} of ${paths.length} → ${label}`;
    if (problems.length) say(`${head}. ${problems[0]}`, moved === 0);
    else say(head);
  };

  /** Where a drop on a tab lands: the folder itself for a library, the inbox
   *  for a staging area (or its output, if it has no inbox). */
  const tabTarget = (g: { todo?: MovieSource; done?: MovieSource }) => g.todo ?? g.done;

  /** Open a file from one of the panes. `area` is which pane: an inbox and
   *  its output can hold the same relative path, so the path alone does not
   *  say which file this is. */
  const pickFile = (f: StagedFile, area: string) => {
    // A plain click drops the selection within its own tree; one in the
    // *other* pane has to drop it too, or ticks left in the inbox would
    // quietly survive into the next Delete.
    if (picked.size && pickedArea !== area) setPicked(new Set());
    if (f.kind === "video" && f.movie_id) {
      if (selected?.id === f.movie_id) return;   // already open (the id carries the area)
      setSource(area);
      setViewFile(null);
      pick({ id: f.movie_id, title: f.name, file: f.name, size: f.size });
    } else {
      if (viewFile?.path === f.path && source === area) return;   // already showing
      stop();
      setSource(area);
      setSelected(null); setInfo(null);
      setViewFile(f);
    }
  };

  const pick = (movie: MovieItem) => {
    // Re-clicking what is already open would tear down the transcode and
    // refetch for no gain — and lose your position doing it.
    if (selected?.id === movie.id) return;
    setSelected(movie);
    setInfo(null);
    setInfoError("");
    setDelays(loadDelays(movie.id));
    setDraft({});
    // A different film starts at the beginning; carrying the old position
    // over means the scrub bar claims a time that belongs to another file.
    setPosition(0);
    setScrub(null);
    setPaused(false);
    setDead(false);
    stop();
    api
      .movieInfo(movie.id)
      .then((meta) => {
        setInfo(meta);
        // Prefer the track the file itself marks default, like any player.
        const def = meta.audio.findIndex((a) => a.default);
        setAudio(def >= 0 ? def : 0);
        setSub(null);
        setNote("");
        // A staged film arrives with delays already in its plan; start from
        // those so the player and the mux agree from the first frame.
        const staged = plans[movie.id];
        if (staged) {
          const seeded: Delays = {};
          for (const t of staged.tracks) if (t.delay_ms) seeded[t.key] = t.delay_ms;
          setDelays(seeded);
        }
        // Always the smallest rung. Original is faster still, but it can't
        // carry burned-in subtitles, and this panel is for checking those
        // against the audio -- so defaulting to it just means every film
        // starts one click away from what you actually want. It stays
        // selectable for plain watching.
        setHeight(360);
      })
      .catch((e) => setInfoError(String(e)));
  };

  /** Start (or restart) ffmpeg. Every argument that changes the transcode --
   *  position, audio track, subtitle track, size -- goes through here,
   *  because on this pipeline they are all the same operation. */
  const play = useCallback(
    (opts: {
      t?: number; audio?: number; sub?: number | null; height?: number;
      // Passed explicitly when a delay edit triggers the restart, because
      // the state update setting it hasn't landed yet.
      delays?: Delays;
    } = {}) => {
      const movie = selected;
      const meta = info;
      if (!movie || !meta) return;
      const t = Math.max(0, Math.min(opts.t ?? position, Math.max(0, meta.duration - 2)));
      const a = opts.audio ?? audio;
      let s = opts.sub === undefined ? sub : opts.sub;
      let h = opts.height ?? height;

      // Burning subtitles in means re-encoding, which is exactly what the
      // Original rung doesn't do -- so the two can't both be on. Whichever
      // the user just changed wins, and the panel says what it moved.
      let moved = "";
      if (s !== null && h === 0) {
        if (opts.height === 0) {
          s = null;
          moved = ORIGINAL_NEEDS_NO_SUBS;
        } else {
          h = 360;
          moved = SUBS_NEED_TRANSCODE;
        }
      }
      setNote(moved);

      // The delays belong to whichever tracks are active, so they are read
      // here rather than passed in -- a restart for any reason picks up
      // whatever is currently set.
      const subKey = s === null ? null : meta.subtitles[s]?.key;
      const audKey = meta.audio[a]?.key;
      const sd = (subKey && (opts.delays ?? delays)[subKey]) || 0;
      const ad = (audKey && (opts.delays ?? delays)[audKey]) || 0;

      const params = new URLSearchParams({
        id: movie.id,
        sid: sid.current,
        t: t.toFixed(3),
        h: String(h),
        sd: String(sd),
        ad: String(ad),
        // Nothing is cached (the response is no-store) but a repeated URL
        // can still be coalesced by the browser into the request it's
        // already got open -- which is exactly the stream being replaced.
        _: String(Date.now()),
      });
      if (meta.audio.length) params.set("a", String(a));
      if (s !== null) params.set("s", String(s));

      setAudio(a);
      setSub(s);
      setHeight(h);
      setPosition(t);
      setScrub(null);
      setStreamError("");
      setBuffering(true);
      setPaused(false);
      setDead(false);
      setPlaying({ movie, offset: t, audio: a, sub: s, height: h, src: `/api/movies/stream?${params}` });
    },
    [selected, info, position, audio, sub, height, delays],
  );

  // Changing `src` doesn't restart playback on its own once the element has
  // loaded something else.
  useEffect(() => {
    const v = videoRef.current;
    if (!v || !playing) return;
    v.load();
    v.play().catch(() => setPaused(true));
  }, [playing?.src]);

  const seek = (t: number) => (playing ? play({ t }) : setPosition(t));

  const clickTimer = useRef<number | undefined>(undefined);

  const toggleFullscreen = () => {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else stageRef.current?.requestFullscreen?.().catch(() => {});
  };

  /** A single click plays or pauses, a double click goes fullscreen. The
   *  browser fires `click` before it knows a second one is coming, so the
   *  play/pause is held back briefly and cancelled if the pair arrives —
   *  otherwise every double click would also toggle playback. */
  const stageClick = () => {
    if (!playing) return;
    window.clearTimeout(clickTimer.current);
    clickTimer.current = window.setTimeout(() => togglePlay(), 220);
  };

  const stageDoubleClick = () => {
    window.clearTimeout(clickTimer.current);
    toggleFullscreen();
  };

  const togglePlay = () => {
    const v = videoRef.current;
    if (!playing || dead) {
      play({ t: position });
      return;
    }
    if (!v) return;
    if (v.paused) v.play().catch(() => {});
    else v.pause();
  };

  /** Upload subtitles, then select the first one added — you picked the
   *  file because you want to watch with it.
   *
   *  Dropping a whole folder of subtitles in is normal, and so is a .nfo or
   *  a screenshot coming along with them. The server takes what it can read
   *  and names the rest, so this reports both rather than treating one bad
   *  file as a failed upload. */
  const uploadSub = async (files: File[]) => {
    if (!selected || !files.length) return;
    setSubBusy(true);
    setNote(""); setNoteBad(false);
    try {
      const r = await api.uploadMovieSubtitle(selected.id, files);
      setInfo(r.info);
      if (r.accepted.length) {
        const added = r.info.subtitles[r.info.subtitles.length - 1];
        if (added) {
          if (playing) play({ sub: added.id });
          else setSub(added.id);
        }
      }
      const took = r.accepted.length
        ? `Added ${r.accepted.map((a) => a.name).join(", ")}.` : "";
      const left = r.rejected.map((x) => `${x.name}: ${x.reason}`).join(" · ");
      setNote([took, left && `Skipped — ${left}`].filter(Boolean).join(" "));
      setNoteBad(!r.accepted.length);
    } catch (e) {
      setNote(String(e).replace(/^Error:\s*/, ""));
      setNoteBad(true);
    } finally {
      setSubBusy(false);
    }
  };

  const deleteSub = async () => {
    const track = sub === null ? null : info?.subtitles[sub];
    if (!selected || !track || track.source !== "uploaded" || !track.upload_id) return;
    setSubBusy(true);
    try {
      const meta = await api.deleteMovieSubtitle(selected.id, track.upload_id);
      setInfo(meta);
      // Ids are positional and the list just shrank, so the old index points
      // somewhere else now. Go back to no subtitles.
      setSub(null);
      if (playing) play({ sub: null });
      setNote(`Removed ${track.label.replace(/^\d+\.\s*/, "")}.`);
    } catch (e) {
      setNote(String(e).replace(/^Error:\s*/, ""));
    } finally {
      setSubBusy(false);
    }
  };

  const plan = source && selected ? plans[selected.id] : undefined;

  /** Every change to a plan is also sent to the server, which is what makes
   *  it survive a reload, show up in other browsers, and be what a queued
   *  remux actually uses. Sent a moment after the last change rather than on
   *  every keystroke of a title. */
  const setPlan = (next: PrepPlan) => {
    if (!selected) return;
    setPlans((all) => ({ ...all, [selected.id]: next }));
    scheduleSave(next);
  };

  /** Assigning a language takes it from whoever else had it. One track per
   *  language is the rule, so rather than let two claim the same code and
   *  report a conflict afterwards, the claim moves: the previous holder goes
   *  blank, and blank means dropped. The invariant cannot be broken. */
  const setLanguage = (key: string, code: string) => {
    if (!plan) return;
    const target = plan.tracks.find((t) => t.key === key);
    if (!target) return;
    setPlan({
      ...plan,
      tracks: plan.tracks.map((t) => {
        if (t.key === key) return { ...t, language: code, keep: !!code };
        if (code && t.type === target.type && t.language === code) {
          return { ...t, language: "", keep: false };
        }
        return t;
      }),
    });
  };

  const planLang = (key: string) => plan?.tracks.find((t) => t.key === key)?.language ?? "";

  /** Called on blur or Enter, never per keystroke. Restarts the transcode
   *  only when this is a track that is actually playing right now — editing
   *  another track's delay just records the number. */
  const commitDelay = (key: string, isActive: boolean) => {
    const raw = draft[key];
    if (raw === undefined || !selected) return;
    const ms = Math.max(-600000, Math.min(600000, Math.round(Number(raw) || 0)));
    setDraft((d) => {
      const { [key]: _drop, ...rest } = d;
      return rest;
    });
    if ((delays[key] || 0) === ms) return;   // nothing actually changed
    const next = { ...delays, [key]: ms };
    setDelays(next);
    saveDelays(selected.id, next);
    // While preparing, the delay you are previewing is the delay that gets
    // muxed — one number, not one for watching and one for the mux.
    if (plan) {
      setPlan({ ...plan, tracks: plan.tracks.map((t) => (t.key === key ? { ...t, delay_ms: ms } : t)) });
    }
    if (isActive && playing) play({ delays: next });
  };

  /** Uploads grouped by the drop that started them. */
  const batches = useMemo(() => {
    const out: { batch: string; label: string; jobs: typeof uploads.jobs; size: number; sent: number }[] = [];
    const index = new Map<string, number>();
    for (const job of uploads.jobs) {
      let at = index.get(job.batch);
      if (at === undefined) {
        at = out.length;
        index.set(job.batch, at);
        out.push({ batch: job.batch, label: job.batchLabel, jobs: [], size: 0, sent: 0 });
      }
      out[at].jobs.push(job);
      out[at].size += job.size;
      out[at].sent += job.status === "done" ? job.size : job.sent;
    }
    return out;
  }, [uploads.jobs]);

  const uploadSummary = useMemo(() => {
    const moving = uploads.jobs.filter((j) => j.status === "uploading" || j.status === "queued");
    if (!moving.length) return `${uploads.jobs.length} finished`;
    const left = moving.reduce((n, j) => n + (j.size - j.sent), 0);
    return `Uploading ${moving.length} of ${uploads.jobs.length} — ${fmtSize(left)} to go`;
  }, [uploads.jobs]);

  const activeSub = sub === null ? null : info?.subtitles[sub] ?? null;
  const canDelete = activeSub?.source === "uploaded";

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? movies.filter((m) => m.title.toLowerCase().includes(q)) : movies;
  }, [movies, query]);

  const duration = info?.duration ?? 0;
  const shown = scrub ?? position;

  return (
    <div className="panel movies">
      <section className="mv-library">
        {groups.length > 1 && (
          // One tab per library, one per staging area. An area's tab opens
          // its inbox and its output together, one above the other.
          <div className="mv-sources">
            {groups.map((g) => {
              const target = tabTarget(g);
              const ready = !!(g.todo?.ready || g.done?.ready);
              // Only an area with something waiting in it is marked as one.
              // A folder that just holds finished work — the series library,
              // any output-only entry — looks like the film library, because
              // that is what it is.
              const kind = g.todo ? (g.done ? "pair" : "inbox") : "library";
              return (
                <button
                  key={g.key}
                  className={(tab === g.key ? "active " : "") + "mv-src-" + kind +
                             (dropTab === g.key ? " dropping" : "")}
                  title={[g.todo?.path, g.done?.path].filter(Boolean).join("\n")}
                  disabled={!ready}
                  onClick={() => switchTab(g.key)}
                  // Dragging something onto another tab moves it there — into
                  // the library, or into an area's inbox.
                  onDragOver={(e) => {
                    // Another tab is never a folder's own output — that sits
                    // in the same tab — so only a publisher can drop here.
                    if (!publisher || !target?.ready || g.key === tab) return;
                    if (!e.dataTransfer.types.includes(DRAG_TYPE)) return;
                    e.preventDefault();
                    e.dataTransfer.dropEffect = "move";
                    setDropTab(g.key);
                  }}
                  onDragLeave={() => setDropTab((cur) => (cur === g.key ? "" : cur))}
                  onDrop={(e) => target && dropOnTab(e, target).finally(() => setDropTab(""))}
                >
                  {g.label}
                </button>
              );
            })}
            {/* The remux queue, at the far end of the tab row: visible from
                every tab whatever is selected, because it is happening on
                the server regardless. The running one is shown outright; the
                button opens the whole queue. */}
            <div className="mv-queue">
              {running && (
                <button className="mv-jobpill" onClick={() => switchTab(running.area)}
                        title={`${running.target}\nfrom ${running.folder} — click to open its area`}>
                  <span className="mv-ring" aria-hidden />
                  <span className="mv-jobtext">{phaseText(running)}</span>
                  <span className="mv-jobmeter"><span style={{ width: `${running.percent ?? 0}%` }} /></span>
                  <span className="mv-jobpct">{running.percent ?? 0}%</span>
                </button>
              )}
              <button
                className={"mv-queuebtn" + (queueOpen ? " open" : "") + (failedCount ? " failed" : "")}
                title="Remux queue"
                onClick={(e) => { e.stopPropagation(); setQueueOpen((o) => !o); }}
              >
                <span aria-hidden>☰</span>
                {waiting.length > 0 && <span className="mv-queuecount">{waiting.length}</span>}
                {failedCount > 0 && <span className="mv-queuefail" title="failed">!</span>}
              </button>
              {queueOpen && (
                <div className="mv-queuemenu" onClick={(e) => e.stopPropagation()}>
                  <div className="mv-queuehead">
                    <span>Remux queue</span>
                    {jobs.some((j) => j.state !== "queued" && j.state !== "running") && (
                      <button className="ghost" onClick={() => api.prepClearJobs().then((r) => setJobs(r.jobs)).catch(() => {})}>
                        clear finished
                      </button>
                    )}
                  </div>
                  {jobs.length === 0 && <p className="muted small mv-queueempty">Nothing queued.</p>}
                  <ul>
                    {jobs.map((j) => (
                      <li key={j.id} className={"mv-qrow " + j.state} title={j.error || j.output || j.folder}>
                        <span className="mv-qstate" aria-hidden>
                          {j.state === "running" ? <span className="mv-ring" />
                            : j.state === "queued" ? `#${j.position}`
                            : j.state === "done" ? "✔" : j.state === "failed" ? "✘" : "■"}
                        </span>
                        <span className="mv-qtext">
                          <span className="mv-qtarget">{j.target}</span>
                          <span className="mv-qsub">
                            {j.state === "running" ? phaseText(j)
                              : j.state === "queued" ? `${labelOf(j.area)} · ${j.folder}`
                              : j.state === "done" ? `done${j.finished && j.started ? ` in ${Math.round(j.finished - j.started)}s` : ""}`
                              : j.state === "failed" ? j.error
                              : "stopped"}
                          </span>
                          {j.state === "running" && (
                            <span className="mv-jobmeter wide"><span style={{ width: `${j.percent ?? 0}%` }} /></span>
                          )}
                        </span>
                        <button
                          className="ghost mv-qx"
                          disabled={(j.state === "running" && j.phase !== "muxing" && j.phase !== "")
                                    || ((j.state === "running" || j.state === "queued") && !canEditArea(j.area))}
                          title={j.state === "running" ? "Stop — the source is left as it was"
                            : j.state === "queued" ? "Take it out of the queue" : "Clear"}
                          onClick={() => api.prepRemoveJob(j.id).then(loadJobs)
                            .catch((e) => setTreeNote({ text: String(e).replace(/^Error:\s*/, ""), bad: true }))}
                        >
                          {j.state === "running" ? "stop" : "✕"}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}
        <div className="mv-search">
          <input
            placeholder={tab
              ? `Search ${Object.values(listings).reduce((n, l) => n + l.length, 0) || ""} files…`
              : `Search ${movies.length || ""} movies…`}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button
            className="ghost"
            title="Rescan the library folder"
            onClick={() => api.movies(true).then(setMovies).catch((e) => setListError(String(e)))}
          >
            ⟳
          </button>
          {space && (
            <span
              className="mv-space"
              title={`${space.path}\nis on ${space.mount} (${space.name}) — `
                     + `${fmtSize(space.free)} free of ${fmtSize(space.total)}`}
            >
              <b>{space.name}</b> · {fmtSize(space.free)} free of {fmtSize(space.total)}
            </span>
          )}
        </div>
        {listError && <p className="error small">{listError}</p>}
        {treeNote && (
          <p className={(treeNote.bad ? "error" : "muted") + " small mv-note"}>{treeNote.text}</p>
        )}
        {tab ? (
          // A library is one tree; a staging area is two, the inbox on top
          // and its output underneath, splitting the height between them.
          // Dragging from one into the other is how a finished film leaves
          // the queue, so they are drop targets for each other.
          <div className="mv-panes">
            {panes.map((pane) => (
              <div className={"mv-pane " + pane.role} key={pane.key}>
                {panes.length > 1 && (
                  <div className="mv-panehead" title={pane.path}>
                    <span className="mv-panerole">{pane.role === "todo" ? "to process" : "done"}</span>
                    <span className="mv-panepath">{pane.path}</span>
                    {pane.kind === "inbox" && canEditArea(pane.key) && (
                      <button className="mv-remuxall" onClick={() => remuxAll(pane.key)}
                              title="Queue every film here that is identified and ready">
                        REMUX ALL
                      </button>
                    )}
                  </div>
                )}
                {paneErrors[pane.key] ? (
                  <p className="error small mv-paneerror">{paneErrors[pane.key]}</p>
                ) : (
                  <FileTree
                    key={pane.key}
                    area={pane.key}
                    files={listings[pane.key] ?? []}
                    query={query}
                    activePath={source === pane.key ? viewFile?.path ?? null : null}
                    activeMovieId={selected?.id ?? null}
                    canEdit={canEditArea(pane.key)}
                    onPick={(f) => pickFile(f, pane.key)}
                    actions={actionsFor(pane.key)}
                    picked={pickedArea === pane.key ? picked : NO_PICK}
                    onPicked={(next) => { setPickedArea(pane.key); setPicked(next); }}
                    destinations={destinationsFor(pane.key)}
                    acceptsFrom={acceptsFrom(pane.key)}
                  />
                )}
              </div>
            ))}
          </div>
        ) : (
        <ul className="mv-list">
          {filtered.map((m) => (
            <li key={m.id}>
              <button
                className={"mv-item" + (selected?.id === m.id ? " active" : "")}
                onClick={() => pick(m)}
              >
                <span className="mv-title">{m.title}</span>
                <span className="mv-size">{gb(m.size)}</span>
              </button>
            </li>
          ))}
          {!filtered.length && !listError && <li className="muted small">No matches.</li>}
        </ul>
        )}
        {/* What to do with a selection, under the tree it was made in.
            Absent until something is ticked, so it costs no height the rest
            of the time. */}
        {canEditArea(pickedArea) && picked.size > 0 && (
          <div className="mv-bulk">
            <span className="mv-bulkcount">
              {selectionRoots(picked).length} selected{panes.length > 1 ? ` in ${sources.find((x) => x.key === pickedArea)?.short ?? ""}` : ""}
            </span>
            <select value={bulkTo} onChange={(e) => setBulkTo(e.target.value)} disabled={!!bulkBusy}>
              <option value="">move to…</option>
              {/* Every other folder — including the other pane of this
                  pair, which is where a finished film usually goes, and for
                  someone without the publish permission the only one. */}
              {destinationsFor(pickedArea).map((x) => (
                <option key={x.key} value={x.key}>{x.label}</option>
              ))}
            </select>
            <button
              disabled={!bulkTo || !!bulkBusy}
              onClick={() => {
                const target = sources.find((x) => x.key === bulkTo);
                if (target) moveMany(pickedArea, selectionRoots(picked), target.key, "", target.label);
                setBulkTo("");
              }}
            >
              {bulkBusy || "MOVE"}
            </button>
            <button
              className={"mv-bulkdel" + (armedDelete ? " armed" : "")}
              disabled={!!bulkBusy}
              title="Deletes them — there is no undo"
              onClick={() => (armedDelete ? deletePaths(pickedArea, selectionRoots(picked)) : setArmedDelete(true))}
            >
              {armedDelete ? `Delete ${selectionRoots(picked).length}? click again` : "DELETE"}
            </button>
            <button className="ghost" onClick={() => setPicked(new Set())}>clear</button>
          </div>
        )}

        {/* What is going up, under the folder it is going into. Grouped by
            drop: a folder is one row with one stop button, however many
            files it turned out to hold. */}
        {uploads.jobs.length > 0 && (
          <div className="mv-uploads">
            <div className="mv-uploadhead">
              <span>{uploadSummary}</span>
              <button className="ghost" onClick={uploads.clear} title="Clear the finished rows">✕</button>
            </div>
            <ul>
              {batches.map((b) => {
                const pct = b.size ? Math.round((b.sent / b.size) * 100) : 0;
                const running = b.jobs.some((j) => j.status === "uploading" || j.status === "queued");
                const failed = b.jobs.filter((j) => j.status === "error").length;
                const open = openBatch === b.batch;
                return (
                  <li key={b.batch} className={"mv-batch" + (running ? " running" : "")}>
                    <div className="mv-job">
                      <button
                        className="ghost mv-twist"
                        title={open ? "Hide the files" : "Show the files"}
                        onClick={() => setOpenBatch(open ? "" : b.batch)}
                      >
                        {open ? "▾" : "▸"}
                      </button>
                      <span className="mv-jobname">
                        {b.label}
                        {b.jobs.length > 1 && <span className="muted"> · {b.jobs.length} files</span>}
                      </span>
                      <span className="mv-jobbar">
                        <span className="mv-jobfill" style={{ width: `${pct}%` }} />
                      </span>
                      <span className="mv-jobstate">
                        {running ? `${pct}%` : failed ? `${failed} failed` : fmtSize(b.size)}
                      </span>
                      {running && (
                        <button className="ghost" title="Stop this upload" onClick={() => uploads.cancelBatch(b.batch)}>✕</button>
                      )}
                    </div>
                    {open && (
                      <ul className="mv-batchfiles">
                        {b.jobs.map((j) => (
                          <li key={j.id} className={"mv-job " + j.status} title={j.error || j.relPath}>
                            <span className="mv-jobname">{j.relPath}</span>
                            <span className="mv-jobbar">
                              <span
                                className="mv-jobfill"
                                style={{ width: `${j.size ? Math.round((j.sent / j.size) * 100) : 0}%` }}
                              />
                            </span>
                            <span className="mv-jobstate">
                              {j.status === "done" ? fmtSize(j.size)
                                : j.status === "error" ? "failed"
                                : j.status === "cancelled" ? "stopped"
                                : j.status === "queued" ? "waiting"
                                : `${j.size ? Math.round((j.sent / j.size) * 100) : 0}%`}
                            </span>
                            {(j.status === "uploading" || j.status === "queued") && (
                              <button className="ghost" title="Cancel this file" onClick={() => uploads.cancel(j.id)}>✕</button>
                            )}
                            {j.status === "error" && (
                              <button className="ghost" title={j.error} onClick={() => uploads.retry(j.id)}>retry</button>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
            {uploads.jobs.some((j) => j.status === "error") && (
              <p className="error small">
                {uploads.jobs.find((j) => j.status === "error")?.error}
              </p>
            )}
          </div>
        )}
      </section>

      <aside
        className={"mv-player" + (dragging ? " dropping" : "")}
        // Only real files from outside the page. An entry being dragged
        // around the tree carries its own type and is none of this zone's
        // business.
        onDragOver={(e) => {
          if (!selected || !e.dataTransfer.types.includes("Files")) return;
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const files = Array.from(e.dataTransfer.files ?? []);
          if (files.length) uploadSub(files);
        }}
      >
        {viewFile ? (
          <FileView area={source} file={viewFile} />
        ) : !selected ? (
          // Nothing picked: the panel's resting state is a document, not an
          // empty player nobody can press.
          <MoviesHome />
        ) : (
        <>
        <div
          className="mv-stage"
          ref={stageRef}
          onClick={stageClick}
          onDoubleClick={stageDoubleClick}
        >
          {playing ? (
            <video
              ref={videoRef}
              className="mv-video"
              src={playing.src}
              playsInline
              autoPlay
              onTimeUpdate={(e) => setPosition(playing.offset + e.currentTarget.currentTime)}
              onPlay={() => setPaused(false)}
              onPause={() => setPaused(true)}
              onWaiting={() => setBuffering(true)}
              onPlaying={() => setBuffering(false)}
              onCanPlay={() => setBuffering(false)}
              onEnded={() => {
                setPaused(true);
                if (info && position < info.duration - 2) setDead(true);
              }}
              onError={() => {
                setDead(true);
                setBuffering(false);
                setStreamError(
                  "the stream stopped — press play to start it again from here",
                );
              }}
            />
          ) : (
            <div className="mv-placeholder muted">
              {selected ? (info ? "Ready" : infoError || "Reading the file…") : "Pick a movie"}
            </div>
          )}
          {playing && buffering && <div className="mv-spinner">transcoding…</div>}
        </div>

        <div className="mv-meta">
          <h2>{selected ? selected.title : "Movies"}</h2>
          {info ? (
            <p className="muted small">
              {info.video.codec.toUpperCase()} {info.video.width}×{info.video.height}
              {info.video.hdr ? " · HDR → SDR" : ""} · {fmt(info.duration)} · {gb(info.size)} ·{" "}
              {height === 0 && info.remux.ok
                ? " · original stream, not re-encoded"
                : ` · ${info.encoder === "h264_nvenc" ? "GPU" : "CPU"} transcode`}
            </p>
          ) : (
            <p className="muted small">
              {infoError ? <span className="error">{infoError}</span> : " "}
            </p>
          )}
        </div>

        <div className="mv-scrub">
          <input
            type="range"
            min={0}
            max={Math.max(1, duration)}
            step={1}
            value={shown}
            disabled={!info}
            onChange={(e) => setScrub(+e.target.value)}
            onPointerUp={(e) => seek(+(e.target as HTMLInputElement).value)}
            onKeyUp={(e) => seek(+(e.target as HTMLInputElement).value)}
          />
          <span className="mv-time">
            {fmt(shown)} / {fmt(duration)}
          </span>
        </div>

        <div className="mv-transport">
          <button onClick={() => seek(Math.max(0, position - 30))} disabled={!info} title="Back 30s">
            ◀◀
          </button>
          <button onClick={togglePlay} disabled={!info} title="Play / pause">
            {playing && !paused && !dead ? "❚❚" : "▶"}
          </button>
          <button
            onClick={() => seek(Math.min(duration, position + 30))}
            disabled={!info}
            title="Forward 30s"
          >
            ▶▶
          </button>
          <button onClick={stop} disabled={!playing} title="Stop the transcode">
            ■
          </button>
          <label className="mv-volume" title="Volume">
            🔊
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={volume}
              onChange={(e) => {
                const v = +e.target.value;
                setVolume(v);
                if (videoRef.current) videoRef.current.volume = v;
              }}
            />
          </label>
          <button
            className="ghost"
            onClick={toggleFullscreen}
            disabled={!playing}
            title="Fullscreen (or double-click the picture)"
          >
            ⛶
          </button>
        </div>

        {streamError && <p className="error small">{streamError}</p>}
        {note && <p className={(noteBad ? "error" : "muted") + " small mv-note"}>{note}</p>}

        <div className="mv-tracks">
          <div className="mv-quality">
            <span className="muted small">Quality</span>
            <div className="mv-qualityrow">
              {(info?.heights ?? [360, 720, 1080]).map((h) => (
                <label key={h} className={height === h ? "active" : ""}>
                  <input
                    type="radio"
                    name="mv-quality"
                    checked={height === h}
                    disabled={!info}
                    onChange={() => (playing ? play({ height: h }) : setHeight(h))}
                  />
                  {HEIGHT_LABEL[h] ?? `${h}p`}
                </label>
              ))}
            </div>
          </div>

          {/* What the film is, before what goes into it. */}
          {plan && (
            <PrepIdentity
              plan={plan}
              onPlan={setPlan}
            />
          )}

          {/* One table, full width. Two columns of lists left no room for a
              label, a language and a delay, which is how the previous layout
              ended up wrapping every row into three. */}
          <TrackTable
            audioTracks={info?.audio ?? []}
            subTracks={info?.subtitles ?? []}
            activeAudio={info?.audio.length ? audio : null}
            activeSub={sub}
            onAudio={(id) => (playing ? play({ audio: id }) : setAudio(id))}
            onSub={(id) => (playing ? play({ sub: id }) : setSub(id))}
            delays={delays}
            draft={draft}
            setDraft={setDraft}
            commit={commitDelay}
            disabled={!info}
            languages={plan ? languages : undefined}
            planLang={plan ? planLang : undefined}
            onLanguage={plan ? setLanguage : undefined}
            onUpload={() => fileRef.current?.click()}
            onDeleteSub={deleteSub}
            canDelete={canDelete}
            busy={subBusy}
          />
          <input
            ref={fileRef}
            type="file"
            // `multiple` is not a convenience here: a VobSub is a .idx and
            // a .sub that are one subtitle, and the server rejects either
            // half on its own.
            multiple
            accept=".srt,.ass,.ssa,.vtt,.sup,.idx,.sub"
            hidden
            onChange={(e) => {
              const files = Array.from(e.target.files ?? []);
              // Reset first, or picking the same file twice in a row fires
              // no change event the second time.
              e.target.value = "";
              uploadSub(files);
            }}
          />
        </div>
        {prepNote && <p className="muted small mv-note">{prepNote}</p>}
        {/* Last, and pushed to the foot of the column — it is the irreversible
            step, and it reads better with air above it. */}
        {plan && (
          <PrepCommit
            area={source}
            plan={plan}
            allowed={canEditArea(source)}
            job={jobs.find((j) => (j.state === "queued" || j.state === "running")
                                   && (j.fingerprint === plan.fingerprint || j.movie_id === plan.movie_id)) ?? null}
            onChanged={loadJobs}
          />
        )}

        </>
        )}
      </aside>
    </div>
  );
}

/** Every audio and subtitle track of a film, in one table.
 *
 *  The left column is what you are listening to / reading right now; the
 *  right columns are what the file will contain once it is muxed. They are
 *  the same rows on purpose — the delay you preview is the delay that gets
 *  written, so there is one number rather than two that can disagree.
 *
 *  Delay is edited as a draft string and only committed on blur or Enter:
 *  typing "-250" passes through "-", "-2", "-25" on the way, and restarting
 *  a transcode for each would be three dead transcodes and a flickering
 *  picture. */
function TrackTable({
  audioTracks, subTracks, activeAudio, activeSub, onAudio, onSub,
  delays, draft, setDraft, commit, disabled,
  languages, planLang, onLanguage,
  onUpload, onDeleteSub, canDelete, busy,
}: {
  audioTracks: MovieTrack[];
  subTracks: MovieTrack[];
  activeAudio: number | null;
  activeSub: number | null;
  onAudio: (id: number) => void;
  onSub: (id: number | null) => void;
  delays: Delays;
  draft: Record<string, string>;
  setDraft: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  commit: (key: string, isActive: boolean) => void;
  disabled?: boolean;
  /** Present only while preparing a film in a staging folder. */
  languages?: { code: string; name: string }[];
  planLang?: (key: string) => string;
  onLanguage?: (key: string, code: string) => void;
  onUpload: () => void;
  onDeleteSub: () => void;
  canDelete: boolean;
  busy: boolean;
}) {
  const prep = !!languages && !!onLanguage && !!planLang;

  const delayCell = (t: MovieTrack, active: boolean) => (
    <input
      className="mv-delay"
      type="number"
      step={50}
      value={draft[t.key] ?? String(delays[t.key] ?? 0)}
      disabled={disabled}
      title="Delay in milliseconds — positive is later, negative earlier"
      onChange={(e) => setDraft((d) => ({ ...d, [t.key]: e.target.value }))}
      onBlur={() => commit(t.key, active)}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
        if (e.key === "Escape") {
          setDraft((d) => {
            const { [t.key]: _drop, ...rest } = d;
            return rest;
          });
          e.currentTarget.blur();
        }
      }}
    />
  );

  const langCell = (t: MovieTrack) =>
    !prep ? null : (
      <select
        className="mv-preplang"
        data-empty={planLang!(t.key) ? "false" : "true"}
        value={planLang!(t.key)}
        disabled={disabled}
        title={planLang!(t.key) ? "" : "No language — this track will be dropped"}
        onChange={(e) => onLanguage!(t.key, e.target.value)}
      >
        <option value="">— drop —</option>
        {languages!.map((l) => (
          <option key={l.code} value={l.code}>{l.name} ({l.code})</option>
        ))}
      </select>
    );

  return (
    <table className="mv-tracktable">
      <thead>
        <tr>
          <th className="mv-thplay" />
          <th>Track</th>
          {prep && <th className="mv-thlang">Language</th>}
          <th className="mv-thdelay">Delay (ms)</th>
        </tr>
      </thead>

      <tbody>
        <tr className="mv-section"><td colSpan={prep ? 4 : 3}>Audio</td></tr>
        {audioTracks.map((t) => {
          const active = activeAudio === t.id;
          return (
            <tr key={t.key} className={active ? "active" : ""}>
              <td>
                <input type="radio" name="mv-audio" checked={active}
                       disabled={disabled} onChange={() => onAudio(t.id)} />
              </td>
              <td className="mv-tdname" title={t.label}>{t.label}</td>
              {prep && <td>{langCell(t)}</td>}
              <td>{delayCell(t, active)}</td>
            </tr>
          );
        })}
        {!audioTracks.length && (
          <tr><td colSpan={prep ? 4 : 3} className="muted small">no audio</td></tr>
        )}

        <tr className="mv-section">
          <td colSpan={prep ? 4 : 3}>
            Subtitles
            <span className="mv-subtools">
              <button className="ghost" title="Upload subtitles — .srt .ass .ssa .vtt .sup, or a VobSub .idx together with its .sub. You can also drop files anywhere on this panel."
                      disabled={disabled || busy} onClick={onUpload}>＋</button>
              <button className="ghost" title={canDelete ? "Delete this uploaded subtitle" : "Only uploaded subtitles can be deleted"}
                      disabled={!canDelete || busy} onClick={onDeleteSub}>🗑</button>
            </span>
          </td>
        </tr>
        <tr className={activeSub === null ? "active" : ""}>
          <td>
            <input type="radio" name="mv-sub" checked={activeSub === null}
                   disabled={disabled} onChange={() => onSub(null)} />
          </td>
          <td className="mv-tdname muted">off</td>
          {prep && <td />}
          <td />
        </tr>
        {subTracks.map((t) => {
          const active = activeSub === t.id;
          return (
            <tr key={t.key} className={active ? "active" : ""}>
              <td>
                <input type="radio" name="mv-sub" checked={active}
                       disabled={disabled} onChange={() => onSub(t.id)} />
              </td>
              <td className="mv-tdname" title={t.label}>{t.label}</td>
              {prep && <td>{langCell(t)}</td>}
              <td>{delayCell(t, active)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
