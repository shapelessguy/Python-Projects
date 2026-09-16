interface Props {
  humidityPct: number | null;
  width?: number;
  height?: number;
}

/** Vertical capsule "sensor tube", filled bottom-up to the humidity
 * percentage, with the value printed underneath. Fill opacity floors at 50%
 * for anything at or below 50% humidity, then tracks the percentage above
 * that (so 100% humidity is fully opaque). */
export function HumidityGauge({ humidityPct, width = 12, height = 26 }: Props) {
  if (humidityPct == null) return <span className="muted">–</span>;
  const pct = Math.max(0, Math.min(100, humidityPct));
  const opacity = pct <= 50 ? 0.5 : pct / 100;
  const pad = 1.5;
  const innerH = height - pad * 2;
  const fillH = (innerH * pct) / 100;
  const r = (width - pad * 2) / 2;
  return (
    <span className="humidity-gauge">
      <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height}>
        <rect
          x={pad / 2}
          y={pad / 2}
          width={width - pad}
          height={height - pad}
          rx={(width - pad) / 2}
          fill="none"
          stroke="#4c9be8"
          strokeWidth="1.3"
        />
        <rect
          x={pad}
          y={pad + (innerH - fillH)}
          width={width - pad * 2}
          height={fillH}
          rx={r}
          fill="#4c9be8"
          opacity={opacity}
        />
      </svg>
      <span className="humidity-gauge-label">{Math.round(pct)}%</span>
    </span>
  );
}
