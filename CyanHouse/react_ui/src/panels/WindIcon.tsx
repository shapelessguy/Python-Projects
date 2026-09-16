interface Props {
  windSpeedKmh: number | null;
  windLevel: number; // 0-5
  size?: number;
}

const CENTER_Y = 16;
const ROW_SPACING = 5;
const TOP_LEN = 28;
const LEN_STEP = 4;

/** Wavy line, longer ones bow more -- matches the hand-authored curves this
 * replaced (fixed shape family, just parameterized by length so the count
 * can vary without hardcoding one path per row). */
function windCurve(y: number, len: number): string {
  const mid = len / 2;
  const x0 = 2;
  return `M${x0} ${y} Q${x0 + mid * 0.5} ${y - 4} ${x0 + mid} ${y} T${x0 + len} ${y}`;
}

/** wind_level picks how many curves are drawn (0-5), not their opacity --
 * calm shows nothing, a gale shows all five. Whatever subset is shown is
 * re-centered vertically around the icon's middle, so a low count doesn't
 * end up pinned to the top of the fixed-size canvas. */
export function WindIcon({ windSpeedKmh, windLevel, size = 32 }: Props) {
  const count = Math.max(0, Math.min(5, windLevel));
  const yStart = CENTER_Y - ((count - 1) * ROW_SPACING) / 2;
  const curves = Array.from({ length: count }, (_, i) =>
    windCurve(yStart + i * ROW_SPACING, TOP_LEN - i * LEN_STEP),
  );

  return (
    <span className="wind-icon">
      <svg viewBox="0 0 32 32" width={size} height={size}>
        <g fill="none" stroke="#9fb4c7" strokeLinecap="round" strokeWidth="2">
          {curves.map((d, i) => (
            <path key={i} d={d} />
          ))}
        </g>
      </svg>
      <span className="wind-icon-label">{windSpeedKmh ?? "–"} km/h</span>
    </span>
  );
}
