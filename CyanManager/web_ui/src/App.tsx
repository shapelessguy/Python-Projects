import { useEffect, useState } from "react";
import { api, usePoll, type State } from "./api";
import { SyncedInput, ToastProvider, errorText, useToast } from "./fields";
import { Icon, type IconName } from "./icons";
import { General } from "./General";
import { Functions } from "./Functions";
import { Applications } from "./Applications";
import { Terminal } from "./Terminal";

const TABS: { id: string; label: string; icon: IconName }[] = [
  { id: "General", label: "Services", icon: "sliders" },
  { id: "Functions", label: "Functions", icon: "bolt" },
  { id: "Applications", label: "Applications", icon: "apps" },
];

function tabFromHash(): string {
  const h = decodeURIComponent(window.location.hash.slice(1));
  return TABS.some((t) => t.id === h) ? h : "General";
}

export function App() {
  return (
    <ToastProvider>
      <Shell />
    </ToastProvider>
  );
}

function Shell() {
  const toast = useToast();
  const [tab, setTab] = useState(tabFromHash);
  const [terminal, setTerminal] = useState(false);
  const [switching, setSwitching] = useState(false);
  const { data: state, error, reload } = usePoll<State>("/api/state", 1000);

  useEffect(() => {
    const on = () => setTab(tabFromHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  const call = async (method: string, path: string, body?: unknown) => {
    try {
      await api(method, path, body);
      return true;
    } catch (e) {
      toast(errorText(e), true);
      return false;
    } finally {
      reload();
    }
  };

  const setProfile = async (profile: string) => {
    setSwitching(true);
    await call("PUT", "/api/profile", { profile });
    setSwitching(false);
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <img src="/icons/cyan_system_manager.png" alt="" />
          <span>
            Cyan<b>Manager</b>
          </span>
        </div>

        <nav className="tabs">
          {TABS.map((t) => (
            <a key={t.id} href={`#${t.id}`} className={t.id === tab ? "active" : ""}>
              <Icon name={t.icon} />
              {t.label}
            </a>
          ))}
        </nav>

        <div className="spacer" />

        {state && (
          <div className="top-tools">
            <label className="field-inline" title="Profile: which services and applications this PC runs">
              <span>Profile</span>
              <select value={state.profile} disabled={switching} onChange={(e) => setProfile(e.target.value)}>
                {state.profiles.map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
            </label>
            <label className="field-inline password" title="Quick password: what TYPE_PASSWORD types">
              <Icon name="key" />
              <SyncedInput
                key={state.profile}
                type="password"
                value=""
                delay={800}
                autoComplete="new-password"
                placeholder={state.password_set ? "Saved · type to replace" : "Quick password"}
                onCommit={(password) =>
                  call("PUT", "/api/password", { password }).then((ok) => ok && toast("Password saved"))
                }
              />
            </label>
            <button className="icon-btn" title="Terminal" onClick={() => setTerminal(true)}>
              <Icon name="terminal" size={18} />
            </button>
          </div>
        )}
      </header>

      {error && (
        <div className="offline">
          <span className="pulse" /> CyanManager not reachable · {error}
        </div>
      )}

      <main className="tab-body">
        {!state ? (
          <div className="empty">{error ? "Waiting for CyanManager…" : "Loading…"}</div>
        ) : tab === "General" ? (
          <General state={state} call={call} switching={switching} />
        ) : tab === "Functions" ? (
          <Functions groups={state.functions} />
        ) : (
          <Applications />
        )}
      </main>
      {terminal && <Terminal onClose={() => setTerminal(false)} />}
    </div>
  );
}
