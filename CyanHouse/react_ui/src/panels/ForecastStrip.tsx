import { useEffect, useMemo, useState } from "react";
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";
import { api, City, ForecastResponse } from "../api";

const Plot = createPlotlyComponent(Plotly);

const WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** "2026-09-13T14:00:00" -> local Date (no trailing Z => parsed as local). */
const asDate = (iso: string) => new Date(iso);
const dayOf = (iso: string) => iso.slice(0, 10); // YYYY-MM-DD, no tz math
const hourOf = (iso: string) => iso.slice(11, 16); // HH:MM
const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(n, hi));

function pillLabel(dayIdx: number, isoForDay: string): string {
  if (dayIdx === 0) return "Today";
  if (dayIdx === 1) return "Tomorrow";
  return WEEKDAY[asDate(isoForDay).getDay()];
}

function dayLabel(dayIdx: number, isoForDay: string): string {
  const d = asDate(isoForDay);
  const wd = `${WEEKDAY[d.getDay()]} ${d.getDate()}/${d.getMonth() + 1}`;
  if (dayIdx === 0) return `Today · ${wd}`;
  if (dayIdx === 1) return `Tomorrow · ${wd}`;
  return `${wd} · +${dayIdx}d`;
}

function minutesAgo(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.now() - new Date(iso).getTime();
  return ms >= 0 ? Math.round(ms / 60000) : null;
}

interface Props {
  allCities: City[];
  selected: Set<string>;
  forecastVersion: number;
}

export function ForecastStrip({ allCities, selected, forecastVersion }: Props) {
  const [data, setData] = useState<ForecastResponse | null>(null);
  const [selectedDay, setSelectedDay] = useState(0);
  const [busy, setBusy] = useState(false);

  const cityByKey = useMemo(
    () => Object.fromEntries(allCities.map((c) => [c.key, c])) as Record<string, City>,
    [allCities],
  );
  const keys = useMemo(
    () => allCities.filter((c) => selected.has(c.key)).map((c) => c.key),
    [allCities, selected],
  );
  const keyCsv = keys.join(",");

  useEffect(() => {
    if (!keyCsv) {
      setData(null);
      return;
    }
    let alive = true;
    api
      .forecast(keyCsv)
      .then((d) => alive && setData(d))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [keyCsv, forecastVersion]);

  // Only the selected cities the current response actually covers. While a newly
  // added city is still loading, `data` holds the previous set — never index it
  // with a key it doesn't have.
  const ready = useMemo(
    () => keys.filter((k) => data?.series[k]),
    [keys, data],
  );

  // Day list is common to every city (same Open-Meteo horizon); take the first.
  const dayList = useMemo(() => {
    const first = ready.length ? data!.series[ready[0]] : null;
    if (!first) return [] as string[];
    const seen = new Set<string>();
    const days: string[] = [];
    for (const iso of first.index) {
      const d = dayOf(iso);
      if (!seen.has(d)) {
        seen.add(d);
        days.push(iso); // representative timestamp for that day
      }
    }
    return days;
  }, [data, ready]);

  const maxDay = dayList.length - 1;

  if (!keys.length)
    return (
      <section className="forecast-strip">
        <h3>🌧 Precipitation forecast</h3>
        <p className="muted">Select a city (left) to see its forecast.</p>
      </section>
    );

  if (!ready.length || maxDay < 0)
    return (
      <section className="forecast-strip">
        <h3>🌧 Precipitation forecast</h3>
        <p className="muted">
          {data ? "Loading forecast…" : "Forecast not cached yet."}{" "}
          <button
            className="link"
            disabled={busy}
            onClick={() => {
              setBusy(true);
              api.forecastRefresh().finally(() => setBusy(false));
            }}
          >
            {busy ? "Fetching…" : "Fetch now"}
          </button>
        </p>
      </section>
    );

  const day = clamp(selectedDay, 0, maxDay);
  const dayKey = dayOf(dayList[day]);
  const focusCity = cityByKey[ready[0]];

  // ── per-city slice for the selected day ─────────────────────────────────
  const sliced = ready.map((k) => {
    const s = data!.series[k];
    const idx: number[] = [];
    s.index.forEach((iso, i) => {
      if (dayOf(iso) === dayKey) idx.push(i);
    });
    return {
      key: k,
      city: cityByKey[k],
      hours: idx.map((i) => hourOf(s.index[i])),
      mm: idx.map((i) => s.precip_mm[i]),
      prob: idx.map((i) => s.precip_prob[i]),
      sources: idx.map((i) => s.source[i]),
    };
  });

  // ── headline for the focus city ────────────────────────────────────────
  const fSlice = sliced[0];
  const totalMm = fSlice.mm.reduce<number>((a, x) => a + (x ?? 0), 0);
  let peakProb = -1;
  let peakHour = "";
  fSlice.prob.forEach((p, i) => {
    if (p != null && p > peakProb) {
      peakProb = p;
      peakHour = fSlice.hours[i];
    }
  });
  const srcSet = new Set(fSlice.sources);
  const srcBadge =
    srcSet.size > 1 ? "DWD → Open-Meteo" : srcSet.has("dwd") ? "DWD (MOSMIX)" : "Open-Meteo";

  const anyDwd = ready.some((k) => data!.series[k].source.includes("dwd"));
  const mins = minutesAgo(data!.issued_at[ready[0]]);
  const stale = mins != null && mins > 90;
  const issuedText =
    mins == null ? "" : mins < 90 ? `issued ${mins} min ago` : `updated ${Math.round(mins / 60)} h ago`;

  const headline = totalMm >= 0.05 ? `${totalMm.toFixed(1)} mm expected` : "Dry";
  const peakText = peakProb >= 0 ? ` · peak ${Math.round(peakProb)}% at ${peakHour}` : "";

  const baseLayout = {
    height: 190,
    margin: { l: 44, r: 12, t: 24, b: 28 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#bbb", size: 11 },
    xaxis: { gridcolor: "#333", type: "category" as const },
    yaxis: { gridcolor: "#333" },
    showlegend: ready.length > 1,
    legend: { orientation: "h" as const, y: 1.35 },
    bargap: 0.15,
  };

  return (
    <section className="forecast-strip">
      <div className="fc-head">
        <h3>🌧 Precipitation forecast</h3>
        <span className="muted small">
          {focusCity?.flag} {focusCity?.city_name} · {srcBadge}
          {issuedText && (
            <>
              {" · "}
              <span className={stale ? "fc-stale" : ""}>{issuedText}</span>
            </>
          )}
          <button
            className="link"
            disabled={busy}
            style={{ marginLeft: 8 }}
            onClick={() => {
              setBusy(true);
              api.forecastRefresh().finally(() => setBusy(false));
            }}
          >
            {busy ? "↻" : "↻ refresh"}
          </button>
        </span>
      </div>

      <div className="fc-days">
        <div className="fc-pills">
          {[0, 1, 2]
            .filter((i) => i <= maxDay)
            .map((i) => (
              <button
                key={i}
                className={day === i ? "active" : ""}
                onClick={() => setSelectedDay(i)}
              >
                {pillLabel(i, dayList[i])}
              </button>
            ))}
        </div>
        <div className="fc-track">
          <input
            type="range"
            min={0}
            max={maxDay}
            step={1}
            value={day}
            onChange={(e) => setSelectedDay(+e.target.value)}
          />
          <div className="fc-ticks">
            <span>Today</span>
            <span>+{maxDay}d</span>
          </div>
        </div>
        <strong className="fc-daylabel">{dayLabel(day, dayList[day])}</strong>
      </div>

      <p className="fc-headline">
        {headline}
        {peakText}
      </p>

      <Plot
        data={sliced.map((s) => ({
          x: s.hours,
          y: s.mm,
          type: "bar" as const,
          name: s.city?.city_name ?? s.key,
          marker: { color: s.city?.color },
        }))}
        layout={{ ...baseLayout, title: { text: "Precipitation [mm/h]", font: { size: 12 } } }}
        config={{ displayModeBar: false }}
        style={{ width: "100%" }}
        useResizeHandler
      />
      <Plot
        data={sliced.map((s) => ({
          x: s.hours,
          y: s.prob,
          type: "scatter" as const,
          mode: "lines" as const,
          name: s.city?.city_name ?? s.key,
          line: { width: 1.5, color: s.city?.color },
          fill: ready.length === 1 ? ("tozeroy" as const) : ("none" as const),
          fillcolor: "rgba(76,155,232,0.15)",
        }))}
        layout={{
          ...baseLayout,
          title: { text: "Probability of precipitation [%]", font: { size: 12 } },
          yaxis: { ...baseLayout.yaxis, range: [0, 100] },
        }}
        config={{ displayModeBar: false }}
        style={{ width: "100%" }}
        useResizeHandler
      />

      {anyDwd && (
        <p className="muted small">
          German cities: DWD (MOSMIX) for the first 72 h, Open-Meteo beyond. Other cities:
          Open-Meteo (multi-model blend).
        </p>
      )}
    </section>
  );
}
