interface Props {
  tempC: number | null;
  width?: number;
  height?: number;
}

// Clamped display range -- not a hard physical limit, just what the bar maps
// its 0-100% fill onto.
const TEMP_MIN = -10;
const TEMP_MAX = 35;

// Color stops the fill interpolates between, keyed by temperature (°C).
// Plain RGB interpolation straight from cyan to orange crosses a muddy,
// desaturated patch around 15°C -- a yellow stop there keeps the ramp on a
// natural cyan -> green -> yellow -> orange hue path instead.
const TEMP_COLOR_STOPS: { t: number; rgb: [number, number, number] }[] = [
  { t: -10, rgb: [240, 248, 252] }, // white / very light blue
  { t: 0, rgb: [173, 216, 240] }, // very light blue
  { t: 10, rgb: [0, 210, 210] }, // cyan
  { t: 15, rgb: [255, 221, 51] }, // yellow (transition stop, see above)
  { t: 20, rgb: [245, 158, 11] }, // orange
  { t: 27.5, rgb: [239, 108, 100] }, // light red
  { t: 35, rgb: [211, 47, 47] }, // full red
];

function lerp(a: number, b: number, f: number): number {
  return a + (b - a) * f;
}

/** Interpolated fill color for a temperature, walking TEMP_COLOR_STOPS. */
export function tempColor(tempC: number): string {
  const t = Math.max(TEMP_MIN, Math.min(TEMP_MAX, tempC));
  for (let i = 0; i < TEMP_COLOR_STOPS.length - 1; i++) {
    const a = TEMP_COLOR_STOPS[i];
    const b = TEMP_COLOR_STOPS[i + 1];
    if (t <= b.t) {
      const f = (t - a.t) / (b.t - a.t);
      const r = Math.round(lerp(a.rgb[0], b.rgb[0], f));
      const g = Math.round(lerp(a.rgb[1], b.rgb[1], f));
      const bl = Math.round(lerp(a.rgb[2], b.rgb[2], f));
      return `rgb(${r}, ${g}, ${bl})`;
    }
  }
  const [r, g, b] = TEMP_COLOR_STOPS[TEMP_COLOR_STOPS.length - 1].rgb;
  return `rgb(${r}, ${g}, ${b})`;
}

/** Horizontal pill: fill length proportional to temperature within
 * [TEMP_MIN, TEMP_MAX], fill color running white/ice-blue -> light blue ->
 * cyan -> orange -> light red -> red as it warms up. Value in °C printed
 * next to it. */
export function TemperatureBar({ tempC, width = 46, height = 10 }: Props) {
  if (tempC == null) return <span className="muted">–</span>;
  const frac = Math.max(0, Math.min(1, (tempC - TEMP_MIN) / (TEMP_MAX - TEMP_MIN)));
  return (
    <span className="temp-bar">
      <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height}>
        <rect width={width} height={height} rx={height / 2} fill="#2a2f3a" />
        <rect width={width * frac} height={height} rx={height / 2} fill={tempColor(tempC)} />
      </svg>
      <span className="temp-bar-label">{Math.round(tempC)}°</span>
    </span>
  );
}
