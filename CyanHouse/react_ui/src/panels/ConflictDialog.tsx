import { useEffect, useState } from "react";
import { api, MoveConflict } from "../api";
import { fmtSize } from "./StagingView";
import { useT } from "../i18n";

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
  const { t, lang } = useT();
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
    onDone([replaced && t("cf_replaced", { n: replaced }), kept && t("cf_kept", { n: kept }),
            skipped && t("cf_skipped", { n: skipped })].filter(Boolean).join(", "));
  };

  const when = (secs: number) => new Date(secs * 1000).toLocaleString(lang);
  const size = (n: number | null) => (n === null ? t("cf_folder") : fmtSize(n));

  return (
    <div className="cf-backdrop" onClick={() => !busy && onDone("")}>
      <div className="cf-dialog" role="dialog" aria-modal onClick={(e) => e.stopPropagation()}>
        <h2>{rows.length === 1 ? t("cf_one_there") : t("cf_many_there", { n: rows.length })}</h2>
        <p className="muted small">{t("cf_intro")}</p>
        <div className="cf-all">
          <span className="muted small">{t("cf_all")}</span>
          <button className="ghost" onClick={() => setAll("skip")}>{t("cf_leave")}</button>
          <button className="ghost" onClick={() => setAll("replace")}>{t("cf_replace")}</button>
          <button className="ghost" onClick={() => setAll("keep")}>{t("cf_keep")}</button>
        </div>
        <ul className="cf-list">
          {rows.map(({ clash, item }, i) => (
            <li key={`${clash.fromArea}/${item.path}`} className="cf-row">
              <div className="cf-name" title={item.dest}>
                {item.dest}
                <span className="muted small"> → {labelOf(clash.toArea)}</span>
              </div>
              <div className="cf-sides small">
                <span><b>{t("cf_incoming")}</b> {size(item.size)} · {when(item.modified)}</span>
                <span><b>{t("cf_there")}</b> {size(item.dest_size)} · {when(item.dest_modified)}</span>
              </div>
              <div className="cf-choice">
                {(["skip", "replace", "keep"] as Choice[]).map((c) => (
                  <label key={c} className={choice[i] === c ? "active" : ""}
                         title={c === "replace" && item.mixed ? t("cf_mixed") : ""}>
                    <input type="radio" name={`cf-${i}`} checked={choice[i] === c}
                           disabled={busy || (c === "replace" && item.mixed)}
                           onChange={() => setChoice((all) => all.map((x, j) => (j === i ? c : x)))} />
                    {t(c === "skip" ? "cf_leave" : c === "replace" ? "cf_replace" : "cf_keep")}
                  </label>
                ))}
              </div>
            </li>
          ))}
        </ul>
        {error && <p className="error small">{error}</p>}
        <div className="cf-actions">
          <button className="ghost" disabled={busy} onClick={() => onDone("")}>{t("cancel")}</button>
          <button className="cf-apply" disabled={busy} onClick={apply}>{busy ? t("cf_working") : t("cf_apply")}</button>
        </div>
      </div>
    </div>
  );
}
