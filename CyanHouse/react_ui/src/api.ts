import { useEffect, useRef, useState } from "react";
import { onAuthFailed } from "./auth";

export type ColType = "number" | "text" | "bool" | "enum";

export interface Column {
  key: string;
  name: string;
  description: string;
  unit: string;
  type: ColType;
  position: number;
  options: string[];
}

export interface DayRow {
  date: string;
  values: Record<string, unknown>;
}

export interface MonthData {
  month: string;
  columns: Column[];
  units: string[];
  rows: DayRow[];
  version: number;
}

export interface City {
  key: string;
  city_name: string;
  country: string;
  flag: string;
  color: string;
  default: boolean;
}

export interface Variable {
  key: string;
  label: string;
  unit: string;
  group: string;
  default: boolean;
  description: string;
}

export interface EnvBootstrap {
  cities: City[];
  variables: Variable[];
  min_date: string | null;
  max_date: string | null;
  weather_version: number;
}

export interface SeriesResponse {
  resample: string;
  start: string;
  end: string;
  series: Record<string, Record<string, (number | null)[] | string[]>>;
}

export interface ForecastBootstrap {
  cities: City[];
  issued_at: Record<string, string | null>;
  dwd_hours: number;
  forecast_version: number;
}

export interface ForecastCitySeries {
  index: string[];
  precip_mm: (number | null)[];
  precip_prob: (number | null)[];
  source: string[];
}

export interface ForecastResponse {
  issued_at: Record<string, string | null>;
  series: Record<string, ForecastCitySeries>;
}

export interface ControlsInfo {
  volume?: number;
  device?: string;
}

export interface Torrent {
  hash: string;
  name: string;
  size: number;
  progress: number;
  dlspeed: number;
  upspeed: number;
  eta: number;
  state: string;
  ratio: number;
  category: string;
  added_on: number;
  num_seeds: number;
  num_leechs: number;
}

export interface TorrentVideo {
  name: string;
  path: string;
  size: number;
  subtitlePath: string | null;
}

async function j<T>(r: Response): Promise<T> {
  if (r.status === 401) {
    onAuthFailed();
    throw new Error("401 — not signed in");
  }
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text()}`);
  return r.json() as Promise<T>;
}

const JSON_HEADERS = { "content-type": "application/json" };

// Per-user data behind a same-origin cookie: never let the browser reuse one
// user's API response for another after a logout / account switch.
const f = (url: string, init: RequestInit = {}) =>
  fetch(url, { cache: "no-store", ...init });

export interface Versions {
  diary: number;
  weather: number;
  food: number;
  forecast: number;
}

export const api = {
  version: () => f("/api/version").then(j<Versions>),

  envBootstrap: () => f("/api/environment/bootstrap").then(j<EnvBootstrap>),
  series: (q: Record<string, string>) =>
    f("/api/environment/series?" + new URLSearchParams(q)).then(j<SeriesResponse>),
  refresh: () => f("/api/environment/refresh", { method: "POST" }).then(j<EnvBootstrap>),

  forecastBootstrap: () => f("/api/forecast/bootstrap").then(j<ForecastBootstrap>),
  forecast: (cities: string) =>
    f("/api/forecast/series?" + new URLSearchParams({ cities })).then(j<ForecastResponse>),
  forecastRefresh: () =>
    f("/api/forecast/refresh", { method: "POST" }).then(j<ForecastBootstrap>),

  // ── controls (CC) — thin proxy to the CyanControls RoomServer services ──
  controlInfo: () => f("/api/controls/info").then(j<ControlsInfo>),
  controlRoom: (topic: string, command: string, extra?: Record<string, unknown>) =>
    f(`/api/controls/room/${topic}`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ command, ...extra }),
    }).then(j<ControlsInfo>),
  controlFn: (name: string, body?: Record<string, unknown>) =>
    f(
      `/api/controls/fn/${name}`,
      body
        ? { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) }
        : { method: "POST" },
    ).then(j<ControlsInfo>),

  torrents: () => f("/api/torrents").then(j<Torrent[]>),
  torrentVideos: (hash: string) => f(`/api/torrents/${hash}/videos`).then(j<TorrentVideo[]>),

  // Every diary mutation replies with the full month snapshot for `month`.
  columns: () => f("/api/personal/columns").then(j<Column[]>),
  addColumn: (body: Partial<Column>, month: string) =>
    f(`/api/personal/columns?month=${month}`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) }).then(j<MonthData>),
  patchColumn: (key: string, body: Partial<Column>, month: string) =>
    f(`/api/personal/columns/${key}?month=${month}`, { method: "PATCH", headers: JSON_HEADERS, body: JSON.stringify(body) }).then(j<MonthData>),
  deleteColumn: (key: string, month: string) =>
    f(`/api/personal/columns/${key}?month=${month}`, { method: "DELETE" }).then(j<MonthData>),
  reorderColumns: (keys: string[], month: string) =>
    f(`/api/personal/columns/order?month=${month}`, { method: "PUT", headers: JSON_HEADERS, body: JSON.stringify({ keys }) }).then(j<MonthData>),

  units: () => f("/api/personal/units").then(j<string[]>),
  addUnit: (unit: string, month: string) =>
    f(`/api/personal/units?month=${month}`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ unit }) }).then(j<MonthData>),
  deleteUnit: (unit: string, month: string) =>
    f(`/api/personal/units?unit=${encodeURIComponent(unit)}&month=${month}`, { method: "DELETE" }).then(j<MonthData>),

  month: (month: string) => f(`/api/personal/entries?month=${month}`).then(j<MonthData>),
  putDay: (date: string, values: Record<string, unknown>) =>
    f(`/api/personal/entries/${date}`, { method: "PUT", headers: JSON_HEADERS, body: JSON.stringify({ values }) }).then(j<MonthData>),
};

/** Poll GET /api/version every second so the UI refetches on any DB change,
 *  including ones made from another client (e.g. the future Android app). */
export function useVersionPoll(intervalMs = 1000): Versions {
  const [v, setV] = useState<Versions>({ diary: 0, weather: 0, food: 0, forecast: 0 });
  const ref = useRef(v);
  ref.current = v;

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const next = await api.version();
        if (
          alive &&
          (next.diary !== ref.current.diary ||
            next.weather !== ref.current.weather ||
            next.food !== ref.current.food ||
            next.forecast !== ref.current.forecast)
        ) {
          setV(next);
        }
      } catch {
        /* server down / transient — keep last known */
      }
    };
    tick();
    const id = window.setInterval(tick, intervalMs);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [intervalMs]);

  return v;
}
