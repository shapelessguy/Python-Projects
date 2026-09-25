import { useEffect, useRef, useState } from "react";
import { api, MusicSong } from "../api";

/** The Music tab's player: one bar along the bottom of the library, like a
 *  music app's — what is playing on the left, the controls in the middle,
 *  the details and the volume on the right.
 *
 *  `song` is what is loaded; `play` changes (a new object) whenever it
 *  should start playing rather than just be loaded. Previous / next walk the
 *  album or list it was started from — the panel owns that list. */
export function MusicPlayerBar({ song, play, hasPrev, hasNext, onPrev, onNext }: {
  song: MusicSong | null;
  play: object | null;
  hasPrev: boolean;
  hasNext: boolean;
  onPrev: () => void;
  onNext: () => void;
}) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [length, setLength] = useState(0);
  const [scrub, setScrub] = useState<number | null>(null);
  const [volume, setVolume] = useState(() => {
    try { return Number(localStorage.getItem("music.volume") ?? 1); } catch { return 1; }
  });

  useEffect(() => { if (audio.current) audio.current.volume = volume; }, [volume, song?.path]);
  useEffect(() => {
    setTime(0);
    setLength(song?.seconds ?? 0);
    setScrub(null);
  }, [song?.path]);

  // A drag on the seek bar ends wherever the pointer is let go — often off
  // the bar — so the release is caught on the window; missing it left the
  // bar frozen at the dragged-to time.
  const scrubbing = useRef(false);
  const commitScrub = useRef<() => void>(() => {});
  commitScrub.current = () => {
    if (!scrubbing.current) return;
    scrubbing.current = false;
    if (audio.current && scrub !== null) audio.current.currentTime = scrub;
    setScrub(null);
  };
  useEffect(() => {
    const up = () => commitScrub.current();
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
    return () => {
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
    };
  }, []);
  // Only a *new* request plays. The bar is built afresh each time the Music
  // tab is opened, and the last request it was given — from before — must
  // not start the song again: coming back to the tab loads it, paused.
  const handled = useRef(play);
  useEffect(() => {
    if (!play || play === handled.current) return;
    handled.current = play;
    audio.current?.play().catch(() => {});
  }, [play]);

  const toggle = () => {
    const a = audio.current;
    if (!a || !song) return;
    if (a.paused) a.play().catch(() => {}); else a.pause();
  };

  // Space plays and pauses, unless a text field has the keyboard — also
  // with a button or a slider focused (the last thing clicked), whose own
  // space (clicking a song row again, say) is held back on key-up.
  useEffect(() => {
    const typing = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      return e.code !== "Space" || !!t?.closest("textarea, select, [contenteditable], "
        + "input:not([type=range]):not([type=button]):not([type=checkbox])");
    };
    const down = (e: KeyboardEvent) => {
      if (typing(e)) return;
      e.preventDefault();
      if (!e.repeat) toggle();
    };
    const up = (e: KeyboardEvent) => { if (!typing(e)) e.preventDefault(); };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  });

  const shown = scrub ?? time;
  return (
    <div className={"mp-bar" + (song ? "" : " empty")}>
      {song && (
        <audio
          ref={audio}
          src={api.prepRawUrl(":music", song.path)}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          // A new song swapped in stops the old one without a pause event.
          onEmptied={() => setPlaying(false)}
          onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
          onLoadedMetadata={(e) => setLength(e.currentTarget.duration || song.seconds)}
          onEnded={() => { setPlaying(false); if (hasNext) onNext(); }}
        />
      )}

      <div className="mp-now">
        <span className="mp-art">
          {song?.folder && <img src={api.musicArtUrl(song.folder, 240)} alt=""
                                onError={(e) => { e.currentTarget.style.visibility = "hidden"; }} />}
        </span>
        <span className="mp-names">
          <span className="mp-title">{song ? song.title : "Nothing playing"}</span>
          <span className="mp-artist">{song ? song.artist : "Double-click a song to play it"}</span>
        </span>
      </div>

      <div className="mp-controls">
        <div className="mp-buttons">
          <button className="ghost" disabled={!song} title="Previous (or back to the start)"
                  onClick={() => (audio.current && audio.current.currentTime > 3 || !hasPrev
                    ? audio.current && (audio.current.currentTime = 0) : onPrev())}>⏮</button>
          <button className="mp-play" disabled={!song} title="Play / pause (space)" onClick={toggle}>
            {playing ? "❚❚" : "▶"}
          </button>
          <button className="ghost" disabled={!hasNext} title="Next" onClick={onNext}>⏭</button>
        </div>
        <div className="mp-seek">
          <span className="mp-time">{mmss(shown)}</span>
          <input
            type="range" min={0} max={Math.max(1, length)} step={0.5} value={shown} disabled={!song}
            onPointerDown={() => { scrubbing.current = true; }}
            onChange={(e) => {
              // Arrow keys seek straight away; a drag waits for the release.
              if (scrubbing.current) setScrub(+e.target.value);
              else if (audio.current) audio.current.currentTime = +e.target.value;
            }}
          />
          <span className="mp-time">{mmss(length)}</span>
        </div>
      </div>

      <div className="mp-side">
        <span className="mp-meta" title={song?.path}>
          {song && [song.album, song.year, song.path.split(".").pop()?.toUpperCase(),
                    song.size ? `${(song.size / 1e6).toFixed(1)} MB` : ""].filter(Boolean).join(" · ")}
        </span>
        <label className="mp-volume" title="Volume">
          🔊
          <input type="range" min={0} max={1} step={0.01} value={volume}
                 onChange={(e) => {
                   setVolume(+e.target.value);
                   try { localStorage.setItem("music.volume", e.target.value); } catch { /* ignore */ }
                 }} />
        </label>
      </div>
    </div>
  );
}

function mmss(s: number): string {
  if (!isFinite(s) || s < 0) s = 0;
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}
