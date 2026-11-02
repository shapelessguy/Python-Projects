// Small line icons for buttons that are icon-only on a phone (or always),
// drawn in currentColor so they follow the button's text colour -- emoji
// render in whatever palette and size the phone's emoji font picks.

export type IconName = "today" | "month" | "week" | "calendars" | "reorder" | "columns" | "search";

const PATHS: Record<IconName, JSX.Element> = {
  today: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="2.5" fill="currentColor" /></>,
  month: <><rect x="3" y="4" width="18" height="17" rx="2" /><path d="M3 9h18M9 9v12M15 9v12M3 15h18" /></>,
  week: <><rect x="3" y="4" width="18" height="17" rx="2" /><path d="M3 9h18M7.5 9v12M12 9v12M16.5 9v12" /></>,
  calendars: <><path d="M12 3 2 8l10 5 10-5-10-5Z" /><path d="m2 12.5 10 5 10-5" /><path d="m2 17 10 5 10-5" /></>,
  reorder: <path d="M7 20V4M3 8l4-4 4 4M17 4v16M13 16l4 4 4-4" />,
  columns: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16M15 4v16" /></>,
  search: <><circle cx="10.5" cy="10.5" r="6" /><path d="M15 15l5 5" /></>,
};

export function Icon({ name, size = 16, className = "nav-icon" }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {PATHS[name]}
    </svg>
  );
}
