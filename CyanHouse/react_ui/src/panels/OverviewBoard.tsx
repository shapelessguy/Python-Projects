import { useEffect, useState } from "react";
import { api, OverviewResponse, OverviewSegment } from "../api";
import { HumidityGauge } from "./HumidityGauge";
import { SegmentIcon } from "./SegmentIcon";
import { TemperatureBar } from "./TemperatureBar";
import { WindIcon } from "./WindIcon";

interface Props {
  city: string;
  range: "today" | "week";
  forecastVersion: number;
}

const hh = (iso: string) => iso.slice(11, 13); // always on the hour, ":00" adds nothing
const dayShortLabel = (iso: string) => {
  const d = new Date(iso);
  return `${d.toLocaleDateString(undefined, { weekday: "short" })} ${d.getDate()}`;
};

// "today": each day cut into 4 six-hour parts (3 of the 2h segments apiece).
const DAY_PARTS = ["Early morning", "Morning", "Afternoon", "Night"];
const partOf = (iso: string) => Math.min(3, Math.floor(Number(iso.slice(11, 13)) / 6));

// Every row -- data or header -- uses this same 6-column grid (see .ov-row),
// so column edges line up across rows regardless of how wide any one row's
// content happens to be.
function SegmentRow({ s, timeLabel }: { s: OverviewSegment; timeLabel: string }) {
  return (
    <div className="ov-row">
      <span className="ov-time">{timeLabel}</span>
      <SegmentIcon
        solarLight={s.solar_light}
        cloudCoverPct={s.cloud_cover_pct}
        rainLevel={s.rain_level}
        precipProb={s.precip_prob}
      />
      <TemperatureBar tempC={s.temperature_c} />
      <HumidityGauge humidityPct={s.humidity_pct} />
      <WindIcon windSpeedKmh={s.wind_speed_kmh} windLevel={s.wind_level} />
      <span className="ov-numbers">
        <span>{Math.round(s.solar_light * 100)}%</span>
        <span>{s.cloud_cover_pct ?? "–"}%</span>
        <span>{s.precip_prob ?? "–"}%</span>
        <span>
          {s.precip_mm} mm (L{s.rain_level})
        </span>
        <span>{s.temperature_c ?? "–"}°</span>
        <span>{s.humidity_pct ?? "–"}%</span>
        <span>
          {s.wind_speed_kmh ?? "–"} km/h (L{s.wind_level})
        </span>
      </span>
    </div>
  );
}

/** Column titles for the numbers -- same grid as SegmentRow, first 5 cells
 * left blank so the numbers cell lands in the same grid column. */
function HeaderRow() {
  return (
    <div className="ov-row ov-header-row">
      <span />
      <span />
      <span />
      <span />
      <span />
      <span className="ov-numbers ov-numbers-head">
        <span>Solar</span>
        <span>Cloud</span>
        <span>Rain %</span>
        <span>Rain</span>
        <span>Temp</span>
        <span>Humidity</span>
        <span>Wind</span>
      </span>
    </div>
  );
}

/** Overview board over /api/forecast/overview -- a first look at the derived
 * attributes (solar light, rain/wind levels, ...) before they get a fully
 * polished rendering. Icons always show; the raw numbers behind them (plus
 * the header naming them) are a reference and hide below 900px (see
 * .ov-numbers / .ov-header-row).
 *
 * "today" is 12 rows of 2h detail grouped into 4 day parts; "week" is one
 * row per day (already a daily average from the API), so it renders as a
 * flat list with no day-part grouping. Both fill the panel's exact height
 * (see the flex/grid chain in .ov-board / .ov-part / .ov-rows / .ov-row)
 * rather than scrolling. */
export function OverviewBoard({ city, range, forecastVersion }: Props) {
  const [data, setData] = useState<OverviewResponse | null>(null);

  useEffect(() => {
    if (!city) {
      setData(null);
      return;
    }
    let alive = true;
    api
      .forecastOverview(city, range)
      .then((d) => alive && setData(d))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [city, range, forecastVersion]);

  if (!city) return <p className="muted">Pick a city above.</p>;
  if (!data) return <p className="muted">Loading…</p>;
  if (!data.segments.length) return <p className="muted">No forecast data yet.</p>;

  if (range === "week") {
    return (
      <div className="ov-board">
        <HeaderRow />
        <div className="ov-rows">
          {data.segments.map((s) => (
            <SegmentRow key={s.start} s={s} timeLabel={dayShortLabel(s.start)} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="ov-board">
      {/* Indented by ov-part-label's fixed width so it lines up with the
          per-part rows below, which are indented by the real label. */}
      <div className="ov-header">
        <span className="ov-header-spacer" />
        <HeaderRow />
      </div>
      {DAY_PARTS.map((label, partIdx) => {
        const partSegs = data.segments.filter((s) => partOf(s.start) === partIdx);
        if (!partSegs.length) return null;
        return (
          <div key={label} className="ov-part">
            <span className="ov-part-label">{label}</span>
            <div className="ov-rows">
              {partSegs.map((s) => (
                <SegmentRow key={s.start} s={s} timeLabel={`${hh(s.start)}–${hh(s.end)}`} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
