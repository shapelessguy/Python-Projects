import { useEffect, useMemo, useRef, useState } from "react";
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";
import { api, City, EnvBootstrap, SeriesResponse, useVersionPoll, Variable } from "../api";
import { ForecastStrip } from "./ForecastStrip";
import { OverviewBoard } from "./OverviewBoard";

const Plot = createPlotlyComponent(Plotly);

const PRESETS: Record<string, number | null> = {
  "1W": 7,
  "1M": 30,
  "6M": 182,
  "1Y": 365,
  MAX: null,
};

function shiftDays(iso: string, days: number): string {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() - days);
  return d.toLocaleDateString("en-CA");
}

type Tab = "overview" | "forecast" | "historical";
const TABS: Tab[] = ["overview", "forecast", "historical"];
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
  const { weather, forecast } = useVersionPoll();
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
  const [overviewCity, setOverviewCity] = useState<string>(loadOverviewCity);
  const [overviewRange, setOverviewRange] = useState<OverviewRange>(loadOverviewRange);
  const appliedWeather = useRef(0);

  const changeTab = (t: Tab) => {
    setTab(t);
    saveTab(t);
  };

  const changeOverviewCity = (key: string) => {
    setOverviewCity(key);
    saveOverviewCity(key);
  };

  const changeOverviewRange = (r: OverviewRange) => {
    setOverviewRange(r);
    saveOverviewRange(r);
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
    setOverviewCity((prev) => {
      if (prev && b.cities.some((c) => c.key === prev)) return prev;
      const next = (b.cities.find((c) => c.default) ?? b.cities[0])?.key ?? "";
      saveOverviewCity(next);
      return next;
    });
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

  const groups = useMemo(() => {
    const g: Record<string, Variable[]> = {};
    for (const v of boot?.variables ?? []) {
      if (vars.has(v.key)) (g[v.group] ||= []).push(v);
    }
    return g;
  }, [boot, vars]);

  if (!boot) return <div className="panel"><p className="muted">Loading…</p></div>;

  const cityByKey = Object.fromEntries(boot.cities.map((c) => [c.key, c])) as Record<string, City>;

  return (
    <div className="panel environment panel--column">
      <div className="env-tabs">
        <button className={tab === "overview" ? "active" : ""} onClick={() => changeTab("overview")}>
          Overview
        </button>
        <button className={tab === "forecast" ? "active" : ""} onClick={() => changeTab("forecast")}>
          Forecast
        </button>
        <button className={tab === "historical" ? "active" : ""} onClick={() => changeTab("historical")}>
          Historical
        </button>
      </div>

      <div className="env-tab-body">
      {tab === "overview" && (
        <div className="env-charts env-charts--fit">
          <div className="overview-toolbar">
            <select
              value={overviewCity}
              onChange={(e) => changeOverviewCity(e.target.value)}
            >
              {boot.cities.map((c) => (
                <option key={c.key} value={c.key}>
                  {c.flag} {c.city_name}
                </option>
              ))}
            </select>
            <div className="presets">
              <button
                className={overviewRange === "today" ? "active" : ""}
                onClick={() => changeOverviewRange("today")}
              >
                Today
              </button>
              <button
                className={overviewRange === "tomorrow" ? "active" : ""}
                onClick={() => changeOverviewRange("tomorrow")}
              >
                Tomorrow
              </button>
              <button
                className={overviewRange === "in2days" ? "active" : ""}
                onClick={() => changeOverviewRange("in2days")}
              >
                In 2 days
              </button>
              <button
                className={overviewRange === "week" ? "active" : ""}
                onClick={() => changeOverviewRange("week")}
              >
                2 weeks
              </button>
            </div>
          </div>
          <OverviewBoard city={overviewCity} range={overviewRange} forecastVersion={forecast} />
        </div>
      )}

      {tab === "historical" && (
      <aside className="env-controls">
        <section>
          <h3>Cities</h3>
          {boot.cities.map((c) => (
            <label key={c.key} className="check">
              <input
                type="checkbox"
                checked={cities.has(c.key)}
                onChange={(e) =>
                  changeCities((s) => {
                    const n = new Set(s);
                    e.target.checked ? n.add(c.key) : n.delete(c.key);
                    return n;
                  })
                }
              />
              <span style={{ color: c.color }}>{c.flag} {c.city_name}</span>
            </label>
          ))}
        </section>

        <section>
          <h3>Date range</h3>
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
          <h3>Resample</h3>
          <select value={resample} onChange={(e) => setResample(e.target.value)}>
            <option value="hourly">Hourly (raw)</option>
            <option value="daily">Daily mean</option>
            <option value="weekly">Weekly mean</option>
          </select>
        </section>

        <section>
          <h3>Variables</h3>
          {Object.entries(groupBy(boot.variables)).map(([group, list]) => (
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
          {refreshing ? "Refreshing…" : "↻ Fetch latest weather"}
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
          <h1>
            {[...cities].map((k) => cityByKey[k]?.flag + " " + cityByKey[k]?.city_name).join(" · ")}
          </h1>
          <p className="muted">{start} → {end} · {resample}</p>

          {!series && <p className="muted">Pick at least one city and variable.</p>}
          {series &&
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
                      data={[...cities]
                        .filter((ck) => Array.isArray(series.series[ck]?.[v.key]))
                        .map((ck) => ({
                          x: series.series[ck].index as string[],
                          y: series.series[ck][v.key] as (number | null)[],
                          type: "scatter",
                          mode: "lines",
                          name: cityByKey[ck]?.city_name ?? ck,
                          line: { width: 1.5, color: cityByKey[ck]?.color },
                        }))}
                      layout={{
                        height: 220,
                        margin: { l: 44, r: 12, t: 32, b: 30 },
                        paper_bgcolor: "rgba(0,0,0,0)",
                        plot_bgcolor: "rgba(0,0,0,0)",
                        font: { color: "#bbb" },
                        xaxis: { gridcolor: "#333" },
                        yaxis: { gridcolor: "#333" },
                        showlegend: true,
                        legend: { orientation: "h", x: 1, xanchor: "right", y: 1.18 },
                      }}
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

function groupBy(vars: Variable[]): Record<string, Variable[]> {
  const g: Record<string, Variable[]> = {};
  for (const v of vars) (g[v.group] ||= []).push(v);
  return g;
}
