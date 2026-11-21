import { useState } from "react";
import { enc, type Service, type ServiceParam, type State } from "./api";
import { Card, Masonry, Switch, SyncedInput, useColumns } from "./fields";

const STATUS_TEXT: Record<Service["status"], string> = {
  running: "Running",
  stopping: "Stopping",
  down: "Down",
  not_installed: "Not installed",
  installing: "Installing",
  install_failed: "Install failed",
};

type Call = (method: string, path: string, body?: unknown) => Promise<boolean>;

export function General({ state, call, switching }: { state: State; call: Call; switching: boolean }) {
  const columns = useColumns();
  const running = state.services.filter((s) => s.status === "running").length;
  const enabled = state.services.filter((s) => s.enabled).length;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Services</h1>
          <p className="sub">
            {switching ? (
              "Switching profile, restarting services…"
            ) : (
              <>
                <b>{running}</b> running · {enabled} enabled · {state.services.length} in all
              </>
            )}
          </p>
        </div>
      </div>
      <Masonry
        items={state.services}
        count={columns}
        weight={(s) => 2 + s.params.length}
        render={(s) => <ServiceCard key={s.name} service={s} call={call} />}
      />
    </div>
  );
}

export function StatusPill({ status, text }: { status: string; text: string }) {
  return (
    <span className={`pill ${status}`}>
      <span className="pill-dot" />
      {text}
    </span>
  );
}

function ServiceCard({ service: s, call }: { service: Service; call: Call }) {
  const [busy, setBusy] = useState(false);
  const path = `/api/services/${enc(s.name)}`;

  const setEnabled = async (enabled: boolean) => {
    setBusy(true);
    await call("PUT", path, { enabled });
    setBusy(false);
  };
  const setParam = (key: string, value: string | boolean) => call("PUT", path, { params: { [key]: value } });

  const status = busy ? "stopping" : s.status;
  const text = busy ? (s.enabled ? "Stopping" : "Starting") : STATUS_TEXT[s.status];

  return (
    <Card
      title={s.name}
      className={s.enabled ? "" : "dim"}
      aside={<StatusPill status={status} text={text} />}
    >
      <div className="service-body">
        <div className="row-between">
          <span className="label">Enabled</span>
          {s.installed ? (
            <Switch checked={s.enabled} disabled={busy} onChange={setEnabled} label={`Enable ${s.name}`} />
          ) : (
            <button
              className="btn small accent"
              disabled={s.status === "installing"}
              title={
                s.error
                  ? `Failed, see logs/dependencies.log: ${s.error}`
                  : `pip install -r services/${s.module}/requirements.txt`
              }
              onClick={() => call("POST", `${path}/install`)}
            >
              {s.status === "installing" ? "Installing…" : "Install dependencies"}
            </button>
          )}
        </div>
        {s.params.length > 0 && (
          <div className="params">
            {s.params.map((p) => (
              <Param key={p.key} param={p} onCommit={(v) => setParam(p.key, v)} />
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}

function Param({ param: p, onCommit }: { param: ServiceParam; onCommit: (v: string | boolean) => void }) {
  if (p.kind === "check") {
    return (
      <div className="param-check">
        <span className="param-label">{p.label}</span>
        <Switch checked={Boolean(p.value)} onChange={onCommit} label={p.label} />
      </div>
    );
  }
  let field;
  if (p.kind === "select") {
    field = (
      <select value={String(p.value)} onChange={(e) => onCommit(e.target.value)}>
        {!p.options.includes(String(p.value)) && <option value={String(p.value)}>{String(p.value) || "—"}</option>}
        {p.options.map((o) => (
          <option key={o}>{o}</option>
        ))}
      </select>
    );
  } else if (p.kind === "time") {
    field = (
      <SyncedInput
        type="time"
        value={String(p.value ?? "")}
        validate={(v) => /^\d\d:\d\d$/.test(v)}
        onCommit={onCommit}
      />
    );
  } else {
    field = <SyncedInput value={String(p.value ?? "")} onCommit={onCommit} />;
  }
  return (
    <>
      <span className="param-label">{p.label}</span>
      {field}
    </>
  );
}
