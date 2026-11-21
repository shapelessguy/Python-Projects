import { useMemo, useState } from "react";
import { api, enc, usePoll } from "./api";
import { errorText, useToast } from "./fields";
import { Icon } from "./icons";

interface Binding {
  vk: number;
  modifiers: number; // RegisterHotKey bits: 1 Alt, 2 Ctrl, 4 Shift, 8 Win
  function: string;
  description: string | null;
}

interface Hotkeys {
  bindings: Binding[];
  active: boolean;
  error?: string;
}

// ---- Layout: a full-size keyboard in key units (1 = one letter key) ----

interface Key {
  vk: number;
  label: string;
  name: string; // how a combination names it
  x: number;
  y: number;
  w: number;
  h: number;
  mod?: number; // a modifier key: the bit it stands for
}

const WIDTH = 22.75;
const HEIGHT = 6.5;

function buildLayout(): Key[] {
  const keys: Key[] = [];
  const add = (vk: number, label: string, x: number, y: number, w = 1, h = 1, name?: string, mod?: number) =>
    keys.push({ vk, label, name: name ?? label, x, y, w, h, mod });
  const row = (y: number, x: number, items: [number, string, number?, string?][]) => {
    for (const [vk, label, w = 1, name] of items) {
      add(vk, label, x, y, w, 1, name);
      x += w;
    }
  };

  // Function row
  add(27, "Esc", 0, 0);
  for (let i = 0; i < 12; i++) add(112 + i, `F${i + 1}`, 2 + i + Math.floor(i / 4) * 0.5, 0);
  add(44, "PrtSc", 15.25, 0);
  add(145, "ScrLk", 16.25, 0);
  add(19, "Pause", 17.25, 0);
  // Media keys above the numpad
  [
    [173, "🔇", "Mute"],
    [174, "🔉", "Vol −"],
    [175, "🔊", "Vol +"],
    [177, "⏮", "Prev track"],
    [179, "⏯", "Play/Pause"],
    [176, "⏭", "Next track"],
  ].forEach(([vk, label, name], i) =>
    add(vk as number, label as string, 18.75 + i * (4 / 6), 0, 4 / 6, 1, name as string),
  );

  const y = (r: number) => 1.5 + r;
  row(y(0), 0, [
    [192, "`"], [49, "1"], [50, "2"], [51, "3"], [52, "4"], [53, "5"], [54, "6"], [55, "7"], [56, "8"], [57, "9"],
    [48, "0"], [189, "-"], [187, "="], [8, "Backspace", 2],
  ]);
  row(y(1), 0, [
    [9, "Tab", 1.5], [81, "Q"], [87, "W"], [69, "E"], [82, "R"], [84, "T"], [89, "Y"], [85, "U"], [73, "I"], [79, "O"],
    [80, "P"], [219, "["], [221, "]"], [220, "\\", 1.5],
  ]);
  row(y(2), 0, [
    [20, "Caps", 1.75], [65, "A"], [83, "S"], [68, "D"], [70, "F"], [71, "G"], [72, "H"], [74, "J"], [75, "K"], [76, "L"],
    [186, ";"], [222, "'"], [13, "Enter", 2.25],
  ]);
  add(16, "Shift", 0, y(3), 2.25, 1, "Shift", 4);
  row(y(3), 2.25, [[90, "Z"], [88, "X"], [67, "C"], [86, "V"], [66, "B"], [78, "N"], [77, "M"], [188, ","], [190, "."], [191, "/"]]);
  add(16, "Shift", 12.25, y(3), 2.75, 1, "Shift", 4);
  add(17, "Ctrl", 0, y(4), 1.25, 1, "Ctrl", 2);
  add(91, "Win", 1.25, y(4), 1.25, 1, "Win", 8);
  add(18, "Alt", 2.5, y(4), 1.25, 1, "Alt", 1);
  add(32, "Space", 3.75, y(4), 6.25);
  add(18, "Alt", 10, y(4), 1.25, 1, "Alt", 1);
  add(92, "Win", 11.25, y(4), 1.25, 1, "Win", 8);
  add(93, "Menu", 12.5, y(4), 1.25);
  add(17, "Ctrl", 13.75, y(4), 1.25, 1, "Ctrl", 2);

  // Navigation cluster
  row(y(0), 15.25, [[45, "Ins"], [36, "Home"], [33, "PgUp"]]);
  row(y(1), 15.25, [[46, "Del"], [35, "End"], [34, "PgDn"]]);
  add(38, "↑", 16.25, y(3), 1, 1, "Up");
  row(y(4), 15.25, [[37, "←", 1, "Left"], [40, "↓", 1, "Down"], [39, "→", 1, "Right"]]);

  // Numpad
  const nx = 18.75;
  row(y(0), nx, [[144, "Num", 1, "NumLock"], [111, "/", 1, "Num /"], [106, "*", 1, "Num *"], [109, "−", 1, "Num −"]]);
  row(y(1), nx, [[103, "7", 1, "Num 7"], [104, "8", 1, "Num 8"], [105, "9", 1, "Num 9"]]);
  add(107, "+", nx + 3, y(1), 1, 2, "Num +");
  row(y(2), nx, [[100, "4", 1, "Num 4"], [101, "5", 1, "Num 5"], [102, "6", 1, "Num 6"]]);
  row(y(3), nx, [[97, "1", 1, "Num 1"], [98, "2", 1, "Num 2"], [99, "3", 1, "Num 3"]]);
  add(13, "Enter", nx + 3, y(3), 1, 2, "Enter");
  add(96, "0", nx, y(4), 2, 1, "Num 0");
  add(110, ".", nx + 2, y(4), 1, 1, "Num .");
  return keys;
}

const LAYOUT = buildLayout();
const KEY_NAME = new Map<number, string>();
for (const k of LAYOUT) if (!KEY_NAME.has(k.vk)) KEY_NAME.set(k.vk, k.name);

const MOD_NAMES: [number, string][] = [
  [2, "Ctrl"],
  [1, "Alt"],
  [4, "Shift"],
  [8, "Win"],
];

export const modsText = (mods: number) =>
  MOD_NAMES.filter(([bit]) => mods & bit)
    .map(([, n]) => n)
    .join(" + ");

export const comboText = (b: Binding) =>
  [modsText(b.modifiers), KEY_NAME.get(b.vk) ?? `Key ${b.vk}`].filter(Boolean).join(" + ");

/** Functions bound to keys by the Hotkeys service, on a keyboard. */
export function Keyboard() {
  const { data } = usePoll<Hotkeys>("/api/hotkeys", 3000);
  // null: every layer; a number: only bindings with exactly those modifiers
  const [layer, setLayer] = useState<number | null>(null);
  const [selected, setSelected] = useState<number | null>(null);

  const bindings = data?.bindings ?? [];
  const layers = useMemo(() => [...new Set(bindings.map((b) => b.modifiers))].sort((a, b) => a - b), [bindings]);
  const inLayer = (b: Binding) => layer === null || b.modifiers === layer;
  const byKey = useMemo(() => {
    const m = new Map<number, Binding[]>();
    for (const b of bindings) m.set(b.vk, [...(m.get(b.vk) ?? []), b]);
    return m;
  }, [bindings]);

  if (!data) return <div className="empty">Loading…</div>;

  const listed = selected === null ? bindings.filter(inLayer) : (byKey.get(selected) ?? []).filter(inLayer);
  const sorted = [...listed].sort((a, b) => a.modifiers - b.modifiers || a.vk - b.vk);

  return (
    <div className="kbd-view">
      <div className="kbd-toolbar">
        <div className="chips">
          <button className={`chip ${layer === null ? "on" : ""}`} onClick={() => setLayer(null)}>
            All <span>{bindings.length}</span>
          </button>
          {layers.map((m) => (
            <button key={m} className={`chip ${layer === m ? "on" : ""}`} onClick={() => setLayer(m)}>
              {m === 0 ? "No modifier" : modsText(m)}
              <span>{bindings.filter((b) => b.modifiers === m).length}</span>
            </button>
          ))}
        </div>
        {!data.active && (
          <span className="pill down" title={data.error}>
            <span className="pill-dot" />
            Hotkeys service is off: the keys do nothing now
          </span>
        )}
      </div>

      <div className="kbd-card">
        <div className="kbd" style={{ aspectRatio: `${WIDTH} / ${HEIGHT}` }}>
          {LAYOUT.map((k, i) => {
            const all = byKey.get(k.vk) ?? [];
            const shown = all.filter(inLayer);
            const isMod = k.mod !== undefined && layer !== null && (layer & k.mod) !== 0;
            const cls = [
              "key",
              shown.length ? "bound" : all.length ? "bound-other" : "",
              selected === k.vk ? "selected" : "",
              isMod ? "held" : "",
            ].join(" ");
            const style = {
              left: `${(k.x / WIDTH) * 100}%`,
              top: `${(k.y / HEIGHT) * 100}%`,
              width: `${(k.w / WIDTH) * 100}%`,
              height: `${(k.h / HEIGHT) * 100}%`,
            };
            return (
              <button
                key={i}
                className={cls}
                style={style}
                title={all.map((b) => `${comboText(b)} → ${b.function}`).join("\n") || k.name}
                onClick={() => setSelected(selected === k.vk || !all.length ? null : k.vk)}
              >
                <span className="cap">
                  <span className="key-label">{k.label}</span>
                  {shown.length > 0 && (
                    <span className="key-fn">
                      {shown[0].function.replace(/_/g, "_" + String.fromCharCode(0x200b)) /* a line may break after _ */}
                      {shown.length > 1 && <b> +{shown.length - 1}</b>}
                    </span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="card bindings">
        <header className="card-head">
          <h3>{selected === null ? "All bindings" : `${KEY_NAME.get(selected) ?? selected}`}</h3>
          {selected !== null && (
            <button className="btn small" onClick={() => setSelected(null)}>
              Show all
            </button>
          )}
        </header>
        <div className="binding-list">
          {sorted.map((b, i) => (
            <BindingRow key={`${b.vk}-${b.modifiers}-${i}`} b={b} />
          ))}
          {sorted.length === 0 && <div className="empty">Nothing bound here.</div>}
        </div>
      </div>
    </div>
  );
}

function BindingRow({ b }: { b: Binding }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      const r = await api<{ result: string }>("POST", `/api/functions/${enc(b.function)}/run`);
      const failed = r.result === "'CyanManagerError'";
      toast(failed ? `${b.function} failed, see the terminal` : `${b.function} done`, failed);
    } catch (e) {
      toast(`${b.function}: ${errorText(e)}`, true);
    }
    setBusy(false);
  };
  return (
    <div className="binding">
      <span className="combo">
        {comboText(b)
          .split(" + ")
          .map((part, i) => (
            <kbd key={i}>{part}</kbd>
          ))}
      </span>
      <span className="binding-fn">
        <span className="fn-name">{b.function}</span>
        {b.description && <span className="fn-desc">{b.description}</span>}
      </span>
      <button className="icon-btn" title={`Run ${b.function}`} onClick={run} disabled={busy}>
        {busy ? <span className="spinner" /> : <Icon name="play" size={12} />}
      </button>
    </div>
  );
}
