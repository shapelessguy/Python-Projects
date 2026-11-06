import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ControlsPanel } from "./panels/ControlsPanel";
import { EnvironmentPanel } from "./panels/EnvironmentPanel";
import { PersonalPanel } from "./panels/PersonalPanel";
import { FoodPanel } from "./panels/FoodPanel";
import { CalendarPanel } from "./panels/CalendarPanel";
import { MoviesPanel } from "./panels/MoviesPanel";
import { AlarmOverlay } from "./AlarmOverlay";
import { WeatherPopup } from "./WeatherPopup";
import { inShell, useNative } from "./native";
import { useVisibility } from "./api";
import { currentUsername, logout } from "./auth";
import { SettingsDialog } from "./SettingsDialog";
import { Key, useT } from "./i18n";
import { readCookie, writeCookie } from "./cookies";

type PanelId = "controls" | "environment" | "personal" | "food" | "calendar" | "media";

// Icons ending in an invisible U+FE0F are "text by default" emoji, which
// desktop Linux otherwise draws as small monochrome glyphs from a text
// font. The selector asks for the colour emoji.
const PANELS: { id: PanelId; icon: string; label: Key; render: () => JSX.Element }[] = [
  { id: "controls", icon: "🎛️", label: "panel_controls", render: () => <ControlsPanel /> },
  { id: "environment", icon: "📈", label: "panel_environment", render: () => <EnvironmentPanel /> },
  { id: "personal", icon: "🧮", label: "panel_personal", render: () => <PersonalPanel /> },
  { id: "food", icon: "🍽️", label: "panel_food", render: () => <FoodPanel /> },
  { id: "calendar", icon: "📅", label: "panel_calendar", render: () => <CalendarPanel /> },
  // "media" is also its permission name in secrets.json's visibility lists
  // and the backend's require_panel ("movies" before, still accepted there).
  { id: "media", icon: "🍿", label: "panel_media", render: () => <MoviesPanel /> },
];

const LAST_SECTION_COOKIE = "last_section";

function loadLastPanel(): PanelId {
  const saved = readCookie(LAST_SECTION_COOKIE);
  const v = saved === "movies" ? "media" : saved;   // the Media panel's old id
  return PANELS.some((p) => p.id === v) ? (v as PanelId) : "controls";
}

export default function App() {
  const { visible: visiblePanelIds, loaded } = useVisibility();
  const [panel, setPanelState] = useState<PanelId>(loadLastPanel);
  const setPanel = (id: PanelId) => {
    setPanelState(id);
    writeCookie(LAST_SECTION_COOKIE, id);
  };
  // The phone's music notification tapped: to the Media panel, whose Music
  // tab the panel itself opens (and then forgets the request).
  const opening = useNative<{ to: string }>("open");
  useEffect(() => {
    if (opening?.to === "music") setPanel("media");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opening]);
  const username = currentUsername();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { t } = useT();

  // Icons only once the full labels no longer fit in the bar. The bar
  // measures itself rather than trusting a breakpoint, because how much room
  // the labels need depends on how many panels this user can see. `needed`
  // is the width the labelled bar overflowed at, so it comes back only once
  // there is really room for it again.
  const navRef = useRef<HTMLElement | null>(null);
  const [compact, setCompact] = useState(false);
  const needed = useRef(0);

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

  // These own their own scrolling: the environment charts, the media library
  // and the dishes are each taller than the viewport, and only that column --
  // not the page, tab bar included -- should get a scrollbar.
  const fixedHeight = active?.id === "environment" || active?.id === "media" || active?.id === "controls"
    || active?.id === "food";

  useLayoutEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    const check = () => {
      if (!nav.classList.contains("compact")) {
        if (nav.scrollWidth > nav.clientWidth) {
          needed.current = nav.scrollWidth;
          setCompact(true);
        }
      } else if (nav.clientWidth >= needed.current) {
        setCompact(false);
      }
    };
    check();
    const ro = new ResizeObserver(check);
    ro.observe(nav);
    return () => ro.disconnect();
  }, [loaded, visible.length, compact]);

  return (
    <div className={"app" + (fixedHeight ? " app--fixed" : "")}>
      <header className="topbar">
        <nav className={"switcher" + (compact ? " compact" : "")} ref={navRef}>
          {loaded && visible.map((p) => (
            <button
              key={p.id}
              className={active && p.id === active.id ? "active" : ""}
              title={compact ? t(p.label) : undefined}
              onClick={() => setPanel(p.id)}
            >
              <span className="sw-icon">{p.icon}</span>
              <span className="sw-label">{t(p.label)}</span>
            </button>
          ))}
          {username && (
            <span className="whoami">
              <span className="whoami-name">{username}</span>
              <span className="whoami-actions">
                <button className="ghost icon-btn" onClick={() => setSettingsOpen(true)}
                        title={t("settings")} aria-label={t("settings")}>
                  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
                       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="3" />
                    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
                  </svg>
                </button>
                <button className="ghost icon-btn" onClick={logout} title={t("sign_out")} aria-label={t("sign_out")}>
                  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor"
                       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 3v9" />
                    <path d="M6.3 7.2a8 8 0 1 0 11.4 0" />
                  </svg>
                </button>
              </span>
            </span>
          )}
        </nav>
      </header>
      {settingsOpen && <SettingsDialog onClose={() => setSettingsOpen(false)} />}
      <main className="content">
        {!loaded ? (
          <p className="muted">{t("loading")}</p>
        ) : active ? (
          active.render()
        ) : (
          <p className="muted">{t("no_panels")}</p>
        )}
      </main>
      {/* Alarms are calendar events -- nothing to check if this user can't
          see the calendar panel at all, and fetching anyway would just be a
          request the backend 403s for no visible reason. In the Android
          shell they are its own: it rings and opens its alarm window
          (/ui/?alarm), so the app itself never comes up for one. */}
      <AlarmOverlay enabled={loaded && !inShell
                             && (visiblePanelIds === null || visiblePanelIds.includes("calendar"))} />
      <WeatherPopup enabled={loaded && (visiblePanelIds === null || visiblePanelIds.includes("environment"))} />
    </div>
  );
}
