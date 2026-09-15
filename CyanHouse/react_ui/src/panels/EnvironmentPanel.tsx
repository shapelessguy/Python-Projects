import { useEffect, useMemo, useRef, useState } from "react";
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";
import { api, City, EnvBootstrap, SeriesResponse, useVersionPoll, Variable } from "../api";
import { ForecastStrip } from "./ForecastStrip";

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

export function EnvironmentPanel() {
  const { weather, forecast } = useVersionPoll();
  const [boot, setBoot] = useState<EnvBootstrap | null>(null);
  const [cities, setCities] = useState<Set<string>>(new Set());
  const [vars, setVars] = useState<Set<string>>(new Set());
  const [preset, setPreset] = useState<string>("1Y");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [resample, setResample] = useState("daily");
  const [series, setSeries] = useState<SeriesResponse | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [seriesNonce, setSeriesNonce] = useState(0);
  const appliedWeather = useRef(0);

  const applyBoot = (b: EnvBootstrap) => {
    setBoot(b);
    appliedWeather.current = b.weather_version;
    setCities((prev) =>
      prev.size ? prev : new Set(b.cities.filter((c) => c.default).map((c) => c.key)),
    );
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
    <div className="panel environment">
      <aside className="env-controls">
        <section>
          <h3>Cities</h3>
          {boot.cities.map((c) => (
            <label key={c.key} className="check">
              <input
                type="checkbox"
                checked={cities.has(c.key)}
                onChange={(e) =>
                  setCities((s) => {
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

      <div className="env-charts">
        <h1>
          {[...cities].map((k) => cityByKey[k]?.flag + " " + cityByKey[k]?.city_name).join(" · ")}
        </h1>
        <p className="muted">{start} → {end} · {resample}</p>

        <ForecastStrip allCities={boot.cities} selected={cities} forecastVersion={forecast} />

        {!series && <p className="muted">Pick at least one city and variable.</p>}
        {series &&
          Object.entries(groups).map(([group, list]) => (
            <div key={group} className="chart-group">
              <h3>{group}</h3>
              {list.map((v) => (
                <Plot
                  key={v.key}
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
                    margin: { l: 44, r: 12, t: 26, b: 30 },
                    title: { text: `${v.label}${v.unit ? ` [${v.unit}]` : ""}`, font: { size: 12 } },
                    paper_bgcolor: "rgba(0,0,0,0)",
                    plot_bgcolor: "rgba(0,0,0,0)",
                    font: { color: "#bbb" },
                    xaxis: { gridcolor: "#333" },
                    yaxis: { gridcolor: "#333" },
                    showlegend: true,
                    legend: { orientation: "h", y: 1.3 },
                  }}
                  config={{ displayModeBar: false }}
                  style={{ width: "100%" }}
                  useResizeHandler
                />
              ))}
            </div>
          ))}
      </div>
    </div>
  );
}

function groupBy(vars: Variable[]): Record<string, Variable[]> {
  const g: Record<string, Variable[]> = {};
  for (const v of vars) (g[v.group] ||= []).push(v);
  return g;
}
