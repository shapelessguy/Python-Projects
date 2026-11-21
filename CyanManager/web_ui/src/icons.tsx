// Stroke icons (24-unit grid, currentColor), drawn inline so they follow the theme.
const PATHS = {
  play: "M7 4v16l13-8z",
  stop: "M6 6h12v12H6z",
  terminal: "M5 7l5 5-5 5M12 19h7",
  up: "M6 15l6-6 6 6",
  down: "M6 9l6 6 6-6",
  left: "M15 6l-6 6 6 6",
  right: "M9 6l6 6-6 6",
  plus: "M12 5v14M5 12h14",
  minus: "M5 12h14",
  trash: "M4 7h16M10 11v6M14 11v6M5 7l1 12a2 2 0 002 2h8a2 2 0 002-2l1-12M9 7V4h6v3",
  save: "M5 4h11l3 3v13H5zM8 4v5h7M8 20v-6h8v6",
  add: "M12 5v14M5 12h14",
  apps: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
  bolt: "M13 3L4 14h7l-1 7 9-11h-7z",
  sliders: "M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0M14 4v4M8 10v4M16 16v4",
  key: "M15 9a3 3 0 11-6 0 3 3 0 016 0zM12 12v9M12 17h3M12 20h2",
  check: "M5 12l5 5 9-10",
  move: "M12 4v16M4 12h16M9 7l3-3 3 3M9 17l3 3 3-3M7 9l-3 3 3 3M17 9l3 3-3 3",
  resize: "M9 4H4v5M15 4h5v5M9 20H4v-5M15 20h5v-5",
  x: "M6 6l12 12M18 6L6 18",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 16, className }: { name: IconName; size?: number; className?: string }) {
  const filled = name === "play" || name === "stop";
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke={filled ? "none" : "currentColor"}
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
