import { useEffect, useState } from "react";
import { onAuthFailed } from "./auth";

export type ColType = "number" | "text" | "bool" | "enum";

export interface Column {
  key: string;
  name: string;
  description: string;
  unit: string;
  type: ColType;
  position: number;
  options: string[];
}

export interface DayRow {
  date: string;
  values: Record<string, unknown>;
}

export interface MonthData {
  month: string;
  columns: Column[];
  units: string[];
  rows: DayRow[];
  version: number;
}

export interface City {
  key: string;
  city_name: string;
  country: string;
  flag: string;
  color: string;
  default: boolean;
}

export interface Variable {
  key: string;
  label: string;
  unit: string;
  group: string;
  default: boolean;
  description: string;
}

export interface EnvBootstrap {
  cities: City[];
  variables: Variable[];
  min_date: string | null;
  max_date: string | null;
  weather_version: number;
}

export interface SeriesResponse {
  resample: string;
  start: string;
  end: string;
  series: Record<string, Record<string, (number | null)[] | string[]>>;
}

export interface ForecastBootstrap {
  cities: City[];
  issued_at: Record<string, string | null>;
  dwd_hours: number;
  forecast_version: number;
}

export interface ForecastCitySeries {
  index: string[];
  precip_mm: (number | null)[];
  precip_prob: (number | null)[];
  temperature_c: (number | null)[];
  wind_speed_kmh: (number | null)[];
  cloud_cover_pct: (number | null)[];
  humidity_pct: (number | null)[];
  source: string[];
}

export interface ForecastResponse {
  issued_at: Record<string, string | null>;
  series: Record<string, ForecastCitySeries>;
}

export interface OverviewSegment {
  start: string;
  end: string;
  temperature_c: number | null;
  humidity_pct: number | null;
  cloud_cover_pct: number | null;
  precip_prob: number | null;
  precip_mm: number;
  rain_level: number;
  wind_speed_kmh: number | null;
  wind_level: number;
  solar_light: number;
  source: string | null;
}

export interface OverviewResponse {
  city: string;
  range: "today" | "tomorrow" | "in2days" | "week";
  issued_at: string | null;
  segments: OverviewSegment[];
}

export interface ControlsInfo {
  volume?: number;
  device?: string;
}

async function j<T>(r: Response): Promise<T> {
  if (r.status === 401) {
    onAuthFailed();
    throw new Error("401 — not signed in");
  }
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} — ${await r.text()}`);
  return r.json() as Promise<T>;
}

const JSON_HEADERS = { "content-type": "application/json" };

// Per-user data behind a same-origin cookie: never let the browser reuse one
// user's API response for another after a logout / account switch.
const f = (url: string, init: RequestInit = {}) =>
  fetch(url, { cache: "no-store", ...init });

export interface Versions {
  diary: number;
  weather: number;
  food: number;
  forecast: number;
  calendar: number;
  /** Bumps when a folder the Media panel shows changes -- the backend
   *  follows them, and the held version request carries it at once. */
  prep: number;
}

// null = every panel (the default, unrestricted); otherwise the explicit
// allowed set. The corresponding APIs are 403'd server-side regardless of
// whether the frontend respects this -- see api/auth.py's require_panel.
export interface Me {
  username: string;
  visible_panels: string[] | null;
  /** Opt-in permissions, default off — unlike visible_panels, which narrows
   *  a default of "everything". Used to hide actions the user cannot take
   *  rather than letting them discover it from a 403. */
  permissions: Record<string, boolean>;
}

export type RecurFreq = "daily" | "weekly" | "monthly" | "yearly";

export interface Calendar {
  id: number;
  name: string;
  color: string;
  shared: boolean;
  // Whether the current user may rename/recolor/delete/(un-)share this
  // calendar -- true for one they own, or for the original owner-less
  // "Shared" calendar (predates per-calendar sharing) which answers to
  // everyone since nobody in particular owns it. False only for a calendar
  // someone else owns and has shared with them.
  mine: boolean;
}

export interface CalendarEvent {
  id: number;
  owner: string;
  mine: boolean;
  calendar_id: number;
  calendar_name: string;
  calendar_color: string;
  calendar_shared: boolean;
  title: string;
  description: string;
  start_date: string;
  end_date: string;
  all_day: boolean;
  start_time: string | null;
  end_time: string | null;
  recur_freq: RecurFreq | null;
  recur_interval: number;
  recur_until: string | null;
  recurring: boolean;
  alarm: boolean;
  // "" (not acknowledged); else "true" for a plain event or a YYYY-MM-DD
  // date -- the last occurrence acknowledged -- for a recurring one. See
  // alarms.ts for how this decides whether an alarm is currently due.
  alarm_ack: string | null;
  // Set together, cleared together: while alarm_snooze_until (epoch ms) is
  // still in the future AND alarm_snooze_occurrence still matches whichever
  // occurrence is currently due, the alarm stays hidden without being
  // permanently acknowledged. Synced through the backend (not a cookie) so
  // snoozing/closing from one client is reflected on every other.
  alarm_snooze_occurrence: string | null;
  alarm_snooze_until: number | null;
}

export interface MonthEvents {
  month: string;
  events: CalendarEvent[];
  calendar_version: number;
}

export interface EventInput {
  title: string;
  description?: string;
  start_date: string;
  end_date: string;
  all_day?: boolean;
  start_time?: string | null;
  end_time?: string | null;
  calendar_id: number;
  recur_freq?: RecurFreq | null;
  recur_interval?: number;
  recur_until?: string | null;
  alarm?: boolean;
  alarm_ack?: string | null;
  // Patch-only in practice (see alarms.ts) -- a freshly created event has
  // nothing to snooze yet.
  alarm_snooze_occurrence?: string | null;
  alarm_snooze_until?: number | null;
}

export interface MovieItem {
  id: string;
  title: string;
  file: string;
  size: number;
  /** Version of the cover Plex has for this file (see /api/movies/poster),
   *  or null/absent when it has none. */
  poster?: string | null;
}

export interface MovieTrack {
  id: number;
  /** Stable across uploads and deletions, unlike `id`, which is this track's
   *  position in the list. Delays are stored against this. */
  key: string;
  label: string;
  language: string;
  /** Subtitles only: "text" (SRT/ASS) or "image" (PGS/VobSub). Both are
   *  burned into the picture server-side -- the distinction is only there
   *  for the label. */
  kind?: "text" | "image";
  /** Where the track came from: muxed into the file, found next to it in the
   *  movie folder, or uploaded here. Only "uploaded" ones can be deleted --
   *  a file sitting in the library isn't ours to remove. */
  source?: "embedded" | "folder" | "uploaded";
  /** Present only on uploaded tracks; the handle the delete endpoint takes. */
  upload_id?: string;
  default?: boolean;
}

export interface MovieInfo {
  id: string;
  title: string;
  file: string;
  /** Seconds, from ffprobe. The <video> element can't know this -- the
   *  stream it gets is a fragmented MP4 with no index -- so every position
   *  the player shows is measured against this, not video.duration. */
  duration: number;
  size: number;
  video: { codec: string; width: number; height: number; hdr: boolean; pix_fmt: string };
  audio: MovieTrack[];
  subtitles: MovieTrack[];
  /** Selectable output heights. A leading 0 is the "Original" rung: the
   *  video stream is copied to the browser untouched, no re-encoding. Only
   *  present when `remux.ok`. */
  heights: number[];
  /** Whether this file's video can be sent as-is, and if not, why not. */
  remux: { ok: boolean; reason: string };
  encoder: string;
}

/** One browsable folder: the real library, a staging inbox, or the folder an
 *  area's finished films land in. */
export interface MovieSource {
  key: string;
  label: string;
  /** The label without the area name in front, for when the area is already
   *  named by the button sitting above this one. */
  short: string;
  path: string;
  /** "library" is a library of its own, with no staging pair: the films
   *  (key "", shown as covers or a list of films), music and images (browsed
   *  as a tree, like every other folder — a staging inbox, an output, the
   *  series library). */
  kind: "library" | "inbox" | "output";
  /** The folders its things may be moved into, by the move rules in
   *  secrets.json (movie_prep.may_move_between) — among the ones this user sees. */
  moves_to?: string[];
  /** What the folder is for: work waiting, or work finished. The panel
   *  stacks one above the other. */
  role: "todo" | "done";
  /** Which staging area this belongs to; the inbox and the output of one
   *  area share it, which is what pairs them into a column. */
  group: string;
  ready: boolean;
  /** A staging area's icon (secrets.json "icon"), which its tab shows in
   *  place of its name when the tab row is narrow. */
  icon?: string;
  /** Set on the libraries that are not films — the Music and Images tabs. */
  media?: "music" | "images";
  /** What a staging pair holds: films (identify + remux) or songs
   *  (recognise + tag + file — api/services/music_prep.py). */
  type?: "film" | "music";
  /** What the folder is for, per language — secrets.json's `description`,
   *  shown in the panel's help text. */
  description?: Record<string, string>;
}

/** One album a song can be filed under — see api/services/music_prep.py. */
export interface MusicOption {
  recording_id: string;
  release_id: string;
  release_group_id: string;
  artist: string;
  title: string;
  album: string;
  album_artist: string;
  date: string;
  year: string;
  /** Position on the disc (what the file is numbered by)… */
  track: string;
  /** …and the number as printed on the release ("B1" on vinyl). */
  track_label?: string;
  tracks: number;
  disc: number;
  discs: number;
  /** "Album", "Single", "Album + Compilation", … */
  type: string;
  status: string;
  country: string;
  live: boolean;
  /** Where it would be filed, relative to the pair's output. */
  target: string;
}

export interface MusicIdentity {
  path: string;
  song: { artist: string; title: string; album: string; from: "tags" | "name" | "you" };
  options: MusicOption[];
  /** Why the background filing left this song for a person, if it did. */
  review?: string | null;
}

/** The music library, from the files' tags — api/services/music_library.py. */
export interface MusicSong {
  path: string;
  folder: string;
  title: string;
  artist: string;
  album_artist: string;
  album: string;
  track: number;
  disc: number;
  year: string;
  seconds: number;
  size: number;
}

export interface MusicAlbum {
  /** The album's folder, relative to the library: its id. */
  folder: string;
  title: string;
  artist: string;
  year: string;
  tracks: number;
  seconds: number;
  cover: boolean;
}

export interface MusicArtist {
  name: string;
  albums: number;
  tracks: number;
  /** An album folder whose cover stands for the artist, or "". */
  cover: string;
}

export interface MusicLibrary {
  songs: MusicSong[];
  albums: MusicAlbum[];
  artists: MusicArtist[];
}

/** The background filing in one music inbox — see music_prep.auto_status. */
export interface MusicAuto {
  enabled: boolean;
  /** The song it is on right now, relative to the inbox. */
  current: string | null;
  pending: number;
  filed: number;
  /** Songs it left for a person, by path, with the reason. */
  review: Record<string, string>;
}

/** A file a move could not place: the destination already has one. */
export interface MoveConflict {
  /** Where it still is, in the area it came from. */
  path: string;
  /** What it clashed with, in the area it was going to. */
  dest: string;
  size: number | null;
  modified: number;
  dest_size: number | null;
  dest_modified: number;
  /** A file against a folder: only "keep both" can settle it. */
  mixed: boolean;
}

export interface StagingArea {
  name: string;
  inbox: string;
  library: string;
  ready: boolean;
  problem: string;
}

/** One entry in a browsable folder — every file *and* every folder, not just
 *  the films. The list is flat and the panel rebuilds the tree from `path`:
 *  a download can be three levels deep or loose in the root, and assuming a
 *  shape is how a browser ends up hiding things. */
export interface StagedFile {
  path: string;
  folder: string;
  name: string;
  size: number;
  modified: number;
  kind: "folder" | "video" | "image" | "audio" | "subtitle" | "text" | "binary";
  readable: boolean;
  /** Folders only: how many entries are directly inside. */
  children?: number;
  /** Videos only: streamable through the normal player. */
  movie_id?: string;
  /** Pictures in the Images folder, once the server knows them: their size
   *  in pixels, so a tile can be drawn at its shape before it loads. */
  width?: number;
  height?: number;
}

/** What an upload did with each file it was given. Partial success is normal
 *  — drop a folder's worth of subtitles in and the .nfo among them is named
 *  and skipped rather than failing the batch. */
export interface SubtitleUpload {
  info: MovieInfo;
  accepted: { id: string; name: string; kind: "text" | "image" }[];
  rejected: { name: string; reason: string }[];
}

export interface PrepTrack {
  key: string;
  type: "video" | "audio" | "subtitle";
  index?: number;
  codec: string;
  label: string;
  keep: boolean;
  language: string;
  language_guessed?: boolean;
  delay_ms: number;
  default: boolean;
  external?: string;
  cover_art?: boolean;
  /** Audio only: generate a subtitle in this track's language from it, as
   *  the first stage of the remux (api/services/srt_gen.py). */
  gen_srt?: boolean;
}

/** One entry in the server's remux queue. The server is the record — it
 *  keeps the queue on disk — and every browser only draws it. */
export interface RemuxJob {
  id: string;
  /** The inbox it came from; also the tab it belongs to. */
  area: string;
  fingerprint: string;
  movie_id: string;
  target: string;
  /** The film's folder in the inbox, for recognising it. */
  folder: string;
  output: string;
  by: string;
  created: number;
  started: number | null;
  finished: number | null;
  state: "queued" | "running" | "done" | "failed" | "cancelled";
  phase: "" | "generating" | "muxing" | "verifying" | "tidying" | "done";
  /** 1-based; one step per subtitle to generate, then the mux. */
  step?: number;
  steps?: number;
  /** While generating: the language of the subtitle being made. */
  step_label?: string;
  /** While generating: "extracting audio" | "uploading" | "transcribing". */
  detail?: string;
  percent: number | null;
  error: string;
  attempts: number;
  /** Queued only: its place in line, 1 being next. */
  position?: number;
  /** Set when asking to queue a film that already was. */
  already?: boolean;
}

/** A proposed preparation: what the film is, and what the muxed file gets. */
export interface PrepPlan {
  area?: string;
  folder: string;
  video: string;
  /** Where a successful remux lands. Shown before committing, because an
   *  area that omits `library` in secrets.json defaults to the real one. */
  destination?: string;
  movie_id?: string;
  /** What its saved decisions are filed under: the file, not its path. */
  fingerprint?: string;
  /** Whether saved decisions were applied to it. */
  saved?: boolean;
  title: string;
  year: string;
  tmdb_id: number | null;
  target: string;
  duration: number;
  size: number;
  tracks: PrepTrack[];
  junk: string[];
  extra_videos: string[];
  conflicts: string[];
  error?: string;
}

export interface TmdbCandidate {
  id: number;
  title: string;
  original_title: string;
  year: string;
  name: string;
  overview: string;
  poster: string | null;
}

export const api = {
  version: () => f("/api/version").then(j<Versions>),
  me: () => f("/api/me").then(j<Me>),

  envBootstrap: () => f("/api/environment/bootstrap").then(j<EnvBootstrap>),
  series: (q: Record<string, string>) =>
    f("/api/environment/series?" + new URLSearchParams(q)).then(j<SeriesResponse>),
  refresh: () => f("/api/environment/refresh", { method: "POST" }).then(j<EnvBootstrap>),

  forecastBootstrap: () => f("/api/forecast/bootstrap").then(j<ForecastBootstrap>),
  forecast: (cities: string) =>
    f("/api/forecast/series?" + new URLSearchParams({ cities })).then(j<ForecastResponse>),
  forecastRefresh: () =>
    f("/api/forecast/refresh", { method: "POST" }).then(j<ForecastBootstrap>),
  forecastOverview: (city: string, range: "today" | "tomorrow" | "in2days" | "week") =>
    f("/api/forecast/overview?" + new URLSearchParams({ city, range })).then(j<OverviewResponse>),

  calendars: () => f("/api/calendar/calendars").then(j<Calendar[]>),
  createCalendar: (name: string, color?: string, shared?: boolean) =>
    f("/api/calendar/calendars", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ name, color, shared }) }).then(j<Calendar[]>),
  patchCalendar: (id: number, body: { name?: string; color?: string; shared?: boolean }) =>
    f(`/api/calendar/calendars/${id}`, { method: "PATCH", headers: JSON_HEADERS, body: JSON.stringify(body) }).then(j<Calendar[]>),
  deleteCalendar: (id: number) =>
    f(`/api/calendar/calendars/${id}`, { method: "DELETE" }).then(j<Calendar[]>),

  // Every calendar mutation replies with the full month snapshot for the
  // affected event's month (create/patch: its date; delete: its old date).
  calendarMonth: (month: string) =>
    f("/api/calendar/events?" + new URLSearchParams({ month })).then(j<MonthEvents>),
  createEvent: (body: EventInput) =>
    f("/api/calendar/events", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) }).then(j<MonthEvents>),
  patchEvent: (id: number, body: Partial<EventInput>) =>
    f(`/api/calendar/events/${id}`, { method: "PATCH", headers: JSON_HEADERS, body: JSON.stringify(body) }).then(j<MonthEvents>),
  // `occurrence` ("delete this event", only meaningful for a recurring
  // series) suppresses just that one date; omitted, it deletes the series.
  deleteEvent: (id: number, occurrence?: string) =>
    f(
      `/api/calendar/events/${id}` + (occurrence ? "?" + new URLSearchParams({ occurrence }) : ""),
      { method: "DELETE" },
    ).then(j<MonthEvents>),

  // ── controls (CC) — thin proxy to the CyanControls RoomServer services ──
  controlInfo: () => f("/api/controls/info").then(j<ControlsInfo>),
  controlRoom: (topic: string, command: string, extra?: Record<string, unknown>) =>
    f(`/api/controls/room/${topic}`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ command, ...extra }),
    }).then(j<ControlsInfo>),
  controlFn: (name: string, body?: Record<string, unknown>) =>
    f(
      `/api/controls/fn/${name}`,
      body
        ? { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) }
        : { method: "POST" },
    ).then(j<ControlsInfo>),
  /** Voice names currently available on CyanManager (its `voices/` sub-folders). */
  controlVoices: () => f("/api/controls/voices").then(j<string[]>),
  controlPlayVoice: (name: string) =>
    f(`/api/controls/voices/${encodeURIComponent(name)}`, { method: "POST" }).then(j<unknown>),

  // ── movies — see api/services/movies.py. `id` is already percent-encoded
  // server-side; URLSearchParams encodes it a second time, which Starlette
  // undoes on the way in, so the backend still receives exactly that id.
  movies: (refresh = false) =>
    f("/api/movies/list" + (refresh ? "?refresh=true" : "")).then(j<MovieItem[]>),
  movieInfo: (id: string) =>
    f("/api/movies/info?" + new URLSearchParams({ id })).then(j<MovieInfo>),
  /** Attach subtitle files to a film. Stored server-side under the film's
   *  fingerprint, never written into the movie folder. Replies with the
   *  refreshed MovieInfo. No content-type header on purpose: the browser has
   *  to set it itself so the multipart boundary matches the body.
   *
   *  Takes a list because VobSub is two files -- a `.idx` and its `.sub` --
   *  that are one subtitle and have to arrive together. */
  uploadMovieSubtitle: (id: string, files: File[]) => {
    const body = new FormData();
    for (const file of files) body.append("files", file);
    return f("/api/movies/subtitles?" + new URLSearchParams({ id }), {
      method: "POST",
      body,
    }).then(j<SubtitleUpload>);
  },
  deleteMovieSubtitle: (id: string, sub: string) =>
    f("/api/movies/subtitles?" + new URLSearchParams({ id, sub }), {
      method: "DELETE",
    }).then(j<MovieInfo>),

  /** Fire-and-forget teardown of a client's transcode. `keepalive` so it
   *  still goes out from a page that is being unloaded. */
  movieStop: (sid: string) =>
    fetch("/api/movies/stop?" + new URLSearchParams({ sid }), {
      method: "POST",
      keepalive: true,
    }).catch(() => {}),

  // ── movie preparation (staging folders) ────────────────────────────
  prepAreas: () => f("/api/prep/areas").then(j<{ areas: StagingArea[]; sources: MovieSource[]; tmdb: boolean; languages: { code: string; name: string }[] }>),
  prepFiles: (area: string) =>
    f("/api/prep/files?" + new URLSearchParams({ area })).then(j<{ files: StagedFile[] }>),
  prepScan: (area: string) =>
    f("/api/prep/scan?" + new URLSearchParams({ area })).then(j<{ films: PrepPlan[] }>),
  prepText: (area: string, path: string) =>
    f("/api/prep/text?" + new URLSearchParams({ area, path }))
      .then(j<{ name: string; size: number; encoding: string; text: string }>),
  prepInfo: (area: string, path: string) =>
    f("/api/prep/info?" + new URLSearchParams({ area, path })).then(j<Record<string, any>>),
  prepRawUrl: (area: string, path: string) =>
    "/api/prep/raw?" + new URLSearchParams({ area, path }),
  /** A picture scaled down to about `width` pixels, for galleries. `version`
   *  (the file's time) makes a changed picture a new URL. */
  prepThumbUrl: (area: string, path: string, width: number, version: number) =>
    "/api/prep/thumb?" + new URLSearchParams({ area, path, w: String(width), v: String(version) }),
  prepIdentify: (title: string, year: string) =>
    f("/api/prep/identify?" + new URLSearchParams({ title, year }))
      .then(j<{ confident: boolean; match: TmdbCandidate | null; candidates: TmdbCandidate[] }>),
  /** Move a film's folder to another configured folder — a staging inbox,
   *  a staging output, or the library itself. Needs the `publish` permission. */
  prepMove: (id: string, to: string) =>
    f("/api/prep/move?" + new URLSearchParams({ id, to }), { method: "POST" })
      .then(j<{ moved: string; to: string; size: number }>),
  /** Rename one file or folder where it sits. Inside the real libraries this
   *  needs the `publish` permission; a staging folder is open. */
  prepRename: (area: string, path: string, name: string) =>
    f("/api/prep/rename?" + new URLSearchParams({ area, path, name }), { method: "POST" })
      .then(j<{ renamed: boolean; new_path: string; name: string; is_dir: boolean }>),
  // ── music staging — api/routers/music.py
  musicIdentify: (area: string, path: string, artist?: string, title?: string) =>
    f("/api/music/identify?" + new URLSearchParams({
      area, path,
      ...(artist !== undefined ? { artist } : {}),
      ...(title !== undefined ? { title } : {}),
    })).then(j<MusicIdentity>),
  musicFile: (area: string, path: string, choice: MusicOption) =>
    f("/api/music/file?" + new URLSearchParams({ area, path }), {
      method: "POST", headers: JSON_HEADERS, body: JSON.stringify(choice),
    }).then(j<{ path: string; new_path: string; tagged: boolean; cover: boolean }>),
  musicLibrary: () => f("/api/music/library").then(j<MusicLibrary>),
  /** An album's cover — with `width`, a copy about that many pixels wide. */
  musicArtUrl: (folder: string, width?: number) =>
    "/api/music/art?" + new URLSearchParams(width ? { folder, w: String(width) } : { folder }),
  musicAuto: (area: string) =>
    f("/api/music/auto?" + new URLSearchParams({ area })).then(j<MusicAuto>),
  musicCoverUrl: (releaseGroupId: string) =>
    "/api/music/cover?" + new URLSearchParams({ rg: releaseGroupId }),

  /** Create an empty folder inside `path` ("" being the area's root). */
  prepMkdir: (area: string, path: string, name: string) =>
    f("/api/prep/mkdir?" + new URLSearchParams({ area, path, name }), { method: "POST" })
      .then(j<{ new_path: string; name: string }>),
  /** Move a file or folder into another folder — the tree's drag and drop.
   *  `to` is the destination *folder*, "" being that area's root. */
  prepMovePath: (area: string, path: string, toArea: string, to: string) =>
    f("/api/prep/movepath?" + new URLSearchParams({ area, path, to_area: toArea, to }),
      { method: "POST" })
      .then(j<{
        moved: string; new_path: string; to_area: string; is_dir: boolean;
        /** Merged into a folder of the same name that was already there. */
        merged: boolean;
        /** Small files identical to one already there, dropped not moved. */
        identical: number;
        /** Files the destination already had, so not moved: for a person. */
        conflicts: MoveConflict[];
      }>),
  /** Settle one conflict: replace the file that was there, or keep both. */
  prepResolve: (area: string, path: string, toArea: string, dest: string,
                action: "replace" | "keep", upto: string) =>
    f("/api/prep/resolve?" + new URLSearchParams({ area, path, to_area: toArea, dest, action, upto }),
      { method: "POST" }).then(j<{ path: string; new_path: string }>),
  /** Remove a file, or a folder and everything under it. Not an unlink: it
   *  moves to that area's `.trash`, which the listing hides. */
  prepDelete: (area: string, path: string) =>
    f("/api/prep/delete?" + new URLSearchParams({ area, path }), { method: "POST" })
      .then(j<{ removed: string; is_dir: boolean; files: number; size: number; trash: string }>),
  /** The disk this folder sits on — what it is called, and how full. */
  prepSpace: (area: string) =>
    f("/api/prep/space?" + new URLSearchParams({ area }))
      .then(j<{ name: string; mount: string; path: string; total: number; free: number; used: number }>),
  /** Queue a film for remuxing, saving the plan it was queued with. Always
   *  accepted if the film *can* be remuxed; refused at once if it cannot. */
  prepExecute: (area: string, plan: PrepPlan) =>
    f("/api/prep/execute?" + new URLSearchParams({ area }), {
      method: "POST", headers: JSON_HEADERS, body: JSON.stringify(plan),
    }).then(j<RemuxJob>),
  /** Queue every film in an inbox that is ready; the rest come back with
   *  the reason each is not. */
  prepRemuxAll: (area: string) =>
    f("/api/prep/remux_all?" + new URLSearchParams({ area }), { method: "POST" })
      .then(j<{ queued: RemuxJob[]; skipped: { folder: string; reason: string }[] }>),
  /** The queue: running first, then waiting in order, then finished. */
  prepJobs: () => f("/api/prep/jobs").then(j<{ jobs: RemuxJob[] }>),
  /** Drop a queued remux, stop a running one, or clear a finished one. */
  prepRemoveJob: (id: string) =>
    f(`/api/prep/jobs/${encodeURIComponent(id)}`, { method: "DELETE" }).then(j<RemuxJob>),
  prepClearJobs: () => f("/api/prep/jobs/clear", { method: "POST" }).then(j<{ jobs: RemuxJob[] }>),
  /** Remember what was decided about a film — sent on every change, so the
   *  server always has the latest, and a queued remux uses it. */
  prepSavePlan: (area: string, plan: PrepPlan) =>
    f("/api/prep/plan?" + new URLSearchParams({ area }), {
      method: "PUT", headers: JSON_HEADERS, body: JSON.stringify(plan),
    }).then(j<{ fingerprint: string }>),

  // Every diary mutation replies with the full month snapshot for `month`.
  columns: () => f("/api/personal/columns").then(j<Column[]>),
  addColumn: (body: Partial<Column>, month: string) =>
    f(`/api/personal/columns?month=${month}`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) }).then(j<MonthData>),
  patchColumn: (key: string, body: Partial<Column>, month: string) =>
    f(`/api/personal/columns/${key}?month=${month}`, { method: "PATCH", headers: JSON_HEADERS, body: JSON.stringify(body) }).then(j<MonthData>),
  deleteColumn: (key: string, month: string) =>
    f(`/api/personal/columns/${key}?month=${month}`, { method: "DELETE" }).then(j<MonthData>),
  reorderColumns: (keys: string[], month: string) =>
    f(`/api/personal/columns/order?month=${month}`, { method: "PUT", headers: JSON_HEADERS, body: JSON.stringify({ keys }) }).then(j<MonthData>),

  units: () => f("/api/personal/units").then(j<string[]>),
  addUnit: (unit: string, month: string) =>
    f(`/api/personal/units?month=${month}`, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ unit }) }).then(j<MonthData>),
  deleteUnit: (unit: string, month: string) =>
    f(`/api/personal/units?unit=${encodeURIComponent(unit)}&month=${month}`, { method: "DELETE" }).then(j<MonthData>),

  month: (month: string) => f(`/api/personal/entries?month=${month}`).then(j<MonthData>),
  putDay: (date: string, values: Record<string, unknown>) =>
    f(`/api/personal/entries/${date}`, { method: "PUT", headers: JSON_HEADERS, body: JSON.stringify({ values }) }).then(j<MonthData>),
};

/** Follow a held endpoint (api/longpoll.py on the server): ask with the tag
 *  of what we have, get an answer when it changes (or after `wait` seconds
 *  anyway), ask again. `onValue` hears every answer. Stops when `signal`
 *  aborts; after a failure it waits a little before asking again. */
export function follow<T>(url: string, onValue: (v: T) => void, signal: AbortSignal, wait = 25): void {
  let since = "";
  const sleep = (ms: number) => new Promise<void>((r) => {
    const t = window.setTimeout(r, ms);
    signal.addEventListener("abort", () => { window.clearTimeout(t); r(); }, { once: true });
  });
  (async () => {
    while (!signal.aborted) {
      try {
        const sep = url.includes("?") ? "&" : "?";
        const r = await f(`${url}${sep}${new URLSearchParams({ since, wait: String(wait) })}`, { signal });
        const v = await j<T>(r);
        since = r.headers.get("X-Tag") ?? "";
        if (!signal.aborted) onValue(v);
        // An answer without a tag (an older server) would come back at once
        // every time: pace it like the old poll instead.
        if (!since) await sleep(1000);
      } catch {
        if (!signal.aborted) await sleep(3000);
      }
    }
  })();
}

/** The version counters, followed once for the whole page however many
 *  panels want them: the first to subscribe starts the one held request,
 *  the last to leave stops it. Each panel picks the counters it cares about
 *  and refetches when those move. */
const versionStore = {
  value: { diary: 0, weather: 0, food: 0, forecast: 0, calendar: 0, prep: 0 } as Versions,
  listeners: new Set<(v: Versions) => void>(),
  stop: null as AbortController | null,
};

function subscribeVersions(listener: (v: Versions) => void): () => void {
  versionStore.listeners.add(listener);
  if (!versionStore.stop) {
    const stop = new AbortController();
    versionStore.stop = stop;
    follow<Versions>("/api/version", (next) => {
      const cur = versionStore.value;
      if ((Object.keys(next) as (keyof Versions)[]).some((k) => next[k] !== cur[k])) {
        versionStore.value = next;
        versionStore.listeners.forEach((l) => l(next));
      }
    }, stop.signal);
  }
  return () => {
    versionStore.listeners.delete(listener);
    if (!versionStore.listeners.size && versionStore.stop) {
      versionStore.stop.abort();
      versionStore.stop = null;
    }
  };
}

/** The counters, kept current: see versionStore. */
export function useVersionPoll(): Versions {
  const [v, setV] = useState<Versions>(versionStore.value);
  useEffect(() => {
    setV(versionStore.value);
    return subscribeVersions(setV);
  }, []);
  return v;
}

/** One-shot fetch (not polled -- permissions are static for the life of a
 *  session, only changing via a backend restart): what the current user is
 *  allowed to see, fetched once at app start so panels can be hidden and
 *  their APIs never called in the first place, rather than every panel
 *  discovering it's restricted from its own first request 403ing. `loaded`
 *  is false until that first reply lands (or fails); callers should hold
 *  off rendering/mounting any panel content until then, since `visible` is
 *  meaningless -- neither "restricted" nor "unrestricted" -- before that. */
export function useVisibility(): {
  visible: string[] | null;
  loaded: boolean;
  permissions: Record<string, boolean>;
} {
  const [visible, setVisible] = useState<string[] | null>(null);
  const [permissions, setPermissions] = useState<Record<string, boolean>>({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const attempt = () => {
      api.me()
        .then((me) => {
          if (!alive) return;
          setVisible(me.visible_panels);
          setPermissions(me.permissions || {});
          setLoaded(true);
        })
        .catch(() => {
          // Transient (server not up yet, brief network blip) -- retry
          // rather than leaving the app stuck on its loading state forever.
          if (alive) timer = window.setTimeout(attempt, 2000);
        });
    };
    attempt();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, []);

  return { visible, loaded, permissions };
}
