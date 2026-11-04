// Small line icons for buttons that are icon-only on a phone (or always),
// drawn in currentColor so they follow the button's text colour -- emoji
// render in whatever palette and size the phone's emoji font picks.

export type IconName = "today" | "month" | "week" | "calendars" | "reorder" | "columns" | "search"
  | "mouse" | "pcSound" | "keyboard" | "left" | "right" | "winLeft" | "winRight" | "maximize" | "scroll";

const PATHS: Record<IconName, JSX.Element> = {
  today: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="2.5" fill="currentColor" /></>,
  month: <><rect x="3" y="4" width="18" height="17" rx="2" /><path d="M3 9h18M9 9v12M15 9v12M3 15h18" /></>,
  week: <><rect x="3" y="4" width="18" height="17" rx="2" /><path d="M3 9h18M7.5 9v12M12 9v12M16.5 9v12" /></>,
  calendars: <><path d="M12 3 2 8l10 5 10-5-10-5Z" /><path d="m2 12.5 10 5 10-5" /><path d="m2 17 10 5 10-5" /></>,
  reorder: <path d="M7 20V4M3 8l4-4 4 4M17 4v16M13 16l4 4 4-4" />,
  columns: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16M15 4v16" /></>,
  search: <><circle cx="10.5" cy="10.5" r="6" /><path d="M15 15l5 5" /></>,
  // The PC's sound on this device: a screen giving out sound.
  pcSound: <><rect x="2" y="4" width="14" height="10" rx="1.5" /><path d="M6 18h6M9 14v4M19 7.5a4 4 0 0 1 0 5M21.5 5a7.5 7.5 0 0 1 0 10" /></>,
  mouse: <><rect x="6" y="3" width="12" height="18" rx="6" /><path d="M12 7v4" /></>,
  keyboard: <><rect x="2" y="6" width="20" height="12" rx="2" /><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10" /></>,
  left: <path d="M19 12H5M11 6l-6 6 6 6" />,
  right: <path d="M5 12h14M13 6l6 6-6 6" />,
  winLeft: <><path d="M4 4v16" /><path d="M20 12H9M14 7l-5 5 5 5" /></>,
  winRight: <><path d="M20 4v16" /><path d="M4 12h11M10 7l5 5-5 5" /></>,
  maximize: <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />,
  scroll: <path d="M12 3v18M8 7l4-4 4 4M8 17l4 4 4-4" />,
};

export function Icon({ name, size = 16, className = "nav-icon" }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {PATHS[name]}
    </svg>
  );
}
