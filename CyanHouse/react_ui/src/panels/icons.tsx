// Small line icons for buttons that are icon-only on a phone (or always),
// drawn in currentColor so they follow the button's text colour -- emoji
// render in whatever palette and size the phone's emoji font picks.

export type IconName = "today" | "month" | "week" | "calendars" | "reorder" | "columns" | "search"
  | "mouse" | "pcSound" | "keyboard" | "left" | "right" | "winLeft" | "winRight" | "maximize" | "scroll"
  | "settings" | "prev" | "next" | "play" | "pause" | "moveTo" | "download" | "upload" | "music" | "trash" | "close"
  | "block" | "eye" | "eyeOff" | "plus" | "edit" | "pie" | "all";

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
  // The player's: filled, and centred on the box's middle by their weight
  // (a font's ⏮ ▶ ⏭ sit off-centre in their own glyph boxes).
  prev: <><path d="M6.5 6v12" /><path d="M18 6.5 9.5 12l8.5 5.5Z" fill="currentColor" /></>,
  next: <><path d="M17.5 6v12" /><path d="M6 6.5l8.5 5.5L6 17.5Z" fill="currentColor" /></>,
  play: <path d="M8.5 5.5v13l10-6.5Z" fill="currentColor" />,
  pause: <path d="M9 6.5v11M15 6.5v11" strokeWidth="3.2" />,
  moveTo: <><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" /><path d="M9 13h7M13 10l3 3-3 3" /></>,
  download: <path d="M12 4v11M7 10l5 5 5-5M5 20h14" />,
  upload: <path d="M12 15V4M7 9l5-5 5 5M5 20h14" />,
  music: <><path d="M9 18V5l11-2v13" /><circle cx="6" cy="18" r="3" /><circle cx="17" cy="16" r="3" /></>,
  trash: <path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6" />,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  block: <><circle cx="12" cy="12" r="8.5" /><path d="M6 6l12 12" /></>,
  eye: <><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></>,
  eyeOff: <><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /><path d="M4 4l16 16" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  all: <path d="M12 20V9M7 14l5-5 5 5M5 4h14" />,
  pie: <><path d="M21 12A9 9 0 1 1 12 3v9Z" /><path d="M15 3.5A9 9 0 0 1 20.5 9H15Z" /></>,
  edit: <path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16Z M13.5 6.5l4 4" />,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></>,
};

export function Icon({ name, size = 16, className = "nav-icon" }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {PATHS[name]}
    </svg>
  );
}

/** Upload files into a folder by picking them -- a phone has no drag and
 *  drop, which is how they go in everywhere else. */
export function UploadButton({ onFiles, title, className = "" }: {
  onFiles: (files: File[]) => void; title: string; className?: string;
}) {
  return (
    <label className={"upload-pick " + className} title={title} onClick={(e) => e.stopPropagation()}>
      <Icon name="upload" size={16} className="" />
      <input type="file" multiple hidden onChange={(e) => {
        const files = Array.from(e.target.files ?? []);
        e.target.value = "";
        if (files.length) onFiles(files);
      }} />
    </label>
  );
}
