import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";
import { api, City, EnvBootstrap, SeriesResponse, useVersionPoll, Variable } from "../api";
import { ForecastStrip } from "./ForecastStrip";
import { OverviewBoard } from "./OverviewBoard";
import { isKey, Key, plotSeparators, useT } from "../i18n";
import { useBackToClose } from "../backClose";
import { Icon } from "./icons";
import { ChartPager } from "./ChartPager";
import { StocksView } from "./StocksView";
import { MenuTab, TabMenu } from "./TabMenu";
import { usePhone } from "../narrow";

const Plot = createPlotlyComponent(Plotly);

const PRESETS: Record<string, number | null> = {
  "1W": 7,
  "1M": 30,
  "6M": 182,
  "1Y": 365,
  MAX: null,
};

// The server names its variables and groups in English; they are said again
// here by key, and one the dictionaries do not know yet keeps its own text.
const GROUP_KEYS: Record<string, Key> = {
  "🌡 Temperature & Humidity": "wg_temp",
  "☁ Cloudiness & Sun": "wg_cloud",
  "🌬 Pressure": "wg_pressure",
  "🌧 Precipitation": "wg_precip",
  "🌱 Soil Temperature": "wg_soil",
  "☀ Solar Radiation": "wg_solar",
  "💨 Wind": "wg_wind",
  "Other": "wg_other",
};
function localVariable(v: Variable, t: ReturnType<typeof useT>["t"], has: (k: string) => k is Key): Variable {
  const label = `wv_${v.key}`, about = `wvd_${v.key}`;
  return {
    ...v,
    label: has(label) ? t(label) : v.label,
    description: has(about) ? t(about) : v.description,
    group: v.group in GROUP_KEYS ? t(GROUP_KEYS[v.group]) : v.group,
  };
}

const RESAMPLE_KEYS: Record<string, Key> = { hourly: "env_hourly", daily: "env_daily", weekly: "env_weekly" };

function shiftDays(iso: string, days: number): string {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() - days);
  return d.toLocaleDateString("en-CA");
}

type Tab = "overview" | "forecast" | "historical" | "stocks";
const TABS: Tab[] = ["overview", "forecast", "historical", "stocks"];
const TAB_KEY = "environment.tab";
const CITIES_KEY = "environment.cities";

type OverviewRange = "today" | "tomorrow" | "in2days" | "week";
const OVERVIEW_RANGES: OverviewRange[] = ["today", "tomorrow", "in2days", "week"];
const OVERVIEW_CITY_KEY = "environment.overview.city";
const OVERVIEW_RANGE_KEY = "environment.overview.range";

function loadTab(): Tab {
  try {
    const raw = localStorage.getItem(TAB_KEY);
    if (raw && (TABS as string[]).includes(raw)) return raw as Tab;
  } catch {
    /* private mode / disabled storage */
  }
  return "overview";
}

function saveTab(t: Tab): void {
  try {
    localStorage.setItem(TAB_KEY, t);
  } catch {
    /* ignore */
  }
}

function loadCities(): Set<string> {
  try {
    const raw = localStorage.getItem(CITIES_KEY);
    if (raw !== null) return new Set(JSON.parse(raw) as string[]);
  } catch {
    /* private mode / disabled storage */
  }
  return new Set();
}

function saveCities(cities: Set<string>): void {
  try {
    localStorage.setItem(CITIES_KEY, JSON.stringify([...cities]));
  } catch {
    /* ignore */
  }
}

function loadOverviewCity(): string {
  try {
    return localStorage.getItem(OVERVIEW_CITY_KEY) ?? "";
  } catch {
    return "";
  }
}

function saveOverviewCity(key: string): void {
  try {
    localStorage.setItem(OVERVIEW_CITY_KEY, key);
  } catch {
    /* ignore */
  }
}

function loadOverviewRange(): OverviewRange {
  try {
    const raw = localStorage.getItem(OVERVIEW_RANGE_KEY);
    if (raw && (OVERVIEW_RANGES as string[]).includes(raw)) return raw as OverviewRange;
  } catch {
    /* private mode / disabled storage */
  }
  return "today";
}

function saveOverviewRange(r: OverviewRange): void {
  try {
    localStorage.setItem(OVERVIEW_RANGE_KEY, r);
  } catch {
    /* ignore */
  }
}

export function EnvironmentPanel() {
  const { t, lang } = useT();
  const { weather, forecast } = useVersionPoll("weather", "forecast");
  const [boot, setBoot] = useState<EnvBootstrap | null>(null);
  const [cities, setCities] = useState<Set<string>>(loadCities);
  const [vars, setVars] = useState<Set<string>>(new Set());
  const [preset, setPreset] = useState<string>("1Y");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [resample, setResample] = useState("daily");
  const [series, setSeries] = useState<SeriesResponse | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [seriesNonce, setSeriesNonce] = useState(0);
  const [tab, setTab] = useState<Tab>(loadTab);
  // In phone mode the controls column is hidden; the gear by the city opens
  // it over the whole screen instead.
  const [controlsOpen, setControlsOpen] = useState(false);
  // Where the Stocks tab draws its stock picker, in the tab row.
  const [pickerSlot, setPickerSlot] = useState<HTMLSpanElement | null>(null);
  const narrow = usePhone();
  useBackToClose(() => setControlsOpen(false), controlsOpen);
  const appliedWeather = useRef(0);

  const changeTab = (t: Tab) => {
    setTab(t);
    saveTab(t);
  };

  const changeCities = (updater: (prev: Set<string>) => Set<string>) => {
    setCities((prev) => {
      const next = updater(prev);
      saveCities(next);
      return next;
    });
  };

  const applyBoot = (b: EnvBootstrap) => {
    setBoot(b);
    appliedWeather.current = b.weather_version;
    setCities((prev) => {
      const next = prev.size
        ? new Set([...prev].filter((k) => b.cities.some((c) => c.key === k)))
        : new Set(b.cities.filter((c) => c.default).map((c) => c.key));
      saveCities(next);
      return next;
    });
    setVars((prev) =>
      prev.size ? prev : new Set(b.variables.filter((v) => v.default).map((v) => v.key)),
    );
    if (b.max_date) {
      if (preset && preset in PRESETS) {
        // Re-anchor the active preset to the (possibly new) data range so a
        // refresh actually shows the fetched changes.
        const days = PRESETS[preset];
        setEnd(b.max_date);
        setStart(days === null ? b.min_date ?? b.max_date : shiftDays(b.max_date, days));
      } else {
        setEnd((e) => e || b.max_date!);
        setStart((s) => s || shiftDays(b.max_date!, 365));
      }
    }
    setSeriesNonce((n) => n + 1);
  };

  const loadBoot = () => api.envBootstrap().then(applyBoot);

  useEffect(() => {
    loadBoot();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // Fires only for a weather refresh triggered elsewhere; our own refresh
  // already applied its reply and advanced appliedWeather.
  useEffect(() => {
    if (boot && weather !== appliedWeather.current) loadBoot();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [weather]);

  const applyPreset = (label: string) => {
    setPreset(label);
    if (!boot?.max_date) return;
    const days = PRESETS[label];
    setEnd(boot.max_date);
    setStart(days === null ? boot.min_date ?? boot.max_date : shiftDays(boot.max_date, days));
  };

  useEffect(() => {
    if (!start || !end || cities.size === 0 || vars.size === 0) {
      setSeries(null);
      return;
    }
    const ctrl = new AbortController();
    api
      .series({
        cities: [...cities].join(","),
        start,
        end,
        resample,
        vars: [...vars].join(","),
      })
      .then(setSeries)
      .catch(() => {});
    return () => ctrl.abort();
  }, [cities, vars, start, end, resample, seriesNonce]);

  const variables = useMemo(
    () => (boot?.variables ?? []).map((v) => localVariable(v, t, isKey)),
    [boot, t],
  );
  const groups = useMemo(() => {
    const g: Record<string, Variable[]> = {};
    for (const v of variables) {
      if (vars.has(v.key)) (g[v.group] ||= []).push(v);
    }
    return g;
  }, [variables, vars]);

  if (!boot) return <div className="panel"><p className="muted">{t("loading")}</p></div>;

  const envTabs: MenuTab<Tab>[] = [
    { key: "overview", icon: "🌤️", label: t("env_overview") },
    { key: "forecast", icon: "🌦️", label: t("env_forecast") },
    { key: "historical", icon: "🌡️", label: t("env_historical") },
    { key: "stocks", icon: "💹", label: t("env_stocks") },
  ];
  const cityByKey = Object.fromEntries(boot.cities.map((c) => [c.key, c])) as Record<string, City>;
  const chartData = (v: Variable) =>
    [...cities]
      .filter((ck) => Array.isArray(series!.series[ck]?.[v.key]))
      .map((ck) => ({
        x: series!.series[ck].index as string[],
        y: series!.series[ck][v.key] as (number | null)[],
        type: "scatter" as const,
        mode: "lines" as const,
        name: cityByKey[ck]?.city_name ?? ck,
        line: { width: 1.5, color: cityByKey[ck]?.color },
      }));
  const chartLayout = {
    height: 220,
    margin: { l: 44, r: 12, t: 32, b: 30 },
    separators: plotSeparators(),
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#bbb" },
    xaxis: { gridcolor: "#333" },
    yaxis: { gridcolor: "#333" },
    showlegend: true,
    legend: { orientation: "h" as const, x: 1, xanchor: "right" as const, y: 1.18 },
  };

  return (
    <div className="panel environment panel--column">
      <div className="env-tabs">
        {narrow ? (
          <TabMenu tabs={envTabs} value={tab} onChange={changeTab} />
        ) : envTabs.map((x) => (
          <button key={x.key} className={tab === x.key ? "active" : ""} onClick={() => changeTab(x.key)}>
            <span className="tm-icon" aria-hidden>{x.icon}</span>
            {x.label}
          </button>
        ))}
        {(tab === "stocks" || tab === "overview") && <span className="env-pickslot" ref={setPickerSlot} />}
        {(tab === "forecast" || tab === "historical") && (
          <CityPicker cities={boot.cities} selected={cities} onToggle={(key, on) =>
            changeCities((s) => {
              const n = new Set(s);
              on ? n.add(key) : n.delete(key);
              return n;
            })
          } />
        )}
        {tab === "historical" && (
          <button className="env-controls-btn" onClick={() => setControlsOpen(true)}
                  title={t("settings")} aria-label={t("settings")}>
            <Icon name="settings" size={20} className="" />
          </button>
        )}
      </div>

      <div className="env-tab-body">
      {tab === "overview" && <OverviewView cities={boot.cities} pickerSlot={pickerSlot} />}
      {tab === "stocks" && <StocksView pickerSlot={pickerSlot} />}

      {tab === "historical" && (
      <aside className={"env-controls" + (controlsOpen ? " env-controls--open" : "")}>
        <div className="env-controls-head">
          <span>{t("settings")}</span>
          <button className="env-controls-close" onClick={() => setControlsOpen(false)}
                  title={t("close")} aria-label={t("close")}>
            <Icon name="close" size={18} className="" />
          </button>
        </div>
        <section>
          <h3>{t("env_date_range")}</h3>
          <div className="presets">
            {Object.keys(PRESETS).map((label) => (
              <button
                key={label}
                className={preset === label ? "active" : ""}
                onClick={() => applyPreset(label)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="dates">
            <input
              type="date"
              value={start}
              min={boot.min_date ?? undefined}
              max={boot.max_date ?? undefined}
              onChange={(e) => {
                setPreset("");
                setStart(e.target.value);
              }}
            />
            <input
              type="date"
              value={end}
              min={boot.min_date ?? undefined}
              max={boot.max_date ?? undefined}
              onChange={(e) => {
                setPreset("");
                setEnd(e.target.value);
              }}
            />
          </div>
        </section>

        <section>
          <h3>{t("env_resample")}</h3>
          <select value={resample} onChange={(e) => setResample(e.target.value)}>
            <option value="hourly">{t("env_hourly")}</option>
            <option value="daily">{t("env_daily")}</option>
            <option value="weekly">{t("env_weekly")}</option>
          </select>
        </section>

        <section>
          <h3>{t("env_variables")}</h3>
          {Object.entries(groupBy(variables)).map(([group, list]) => (
            <details key={group} open>
              <summary>{group}</summary>
              {list.map((v) => (
                <label key={v.key} className="check" title={v.description}>
                  <input
                    type="checkbox"
                    checked={vars.has(v.key)}
                    onChange={(e) =>
                      setVars((s) => {
                        const n = new Set(s);
                        e.target.checked ? n.add(v.key) : n.delete(v.key);
                        return n;
                      })
                    }
                  />
                  {v.label}
                  {v.unit ? <span className="unit"> [{v.unit}]</span> : null}
                </label>
              ))}
            </details>
          ))}
        </section>

        <button className="refresh" disabled={refreshing} onClick={() => {
          setRefreshing(true);
          api.refresh().then(applyBoot).finally(() => setRefreshing(false));
        }}>
          {refreshing ? t("env_refreshing") : t("env_fetch_latest")}
        </button>
      </aside>
      )}

      {tab === "forecast" && (
        <div className="env-charts">
          <ForecastStrip allCities={boot.cities} selected={cities} forecastVersion={forecast} />
        </div>
      )}

      {tab === "historical" && (
        <div className="env-charts">
          <div className="env-title">
            <h1>
              {t("env_historical")} {shortDate(start, lang)} – {shortDate(end, lang)}
            </h1>
          </div>
          <p className="muted env-range">{t(RESAMPLE_KEYS[resample] ?? "env_hourly")}</p>

          {!series && <p className="muted">{t("env_pick")}</p>}
          {series && narrow && (
            <ChartPager
              charts={Object.values(groups).flat().map((v) => ({
                key: v.key,
                title: v.label + (v.unit ? ` [${v.unit}]` : ""),
                data: chartData(v),
                layout: chartLayout,
              }))}
            />
          )}
          {series && !narrow &&
            Object.entries(groups).map(([group, list]) => (
              <div key={group} className="chart-group">
                <h3>{group}</h3>
                {list.map((v) => (
                  <div key={v.key} className="chart-block">
                    <div className="chart-title">
                      {v.label}
                      {v.unit ? ` [${v.unit}]` : ""}
                    </div>
                    <Plot
                      data={chartData(v)}
                      layout={chartLayout}
                      config={{ displayModeBar: false }}
                      style={{ width: "100%" }}
                      useResizeHandler
                    />
                  </div>
                ))}
              </div>
            ))}
        </div>
      )}
      </div>
    </div>
  );
}

/** "2025-11-03" -> "03/11/25", in the UI's language. */
function shortDate(iso: string, lang: string): string {
  if (!iso) return "";
  return new Date(iso + "T00:00:00").toLocaleDateString(lang, { day: "2-digit", month: "2-digit", year: "2-digit" });
}

/** The cities shown (forecast and history): a button with their flags, and
 *  under it a small list to tick them on and off. A tap elsewhere or Back
 *  puts it away. `single` (the overview, one city): a pick replaces the
 *  city and closes the list. */
function CityPicker({ cities, selected, onToggle, single = false }: {
  cities: City[]; selected: Set<string>; onToggle: (key: string, on: boolean) => void; single?: boolean;
}) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useBackToClose(() => setOpen(false), open);
  useEffect(() => {
    if (!open) return;
    const down = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", down);
    return () => document.removeEventListener("pointerdown", down);
  }, [open]);
  const flags = cities.filter((c) => selected.has(c.key)).map((c) => c.flag).join(" ");
  return (
    <div className="env-citypick" ref={box}>
      <button className={open ? "active" : ""} onClick={() => setOpen(!open)}
              title={t("env_cities")} aria-label={t("env_cities")}>
        {flags || t("env_cities")} ▾
      </button>
      {open && (
        <div className="env-citypop">
          {cities.map((c) => (
            <label key={c.key} className="check">
              <input type={single ? "radio" : "checkbox"} checked={selected.has(c.key)}
                     onChange={(e) => { onToggle(c.key, e.target.checked); if (single) setOpen(false); }} />
              <span style={{ color: c.color }}>{c.flag} {c.city_name}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function groupBy(vars: Variable[]): Record<string, Variable[]> {
  const g: Record<string, Variable[]> = {};
  for (const v of vars) (g[v.group] ||= []).push(v);
  return g;
}

/** The Overview tab: the forecast board of one city, over a range, both
 *  remembered on this device. Also the Android shell's morning popup
 *  (WeatherPopup.tsx). */
export function OverviewView({ cities, pickerSlot = null }: { cities: City[]; pickerSlot?: HTMLElement | null }) {
  const { t } = useT();
  const { forecast } = useVersionPoll("forecast");
  const [saved, setCity] = useState<string>(loadOverviewCity);
  const [range, setRange] = useState<OverviewRange>(loadOverviewRange);
  // The remembered city, while there is one by that name; else the default.
  const city = cities.some((c) => c.key === saved) ? saved
    : (cities.find((c) => c.default) ?? cities[0])?.key ?? "";
  const changeCity = (key: string) => {
    setCity(key);
    saveOverviewCity(key);
  };
  const changeRange = (r: OverviewRange) => {
    setRange(r);
    saveOverviewRange(r);
  };
  return (
    <div className="env-charts env-charts--fit">
      {/* In the panel the city is the tab row's button, as on Forecast; the
          Android popup has no tab row and keeps a plain select. */}
      {pickerSlot && createPortal(
        <CityPicker cities={cities} selected={new Set([city])} single onToggle={(key) => changeCity(key)} />,
        pickerSlot)}
      <div className="overview-toolbar">
        {!pickerSlot && <select
          value={city}
          onChange={(e) => changeCity(e.target.value)}
        >
          {cities.map((c) => (
            <option key={c.key} value={c.key}>
              {c.flag} {c.city_name}
            </option>
          ))}
        </select>}
        <div className="presets">
          <button
            className={range === "today" ? "active" : ""}
            onClick={() => changeRange("today")}
          >
            {t("env_today")}
          </button>
          <button
            className={range === "tomorrow" ? "active" : ""}
            onClick={() => changeRange("tomorrow")}
          >
            {t("env_tomorrow")}
          </button>
          <button
            className={range === "in2days" ? "active" : ""}
            onClick={() => changeRange("in2days")}
          >
            {t("env_in_2_days")}
          </button>
          <button
            className={range === "week" ? "active" : ""}
            onClick={() => changeRange("week")}
          >
            {t("env_2_weeks")}
          </button>
        </div>
      </div>
      <OverviewBoard city={city} range={range} forecastVersion={forecast} />
    </div>
  );
}
