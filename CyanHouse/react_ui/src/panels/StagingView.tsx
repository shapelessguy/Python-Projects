import { useEffect, useState } from "react";
import { api, PrepPlan, StagedFile, TmdbCandidate } from "../api";

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
  area, plan, onDone,
}: {
  area: string;
  plan: PrepPlan;
  onDone: (msg: string) => void;
}) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const dropped = plan.tracks.filter(
    (t) => t.type !== "video" && !t.cover_art && !t.language);
  const identified = plan.tmdb_id != null && !!plan.target;
  const blocked = plan.conflicts.length > 0;

  const [percent, setPercent] = useState<number | null>(null);

  const remux = async () => {
    setBusy("Remuxing…"); setError(""); setPercent(0);
    // /execute blocks until the file is written *and* verified, so the
    // percentage has to be polled alongside it rather than come back with it.
    const poll = window.setInterval(() => {
      api.prepProgress(area, plan.target)
        .then((p) => setPercent(p.percent))
        .catch(() => {});
    }, 500);
    try {
      const r = await api.prepExecute(area, plan);
      onDone(`Wrote ${r.output.split("/").pop()} in ${r.seconds}s; ${r.trashed.length} file(s) moved to trash.`);
    } catch (e) { setError(String(e).replace(/^Error:\s*/, "")); }
    finally {
      window.clearInterval(poll);
      setBusy(""); setPercent(null);
    }
  };

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
        <div className="mv-muxbar" data-busy={busy ? "true" : "false"}>
          {busy && (
            <>
              <div
                className={"mv-muxfill" + (percent === null ? " indeterminate" : "")}
                style={percent === null ? undefined : { width: `${percent}%` }}
              />
              <span className="mv-muxlabel">
                {percent === null ? "remuxing…" : `${percent}%`}
              </span>
            </>
          )}
        </div>
        <button className="mv-remux" onClick={remux} disabled={!!busy || blocked || !identified}>
          REMUX
        </button>
      </div>
    </div>
  );
}

export function fmtSize(bytes: number): string {
  if (!bytes) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
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

/** Group a flat file list by its folder, folders in name order. */
export function byFolder(files: StagedFile[]): [string, StagedFile[]][] {
  const map = new Map<string, StagedFile[]>();
  for (const f of files) {
    const k = f.folder || "(root)";
    if (!map.has(k)) map.set(k, []);
    map.get(k)!.push(f);
  }
  return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}
