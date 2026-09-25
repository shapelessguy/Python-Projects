import { useEffect, useState } from "react";
import { AccessMode, AccessRule, api, Calendar, FolderAccess } from "../api";

/** How an album's visibility shows next to its name, everywhere it is drawn
 *  (the gallery's cards and path, the folder tree). */
export const ACCESS_ICON: Record<AccessMode, string> = { public: "🌐", shared: "👥", private: "🔒" };

export function accessTitle(a: FolderAccess): string {
  const what = a.mode === "public" ? "Public — everyone sees it"
    : a.mode === "shared" ? "Shared — only the people chosen"
    : "Private — only its owner";
  const from = a.from !== null && a.from !== undefined ? "" : " (no rule set: public)";
  return `${what}${from}${a.owner ? `\nowner: ${a.owner}` : ""}${a.can_share ? "\nclick to change" : ""}`;
}

/** The badge itself: a button when this user may change it. */
export function AccessBadge({ access, onShare, className = "" }: {
  access: FolderAccess; onShare?: () => void; className?: string;
}) {
  const icon = ACCESS_ICON[access.mode];
  if (access.can_share && onShare) {
    // A span acting as a button, not a <button>: it sits inside other
    // buttons (the gallery's album cards, the tree's rows).
    return (
      <span role="button" tabIndex={0} className={`mv-access clickable ${access.mode} ${className}`}
            title={accessTitle(access)}
            onClick={(e) => { e.stopPropagation(); onShare(); }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); onShare(); }
            }}>{icon}</span>
    );
  }
  return <span className={`mv-access ${access.mode} ${className}`} title={accessTitle(access)}>{icon}</span>;
}

type Level = "see" | "add" | "manage";
const LEVEL_TEXT: Record<Level, string> = { see: "can see", add: "can add photos", manage: "can manage" };

/** Who sees an album, set by its owner (or an admin): shared with chosen
 *  people — each with what they may do; everyone, for a public album — or
 *  private. A subfolder may also simply follow the folder it is in. An album
 *  never set is public (the server's default), and shows as shared with all. api/services/image_access.py
 *  holds the rules; this only edits them. */
export function ShareDialog({ path, onClose, onSaved }: {
  path: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [users, setUsers] = useState<string[]>([]);
  const [owner, setOwner] = useState<string | null>(null);
  const [mode, setMode] = useState<AccessMode | null>(null);   // null: as the folder above
  const [people, setPeople] = useState<NonNullable<AccessRule["people"]>>({});
  const [inherited, setInherited] = useState<FolderAccess | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const nested = path.includes("/");
  const name = path.split("/").pop();

  useEffect(() => {
    api.prepAccess(path).then((r) => {
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
  }, [path, nested]);

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
      await api.prepSetAccess(path, mode, mode === "private" ? {} : keep);
      onSaved();
      onClose();
    } catch (e) {
      setError(String(e).replace(/^Error:\s*/, ""));
    } finally {
      setBusy(false);
    }
  };

  const others = users.filter((u) => u !== owner);
  const option = (m: AccessMode | null, icon: string, title: string, sub: string) => (
    <label className={"sd-option" + (mode === m ? " on" : "")}>
      <input type="radio" name="sd-mode" checked={mode === m} onChange={() => setMode(m)} />
      <span className="sd-icon" aria-hidden>{icon}</span>
      <span className="sd-text"><b>{title}</b><small>{sub}</small></span>
    </label>
  );

  return (
    <div className="sd-overlay" onClick={onClose}>
      <div className="sd-box" role="dialog" aria-label={`Sharing ${name}`} onClick={(e) => e.stopPropagation()}>
        <header className="sd-head">
          <h3>Sharing · {name}</h3>
          <span className="muted small">{owner ? `owner: ${owner}` : "no owner — made before sharing existed"}</span>
        </header>
        <div className="sd-options">
          {option("shared", ACCESS_ICON.shared, "Shared", "With the people chosen below — all of them, or some")}
          {option("private", ACCESS_ICON.private, "Private", owner ? `Only ${owner}` : "Only admins")}
          {nested && option(null, "↰", "As the folder above",
            inherited && inherited.from !== path
              ? `Now: ${inherited.mode}${inherited.from ? ` (from ${inherited.from.split("/").pop()})` : ""}`
              : "Follows whatever the folder it is in says")}
        </div>
        {mode === "shared" && others.length > 0 && (
          <div className="sd-people">
            <div className="sd-peoplehead">Who</div>
            {others.map((u) => {
              const level = people[u] ?? "";
              return (
                <div key={u} className="sd-person">
                  <span>{u}</span>
                  <select value={level} onChange={(e) => {
                    const v = e.target.value as Level | "";
                    setPeople((p) => {
                      const next = { ...p };
                      if (v) next[u] = v; else delete next[u];
                      return next;
                    });
                  }}>
                    <option value="">no access</option>
                    {(["see", "add", "manage"] as Level[]).map((l) => <option key={l} value={l}>{LEVEL_TEXT[l]}</option>)}
                  </select>
                </div>
              );
            })}
          </div>
        )}
        {error && <p className="error small">{error}</p>}
        <footer className="sd-foot">
          <button className="ghost" onClick={onClose}>Cancel</button>
          <button onClick={save} disabled={busy || (mode === null && !nested)}>{busy ? "Saving…" : "Save"}</button>
        </footer>
      </div>
    </div>
  );
}

type CalLevel = "see" | "edit" | "manage";
const CAL_LEVEL_TEXT: Record<CalLevel, string> = { see: "can see", edit: "can edit events", manage: "can manage" };

/** Who a calendar is shared with, set by its owner or whoever may manage
 *  it (api/services/calendar.py): private, or shared with chosen people —
 *  each seeing, editing its events, or managing it too. The same dialog as
 *  an album's, without the album-only choices. */
export function CalendarShareDialog({ calendar, onClose, onSaved }: {
  calendar: Calendar;
  onClose: () => void;
  onSaved: (calendars: Calendar[]) => void;
}) {
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
  const option = (m: "shared" | "private", icon: string, title: string, sub: string) => (
    <label className={"sd-option" + (mode === m ? " on" : "")}>
      <input type="radio" name="sd-cal-mode" checked={mode === m} onChange={() => setMode(m)} />
      <span className="sd-icon" aria-hidden>{icon}</span>
      <span className="sd-text"><b>{title}</b><small>{sub}</small></span>
    </label>
  );
  return (
    <div className="sd-overlay" onClick={onClose}>
      <div className="sd-box" role="dialog" aria-label={`Sharing ${calendar.name}`} onClick={(e) => e.stopPropagation()}>
        <header className="sd-head">
          <h3>Sharing · {calendar.name}</h3>
          <span className="muted small">owner: {calendar.owner}</span>
        </header>
        <div className="sd-options">
          {option("shared", ACCESS_ICON.shared, "Shared", "With the people chosen below — all of them, or some")}
          {option("private", ACCESS_ICON.private, "Private", `Only ${calendar.owner}`)}
        </div>
        {mode === "shared" && others.length > 0 && (
          <div className="sd-people">
            <div className="sd-peoplehead">Who</div>
            {others.map((u) => (
              <div key={u} className="sd-person">
                <span>{u}</span>
                <select value={people[u] ?? ""} onChange={(e) => {
                  const v = e.target.value as CalLevel | "";
                  setPeople((p) => {
                    const next = { ...p };
                    if (v) next[u] = v; else delete next[u];
                    return next;
                  });
                }}>
                  <option value="">no access</option>
                  {(["see", "edit", "manage"] as CalLevel[]).map((l) => <option key={l} value={l}>{CAL_LEVEL_TEXT[l]}</option>)}
                </select>
              </div>
            ))}
          </div>
        )}
        {error && <p className="error small">{error}</p>}
        <footer className="sd-foot">
          <button className="ghost" onClick={onClose}>Cancel</button>
          <button onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        </footer>
      </div>
    </div>
  );
}
