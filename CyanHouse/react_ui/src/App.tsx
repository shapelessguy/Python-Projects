import { useState } from "react";
import { ControlsPanel } from "./panels/ControlsPanel";
import { EnvironmentPanel } from "./panels/EnvironmentPanel";
import { PersonalPanel } from "./panels/PersonalPanel";
import { FoodPanel } from "./panels/FoodPanel";
import { currentUsername, logout } from "./auth";

type PanelId = "controls" | "environment" | "personal" | "food";

const PANELS: { id: PanelId; label: string; render: () => JSX.Element }[] = [
  { id: "controls", label: "🎛 Controls", render: () => <ControlsPanel /> },
  { id: "environment", label: "🌦 Environment", render: () => <EnvironmentPanel /> },
  { id: "personal", label: "🗂 Personal", render: () => <PersonalPanel /> },
  { id: "food", label: "🍽 Food", render: () => <FoodPanel /> },
];

export default function App() {
  const [panel, setPanel] = useState<PanelId>("controls");
  const active = PANELS.find((p) => p.id === panel) ?? PANELS[0];
  const username = currentUsername();

  return (
    <div className="app">
      <header className="topbar">
        <nav className="switcher">
          {PANELS.map((p) => (
            <button
              key={p.id}
              className={p.id === panel ? "active" : ""}
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
      <main className="content">{active.render()}</main>
    </div>
  );
}
