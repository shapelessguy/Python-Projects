import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, MovieInfo, MovieItem } from "../api";

/** The stream is a transcode piped into a fragmented MP4: no byte ranges, no
 *  index, so the browser can't seek it and `video.duration` is meaningless.
 *  Seeking is therefore a *server* operation -- a new request at `t=`, which
 *  restarts ffmpeg there -- and everything this player displays is
 *  `offset + video.currentTime` measured against the duration ffprobe
 *  reported. That's also why the native controls are off: they'd offer a
 *  scrub bar that can't work. See api/services/movies.py. */

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

  // Defaults for the *next* start, editable before anything is playing.
  const [audio, setAudio] = useState(0);
  const [sub, setSub] = useState<number | null>(null);
  const [height, setHeight] = useState(360);

  useEffect(() => {
    api.movies().then(setMovies).catch((e) => setListError(String(e)));
  }, []);

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

  const pick = (movie: MovieItem) => {
    setSelected(movie);
    setInfo(null);
    setInfoError("");
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
        // Original when the file allows it -- it is by far the fastest thing
        // this can do (no encoding at all: ~9x realtime and a 0.3s first
        // frame, against ~1.5x and ~2.5s for a 360p transcode). Otherwise the
        // smallest rung, since speed matters here and quality doesn't.
        setHeight(meta.remux.ok ? 0 : 360);
      })
      .catch((e) => setInfoError(String(e)));
  };

  /** Start (or restart) ffmpeg. Every argument that changes the transcode --
   *  position, audio track, subtitle track, size -- goes through here,
   *  because on this pipeline they are all the same operation. */
  const play = useCallback(
    (opts: { t?: number; audio?: number; sub?: number | null; height?: number } = {}) => {
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

      const params = new URLSearchParams({
        id: movie.id,
        sid: sid.current,
        t: t.toFixed(3),
        h: String(h),
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
    [selected, info, position, audio, sub, height],
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

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!info) return;
    if (e.key === " " || e.key === "k") {
      e.preventDefault();
      togglePlay();
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      seek(Math.max(0, position - 10));
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      seek(Math.min(info.duration, position + 10));
    } else if (e.key === "f") {
      e.preventDefault();
      stageRef.current?.requestFullscreen?.().catch(() => {});
    }
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? movies.filter((m) => m.title.toLowerCase().includes(q)) : movies;
  }, [movies, query]);

  const duration = info?.duration ?? 0;
  const shown = scrub ?? position;

  return (
    <div className="panel movies" onKeyDown={onKeyDown} tabIndex={-1}>
      <section className="mv-library">
        <div className="mv-search">
          <input
            placeholder={`Search ${movies.length || ""} movies…`}
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
      </section>

      <aside className="mv-player">
        <div className="mv-stage" ref={stageRef}>
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
            ⏪
          </button>
          <button onClick={togglePlay} disabled={!info} title="Play / pause">
            {playing && !paused && !dead ? "⏸" : "▶"}
          </button>
          <button
            onClick={() => seek(Math.min(duration, position + 30))}
            disabled={!info}
            title="Forward 30s"
          >
            ⏩
          </button>
          <button onClick={stop} disabled={!playing} title="Stop the transcode">
            ⏹
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
            onClick={() => stageRef.current?.requestFullscreen?.().catch(() => {})}
            disabled={!playing}
            title="Fullscreen"
          >
            ⛶
          </button>
        </div>

        {streamError && <p className="error small">{streamError}</p>}
        {note && <p className="muted small mv-note">{note}</p>}

        <div className="mv-tracks">
          <label>
            <span className="muted small">Audio</span>
            <select
              value={audio}
              disabled={!info || !info.audio.length}
              onChange={(e) => (playing ? play({ audio: +e.target.value }) : setAudio(+e.target.value))}
            >
              {info?.audio.length ? (
                info.audio.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.label}
                  </option>
                ))
              ) : (
                <option>none</option>
              )}
            </select>
          </label>
          <label>
            {/* Burned into the picture, so switching is a restart like a seek
                -- there is no client-side subtitle track to toggle. */}
            <span className="muted small">Subtitles</span>
            <select
              value={sub === null ? "" : String(sub)}
              disabled={!info}
              onChange={(e) => {
                const next = e.target.value === "" ? null : +e.target.value;
                if (playing) play({ sub: next });
                else setSub(next);
              }}
            >
              <option value="">off</option>
              {info?.subtitles.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="muted small">Quality</span>
            <select
              value={height}
              disabled={!info}
              onChange={(e) => (playing ? play({ height: +e.target.value }) : setHeight(+e.target.value))}
            >
              {(info?.heights ?? [720]).map((h) => (
                <option key={h} value={h}>
                  {HEIGHT_LABEL[h] ?? `${h}p`}
                </option>
              ))}
              {info && !info.remux.ok && (
                <option value={-1} disabled>
                  Original — {info.remux.reason}
                </option>
              )}
            </select>
          </label>
        </div>
        <p className="muted small mv-hint">
          Space play/pause · ← → 10s · F fullscreen. Every seek restarts the transcode, so
          expect a second before the picture comes back.
        </p>
      </aside>
    </div>
  );
}
