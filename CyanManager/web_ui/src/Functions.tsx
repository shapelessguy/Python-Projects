import { useState } from "react";
import { api, enc, type FunctionGroup } from "./api";
import { Card, Masonry, errorText, useColumns, useToast } from "./fields";
import { Icon } from "./icons";
import { Keyboard } from "./Keyboard";

const VIEW_KEY = "functions.view";
function savedView(): "list" | "keyboard" {
  try {
    return localStorage.getItem(VIEW_KEY) === "keyboard" ? "keyboard" : "list";
  } catch {
    return "list";
  }
}

const FAILED = "'CyanManagerError'";

export function Functions({ groups }: { groups: FunctionGroup[] }) {
  const columns = useColumns();
  const [filter, setFilter] = useState("");
  const [view, setViewState] = useState(savedView);
  const setView = (v: "list" | "keyboard") => {
    setViewState(v);
    try {
      localStorage.setItem(VIEW_KEY, v);
    } catch {
      /* private window: not remembered */
    }
  };
  const words = filter.toLowerCase().split(/\s+/).filter(Boolean);
  const match = (name: string, description: string | null) =>
    words.every((w) => name.toLowerCase().replace(/_/g, " ").includes(w) || description?.toLowerCase().includes(w));
  const shown = groups
    .map((g) => ({ ...g, functions: g.functions.filter((f) => match(f.name, f.description)) }))
    .filter((g) => g.functions.length);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Functions</h1>
          <p className="sub">
            {view === "list" ? "Run any registered function on this PC." : "What the Hotkeys service binds to each key."}
          </p>
        </div>
        <div className="head-actions">
          {view === "list" && (
            <input
              className="search"
              type="search"
              placeholder="Search functions…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          )}
          <div className="segmented">
            <button className={view === "list" ? "on" : ""} onClick={() => setView("list")}>
              List
            </button>
            <button className={view === "keyboard" ? "on" : ""} onClick={() => setView("keyboard")}>
              Keyboard
            </button>
          </div>
        </div>
      </div>
      {view === "keyboard" ? (
        <Keyboard />
      ) : (
        <>
      <Masonry
        items={shown}
        count={columns}
        weight={(g) => 1.5 + g.functions.length}
        render={(g) => (
          <Card key={g.module} title={g.module} aside={<span className="count">{g.functions.length}</span>}>
            <div className="fn-list">
              {g.functions.map((f) => (
                <FunctionRow key={f.name} name={f.name} description={f.description} />
              ))}
            </div>
          </Card>
        )}
      />
      {shown.length === 0 && <div className="empty">No function matches “{filter}”.</div>}
        </>
      )}
    </div>
  );
}

function FunctionRow({ name, description }: { name: string; description: string | null }) {
  const toast = useToast();
  const [state, setState] = useState<"idle" | "running" | "ok" | "failed">("idle");

  const run = async () => {
    setState("running");
    try {
      const r = await api<{ result: string }>("POST", `/api/functions/${enc(name)}/run`);
      const failed = r.result === FAILED;
      const result = r.result && r.result !== "None" ? `: ${r.result.slice(0, 200)}` : "";
      toast(failed ? `${name} failed, see the terminal` : `${name} done${result}`, failed);
      setState(failed ? "failed" : "ok");
    } catch (e) {
      toast(`${name}: ${errorText(e)}`, true);
      setState("failed");
    }
    window.setTimeout(() => setState("idle"), 1500);
  };

  return (
    <button className={`fn ${state}`} onClick={run} disabled={state === "running"} title={description ?? name}>
      <span className="fn-text">
        <span className="fn-name">{name}</span>
        {description && <span className="fn-desc">{description}</span>}
      </span>
      <span className="fn-run">
        {state === "running" ? (
          <span className="spinner" />
        ) : state === "ok" ? (
          <Icon name="check" />
        ) : state === "failed" ? (
          <Icon name="x" />
        ) : (
          <Icon name="play" size={12} />
        )}
      </span>
    </button>
  );
}
