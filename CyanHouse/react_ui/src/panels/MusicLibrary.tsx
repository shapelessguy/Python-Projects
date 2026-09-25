import { useEffect, useMemo, useState } from "react";
import { api, MusicLibrary as Library, MusicSong } from "../api";
import { CoverBook } from "./CoverBook";

/** The Music tab as a music library rather than a folder tree: artists —
 *  each one a single list of all their songs, album by album under a
 *  divider — or every song in one list.
 *
 *  Drawn from the files' own tags and each album folder's cover.jpg
 *  (api/services/music_library.py). A click on a song loads it in the
 *  player bar under the library, a double-click plays it; previous / next
 *  and the end of a song walk the album or list it was started from. */

export type MusicView = "artists" | "songs";

export function MusicLibrary({ view, query, activePath, version, onOpen, coverSize, active }: {
  view: MusicView;
  query: string;
  /** The artists' picture width (the panel's cover-size slider). */
  coverSize: number;
  /** Whether it is on screen — the arrow keys turn its pages only then. */
  active: boolean;
  activePath: string | null;
  /** Bumped when the library folder changes, to read it again. */
  version: number;
  /** Open (or, with `play`, start) a song, the `index`th of `list` — the
   *  album or list it is in, which previous / next then walk. */
  onOpen: (song: MusicSong, play: boolean, list: MusicSong[], index: number) => void;
}) {
  const [lib, setLib] = useState<Library | null>(null);
  const [error, setError] = useState("");
  const [artist, setArtist] = useState<string | null>(null);   // artist open
  // The last artist opened: back on the artists, the pages open where it
  // is (and it is ringed), not on page 1 — for zapping through them.
  const [lastArtist, setLastArtist] = useState<string | null>(null);

  useEffect(() => {
    api.musicLibrary().then((l) => { setLib(l); setError(""); })
      .catch((e) => setError(String(e).replace(/^Error:\s*/, "")));
  }, [version]);

  // Switching view goes back to the top of it.
  useEffect(() => { setArtist(null); }, [view]);

  const q = query.trim().toLowerCase();
  const hit = (...xs: string[]) => !q || xs.some((x) => x.toLowerCase().includes(q));

  const byFolder = useMemo(() => {
    const m = new Map<string, MusicSong[]>();
    for (const s of lib?.songs ?? []) {
      const l = m.get(s.folder) ?? [];
      l.push(s);
      m.set(s.folder, l);
    }
    for (const l of m.values()) l.sort((a, b) => a.disc - b.disc || a.track - b.track || a.title.localeCompare(b.title));
    return m;
  }, [lib]);

  // In the list's own box, so the player bar under it stays where it will be.
  if (error) return <div className="ml-scroll"><p className="error small">{error}</p></div>;
  if (!lib) return <div className="ml-scroll"><p className="muted small">Reading the library…</p></div>;

  // ── one artist: every song, album by album ──────────────────────────
  if (artist !== null) {
    const albums = lib.albums.filter((a) => a.artist === artist)
      .sort((a, b) => (a.year || "9999").localeCompare(b.year || "9999") || a.title.localeCompare(b.title));
    // One list for the whole artist, so playing runs on across albums.
    const all = albums.flatMap((a) => byFolder.get(a.folder) ?? []);
    const at = new Map(all.map((s, i) => [s.path, i]));
    const x = lib.artists.find((y) => y.name === artist);
    return (
      <div className="ml-scroll">
        <button className="ghost ml-back" onClick={() => setArtist(null)}>‹ Artists</button>
        <div className="ml-artisthead">
          <span className="ml-art ml-round ml-headart">
            {x?.cover ? <img src={api.musicArtUrl(x.cover, 400)} alt="" /> : <span className="ml-blank">{artist}</span>}
          </span>
          <div className="ml-albuminfo">
            <h2>{artist}</h2>
            <p className="muted small">
              {albums.length} album{albums.length === 1 ? "" : "s"} · {all.length} song{all.length === 1 ? "" : "s"}
              {" · "}{duration(all.reduce((n, s) => n + (s.seconds || 0), 0))}
            </p>
            <button className="ml-play" disabled={!all.length} onClick={() => onOpen(all[0], true, all, 0)}>▶ PLAY</button>
          </div>
        </div>
        {albums.map((a) => (
          <div key={a.folder}>
            <div className="ml-divider">
              <span className="ml-divart">
                {a.cover && <img src={api.musicArtUrl(a.folder, 240)} alt="" loading="lazy" />}
              </span>
              <span className="ml-divtitle">{a.title}</span>
              {a.year && <span className="muted small">{a.year}</span>}
              <span className="ml-divline" aria-hidden />
            </div>
            <SongRows songs={byFolder.get(a.folder) ?? []} list={all} at={at} activePath={activePath}
                      numbered onOpen={onOpen} showArtist={(s) => s.artist !== artist} />
          </div>
        ))}
      </div>
    );
  }

  if (view === "songs") {
    const songs = lib.songs.filter((s) => hit(s.title, s.artist, s.album))
      .sort((a, b) => a.title.localeCompare(b.title));
    return (
      <div className="ml-scroll">
        <SongRows songs={songs} activePath={activePath} onOpen={onOpen} showArtist={() => true} showAlbum />
        {!songs.length && <p className="muted small">No matches.</p>}
      </div>
    );
  }

  // ── every artist (the default): pages of them, like the films ───────
  // Only a page of pictures is fetched at a time, and small copies of them.
  // An artist is found by its name, or by any of its songs' titles or albums
  // — a single filed under some other artist is still found by its title.
  const found = new Set(q ? lib.songs.filter((s) => hit(s.title, s.album, s.artist)).map((s) => s.album_artist) : []);
  const artists = lib.artists.filter((x) => hit(x.name) || found.has(x.name))
    .map((x) => ({ ...x, id: x.name, title: x.name }));
  return (
    <div className="mv-bookwrap">
      <CoverBook
        items={artists}
        size={coverSize}
        selectedId={lastArtist}
        onPick={(x) => { setLastArtist(x.name); setArtist(x.name); }}
        active={active}
        resetKey={query}
        aspect={1}
        round
        art={(x, px) => (x.cover ? api.musicArtUrl(x.cover, px) : null)}
        sub={(x) => `${x.albums} album${x.albums === 1 ? "" : "s"} · ${x.tracks} song${x.tracks === 1 ? "" : "s"}`}
      />
    </div>
  );
}

function SongRows({ songs, list, at, activePath, numbered, showArtist, showAlbum, onOpen }: {
  songs: MusicSong[];
  /** The list playing walks (defaults to `songs`), and where each song is in it. */
  list?: MusicSong[];
  at?: Map<string, number>;
  activePath: string | null;
  numbered?: boolean;
  showArtist: (s: MusicSong) => boolean;
  showAlbum?: boolean;
  onOpen: (song: MusicSong, play: boolean, list: MusicSong[], index: number) => void;
}) {
  return (
    <ul className="ml-songs">
      {songs.map((s, i) => (
        <li key={s.path}>
          <button
            className={"ml-song" + (activePath === s.path ? " active" : "")}
            onClick={() => onOpen(s, false, list ?? songs, at?.get(s.path) ?? i)}
            onDoubleClick={() => onOpen(s, true, list ?? songs, at?.get(s.path) ?? i)}
            title={s.path}
          >
            <span className="ml-num">{numbered ? (s.track || "") : ""}</span>
            <span className="ml-songtitle">
              {s.title}
              {showArtist(s) && <span className="muted"> · {s.artist}</span>}
            </span>
            {showAlbum && <span className="ml-songalbum muted">{s.album}</span>}
            <span className="ml-dur muted">{duration(s.seconds)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function duration(seconds: number): string {
  if (!seconds) return "";
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, r = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}` : `${m}:${String(r).padStart(2, "0")}`;
}
