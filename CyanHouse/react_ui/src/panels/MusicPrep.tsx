import { useEffect, useState } from "react";
import { api, MusicIdentity, MusicOption, StagedFile } from "../api";

/** Under a song opened from a music inbox: what it is, and which album to
 *  file it under.
 *
 *  The song is looked up in MusicBrainz by the artist and title it carries
 *  (its tags, or an "Artist - Title" name). Every album it appears on comes
 *  back, best first — the studio album before the single, compilations and
 *  live recordings last — and the first is ticked. Pick another, or correct
 *  the artist or title and search again, then file it: the tags are written
 *  and it moves to Artist/Album/NN - Title in the pair's output. */
export function MusicIdentify({ area, file, canEdit, onFiled }: {
  area: string;
  file: StagedFile;
  canEdit: boolean;
  /** Filed: `newPath` is where it went, relative to the output. */
  onFiled: (newPath: string) => void;
}) {
  const [data, setData] = useState<MusicIdentity | null>(null);
  const [artist, setArtist] = useState("");
  const [title, setTitle] = useState("");
  const [pick, setPick] = useState(0);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const load = (a?: string, t?: string) => {
    setBusy("Looking it up…");
    setError("");
    api.musicIdentify(area, file.path, a, t)
      .then((r) => {
        setData(r);
        setArtist(r.song.artist);
        setTitle(r.song.title);
        setPick(0);
      })
      .catch((e) => setError(String(e).replace(/^Error:\s*/, "")))
      .finally(() => setBusy(""));
  };

  useEffect(() => { setData(null); load(); }, [area, file.path]);

  const chosen: MusicOption | undefined = data?.options[pick];

  const fileIt = async () => {
    if (!chosen) return;
    setBusy("Filing…");
    setError("");
    try {
      const r = await api.musicFile(area, file.path, chosen);
      onFiled(r.new_path);
    } catch (e) {
      setError(String(e).replace(/^Error:\s*/, ""));
      setBusy("");
    }
  };

  return (
    <div className="mu-identify">
      <div className="mu-search">
        <label>
          <span className="muted small">Artist</span>
          <input value={artist} onChange={(e) => setArtist(e.target.value)}
                 onKeyDown={(e) => e.key === "Enter" && load(artist, title)} />
        </label>
        <label>
          <span className="muted small">Title</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)}
                 onKeyDown={(e) => e.key === "Enter" && load(artist, title)} />
        </label>
        <button onClick={() => load(artist, title)} disabled={!!busy || !title.trim()}>Search</button>
      </div>
      {data?.review && (
        <p className="small mu-review">Not filed automatically: {data.review}.</p>
      )}
      {data && (
        <p className="muted small mu-from">
          {data.song.from === "tags" ? "Read from the file's tags."
            : data.song.from === "name" ? "Read from the file name."
            : "As you typed it."}
        </p>
      )}

      {busy && <p className="muted small">{busy}</p>}
      {error && <p className="error small">{error}</p>}

      {data && !busy && !data.options.length && (
        <p className="muted small">
          Nothing on MusicBrainz for this. Correct the artist or title and search again.
        </p>
      )}

      {data && data.options.length > 0 && (
        <ul className="mu-options">
          {data.options.map((o, i) => (
            <li key={o.release_group_id || o.release_id}>
              <label className={"mu-option" + (i === pick ? " active" : "")}>
                <input type="radio" name="mu-album" checked={i === pick} onChange={() => setPick(i)} />
                <span className="mu-cover">
                  {o.release_group_id && (
                    <img src={api.musicCoverUrl(o.release_group_id)} alt="" loading="lazy"
                         onError={(e) => { e.currentTarget.style.visibility = "hidden"; }} />
                  )}
                </span>
                <span className="mu-optiontext">
                  <span className="mu-album">{o.album}</span>
                  <span className="muted small">
                    {[o.album_artist, o.year, o.type + (o.live ? " (live)" : ""),
                      o.track ? `track ${o.track}${o.tracks ? `/${o.tracks}` : ""}`
                        + (o.track_label && o.track_label !== o.track ? ` (${o.track_label})` : "") : "",
                      o.country].filter(Boolean).join(" · ")}
                  </span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}

      {chosen && (
        <div className="mu-commit">
          <span className="mu-target" title={chosen.target}>→ {chosen.target}</span>
          <button
            className="mu-file"
            disabled={!canEdit || !!busy}
            title={canEdit ? "Write the tags and move it into the output" : "Filing needs the right to change this folder"}
            onClick={fileIt}
          >
            TAG &amp; FILE
          </button>
        </div>
      )}
    </div>
  );
}
