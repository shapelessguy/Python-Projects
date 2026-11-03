import { useId } from "react";

interface Props {
  humidityPct: number | null;
  width?: number;
  height?: number;
}

/** How full the humidity drop is, 0..1: empty at 30% or less, half at 70%,
 * full at 90% or more -- the quadratic through those three points, so the
 * humid end, where differences matter, gets most of the drop. Same as
 * humidityFill in the Android OverviewBoard.kt. */
export function humidityFill(pct: number): number {
  if (pct <= 30) return 0; // the parabola rises again below 10%
  return Math.min(1, ((pct - 30) * (pct - 10)) / 4800);
}

/** Water drop, filled bottom-up by humidityFill, with the value printed
 * next to it. */
export function HumidityGauge({ humidityPct, width = 16, height = 24 }: Props) {
  // One clip path per gauge (a board shows many); useId's colons kept out of url(#...).
  const clipId = `humidity-drop${useId().replace(/:/g, "")}`;
  if (humidityPct == null) return <span className="muted">–</span>;
  const pct = Math.max(0, Math.min(100, humidityPct));
  const pad = 1;
  // A round bottom (circle as wide as the box) tapering to a point at the top.
  const r = width / 2 - pad;
  const cx = width / 2;
  const cy = height - pad - r;
  const tip = pad;
  const bend = tip + (cy - tip) * 0.35;
  const drop =
    `M ${cx} ${tip} ` +
    `C ${cx} ${bend} ${cx + r} ${cy - r * 0.9} ${cx + r} ${cy} ` +
    `A ${r} ${r} 0 0 1 ${cx - r} ${cy} ` +
    `C ${cx - r} ${cy - r * 0.9} ${cx} ${bend} ${cx} ${tip} Z`;
  const bottom = cy + r;
  const fillH = (bottom - tip) * humidityFill(pct);
  return (
    <span className="humidity-gauge">
      <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height}>
        <defs>
          <clipPath id={clipId}>
            <path d={drop} />
          </clipPath>
        </defs>
        <rect
          x={0}
          y={bottom - fillH}
          width={width}
          height={fillH}
          fill="#4c9be8"
          opacity={0.85}
          clipPath={`url(#${clipId})`}
        />
        <path d={drop} fill="none" stroke="#4c9be8" strokeWidth="1.3" />
      </svg>
      <span className="humidity-gauge-label">{Math.round(pct)}%</span>
    </span>
  );
}
