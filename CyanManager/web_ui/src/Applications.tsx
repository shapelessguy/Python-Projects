import { useEffect, useRef, useState } from "react";
import { api, enc, usePoll, type Application, type Applications as AppsData, type WindowProps } from "./api";
import { Switch, SyncedInput, errorText, useToast } from "./fields";
import { Icon } from "./icons";

const isInt = (v: string) => /^-?\d{1,5}$/.test(v.trim());

export function Applications() {
  const toast = useToast();
  const { data, error, reload } = usePoll<AppsData>("/api/applications", 1000);
  // name null: the form creates a new application. `pick` counts the user's
  // picks: the form starts afresh on each, not when a rename changes the name.
  const [{ name: selected, pick }, setSel] = useState<{ name: string | null; pick: number }>({ name: null, pick: 0 });
  const lastSeen = useRef<Application | null>(null);
  const choose = (name: string | null) => setSel((s) => ({ name, pick: s.pick + 1 }));
  const renamed = (name: string) => setSel((s) => ({ ...s, name }));
  const [savingPositions, setSavingPositions] = useState(false);

  const call = async <T,>(method: string, path: string, body?: unknown): Promise<T | null> => {
    try {
      return await api<T>(method, path, body);
    } catch (e) {
      toast(errorText(e), true);
      return null;
    } finally {
      reload();
    }
  };

  if (!data) return <div className="muted pad">{error ?? "Loading…"}</div>;

  // Just renamed, before the next poll has it: the one last seen
  let current = selected === null ? null : data.applications.find((a) => a.name === selected) ?? null;
  if (current) lastSeen.current = current;
  else if (selected !== null) current = lastSeen.current;

  const savePositions = async () => {
    setSavingPositions(true);
    if (await call("POST", "/api/applications/save_positions")) toast("Window positions saved");
    setSavingPositions(false);
  };

  const up = data.applications.filter((a) => a.running).length;

  return (
    <div className="apps">
      <div className="apps-main">
        <div className="page-head">
          <div>
            <h1>Applications</h1>
            <p className="sub">
              <b>{up}</b> running · {data.applications.length} in this profile
              {error && <span className="err"> · {error}</span>}
            </p>
          </div>
          <div className="head-actions">
            <button className="btn" onClick={savePositions} disabled={savingPositions} title="Read where each placed window is now">
              <Icon name="save" />
              {savingPositions ? "Saving…" : "Save window positions"}
            </button>
            <button className="btn accent" onClick={() => choose(null)}>
              <Icon name="add" />
              New
            </button>
          </div>
        </div>
        <div className="table-wrap">
          <div className="app-table">
            <div className="app-row head">
              <span />
              <span>Application</span>
              <span title="Place this window where these fields say">Place</span>
              <span>Screen</span>
              <span className="c">X</span>
              <span className="c">Y</span>
              <span className="c">Width</span>
              <span className="c">Height</span>
              <span>State</span>
              <span />
            </div>
            {data.applications.map((a) => (
              <AppRow
                key={a.name}
                app={a}
                monitors={data.monitors}
                winStates={data.win_states}
                selected={a.name === selected}
                onSelect={() => choose(a.name)}
                call={call}
              />
            ))}
          </div>
          {data.applications.length === 0 && <div className="empty">No applications in this profile yet.</div>}
        </div>
      </div>
      <AppDetail
        key={pick}
        app={current}
        procTypes={data.proc_types}
        call={call}
        onSelect={choose}
        onRenamed={renamed}
      />
    </div>
  );
}

type Call = <T>(method: string, path: string, body?: unknown) => Promise<T | null>;

function AppRow({
  app,
  monitors,
  winStates,
  selected,
  onSelect,
  call,
}: {
  app: Application;
  monitors: string[];
  winStates: string[];
  selected: boolean;
  onSelect: () => void;
  call: Call;
}) {
  const path = `/api/applications/${enc(app.name)}`;
  const props = app.window_props;
  const on = props.order;
  const setProps = (p: Partial<WindowProps>) => call("PUT", path, { window_props: p });
  const state = app.running === null ? "unknown" : app.running ? "up" : "down";

  return (
    <div className={`app-row ${selected ? "selected" : ""} ${on ? "" : "off"}`} onClick={() => !selected && onSelect()}>
      <span className={`dot ${state}`} title={state === "unknown" ? "Checking…" : state === "up" ? "Running" : "Not running"} />
      <span className="app-id">
        <img className="app-icon" src={app.icon} alt="" loading="lazy" />
        <span className="app-name">{app.name}</span>
      </span>
      <Switch checked={on} onChange={(order) => setProps({ order })} label={`Place ${app.name}`} />
      <select value={props.monitor_id} disabled={!on} onChange={(e) => setProps({ monitor_id: e.target.value })}>
        {monitors.map((m) => (
          <option key={m} value={m}>
            {m || "—"}
          </option>
        ))}
      </select>
      {(["x", "y", "width", "height"] as const).map((k) => (
        <SyncedInput
          key={k}
          className="num"
          title={k}
          disabled={!on}
          value={String(props[k])}
          validate={isInt}
          onCommit={(v) => setProps({ [k]: parseInt(v, 10) })}
        />
      ))}
      <select value={props.win_state} disabled={!on} onChange={(e) => setProps({ win_state: e.target.value })}>
        {winStates.map((s) => (
          <option key={s}>{s}</option>
        ))}
      </select>
      <span className="row-actions">
        <button className="icon-btn start" title={`Start ${app.name}`} onClick={() => call("POST", `${path}/start`)}>
          <Icon name="play" size={12} />
        </button>
        <button className="icon-btn kill" title={`Kill ${app.name}`} onClick={() => call("POST", `${path}/kill`)}>
          <Icon name="stop" size={11} />
        </button>
      </span>
    </div>
  );
}

interface Draft {
  name: string;
  include: string;
  exclude: string;
  proc_type: string;
  proc_name: string;
  path: string;
  arguments: string;
  runas: boolean;
  startup: boolean;
}

const draftOf = (a: Application | null): Draft => ({
  name: a?.name ?? "",
  include: a?.window_kw.join(", ") ?? "",
  exclude: a?.excluded_kw.join(", ") ?? "",
  proc_type: a?.proc_type ?? "exe",
  proc_name: a?.proc_name ?? "",
  path: a?.path ?? "",
  arguments: a?.arguments ?? "",
  runas: a?.runas ?? false,
  startup: a?.startup ?? false,
});

const keywords = (s: string) =>
  s
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);

const bodyOf = (d: Draft) => ({
  name: d.name.trim(),
  window_kw: keywords(d.include),
  excluded_kw: keywords(d.exclude),
  proc_type: d.proc_type,
  proc_name: d.proc_name,
  path: d.path,
  arguments: d.arguments,
  runas: d.runas,
  startup: d.startup,
});

/**
 * The selected application's settings, saved as they change (as the Qt form
 * did), or a new one's, added with its button. Keyed by the application, so
 * it starts from the server's values each time another one is picked.
 */
function AppDetail({
  app,
  procTypes,
  call,
  onSelect,
  onRenamed,
}: {
  app: Application | null;
  procTypes: string[];
  call: Call;
  onSelect: (name: string | null) => void;
  onRenamed: (name: string) => void;
}) {
  const toast = useToast();
  const [draft, setDraft] = useState<Draft>(() => draftOf(app));
  const savedAs = useRef(app?.name ?? null);
  const lastSent = useRef(JSON.stringify(bodyOf(draftOf(app))));
  const timer = useRef<number>();
  const latest = useRef({ call, onRenamed });
  latest.current = { call, onRenamed };
  const existing = app !== null;

  const set = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }));

  // An existing application: save 600 ms after the last change
  useEffect(() => {
    if (!existing) return;
    const body = bodyOf(draft);
    const json = JSON.stringify(body);
    if (json === lastSent.current || !body.name) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(async () => {
      lastSent.current = json;
      const r = await latest.current.call<{ name: string }>(
        "PUT",
        `/api/applications/${enc(savedAs.current ?? "")}`,
        body,
      );
      if (r && r.name !== savedAs.current) {
        savedAs.current = r.name;
        latest.current.onRenamed(r.name);
      }
    }, 600);
    return () => window.clearTimeout(timer.current);
  }, [draft, existing]);

  const nudge = (prop: keyof WindowProps, delta: number) =>
    savedAs.current && call("POST", `/api/applications/${enc(savedAs.current)}/nudge`, { prop, delta });

  const add = async () => {
    const body = bodyOf(draft);
    if (!body.name) return toast("Give it a name first", true);
    const r = await call<{ name: string }>("POST", "/api/applications", body);
    if (r) {
      toast(`${r.name} added`);
      onSelect(r.name);
    }
  };

  const remove = async () => {
    const name = savedAs.current;
    if (!name || !window.confirm(`Remove ${name} from this profile?`)) return;
    window.clearTimeout(timer.current);
    if (await call("DELETE", `/api/applications/${enc(name)}`)) onSelect(null);
  };

  const idLabel = draft.proc_type === "python" ? "Script" : draft.proc_type === "chrome" ? null : "Process ID";

  return (
    <aside className="app-detail">
      <div className="detail-head">
        {app ? (
          <img className="detail-icon" src={app.icon} alt="" />
        ) : (
          <span className="detail-icon new">
            <Icon name="add" size={20} />
          </span>
        )}
        <div>
          <h2>{app ? app.name : "New application"}</h2>
          <p className="sub">{app ? "Changes save as you type" : "Fill in, then add it to this profile"}</p>
        </div>
      </div>

      <div className="detail-body">
        <Field label="Name">
          <input value={draft.name} onChange={(e) => set({ name: e.target.value })} placeholder="e.g. Discord" />
        </Field>

        {app && (
          <div className="nudge">
            <div className="nudge-group">
              <span className="field-label">Position</span>
              <div className="dpad">
                <button className="up" title="Move up" onClick={() => nudge("y", -1)}>
                  <Icon name="up" />
                </button>
                <button className="left" title="Move left" onClick={() => nudge("x", -1)}>
                  <Icon name="left" />
                </button>
                <button className="right" title="Move right" onClick={() => nudge("x", 1)}>
                  <Icon name="right" />
                </button>
                <button className="down" title="Move down" onClick={() => nudge("y", 1)}>
                  <Icon name="down" />
                </button>
              </div>
            </div>
            <div className="nudge-group">
              <span className="field-label">Size</span>
              <Stepper label="Width" onMinus={() => nudge("width", -1)} onPlus={() => nudge("width", 1)} />
              <Stepper label="Height" onMinus={() => nudge("height", -1)} onPlus={() => nudge("height", 1)} />
            </div>
          </div>
        )}

        <Field label="Window title includes" hint="comma separated">
          <textarea value={draft.include} onChange={(e) => set({ include: e.target.value })} placeholder="e.g. Discord" />
        </Field>
        <Field label="Window title excludes" hint="comma separated">
          <textarea value={draft.exclude} onChange={(e) => set({ exclude: e.target.value })} />
        </Field>

        <div className="field-row">
          <Field label="Process type">
            <select value={draft.proc_type} onChange={(e) => set({ proc_type: e.target.value })}>
              {procTypes.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </Field>
          {idLabel && (
            <Field label={idLabel} grow>
              <input value={draft.proc_name} onChange={(e) => set({ proc_name: e.target.value })} placeholder="e.g. Discord.exe" />
            </Field>
          )}
        </div>

        <Field label="Exe path">
          <textarea className="mono" value={draft.path} onChange={(e) => set({ path: e.target.value })} placeholder="e.g. C:/…/app.exe or app:Name" />
        </Field>
        <Field label="Additional arguments">
          <input className="mono" value={draft.arguments} onChange={(e) => set({ arguments: e.target.value })} />
        </Field>

        <div className="toggles">
          <div className="row-between">
            <span className="label">Run as administrator</span>
            <Switch checked={draft.runas} onChange={(runas) => set({ runas })} label="Run as administrator" />
          </div>
          <div className="row-between">
            <span className="label">Start with CyanManager</span>
            <Switch checked={draft.startup} onChange={(startup) => set({ startup })} label="Start with CyanManager" />
          </div>
        </div>
      </div>

      <div className="detail-foot">
        {app ? (
          <button className="btn danger" onClick={remove}>
            <Icon name="trash" />
            Remove
          </button>
        ) : (
          <button className="btn accent wide" onClick={add}>
            <Icon name="add" />
            Add application
          </button>
        )}
      </div>
    </aside>
  );
}

function Field({
  label,
  hint,
  grow,
  children,
}: {
  label: string;
  hint?: string;
  grow?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className={`field ${grow ? "grow" : ""}`}>
      <span className="field-label">
        {label}
        {hint && <em>{hint}</em>}
      </span>
      {children}
    </label>
  );
}

function Stepper({ label, onMinus, onPlus }: { label: string; onMinus: () => void; onPlus: () => void }) {
  return (
    <div className="stepper">
      <button title={`Decrease ${label.toLowerCase()}`} onClick={onMinus}>
        <Icon name="minus" />
      </button>
      <span>{label}</span>
      <button title={`Increase ${label.toLowerCase()}`} onClick={onPlus}>
        <Icon name="plus" />
      </button>
    </div>
  );
}
