import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, MovieInfo, MovieItem, MovieTrack, MovieSource, PrepPlan, StagedFile } from "../api";
import { FileView, PrepIdentity, PrepCommit, KIND_ICON, byFolder, fmtSize } from "./StagingView";
import { useVersionPoll, useVisibility } from "../api";

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

  // "" is the library; anything else is a staging area from secrets.json.
  const [source, setSource] = useState("");
  const [sources, setSources] = useState<MovieSource[]>([]);
  const [languages, setLanguages] = useState<{ code: string; name: string }[]>([]);
  const [staged, setStaged] = useState<StagedFile[]>([]);
  const [plans, setPlans] = useState<Record<string, PrepPlan>>({});
  const [viewFile, setViewFile] = useState<StagedFile | null>(null);
  const [prepNote, setPrepNote] = useState("");
  const sourceKind = sources.find((x) => x.key === source)?.kind ?? "library";
  const versions = useVersionPoll();
  const { permissions } = useVisibility();
  const [moveTo, setMoveTo] = useState("");
  const [publishing, setPublishing] = useState("");
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
    api.prepAreas()
      .then((r) => { setSources(r.sources); setLanguages(r.languages); })
      .catch(() => {});
  }, []);

  // The backend watches the staging folders and bumps `prep` when they
  // change, so this refetches on a real change rather than on a timer.
  useEffect(() => {
    if (!source) return;
    let alive = true;
    setListError("");
    api.prepFiles(source)
      .then((r) => alive && setStaged(r.files))
      .catch((e) => alive && setListError(String(e)));
    if (sourceKind !== "inbox") { setPlans({}); return () => { alive = false; }; }
    api.prepScan(source)
      .then((r) => {
        if (!alive) return;
        const next: Record<string, PrepPlan> = {};
        for (const p of r.films) if (p.movie_id) next[p.movie_id] = p;
        setPlans(next);
      })
      .catch(() => {});
    return () => { alive = false; };
  }, [source, sourceKind, versions.prep]);

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

  const switchSource = (next: string) => {
    // Re-clicking the tab you are already on would clear the list without
    // refetching it: the effect that reloads keys off `source` changing, so
    // nothing would bring the files back.
    if (next === source) return;
    stop();
    setSource(next);
    setSelected(null); setInfo(null); setViewFile(null);
    setStaged([]); setPlans({}); setPrepNote(""); setQuery("");
  };

  const pickFile = (f: StagedFile) => {
    if (f.kind === "video" && f.movie_id) {
      if (selected?.id === f.movie_id) return;   // already open
      setViewFile(null);
      pick({ id: f.movie_id, title: f.name, file: f.name, size: f.size });
    } else {
      if (viewFile?.path === f.path) return;     // already showing
      stop();
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
   *  file because you want to watch with it. */
  const uploadSub = async (files: File[]) => {
    if (!selected || !files.length) return;
    setSubBusy(true);
    setNote("");
    try {
      const meta = await api.uploadMovieSubtitle(selected.id, files);
      setInfo(meta);
      const added = meta.subtitles[meta.subtitles.length - 1];
      if (added) {
        if (playing) play({ sub: added.id });
        else setSub(added.id);
      }
      setNote(`Added ${files.map((f) => f.name).join(" + ")}.`);
    } catch (e) {
      setNote(String(e).replace(/^Error:\s*/, ""));
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

  const setPlan = (next: PrepPlan) =>
    selected && setPlans((all) => ({ ...all, [selected.id]: next }));

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

  const activeSub = sub === null ? null : info?.subtitles[sub] ?? null;
  const canDelete = activeSub?.source === "uploaded";

  const stagedFiltered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? staged.filter((f) => (f.folder + "/" + f.name).toLowerCase().includes(q)) : staged;
  }, [staged, query]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? movies.filter((m) => m.title.toLowerCase().includes(q)) : movies;
  }, [movies, query]);

  const duration = info?.duration ?? 0;
  const shown = scrub ?? position;

  return (
    <div className="panel movies">
      <section className="mv-library">
        {sources.length > 1 && (
          <div className="mv-sources">
            {sources.map((x) => (
              <button
                key={x.key}
                className={
                  (source === x.key ? "active " : "") + "mv-src-" + x.kind
                }
                title={x.ready ? x.path : `not found: ${x.path}`}
                disabled={!x.ready}
                onClick={() => switchSource(x.key)}
              >
                {x.label}
              </button>
            ))}
          </div>
        )}
        <div className="mv-search">
          <input
            placeholder={source ? `Search ${staged.length || ""} files…` : `Search ${movies.length || ""} movies…`}
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
        </div>
        {listError && <p className="error small">{listError}</p>}
        {source ? (
          // A staging folder shows *everything* — the subtitles about to be
          // embedded, the release notes, the junk — because deciding what to
          // keep means being able to look at it.
          <ul className="mv-list mv-files">
            {byFolder(stagedFiltered).map(([folder, files]) => (
              <li key={folder}>
                <div className="mv-folder" title={folder}>{folder}</div>
                <ul>
                  {files.map((f) => (
                    <li key={f.path}>
                      <button
                        className={
                          "mv-item mv-file" +
                          ((viewFile?.path === f.path || (f.movie_id && selected?.id === f.movie_id))
                            ? " active" : "")
                        }
                        onClick={() => pickFile(f)}
                      >
                        <span className="mv-kind" aria-hidden>{KIND_ICON[f.kind] ?? "▪"}</span>
                        <span className="mv-title">{f.name}</span>
                        <span className="mv-size">{fmtSize(f.size)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
            {!stagedFiltered.length && !listError && (
              <li className="muted small">Nothing in this folder.</li>
            )}
          </ul>
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
      </section>

      <aside
        className={"mv-player" + (dragging ? " dropping" : "")}
        onDragOver={(e) => { if (selected) { e.preventDefault(); setDragging(true); } }}
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
        {note && <p className="muted small mv-note">{note}</p>}

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
              onPlan={(p) => setPlans((all) => ({ ...all, [selected!.id]: p }))}
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
        {/* Moving between folders is the one action that can put a file into
            the real library, so it has its own permission and is simply
            absent for anyone without it. Destinations are the same folders
            the panel browses, minus wherever the film already is. */}
        {selected && permissions.publish && (
          <div className="mv-move">
            <span className="muted small">Move to:</span>
            <select value={moveTo} onChange={(e) => setMoveTo(e.target.value)}>
              <option value="">choose a folder…</option>
              {sources
                // Inboxes are excluded: they are where unprepared downloads
                // wait, not somewhere a finished film belongs.
                .filter((x) => x.ready && x.kind !== "inbox" && x.key !== source)
                .map((x) => (
                  <option key={x.key} value={x.key}>{x.label}</option>
                ))}
            </select>
            <button
              disabled={!moveTo || !!publishing}
              title={moveTo ? `Move this film's folder into ${sources.find((x) => x.key === moveTo)?.path}` : "Pick a destination"}
              onClick={async () => {
                setPublishing("Moving…");
                try {
                  const r = await api.prepMove(selected.id, moveTo);
                  setPrepNote(`Moved ${r.moved} → ${r.to}`);
                  setMoveTo("");
                  stop(); setSelected(null); setInfo(null);
                } catch (e) {
                  setPrepNote(String(e).replace(/^Error:\s*/, ""));
                } finally { setPublishing(""); }
              }}
            >
              {publishing || "MOVE"}
            </button>
          </div>
        )}
        {prepNote && <p className="muted small mv-note">{prepNote}</p>}
        {/* Last, and pushed to the foot of the column — it is the irreversible
            step, and it reads better with air above it. */}
        {plan && (
          <PrepCommit
            area={source}
            plan={plan}
            onDone={(msg) => { setPrepNote(msg); stop(); setSelected(null); setInfo(null); }}
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
