// CC (Cyan Controls) catalogue — ported from the CyanControls app's `modeConfigs`.
// Each item is either a "room" command (POST /api/controls/room/{topic} with
// {command}) or a "function" command (POST /api/controls/fn/{command}). Sliders
// send { slide_value: 0..1 }.

export interface ControlItem {
  label: string;
  icon: string; // emoji
  topic: string; // room topic ("top" | "lights" | "tv" | "audio"); "" for fn commands
  command: string;
  room: boolean; // true -> /room/{topic}; false -> /fn/{command}
  row?: number;
  col?: number;
  colSpan?: number;
  slider?: boolean;
  tint?: string; // icon accent colour
}

// VOICES is different from the rest: no static catalogue in MODE_CONFIGS -- its
// buttons are whatever voices CyanManager reports, polled while the mode is open.
export type ControlMode = "ALL" | "GROW" | "AUDIO" | "PC" | "VOICES";
export const MODES: ControlMode[] = ["ALL", "GROW", "AUDIO", "PC", "VOICES"];
export const MODE_ICON: Record<ControlMode, string> = {
  ALL: "▦",
  GROW: "🌱",
  AUDIO: "🔊",
  PC: "🖥",
  VOICES: "🗣",
};

/** Separator lines are drawn above these rows in that mode's grid. */
export const SEPARATOR_BEFORE_ROW: Partial<Record<ControlMode, number[]>> = {
  GROW: [1, 3],
  AUDIO: [2],
  PC: [2],
};

const CYAN = "#22b8cf";
const RED = "#e5484d";
const GREEN = "#46a758";
const MAGENTA = "#e93d82";
const BLUE = "#4c9be8";

export const MODE_CONFIGS: Record<Exclude<ControlMode, "ALL" | "VOICES">, ControlItem[]> = {
  GROW: [
    { label: "UV OFF", icon: "⚫", topic: "lights", command: "off", room: true, row: 0, col: 0 },
    { label: "UV AUTO", icon: "🔵", topic: "lights", command: "auto", room: true, row: 0, col: 1, tint: CYAN },
    { label: "UV ON", icon: "🟣", topic: "lights", command: "on", room: true, row: 0, col: 2, tint: MAGENTA },
    { label: "Power", icon: "🔌", topic: "top", command: "w", room: true, row: 1, col: 0, tint: RED },
    { label: "Top RGB", icon: "🎨", topic: "top", command: "rgb", room: true, row: 1, col: 1, tint: BLUE },
    { label: "Heart", icon: "❤️", topic: "top", command: "heart", room: true, row: 1, col: 2, tint: MAGENTA },
    { label: "Bright -", icon: "🔅", topic: "top", command: "bright-", room: true, row: 2, col: 0 },
    { label: "Bright +", icon: "🔆", topic: "top", command: "bright+", room: true, row: 2, col: 1 },
    { label: "Col Loop", icon: "🌈", topic: "top", command: "col_loop", room: true, row: 2, col: 2, tint: CYAN },
    { label: "Fan OFF", icon: "🌀", topic: "fan", command: "off", room: true, row: 3, col: 0, tint: RED },
    { label: "Fan Swing", icon: "🔃", topic: "fan", command: "swing", room: true, row: 3, col: 1, tint: BLUE },
    { label: "Fan ON", icon: "🌀", topic: "fan", command: "on", room: true, row: 3, col: 2, tint: GREEN },
    { label: "Fan Mode", icon: "🌬️", topic: "fan", command: "mode", room: true, row: 4, col: 1, tint: CYAN },
  ],
  AUDIO: [
    { label: "PHONES", icon: "🎧", topic: "", command: "HEADPHONES", room: false, row: 0, col: 0, tint: BLUE },
    { label: "PLAY", icon: "⏯", topic: "", command: "PLAY_PAUSE", room: false, row: 0, col: 1, tint: GREEN },
    { label: "Speaker", icon: "🔊", topic: "", command: "SPEAKERS", room: false, row: 0, col: 2, tint: CYAN },
    { label: "HW Vol -", icon: "🔉", topic: "audio", command: "vol-", room: true, row: 1, col: 0 },
    { label: "AUDIO PWR", icon: "⏻", topic: "audio", command: "on/off", room: true, row: 1, col: 1, tint: RED },
    { label: "HW Vol +", icon: "🔊", topic: "audio", command: "vol+", room: true, row: 1, col: 2 },
    { label: "OS Volume", icon: "🔊", topic: "", command: "SET_VOLUME", room: false, row: 2, col: 0, colSpan: 3, slider: true },
    { label: "Prev", icon: "⏮", topic: "", command: "PREV", room: false, row: 3, col: 0 },
    { label: "Next", icon: "⏭", topic: "", command: "NEXT", room: false, row: 3, col: 2 },
  ],
  PC: [
    { label: "Screens OFF", icon: "🖥", topic: "", command: "SHUTDOWN_MONITORS", room: false, row: 0, col: 0, tint: RED },
    { label: "Startup", icon: "🚀", topic: "", command: "STARTUP", room: false, row: 0, col: 1, tint: CYAN },
    { label: "Screens ON", icon: "🖥", topic: "", command: "TURN_ON_MONITORS", room: false, row: 0, col: 2, tint: GREEN },
    { label: "TV ON/OFF", icon: "🔌", topic: "tv", command: "power", room: true, row: 1, col: 0, tint: RED },
    { label: "Win Snap", icon: "📸", topic: "", command: "WIN_SNAPSHOT", room: false, row: 1, col: 1, tint: CYAN },
    { label: "TV OK", icon: "📺", topic: "tv", command: "ok", room: true, row: 1, col: 2, tint: GREEN },
    { label: "Strips OFF", icon: "⚫", topic: "strips", command: "off", room: true, row: 2, col: 0, tint: RED },
    { label: "Strips ON", icon: "💡", topic: "strips", command: "on", room: true, row: 2, col: 2, tint: GREEN },
    { label: "Mouse OFF", icon: "🖱", topic: "", command: "TURN_OFF_MOUSEPAD", room: false, row: 3, col: 0, tint: RED },
    { label: "Mouse ON", icon: "🖱", topic: "", command: "TURN_ON_MOUSEPAD", room: false, row: 3, col: 2, tint: GREEN },
  ],
};

/** ALL mode: de-duplicated union (by label) of every mode, flowed responsively. */
export function allItems(): ControlItem[] {
  const seen = new Set<string>();
  const out: ControlItem[] = [];
  for (const list of Object.values(MODE_CONFIGS))
    for (const it of list)
      if (!seen.has(it.label)) {
        seen.add(it.label);
        out.push({ ...it, row: undefined, col: undefined, colSpan: undefined });
      }
  return out;
}
