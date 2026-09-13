import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, CalendarEvent, EventInput, RecurFreq, useVersionPoll } from "../api";

const TODAY = new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD, local
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const HOUR_HEIGHT = 48; // px per hour row in the week grid

type ViewMode = "month" | "week";

function addDays(date: string, delta: number): string {
  const d = new Date(date + "T00:00:00");
  d.setDate(d.getDate() + delta);
  return d.toLocaleDateString("en-CA");
}

function addMonths(date: string, delta: number): string {
  const [y, m] = date.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

function startOfWeek(date: string): string {
  const d = new Date(date + "T00:00:00");
  d.setDate(d.getDate() - d.getDay());
  return d.toLocaleDateString("en-CA");
}

/** 6 weeks (42 days) covering the month, padded with adjacent months so the
 *  grid always starts on a Sunday. */
function monthGrid(monthStr: string): string[] {
  const [y, m] = monthStr.split("-").map(Number);
  const first = new Date(y, m - 1, 1);
  const start = new Date(y, m - 1, 1 - first.getDay()).toLocaleDateString("en-CA");
  return Array.from({ length: 42 }, (_, i) => addDays(start, i));
}

function weekDays(anchor: string): string[] {
  const start = startOfWeek(anchor);
  return Array.from({ length: 7 }, (_, i) => addDays(start, i));
}

function monthLabel(monthStr: string): string {
  const [y, m] = monthStr.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleString(undefined, { month: "long", year: "numeric" });
}

function weekLabel(days: string[]): string {
  const fmt = (d: string, withYear: boolean) =>
    new Date(d + "T00:00:00").toLocaleDateString(
      undefined,
      withYear ? { month: "short", day: "numeric", year: "numeric" } : { month: "short", day: "numeric" },
    );
  return `${fmt(days[0], false)} – ${fmt(days[6], true)}`;
}

function dayLabel(d: string): { weekday: string; num: number } {
  const dt = new Date(d + "T00:00:00");
  return { weekday: dt.toLocaleDateString(undefined, { weekday: "short" }), num: dt.getDate() };
}

function toMinutes(t: string): number {
  const [h, m] = t.split(":").map(Number);
  return h * 60 + m;
}

/** Distinct YYYY-MM months covered by a list of ISO dates — a week can
 *  straddle two months, so the caller may need to fetch both. */
function monthsOf(days: string[]): string[] {
  return [...new Set(days.map((d) => d.slice(0, 7)))];
}

const RECUR_LABELS: Record<RecurFreq, string> = {
  daily: "Daily", weekly: "Weekly", monthly: "Monthly", yearly: "Yearly",
};

interface Draft {
  id?: number;
  mine: boolean;
  owner?: string;
  start_date: string;
  end_date: string;
  title: string;
  description: string;
  all_day: boolean;
  start_time: string;
  end_time: string;
  shared: boolean;
  recur_freq: RecurFreq | "";
  recur_interval: number;
  recur_until: string;
}

const blankDraft = (date: string, start = "09:00", end = "10:00", allDay = true): Draft => ({
  mine: true, start_date: date, end_date: date, title: "", description: "",
  all_day: allDay, start_time: start, end_time: end, shared: false,
  recur_freq: "", recur_interval: 1, recur_until: "",
});

const draftFromEvent = (e: CalendarEvent): Draft => ({
  id: e.id, mine: e.mine, owner: e.owner, start_date: e.start_date, end_date: e.end_date,
  title: e.title, description: e.description,
  all_day: e.all_day, start_time: e.start_time ?? "09:00", end_time: e.end_time ?? "10:00", shared: e.shared,
  recur_freq: e.recur_freq ?? "", recur_interval: e.recur_interval, recur_until: e.recur_until ?? "",
});

/** Client-side mirror of the backend's _validate_span/_validate_recurrence,
 *  so the form can block submission and explain why instead of
 *  round-tripping a 400. */
function draftValidationError(d: Draft): string | null {
  if (d.end_date < d.start_date) return "End date must not be before start date.";
  if (!d.all_day && d.end_date === d.start_date && d.end_time <= d.start_time) {
    return "End time must be after start time.";
  }
  if (d.recur_freq && d.recur_until && d.recur_until < d.start_date) {
    return "Repeat-until date must not be before start date.";
  }
  return null;
}

const VIEW_KEY = "calendar.view";

function loadView(): ViewMode {
  try {
    const v = localStorage.getItem(VIEW_KEY);
    if (v === "month" || v === "week") return v;
  } catch {
    /* private mode / disabled storage */
  }
  return "month";
}

export function CalendarPanel() {
  const { calendar } = useVersionPoll();
  const [view, setViewState] = useState<ViewMode>(loadView);
  const setView = (v: ViewMode) => {
    setViewState(v);
    try {
      localStorage.setItem(VIEW_KEY, v);
    } catch {
      /* ignore */
    }
  };
  const [anchor, setAnchor] = useState(TODAY);
  const [events, setEvents] = useState<CalendarEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const appliedVersion = useRef(-1);

  const days = useMemo(
    () => (view === "month" ? monthGrid(anchor.slice(0, 7)) : weekDays(anchor)),
    [view, anchor],
  );
  const neededKey = useMemo(() => monthsOf(days).join(","), [days]);

  const load = useCallback(() => {
    const months = neededKey.split(",");
    Promise.all(months.map((m) => api.calendarMonth(m)))
      .then((results) => {
        const merged: CalendarEvent[] = [];
        for (const r of results) merged.push(...r.events);
        setEvents(merged);
        // calendar_version is a single global counter, identical on every
        // month's reply, so any one of them is the current version.
        appliedVersion.current = results[0]?.calendar_version ?? 0;
        setError(null);
      })
      .catch((e) => setError(String(e)));
  }, [neededKey]);

  useEffect(() => load(), [load]);

  // React only to a calendar version we haven't already applied ourselves —
  // same guard PersonalPanel uses against its own diary version.
  const seenVersion = useRef(0);
  useEffect(() => {
    if (calendar === seenVersion.current) return;
    seenVersion.current = calendar;
    if (events && calendar !== appliedVersion.current) load();
  }, [calendar, events, load]);

  // Expand each event's [start_date, end_date] span across every visible day
  // it touches, clamped to what's actually on screen.
  const eventsByDate = useMemo(() => {
    const g: Record<string, CalendarEvent[]> = {};
    const visible = new Set(days);
    for (const e of events ?? []) {
      let d = e.start_date;
      while (d <= e.end_date) {
        if (visible.has(d)) (g[d] ||= []).push(e);
        d = addDays(d, 1);
      }
    }
    return g;
  }, [events, days]);

  const draftError = draft ? draftValidationError(draft) : null;

  const saveDraft = () => {
    if (!draft || !draft.title.trim() || draftError) return;
    const body: EventInput = {
      title: draft.title.trim(),
      description: draft.description,
      start_date: draft.start_date,
      end_date: draft.end_date,
      all_day: draft.all_day,
      start_time: draft.all_day ? null : draft.start_time,
      end_time: draft.all_day ? null : draft.end_time,
      shared: draft.shared,
      recur_freq: draft.recur_freq || null,
      recur_interval: draft.recur_interval,
      recur_until: draft.recur_freq ? draft.recur_until || null : null,
    };
    const req = draft.id ? api.patchEvent(draft.id, body) : api.createEvent(body);
    req.then(() => { load(); setDraft(null); }).catch((e) => setError(String(e)));
  };

  // For a plain event these are the same thing; for a recurring one,
  // deleteThisOccurrence only adds an exception (the rest of the series is
  // untouched) while deleteSeries removes the whole row.
  const deleteThisOccurrence = () => {
    if (!draft?.id) return;
    api.deleteEvent(draft.id, draft.start_date).then(() => { load(); setDraft(null); }).catch((e) => setError(String(e)));
  };
  const deleteSeries = () => {
    if (!draft?.id) return;
    api.deleteEvent(draft.id).then(() => { load(); setDraft(null); }).catch((e) => setError(String(e)));
  };

  if (error) return <div className="panel"><p className="error">{error}</p></div>;
  if (!events) return <div className="panel"><p className="muted">Loading…</p></div>;

  const headerLabel = view === "month" ? monthLabel(anchor.slice(0, 7)) : weekLabel(days);
  const goPrev = () => setAnchor((a) => (view === "month" ? addMonths(a, -1) : addDays(a, -7)));
  const goNext = () => setAnchor((a) => (view === "month" ? addMonths(a, 1) : addDays(a, 7)));

  return (
    <div className="panel calendar">
      <div className="calendar-main">
        <div className="month-nav">
          <button onClick={goPrev}>◀</button>
          <h2>{headerLabel}</h2>
          <button onClick={goNext}>▶</button>
          <button className="ghost" onClick={() => setAnchor(TODAY)}>Today</button>
          <div className="cal-view-toggle">
            <button className={view === "month" ? "active" : ""} onClick={() => setView("month")}>Month</button>
            <button className={view === "week" ? "active" : ""} onClick={() => setView("week")}>Week</button>
          </div>
        </div>

        {view === "month" ? (
          <>
            <div className="cal-weekdays">
              {WEEKDAYS.map((d) => <div key={d}>{d}</div>)}
            </div>
            <div className="cal-grid">
              {days.map((date) => {
                const inMonth = date.slice(0, 7) === anchor.slice(0, 7);
                const dayEvents = eventsByDate[date] ?? [];
                return (
                  <div key={date} className={"cal-day" + (inMonth ? "" : " out") + (date === TODAY ? " today" : "")}>
                    <div className="cal-day-head">
                      <span className="cal-daynum">{Number(date.slice(8))}</span>
                      <button className="cal-add" title="Add event" onClick={() => setDraft(blankDraft(date))}>
                        +
                      </button>
                    </div>
                    <div className="cal-events">
                      {dayEvents.map((e) => (
                        <button
                          key={e.id}
                          className={"cal-event" + (e.shared ? " shared" : " personal")}
                          onClick={() => setDraft(draftFromEvent(e))}
                          title={e.mine ? e.title : `${e.title} (by ${e.owner})`}
                        >
                          {e.recurring ? "↻ " : ""}
                          {!e.all_day && e.start_date === e.end_date && e.start_time ? `${e.start_time} ` : ""}
                          {e.title}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        ) : (
          <WeekGrid
            days={days}
            eventsByDate={eventsByDate}
            onAdd={(date, start, end) => setDraft(blankDraft(date, start, end, false))}
            onOpen={(e) => setDraft(draftFromEvent(e))}
          />
        )}
      </div>

      {draft && (
        <div className="modal-backdrop" onClick={() => setDraft(null)}>
          <div className="modal event-form" onClick={(e) => e.stopPropagation()}>
            <h4>
              {draft.id ? (draft.mine ? "Edit event" : `By ${draft.owner}`) : "New event"}
            </h4>
            <label className="field">
              Title
              <input
                value={draft.title}
                disabled={!draft.mine}
                onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                autoFocus
              />
            </label>
            <label className="field">
              Description
              <textarea
                value={draft.description}
                disabled={!draft.mine}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              />
            </label>
            <label className="check-row">
              <input
                type="checkbox"
                checked={draft.all_day}
                disabled={!draft.mine}
                onChange={(e) => setDraft({ ...draft, all_day: e.target.checked })}
              />
              All day
            </label>
            <div className="field">
              Start
              <div className="dates">
                <input
                  type="date"
                  value={draft.start_date}
                  disabled={!draft.mine}
                  onChange={(e) => setDraft({ ...draft, start_date: e.target.value })}
                />
                {!draft.all_day && (
                  <input
                    type="time"
                    value={draft.start_time}
                    disabled={!draft.mine}
                    onChange={(e) => setDraft({ ...draft, start_time: e.target.value })}
                  />
                )}
              </div>
            </div>
            <div className="field">
              End
              <div className="dates">
                <input
                  type="date"
                  value={draft.end_date}
                  disabled={!draft.mine}
                  onChange={(e) => setDraft({ ...draft, end_date: e.target.value })}
                />
                {!draft.all_day && (
                  <input
                    type="time"
                    value={draft.end_time}
                    disabled={!draft.mine}
                    onChange={(e) => setDraft({ ...draft, end_time: e.target.value })}
                  />
                )}
              </div>
            </div>
            <label className="check-row">
              <input
                type="checkbox"
                checked={draft.shared}
                disabled={!draft.mine}
                onChange={(e) => setDraft({ ...draft, shared: e.target.checked })}
              />
              Shared with everyone
            </label>
            <div className="field">
              Repeat
              <select
                value={draft.recur_freq}
                disabled={!draft.mine}
                onChange={(e) => setDraft({ ...draft, recur_freq: e.target.value as RecurFreq | "" })}
              >
                <option value="">Doesn't repeat</option>
                {(Object.keys(RECUR_LABELS) as RecurFreq[]).map((f) => (
                  <option key={f} value={f}>{RECUR_LABELS[f]}</option>
                ))}
              </select>
            </div>
            {draft.recur_freq && (
              <div className="field">
                Every / until
                <div className="dates">
                  <input
                    type="number"
                    min={1}
                    value={draft.recur_interval}
                    disabled={!draft.mine}
                    onChange={(e) => setDraft({ ...draft, recur_interval: Math.max(1, Number(e.target.value)) })}
                  />
                  <input
                    type="date"
                    value={draft.recur_until}
                    disabled={!draft.mine}
                    placeholder="never"
                    onChange={(e) => setDraft({ ...draft, recur_until: e.target.value })}
                  />
                </div>
                {draft.mine && (
                  <p className="muted small">
                    {draft.recur_interval > 1
                      ? `Every ${draft.recur_interval} ${draft.recur_freq === "daily" ? "days" : draft.recur_freq === "weekly" ? "weeks" : draft.recur_freq === "monthly" ? "months" : "years"}`
                      : RECUR_LABELS[draft.recur_freq]}
                    {draft.recur_until ? `, until ${draft.recur_until}` : ", no end date"}.
                    Editing or deleting applies to the whole series.
                  </p>
                )}
              </div>
            )}
            {draft.mine && draftError && <p className="error small">{draftError}</p>}
            <div className="row-actions">
              {draft.mine && (
                <button onClick={saveDraft} disabled={!draft.title.trim() || !!draftError}>
                  {draft.id ? "Save" : "Add"}
                </button>
              )}
              {draft.mine && draft.id && (
                draft.recur_freq ? (
                  <>
                    <button className="danger" onClick={deleteThisOccurrence}>Delete this event</button>
                    <button className="danger" onClick={deleteSeries}>Delete series</button>
                  </>
                ) : (
                  <button className="danger" onClick={deleteSeries}>Delete</button>
                )
              )}
              <button className="ghost" onClick={() => setDraft(null)}>
                {draft.mine ? "Cancel" : "Close"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function WeekGrid({
  days, eventsByDate, onAdd, onOpen,
}: {
  days: string[];
  eventsByDate: Record<string, CalendarEvent[]>;
  onAdd: (date: string, start: string, end: string) => void;
  onOpen: (e: CalendarEvent) => void;
}) {
  const hours = useMemo(() => Array.from({ length: 24 }, (_, i) => i), []);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrollbarWidth, setScrollbarWidth] = useState(0);
  const [scrollHeight, setScrollHeight] = useState(480);

  // Land the scroll around 7am by default rather than midnight — most
  // events happen later in the day and this avoids opening on empty space.
  // Also measure the scrollbar's width: the hour grid always overflows
  // vertically (24h of rows in a capped-height box) so it always has one,
  // but the head/all-day rows above it don't scroll and so don't lose that
  // width — without compensating, their 7 day columns end up slightly wider
  // than the grid's, drifting out of alignment further right each column.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: 7 * HOUR_HEIGHT });
    setScrollbarWidth(el.offsetWidth - el.clientWidth);
  }, []);

  // Stretch the grid down to the bottom of the viewport (minus a little
  // breathing room) instead of stopping at a fixed height — remeasured on
  // resize and whenever the rows above it (the all-day banner especially)
  // might have changed height and shifted where the grid itself starts.
  useEffect(() => {
    const measure = () => {
      const el = scrollRef.current;
      if (!el) return;
      const top = el.getBoundingClientRect().top;
      setScrollHeight(Math.max(240, window.innerHeight - top - 16));
    };
    measure();
    const raf = requestAnimationFrame(measure);
    window.addEventListener("resize", measure);
    return () => {
      window.removeEventListener("resize", measure);
      cancelAnimationFrame(raf);
    };
  }, [eventsByDate]);

  const handleColumnClick = (date: string, ev: React.MouseEvent<HTMLDivElement>) => {
    const rect = ev.currentTarget.getBoundingClientRect();
    const hour = Math.max(0, Math.min(23, Math.floor((ev.clientY - rect.top) / HOUR_HEIGHT)));
    const pad = (n: number) => String(n).padStart(2, "0");
    onAdd(date, `${pad(hour)}:00`, `${pad(Math.min(23, hour + 1))}:00`);
  };

  // Multi-day events (whether all_day or not) can't be meaningfully placed
  // at a specific hour, so they live in the all-day banner alongside true
  // all-day events; only a single-day timed event gets an hourly block.
  const isBanner = (e: CalendarEvent) => e.all_day || e.start_date !== e.end_date;
  const isTimedSingleDay = (e: CalendarEvent) =>
    !e.all_day && e.start_date === e.end_date && !!e.start_time && !!e.end_time;

  return (
    <div className="cal-week">
      <div className="cal-week-head" style={{ paddingRight: scrollbarWidth }}>
        <div className="cal-week-gutter" />
        {days.map((date) => {
          const { weekday, num } = dayLabel(date);
          return (
            <div key={date} className={"cal-week-daylabel" + (date === TODAY ? " today" : "")}>
              {weekday} <span className="cal-week-num">{num}</span>
            </div>
          );
        })}
      </div>

      <div className="cal-week-allday" style={{ paddingRight: scrollbarWidth }}>
        <div className="cal-week-gutter cal-allday-label">All day</div>
        {days.map((date) => (
          <div key={date} className="cal-week-allday-col">
            {(eventsByDate[date] ?? []).filter(isBanner).map((e) => (
              <button
                key={e.id}
                className={"cal-event" + (e.shared ? " shared" : " personal")}
                onClick={() => onOpen(e)}
                title={e.mine ? e.title : `${e.title} (by ${e.owner})`}
              >
                {e.recurring ? "↻ " : ""}
                {e.title}
              </button>
            ))}
          </div>
        ))}
      </div>

      <div className="cal-week-scroll" ref={scrollRef} style={{ maxHeight: scrollHeight }}>
        <div className="cal-week-grid" style={{ height: 24 * HOUR_HEIGHT }}>
          <div className="cal-week-gutter cal-hour-labels">
            {hours.map((h) => (
              <div key={h} className="cal-hour-label" style={{ height: HOUR_HEIGHT }}>
                {String(h).padStart(2, "0")}:00
              </div>
            ))}
          </div>
          {days.map((date) => (
            <div key={date} className="cal-week-col" onClick={(ev) => handleColumnClick(date, ev)}>
              {hours.map((h) => (
                <div key={h} className="cal-hour-line" style={{ top: h * HOUR_HEIGHT }} />
              ))}
              {(eventsByDate[date] ?? [])
                .filter(isTimedSingleDay)
                .map((e) => {
                  const top = (toMinutes(e.start_time!) / 60) * HOUR_HEIGHT;
                  const height = Math.max(18, ((toMinutes(e.end_time!) - toMinutes(e.start_time!)) / 60) * HOUR_HEIGHT);
                  return (
                    <button
                      key={e.id}
                      className={"cal-week-event" + (e.shared ? " shared" : " personal")}
                      style={{ top, height }}
                      onClick={(ev) => { ev.stopPropagation(); onOpen(e); }}
                      title={e.mine ? e.title : `${e.title} (by ${e.owner})`}
                    >
                      <span className="cal-week-event-time">{e.start_time}</span> {e.recurring ? "↻ " : ""}{e.title}
                    </button>
                  );
                })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
