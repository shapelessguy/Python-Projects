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
  calendar: number;
}

// null = every panel (the default, unrestricted); otherwise the explicit
// allowed set. The corresponding APIs are 403'd server-side regardless of
// whether the frontend respects this -- see api/auth.py's require_panel.
export interface Me {
  username: string;
  visible_panels: string[] | null;
}

export type RecurFreq = "daily" | "weekly" | "monthly" | "yearly";

export interface Calendar {
  id: number;
  name: string;
  color: string;
  shared: boolean;
}

export interface CalendarEvent {
  id: number;
  owner: string;
  mine: boolean;
  calendar_id: number;
  calendar_name: string;
  calendar_color: string;
  calendar_shared: boolean;
  title: string;
  description: string;
  start_date: string;
  end_date: string;
  all_day: boolean;
  start_time: string | null;
  end_time: string | null;
  recur_freq: RecurFreq | null;
  recur_interval: number;
  recur_until: string | null;
  recurring: boolean;
  alarm: boolean;
  // "" (not acknowledged); else "true" for a plain event or a YYYY-MM-DD
  // date -- the last occurrence acknowledged -- for a recurring one. See
  // alarms.ts for how this decides whether an alarm is currently due.
  alarm_ack: string | null;
  // Set together, cleared together: while alarm_snooze_until (epoch ms) is
  // still in the future AND alarm_snooze_occurrence still matches whichever
  // occurrence is currently due, the alarm stays hidden without being
  // permanently acknowledged. Synced through the backend (not a cookie) so
  // snoozing/closing from one client is reflected on every other.
  alarm_snooze_occurrence: string | null;
  alarm_snooze_until: number | null;
}

export interface MonthEvents {
  month: string;
  events: CalendarEvent[];
  calendar_version: number;
}

export interface EventInput {
  title: string;
  description?: string;
  start_date: string;
  end_date: string;
  all_day?: boolean;
  start_time?: string | null;
  end_time?: string | null;
  calendar_id: number;
  recur_freq?: RecurFreq | null;
  recur_interval?: number;
  recur_until?: string | null;
  alarm?: boolean;
  alarm_ack?: string | null;
  // Patch-only in practice (see alarms.ts) -- a freshly created event has
  // nothing to snooze yet.
  alarm_snooze_occurrence?: string | null;
  alarm_snooze_until?: number | null;
}

export const api = {
  version: () => f("/api/version").then(j<Versions>),
  me: () => f("/api/me").then(j<Me>),

  envBootstrap: () => f("/api/environment/bootstrap").then(j<EnvBootstrap>),
  series: (q: Record<string, string>) =>
    f("/api/environment/series?" + new URLSearchParams(q)).then(j<SeriesResponse>),
  refresh: () => f("/api/environment/refresh", { method: "POST" }).then(j<EnvBootstrap>),

  forecastBootstrap: () => f("/api/forecast/bootstrap").then(j<ForecastBootstrap>),
  forecast: (cities: string) =>
    f("/api/forecast/series?" + new URLSearchParams({ cities })).then(j<ForecastResponse>),
  forecastRefresh: () =>
    f("/api/forecast/refresh", { method: "POST" }).then(j<ForecastBootstrap>),

  calendars: () => f("/api/calendar/calendars").then(j<Calendar[]>),
  createCalendar: (name: string, color?: string) =>
    f("/api/calendar/calendars", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ name, color }) }).then(j<Calendar[]>),
  patchCalendar: (id: number, body: { name?: string; color?: string }) =>
    f(`/api/calendar/calendars/${id}`, { method: "PATCH", headers: JSON_HEADERS, body: JSON.stringify(body) }).then(j<Calendar[]>),
  deleteCalendar: (id: number) =>
    f(`/api/calendar/calendars/${id}`, { method: "DELETE" }).then(j<Calendar[]>),

  // Every calendar mutation replies with the full month snapshot for the
  // affected event's month (create/patch: its date; delete: its old date).
  calendarMonth: (month: string) =>
    f("/api/calendar/events?" + new URLSearchParams({ month })).then(j<MonthEvents>),
  createEvent: (body: EventInput) =>
    f("/api/calendar/events", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) }).then(j<MonthEvents>),
  patchEvent: (id: number, body: Partial<EventInput>) =>
    f(`/api/calendar/events/${id}`, { method: "PATCH", headers: JSON_HEADERS, body: JSON.stringify(body) }).then(j<MonthEvents>),
  // `occurrence` ("delete this event", only meaningful for a recurring
  // series) suppresses just that one date; omitted, it deletes the series.
  deleteEvent: (id: number, occurrence?: string) =>
    f(
      `/api/calendar/events/${id}` + (occurrence ? "?" + new URLSearchParams({ occurrence }) : ""),
      { method: "DELETE" },
    ).then(j<MonthEvents>),

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
  const [v, setV] = useState<Versions>({ diary: 0, weather: 0, food: 0, forecast: 0, calendar: 0 });
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
            next.forecast !== ref.current.forecast ||
            next.calendar !== ref.current.calendar)
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

/** One-shot fetch (not polled -- permissions are static for the life of a
 *  session, only changing via a backend restart): what the current user is
 *  allowed to see, fetched once at app start so panels can be hidden and
 *  their APIs never called in the first place, rather than every panel
 *  discovering it's restricted from its own first request 403ing. `loaded`
 *  is false until that first reply lands (or fails); callers should hold
 *  off rendering/mounting any panel content until then, since `visible` is
 *  meaningless -- neither "restricted" nor "unrestricted" -- before that. */
export function useVisibility(): { visible: string[] | null; loaded: boolean } {
  const [visible, setVisible] = useState<string[] | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const attempt = () => {
      api.me()
        .then((me) => {
          if (!alive) return;
          setVisible(me.visible_panels);
          setLoaded(true);
        })
        .catch(() => {
          // Transient (server not up yet, brief network blip) -- retry
          // rather than leaving the app stuck on its loading state forever.
          if (alive) timer = window.setTimeout(attempt, 2000);
        });
    };
    attempt();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, []);

  return { visible, loaded };
}
