import { useState } from "react";
import { ControlsPanel } from "./panels/ControlsPanel";
import { EnvironmentPanel } from "./panels/EnvironmentPanel";
import { PersonalPanel } from "./panels/PersonalPanel";
import { FoodPanel } from "./panels/FoodPanel";
import { CalendarPanel } from "./panels/CalendarPanel";
import { AlarmOverlay } from "./AlarmOverlay";
import { useVisibility } from "./api";
import { currentUsername, logout } from "./auth";

type PanelId = "controls" | "environment" | "personal" | "food" | "calendar";

const PANELS: { id: PanelId; label: string; render: () => JSX.Element }[] = [
  { id: "controls", label: "🎛 Controls", render: () => <ControlsPanel /> },
  { id: "environment", label: "🌦 Environment", render: () => <EnvironmentPanel /> },
  { id: "personal", label: "🗂 Personal", render: () => <PersonalPanel /> },
  { id: "food", label: "🍽 Food", render: () => <FoodPanel /> },
  { id: "calendar", label: "📅 Calendar", render: () => <CalendarPanel /> },
];

export default function App() {
  const { visible: visiblePanelIds, loaded } = useVisibility();
  const [panel, setPanel] = useState<PanelId>("controls");
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

  return (
    <div className="app">
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
              <button className="ghost" onClick={logout} title="Sign out">
                Log out
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
      <AlarmOverlay />
    </div>
  );
}
