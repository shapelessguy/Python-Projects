import { useEffect, useState } from "react";
import { api, MoveConflict } from "../api";
import { fmtSize } from "./StagingView";

/** The conflicts of one move: the files it could not place, and where. */
export interface Clash {
  fromArea: string;
  toArea: string;
  /** The folder (or file) that was being moved. */
  root: string;
  items: MoveConflict[];
}

type Choice = "skip" | "replace" | "keep";

/** Asked after a move that met files the destination already had.
 *
 *  Folders are merged without asking; only a file with the same name as one
 *  already there needs a person. Each one gets a choice — leave it where it
 *  was, replace the one there, or keep both (the incoming one gets a
 *  "(2)") — with both sides' size and date to go on, and the choice can be
 *  set for all at once. Nothing is done until Apply. */
export function ConflictDialog({ clashes, labelOf, onDone }: {
  clashes: Clash[];
  labelOf: (area: string) => string;
  /** Closed: `summary` says what was done, empty if nothing. */
  onDone: (summary: string) => void;
}) {
  const rows = clashes.flatMap((c) => c.items.map((item) => ({ clash: c, item })));
  const [choice, setChoice] = useState<Choice[]>(() => rows.map((r) => (r.item.mixed ? "keep" : "skip")));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const key = (e: KeyboardEvent) => e.key === "Escape" && !busy && onDone("");
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [busy]);

  const setAll = (c: Choice) =>
    setChoice(rows.map((r) => (c === "replace" && r.item.mixed ? "keep" : c)));

  const apply = async () => {
    setBusy(true);
    setError("");
    let replaced = 0, kept = 0;
    const failed: string[] = [];
    for (const [i, { clash, item }] of rows.entries()) {
      const c = choice[i];
      if (c === "skip") continue;
      try {
        await api.prepResolve(clash.fromArea, item.path, clash.toArea, item.dest, c, clash.root);
        if (c === "replace") replaced += 1; else kept += 1;
      } catch (e) {
        failed.push(`${item.path.split("/").pop()}: ${String(e).replace(/^Error:\s*/, "")}`);
      }
    }
    setBusy(false);
    if (failed.length) { setError(failed.join(" · ")); return; }
    const skipped = rows.length - replaced - kept;
    onDone([replaced && `${replaced} replaced`, kept && `${kept} kept as copies`,
            skipped && `${skipped} left where they were`].filter(Boolean).join(", "));
  };

  const when = (t: number) => new Date(t * 1000).toLocaleString();
  const size = (n: number | null) => (n === null ? "folder" : fmtSize(n));

  return (
    <div className="cf-backdrop" onClick={() => !busy && onDone("")}>
      <div className="cf-dialog" role="dialog" aria-modal onClick={(e) => e.stopPropagation()}>
        <h2>{rows.length === 1 ? "A file is already there" : `${rows.length} files are already there`}</h2>
        <p className="muted small">
          The folders were merged. These files have the same name as one already in the destination:
          choose what to do with each.
        </p>
        <div className="cf-all">
          <span className="muted small">All:</span>
          <button className="ghost" onClick={() => setAll("skip")}>Leave</button>
          <button className="ghost" onClick={() => setAll("replace")}>Replace</button>
          <button className="ghost" onClick={() => setAll("keep")}>Keep both</button>
        </div>
        <ul className="cf-list">
          {rows.map(({ clash, item }, i) => (
            <li key={`${clash.fromArea}/${item.path}`} className="cf-row">
              <div className="cf-name" title={item.dest}>
                {item.dest}
                <span className="muted small"> → {labelOf(clash.toArea)}</span>
              </div>
              <div className="cf-sides small">
                <span><b>Incoming</b> {size(item.size)} · {when(item.modified)}</span>
                <span><b>There</b> {size(item.dest_size)} · {when(item.dest_modified)}</span>
              </div>
              <div className="cf-choice">
                {(["skip", "replace", "keep"] as Choice[]).map((c) => (
                  <label key={c} className={choice[i] === c ? "active" : ""}
                         title={c === "replace" && item.mixed ? "A file and a folder cannot replace each other" : ""}>
                    <input type="radio" name={`cf-${i}`} checked={choice[i] === c}
                           disabled={busy || (c === "replace" && item.mixed)}
                           onChange={() => setChoice((all) => all.map((x, j) => (j === i ? c : x)))} />
                    {c === "skip" ? "Leave" : c === "replace" ? "Replace" : "Keep both"}
                  </label>
                ))}
              </div>
            </li>
          ))}
        </ul>
        {error && <p className="error small">{error}</p>}
        <div className="cf-actions">
          <button className="ghost" disabled={busy} onClick={() => onDone("")}>Cancel</button>
          <button className="cf-apply" disabled={busy} onClick={apply}>{busy ? "Working…" : "APPLY"}</button>
        </div>
      </div>
    </div>
  );
}
