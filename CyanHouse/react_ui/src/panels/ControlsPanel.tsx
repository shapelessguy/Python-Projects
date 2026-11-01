import { useEffect, useRef, useState } from "react";
import { api, ControlsInfo, follow } from "../api";
import {
  ControlItem,
  ControlMode,
  MODE_CONFIGS,
  MODE_ICON,
  MODES,
  SEPARATOR_BEFORE_ROW,
  allItems,
} from "../controls";

const INFO_POLL_MS = 1000;
/** Holding the OS volume −/+ repeats its step: first after NUDGE_DELAY_MS,
 *  then every NUDGE_REPEAT_MS. */
const NUDGE_DELAY_MS = 1000;
const NUDGE_REPEAT_MS = 250;
const MODE_KEY = "cc.mode";

function loadMode(): ControlMode {
  try {
    const s = localStorage.getItem(MODE_KEY);
    if (s && (MODES as string[]).includes(s)) return s as ControlMode;
  } catch {
    /* private mode / disabled storage */
  }
  return "ALL";
}

export function ControlsPanel() {
  const [mode, setModeState] = useState<ControlMode>(loadMode);
  const setMode = (m: ControlMode) => {
    setModeState(m);
    try {
      localStorage.setItem(MODE_KEY, m);
    } catch {
      /* ignore */
    }
  };
  const [info, setInfo] = useState<ControlsInfo>({});
  const [status, setStatus] = useState<string>("");
  const draggingVol = useRef(false);
  const nudgeTimer = useRef<number>();
  const stopNudge = () => {
    window.clearTimeout(nudgeTimer.current);
    window.clearInterval(nudgeTimer.current);
  };
  useEffect(() => stopNudge, []);
  const statusTimer = useRef<number | undefined>(undefined);

  const flash = (msg: string) => {
    setStatus(msg);
    window.clearTimeout(statusTimer.current);
    statusTimer.current = window.setTimeout(() => setStatus(""), 2500);
  };

  // The OS volume and active audio device, followed: a held request that
  // comes back when they change (api/longpoll.py), not a poll a second.
  useEffect(() => {
    const stop = new AbortController();
    follow<ControlsInfo>("/api/controls/info", (i) => {
      if (!draggingVol.current) setInfo((p) => ({ ...p, ...i }));
    }, stop.signal);
    return () => stop.abort();
  }, []);

  // Voices CyanManager offers right now: only refreshed while the VOICES mode is
  // open; an unreachable backend/manager keeps the last known list.
  const [voices, setVoices] = useState<string[]>([]);
  useEffect(() => {
    if (mode !== "VOICES") return;
    let alive = true;
    const tick = () =>
      api
        .controlVoices()
        .then((v) => alive && setVoices(v))
        .catch(() => {});
    tick();
    const id = window.setInterval(tick, INFO_POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [mode]);

  const playVoice = async (name: string) => {
    try {
      await api.controlPlayVoice(name);
      flash(`✓ ${name}`);
    } catch {
      flash(`✕ ${name} failed`);
    }
  };

  const run = async (it: ControlItem, extra?: Record<string, unknown>) => {
    try {
      const res = it.room
        ? await api.controlRoom(it.topic, it.command, extra)
        : await api.controlFn(it.command, extra ?? (it.slider ? {} : undefined));
      if (res && (res.volume != null || res.device != null)) {
        setInfo((p) => ({ ...p, ...res }));
      }
      flash(extra ? `${it.label}: ${Object.values(extra)[0]}` : `✓ ${it.label}`);
    } catch {
      flash(`✕ ${it.label} failed`);
    } finally {
      if (it.slider) draggingVol.current = false;
    }
  };

  const items = mode === "ALL" ? allItems() : mode === "VOICES" ? [] : MODE_CONFIGS[mode];
  // Rows at/after each separator shift down one grid row per separator to make room for it.
  const sepRows = (mode === "ALL" ? undefined : SEPARATOR_BEFORE_ROW[mode]) ?? [];
  const gridRowOf = (row: number) => row + 1 + sepRows.filter((s) => s <= row).length;
  const device = info.device ?? "";
  const vol = info.volume ?? 0;

  return (
    <div className="panel controls">
      <div className="ctl-modes">
        {/* No ALL chip: ALL is simply "nothing selected" -- click the selected
            chip again to deselect it and get back to everything. */}
        {MODES.filter((m) => m !== "ALL").map((m) => (
          <button key={m} className={m === mode ? "active" : ""} onClick={() => setMode(m === mode ? "ALL" : m)}>
            <span aria-hidden>{MODE_ICON[m]}</span> {m}
          </button>
        ))}
      </div>
      <p className="muted small ctl-status">{status || " "}</p>

      <div className={"ctl-grid" + (mode === "ALL" ? " all" : "")}>
        {sepRows.map((s) => (
          <hr
            key={s}
            className="ctl-sep"
            style={{ gridRow: s + 1 + sepRows.filter((o) => o < s).length, gridColumn: "1 / -1" }}
          />
        ))}
        {items.map((it) => {
          // Per-mode views keep CyanControls' fixed 3-column row/col layout (its
          // gaps are intentional) — AUDIO's slider has colSpan 3, so it fills the
          // row. ALL just flows; there the slider spans 2 columns.
          const style: React.CSSProperties | undefined =
            mode === "ALL"
              ? it.slider
                ? { gridColumn: "span 2" }
                : undefined
              : {
                  gridRow: gridRowOf(it.row ?? 0),
                  gridColumn:
                    it.colSpan && it.colSpan > 1
                      ? `${(it.col ?? 0) + 1} / span ${it.colSpan}`
                      : `${(it.col ?? 0) + 1}`,
                };

          if (it.slider) {
            // −/+ just tell CyanManager to step the volume (VOLUME_DOWN/UP);
            // it picks the step and the new level comes back in its reply.
            const nudge = (command: "VOLUME_DOWN" | "VOLUME_UP") =>
              run({ ...it, command, slider: false });
            // One step on press, then repeated while held (NUDGE_DELAY_MS, then
            // every NUDGE_REPEAT_MS).
            // A keyboard press (Enter/Space) arrives only as a click, detail 0.
            const hold = (command: "VOLUME_DOWN" | "VOLUME_UP") => ({
              onPointerDown: (e: React.PointerEvent<HTMLButtonElement>) => {
                if (e.button !== 0) return;
                e.currentTarget.setPointerCapture(e.pointerId);
                stopNudge();
                nudge(command);
                nudgeTimer.current = window.setTimeout(() => {
                  nudge(command);
                  nudgeTimer.current = window.setInterval(() => nudge(command), NUDGE_REPEAT_MS);
                }, NUDGE_DELAY_MS);
              },
              onPointerUp: stopNudge,
              onPointerCancel: stopNudge,
              onLostPointerCapture: stopNudge,
              onClick: (e: React.MouseEvent) => {
                if (e.detail === 0) nudge(command);
              },
              onContextMenu: (e: React.MouseEvent) => e.preventDefault(),
            });
            return (
              <div key={it.label} className="ctl-slider" style={style}>
                <label>
                  {it.icon} OS Volume{device ? `: ${device}` : ""} · {Math.round(vol * 100)}%
                </label>
                <div className="ctl-slider-row">
                  <button
                    className="ctl-nudge"
                    aria-label="volume down"
                    {...hold("VOLUME_DOWN")}
                  >
                    −
                  </button>
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.01}
                    value={vol}
                    onPointerDown={() => (draggingVol.current = true)}
                    onChange={(e) => setInfo((p) => ({ ...p, volume: +e.target.value }))}
                    onPointerUp={(e) =>
                      run(it, { slide_value: +(e.target as HTMLInputElement).value })
                    }
                    onPointerCancel={() => (draggingVol.current = false)}
                  />
                  <button
                    className="ctl-nudge"
                    aria-label="volume up"
                    {...hold("VOLUME_UP")}
                  >
                    +
                  </button>
                </div>
              </div>
            );
          }

          const active =
            (it.label === "Speaker" && /speaker/i.test(device)) ||
            (it.label === "PHONES" && /headphone/i.test(device));

          return (
            <button
              key={it.label}
              className={"ctl-btn" + (active ? " on" : "")}
              style={{ ...(style ?? {}), ["--tint" as string]: it.tint ?? "var(--text)" } as React.CSSProperties}
              onClick={() => run(it)}
            >
              <span className="ctl-ico" aria-hidden>
                {it.icon}
              </span>
              <span className="ctl-lbl">
                {it.label}
                {active ? " (active)" : ""}
              </span>
            </button>
          );
        })}
        {mode === "VOICES" &&
          voices.map((name) => (
            <button key={name} className="ctl-btn voice" onClick={() => playVoice(name)}>
              <span className="ctl-lbl">{name}</span>
            </button>
          ))}
      </div>
      {mode === "VOICES" && voices.length === 0 && <p className="muted small">No voices available</p>}
    </div>
  );
}
