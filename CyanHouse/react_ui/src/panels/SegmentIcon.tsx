interface Props {
  solarLight: number; // 0-1
  cloudCoverPct: number | null; // 0-100
  rainLevel: number; // 0-5
  precipProb: number | null; // 0-100
  size?: number;
}

const RAIN_BAR_X = [10, 14, 18, 22, 26];

/** Sun (opacity = daylight * (1 - cloud fraction squared)), with a soft halo behind
 * it at the same opacity, overlapped by a cloud (opacity = cloud fraction,
 * so it fades from invisible to solid gray) with blue rain bars below it --
 * bar count from rain_level, bar opacity from rain probability (hidden at 5%
 * or below, otherwise floored at 20% so a borderline forecast doesn't render
 * as invisible as a 0% one). rain_level buckets by amount (mm), which can
 * floor to 0 even at a high probability -- e.g. a 74% chance of a
 * barely-measurable drizzle. Without this, that shows as a bare cloud with
 * no hint of rain at all, so once there's real rain odds (rainOpacity > 0),
 * always draw at least one bar. */
export function SegmentIcon({ solarLight, cloudCoverPct, rainLevel, precipProb, size = 32 }: Props) {
  const cloudFrac = Math.max(0, Math.min(1, (cloudCoverPct ?? 0) / 100));
  const sunOpacity = Math.max(0, Math.min(1, solarLight * (1 - cloudFrac * cloudFrac)));
  const prob = precipProb ?? 0;
  const rainOpacity = prob <= 5 ? 0 : Math.max(0.2, prob / 100);
  const bars = rainLevel <= 0 && rainOpacity > 0 ? 1 : Math.max(0, Math.min(RAIN_BAR_X.length, rainLevel));

  return (
    <svg viewBox="0 0 36 36" width={size} height={size}>
      <circle cx="14" cy="13" r="12" fill="#ffb347" opacity={sunOpacity * 0.3} />
      <circle cx="14" cy="13" r="7" fill="#ffb347" opacity={sunOpacity} />
      <g fill="#5c6470" opacity={cloudFrac}>
        <circle cx="13" cy="20" r="6" />
        <circle cx="19" cy="16" r="7.5" />
        <circle cx="25" cy="20" r="6" />
        <rect x="9" y="19" width="20" height="8" rx="4" />
      </g>
      {bars > 0 && (
        <g stroke="#4c9be8" strokeWidth="2" strokeLinecap="round" opacity={rainOpacity}>
          {RAIN_BAR_X.slice(0, bars).map((x) => (
            <line key={x} x1={x} y1="29" x2={x - 1.5} y2="34" />
          ))}
        </g>
      )}
    </svg>
  );
}
