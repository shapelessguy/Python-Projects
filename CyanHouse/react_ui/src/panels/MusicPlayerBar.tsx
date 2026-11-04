import { useEffect, useRef, useState } from "react";
import { api, MusicSong } from "../api";
import { useT } from "../i18n";
import { inShell, NativeMusic, send, useNative } from "../native";
import { useNarrow } from "../narrow";
import { VolumePop } from "./VolumePop";

/** The Music tab's player: one bar along the bottom of the library, like a
 *  music app's — what is playing on the left, the controls in the middle,
 *  the details and the volume on the right.
 *
 *  `song` is what is loaded; `play` changes (a new object) whenever it
 *  should start playing rather than just be loaded. Previous / next walk the
 *  album or list it was started from — the panel owns that list.
 *
 *  In the Android shell the phone plays instead (native.ts): a play request
 *  hands it the whole list, so it goes on to the next song with the screen
 *  off, and its notification's buttons work. The bar shows what the phone
 *  says, and follows it (`onPick`) when it moves on to another song. */
export function MusicPlayerBar({ song, play, list, hasPrev, hasNext, onPrev, onNext, onPick }: {
  song: MusicSong | null;
  play: object | null;
  list: MusicSong[];
  hasPrev: boolean;
  hasNext: boolean;
  onPrev: () => void;
  onNext: () => void;
  onPick: (index: number) => void;
}) {
  const { t: tr } = useT();
  const audio = useRef<HTMLAudioElement | null>(null);
  const [localPlaying, setPlaying] = useState(false);
  const [localTime, setTime] = useState(0);
  const [localLength, setLength] = useState(0);
  const phone = useNative<NativeMusic>("music");
  // The phone has this song loaded (or, with none picked here, whatever it has).
  const mine = inShell && !!phone?.key && (!song || phone.key === song.path);
  const playing = inShell ? mine && phone!.playing : localPlaying;
  const time = inShell ? (mine ? phone!.time : 0) : localTime;
  const length = inShell ? (mine && phone!.length ? phone!.length : song?.seconds ?? 0) : localLength;
  const seek = (s: number) => {
    if (inShell) send("music.seek", { s });
    else if (audio.current) audio.current.currentTime = s;
  };
  const playHere = () => {
    const index = song ? list.findIndex((x) => x.path === song.path) : -1;
    const queue = index >= 0 ? list : song ? [song] : [];
    if (!queue.length) return;
    send("music.play", {
      index: Math.max(index, 0),
      items: queue.map((x) => ({
        key: x.path, url: api.prepRawUrl(":music", x.path), title: x.title, artist: x.artist,
        art: x.folder ? api.musicArtUrl(x.folder, 480) : "",
      })),
    });
  };
  // The phone went on to another song of the list: the bar (and the
  // panel's list) follow.
  useEffect(() => {
    if (!inShell || !phone?.key || phone.key === song?.path) return;
    const i = list.findIndex((x) => x.path === phone.key);
    if (i >= 0) onPick(i);
  }, [phone?.key]);
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
    if (scrub !== null) seek(scrub);
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
    if (inShell) playHere();
    else audio.current?.play().catch(() => {});
  }, [play]);

  const toggle = () => {
    if (inShell) {
      if (mine) send("music.toggle"); else playHere();
      return;
    }
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
  // Nothing picked here, and the phone playing something: that is shown.
  const title = song?.title ?? (mine ? phone!.title : "");
  const artist = song?.artist ?? (mine ? phone!.artist : "");
  const loaded = !!song || mine;
  const narrow = useNarrow();
  const changeVolume = (v: number) => {
    setVolume(v);
    try { localStorage.setItem("music.volume", String(v)); } catch { /* ignore */ }
  };
  return (
    <div className={"mp-bar" + (loaded ? "" : " empty")}>
      {song && !inShell && (
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
          <span className="mp-title">{loaded ? title : tr("mp_nothing")}</span>
          <span className="mp-artist">{loaded ? artist : tr("mp_hint")}</span>
        </span>
      </div>

      <div className="mp-controls">
        <div className="mp-buttons">
          <button className="ghost" disabled={!loaded} title={tr("mp_prev")}
                  onClick={() => (time > 3 || !hasPrev ? seek(0) : onPrev())}>⏮</button>
          <button className="mp-play" disabled={!loaded} title={tr("mp_play_pause")} onClick={toggle}>
            {playing ? "❚❚" : "▶"}
          </button>
          <button className="ghost" disabled={!hasNext} title={tr("mp_next")} onClick={onNext}>⏭</button>
          {/* On a phone the volume is a button at the end of this row, and
              the row with the details goes (styles.css). */}
          {narrow && !inShell && <VolumePop value={volume} onChange={changeVolume} title={tr("mp_volume")} />}
        </div>
        <div className="mp-seek">
          <span className="mp-time">{mmss(shown)}</span>
          <input
            type="range" min={0} max={Math.max(1, length)} step={0.5} value={shown} disabled={!loaded}
            onPointerDown={() => { scrubbing.current = true; }}
            onChange={(e) => {
              // Arrow keys seek straight away; a drag waits for the release.
              if (scrubbing.current) setScrub(+e.target.value);
              else seek(+e.target.value);
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
        {/* On the phone, its own volume keys. */}
        {!inShell && <label className="mp-volume" title={tr("mp_volume")}>
          🔊
          <input type="range" min={0} max={1} step={0.01} value={volume}
                 onChange={(e) => changeVolume(+e.target.value)} />
        </label>}
      </div>
    </div>
  );
}

function mmss(s: number): string {
  if (!isFinite(s) || s < 0) s = 0;
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}
