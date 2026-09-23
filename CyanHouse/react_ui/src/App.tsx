import { useState } from "react";
import { ControlsPanel } from "./panels/ControlsPanel";
import { EnvironmentPanel } from "./panels/EnvironmentPanel";
import { PersonalPanel } from "./panels/PersonalPanel";
import { FoodPanel } from "./panels/FoodPanel";
import { CalendarPanel } from "./panels/CalendarPanel";
import { MoviesPanel } from "./panels/MoviesPanel";
import { AlarmOverlay } from "./AlarmOverlay";
import { useVisibility } from "./api";
import { currentUsername, logout } from "./auth";
import { readCookie, writeCookie } from "./cookies";

type PanelId = "controls" | "environment" | "personal" | "food" | "calendar" | "movies";

const PANELS: { id: PanelId; label: string; render: () => JSX.Element }[] = [
  { id: "controls", label: "🎛 Controls", render: () => <ControlsPanel /> },
  { id: "environment", label: "🌦 Environment", render: () => <EnvironmentPanel /> },
  { id: "personal", label: "🗂 Personal", render: () => <PersonalPanel /> },
  { id: "food", label: "🍽 Food", render: () => <FoodPanel /> },
  { id: "calendar", label: "📅 Calendar", render: () => <CalendarPanel /> },
  // Still keyed "movies": that id is the permission name in secrets.json's
  // visibility lists and the backend's require_panel, so renaming the label
  // alone keeps every existing account's access as it was.
  { id: "movies", label: "🎬 Media", render: () => <MoviesPanel /> },
];

const LAST_SECTION_COOKIE = "last_section";

function loadLastPanel(): PanelId {
  const v = readCookie(LAST_SECTION_COOKIE);
  return PANELS.some((p) => p.id === v) ? (v as PanelId) : "controls";
}

export default function App() {
  const { visible: visiblePanelIds, loaded } = useVisibility();
  const [panel, setPanelState] = useState<PanelId>(loadLastPanel);
  const setPanel = (id: PanelId) => {
    setPanelState(id);
    writeCookie(LAST_SECTION_COOKIE, id);
  };
  const username = currentUsername();

  // Purely a UI nicety -- the APIs behind a hidden panel already 403 a
  // restricted user server-side (api/auth.py's require_panel) regardless of
  // this filter. But `loaded` gates rendering any panel at all below, so no
  // panel component mounts (and so no panel fires its own API calls) before
  // we actually know what's allowed -- otherwise a restricted user's very
  // first paint could still fire a request that comes back 403 for no
  // visible reason, a moment before the tab for it disappears anyway.
  const visible = visiblePanelIds === null
    ? PANELS
    : PANELS.filter((p) => visiblePanelIds.includes(p.id));
  // Falls back to the first visible panel without needing to resync `panel`
  // state itself -- covers a restricted user whose default "controls" isn't
  // in their list.
  const active = visible.find((p) => p.id === panel) ?? visible[0];

  // Both of these own their own scrolling: the environment charts and the
  // media library are each taller than the viewport, and only that column --
  // not the page -- should get a scrollbar.
  const fixedHeight = active?.id === "environment" || active?.id === "movies";

  return (
    <div className={"app" + (fixedHeight ? " app--fixed" : "")}>
      <header className="topbar">
        <nav className="switcher">
          {loaded && visible.map((p) => (
            <button
              key={p.id}
              className={active && p.id === active.id ? "active" : ""}
              onClick={() => setPanel(p.id)}
            >
              {p.label}
            </button>
          ))}
          {username && (
            <span className="whoami">
              {username}
              <button className="ghost icon-btn" onClick={logout} title="Sign out">
                ⏻
              </button>
            </span>
          )}
        </nav>
      </header>
      <main className="content">
        {!loaded ? (
          <p className="muted">Loading…</p>
        ) : active ? (
          active.render()
        ) : (
          <p className="muted">No panels available for this account.</p>
        )}
      </main>
      {/* Alarms are calendar events -- nothing to check if this user can't
          see the calendar panel at all, and fetching anyway would just be a
          request the backend 403s for no visible reason. */}
      <AlarmOverlay enabled={loaded && (visiblePanelIds === null || visiblePanelIds.includes("calendar"))} />
    </div>
  );
}
