import { Fragment, useEffect, useState } from "react";
import { AccessMode, AccessRule, api, Calendar, FolderAccess } from "../api";
import { Key, useT } from "../i18n";
import { Icon, IconName } from "./icons";

/** How an album's visibility shows next to its name, everywhere it is drawn
 *  (the gallery's cards and path, the folder tree). */
export const ACCESS_ICON: Record<AccessMode, string> = { public: "🌐", shared: "👥", private: "🔒" };

type T = ReturnType<typeof useT>["t"];

export function accessTitle(a: FolderAccess, t: T): string {
  const what = t(a.mode === "public" ? "share_title_public" : a.mode === "shared" ? "share_title_shared" : "share_title_private");
  const from = a.from !== null && a.from !== undefined ? "" : ` ${t("share_no_rule")}`;
  return `${what}${from}${a.owner ? `\n${t("share_owner", { owner: a.owner })}` : ""}${a.can_share ? `\n${t("share_click_change")}` : ""}`;
}

/** The badge itself: a button when this user may change it. */
export function AccessBadge({ access, onShare, className = "" }: {
  access: FolderAccess; onShare?: () => void; className?: string;
}) {
  const { t } = useT();
  const icon = ACCESS_ICON[access.mode];
  if (access.can_share && onShare) {
    // A span acting as a button, not a <button>: it sits inside other
    // buttons (the gallery's album cards, the tree's rows).
    return (
      <span role="button" tabIndex={0} className={`mv-access clickable ${access.mode} ${className}`}
            title={accessTitle(access, t)}
            onClick={(e) => { e.stopPropagation(); onShare(); }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); onShare(); }
            }}>{icon}</span>
    );
  }
  return <span className={`mv-access ${access.mode} ${className}`} title={accessTitle(access, t)}>{icon}</span>;
}

type Level = "see" | "add" | "manage";
const levelText = (area: string): Record<Level, Key> =>
  ({ see: "share_can_see", add: area === ":documents" ? "share_can_add_files" : "share_can_add_photos", manage: "share_can_manage" }) as Record<Level, Key>;

/** Who sees an album (or a Documents folder), set by its owner: shared with chosen
 *  people — each with what they may do; everyone, for a public album — or
 *  private. A subfolder may also simply follow the folder it is in. An album
 *  never set is public (the server's default), and shows as shared with all. api/services/folder_access.py
 *  holds the rules; this only edits them. */
export function ShareDialog({ area, path, onClose, onSaved }: {
  /** The library: ":images" or ":documents". */
  area: string;
  path: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useT();
  const [users, setUsers] = useState<string[]>([]);
  const [owner, setOwner] = useState<string | null>(null);
  const [mode, setMode] = useState<AccessMode | null>(null);   // null: as the folder above
  const [people, setPeople] = useState<NonNullable<AccessRule["people"]>>({});
  const [inherited, setInherited] = useState<FolderAccess | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const nested = path.includes("/");
  const name = path.split("/").pop() ?? "";

  useEffect(() => {
    api.prepAccess(area, path).then((r) => {
      setUsers(r.users);
      setOwner(r.access.owner);
      setInherited(r.access);
      const own = r.rule.visibility;
      if (own === "public" || (!own && !nested)) {
        // Public — set that way, or never set at all — is "shared with
        // everyone": offered as exactly that, so saving it unchanged keeps
        // it visible to all, now as a list.
        setMode("shared");
        setPeople(Object.fromEntries(r.users.filter((u) => u !== r.access.owner)
          .map((u) => [u, r.rule.people?.[u] ?? "see"])));
      } else {
        setMode(own ?? null);
        setPeople(r.rule.people ?? {});
      }
    }).catch((e) => setError(String(e).replace(/^Error:\s*/, "")));
  }, [area, path, nested]);

  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } };
    window.addEventListener("keydown", key, true);
    return () => window.removeEventListener("keydown", key, true);
  }, [onClose]);

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      // Only who was given something beyond what the mode already gives.
      const keep = Object.fromEntries(Object.entries(people)
        .filter(([u]) => u !== owner));
      await api.prepSetAccess(area, path, mode, mode === "private" ? {} : keep);
      onSaved();
      onClose();
    } catch (e) {
      setError(String(e).replace(/^Error:\s*/, ""));
    } finally {
      setBusy(false);
    }
  };

  const others = users.filter((u) => u !== owner);
  const option = (m: AccessMode | null, icon: string, title: string, sub?: string) => (
    <label className={"sd-option" + (mode === m ? " on" : "")}>
      <input type="radio" name="sd-mode" checked={mode === m} onChange={() => setMode(m)} />
      <span className="sd-icon" aria-hidden>{icon}</span>
      <span className="sd-text"><b>{title}</b>{sub && <small>{sub}</small>}</span>
    </label>
  );

  return (
    <div className="sd-overlay" onClick={onClose}>
      <div className="sd-box" role="dialog" aria-label={t("share_sharing", { name })} onClick={(e) => e.stopPropagation()}>
        <header className="sd-head">
          <h3>{t("share_sharing", { name })}</h3>
          <span className="muted small">{owner ? t("share_owner", { owner }) : t("share_no_owner")}</span>
        </header>
        <div className="sd-options">
          {option("shared", ACCESS_ICON.shared, t("share_shared"), t("share_shared_desc"))}
          {option("private", ACCESS_ICON.private, t("share_private"))}
          {nested && option(null, "↰", t("share_inherit"),
            inherited && inherited.from !== path
              ? t("share_now", { mode: t(MODE_KEYS[inherited.mode]) }) + (inherited.from ? ` ${t("share_from", { name: inherited.from.split("/").pop() ?? "" })}` : "")
              : t("share_follows"))}
        </div>
        {mode === "shared" && others.length > 0 && (
          <People others={others} people={people} setPeople={setPeople}
                  levels={(["see", "add", "manage"] as Level[]).map((l) => [l, t(levelText(area)[l]), LEVEL_ICON[l]])} />
        )}
        {error && <p className="error small">{error}</p>}
        <footer className="sd-foot">
          <button className="ghost" onClick={onClose}>{t("cancel")}</button>
          <button onClick={save} disabled={busy || (mode === null && !nested)}>{busy ? t("saving") : t("save")}</button>
        </footer>
      </div>
    </div>
  );
}

type CalLevel = "see" | "edit" | "manage";
const CAL_LEVEL_TEXT: Record<CalLevel, Key> = { see: "share_can_see", edit: "share_can_edit_events", manage: "share_can_manage" };
const MODE_KEYS: Record<AccessMode, Key> = { public: "share_public", shared: "share_shared", private: "share_private" };

/** Who a calendar is shared with, set by its owner or whoever may manage
 *  it (api/services/calendar.py): private, or shared with chosen people —
 *  each seeing, editing its events, or managing it too. The same dialog as
 *  an album's, without the album-only choices. */
export function CalendarShareDialog({ calendar, onClose, onSaved }: {
  calendar: Calendar;
  onClose: () => void;
  onSaved: (calendars: Calendar[]) => void;
}) {
  const { t } = useT();
  const [users, setUsers] = useState<string[]>([]);
  const [mode, setMode] = useState<"shared" | "private">(calendar.shared ? "shared" : "private");
  const [people, setPeople] = useState<Record<string, CalLevel>>({ ...(calendar.people ?? {}) });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.calendarSharingUsers().then(setUsers).catch((e) => setError(String(e).replace(/^Error:\s*/, "")));
  }, []);
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } };
    window.addEventListener("keydown", key, true);
    return () => window.removeEventListener("keydown", key, true);
  }, [onClose]);

  const save = async () => {
    setBusy(true);
    setError("");
    try {
      onSaved(await api.setCalendarSharing(calendar.id, mode === "private" ? {} : people));
      onClose();
    } catch (e) {
      setError(String(e).replace(/^Error:\s*/, ""));
    } finally {
      setBusy(false);
    }
  };

  const others = users.filter((u) => u !== calendar.owner);
  const option = (m: "shared" | "private", icon: string, title: string, sub?: string) => (
    <label className={"sd-option" + (mode === m ? " on" : "")}>
      <input type="radio" name="sd-cal-mode" checked={mode === m} onChange={() => setMode(m)} />
      <span className="sd-icon" aria-hidden>{icon}</span>
      <span className="sd-text"><b>{title}</b>{sub && <small>{sub}</small>}</span>
    </label>
  );
  return (
    <div className="sd-overlay" onClick={onClose}>
      <div className="sd-box" role="dialog" aria-label={t("share_sharing", { name: calendar.name })} onClick={(e) => e.stopPropagation()}>
        <header className="sd-head">
          <h3>{t("share_sharing", { name: calendar.name })}</h3>
          <span className="muted small">{t("share_owner", { owner: calendar.owner })}</span>
        </header>
        <div className="sd-options">
          {option("shared", ACCESS_ICON.shared, t("share_shared"), t("share_shared_desc"))}
          {option("private", ACCESS_ICON.private, t("share_private"))}
        </div>
        {mode === "shared" && others.length > 0 && (
          <People others={others} people={people} setPeople={setPeople}
                  levels={(["see", "edit", "manage"] as CalLevel[]).map((l) => [l, t(CAL_LEVEL_TEXT[l]), LEVEL_ICON[l]])} />
        )}
        {error && <p className="error small">{error}</p>}
        <footer className="sd-foot">
          <button className="ghost" onClick={onClose}>{t("cancel")}</button>
          <button onClick={save} disabled={busy}>{busy ? t("saving") : t("save")}</button>
        </footer>
      </div>
    </div>
  );
}

const LEVEL_ICON: Record<"" | Level | CalLevel, IconName> = { "": "block", see: "eye", add: "plus", edit: "edit", manage: "settings" };

/** Who may do what, a row per person: no access or a level, as a row of
 *  icons (their names in the legend under them), so every row lines up.
 *  The first row, everyone, gives one level to all at once -- lit when all
 *  have the same one, none lit when they differ; the people scroll under it. */
function People<L extends string>({ others, people, setPeople, levels }: {
  others: string[];
  people: Record<string, L>;
  setPeople: (p: Record<string, L>) => void;
  levels: [L, string, IconName][];
}) {
  const { t } = useT();
  const choices: ["" | L, string, IconName][] = [["", t("share_no_access"), LEVEL_ICON[""]], ...levels];
  const first = people[others[0]] ?? "";
  const common = others.every((u) => (people[u] ?? "") === first) ? first : null;
  const pick = (value: "" | L | null, onPick: (v: "" | L) => void) => (
    <span className="sd-levels" role="radiogroup">
      {choices.map(([v, text, icon]) => (
        <button key={v} type="button" role="radio" aria-checked={value === v} title={text} aria-label={text}
                className={"ghost sd-level" + (value === v ? " on" : "")} onClick={() => onPick(v)}>
          <Icon name={icon} size={16} className="" />
        </button>
      ))}
    </span>
  );
  return (
    <div className="sd-people">
      <div className="sd-peoplehead">{t("share_who")}</div>
      <div className="sd-grid sd-all">
        <span className="sd-name sd-everyone">{t("share_everyone")}</span>
        {pick(common, (v) => {
          const next: Record<string, L> = {};
          if (v) for (const u of others) next[u] = v;
          setPeople(next);
        })}
      </div>
      <div className="sd-grid sd-list">
        {others.map((u) => (
          <Fragment key={u}>
            <span className="sd-name" title={u}>{u}</span>
            {pick(people[u] ?? "", (v) => {
              const next = { ...people };
              if (v) next[u] = v; else delete next[u];
              setPeople(next);
            })}
          </Fragment>
        ))}
      </div>
      <div className="sd-legend muted small">
        {choices.map(([v, text, icon]) => (
          <span key={v}><Icon name={icon} size={12} className="" /> {text}</span>
        ))}
      </div>
    </div>
  );
}
