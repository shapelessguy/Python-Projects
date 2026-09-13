// App-wide alarm checking: which events with `alarm` are currently due, and
// the two ways to make one stop being due -- snooze (temporary) or close
// (permanent). Both are persisted through the backend (alarm_snooze_* /
// alarm_ack) rather than a client-side cookie, so snoozing or closing an
// alarm on one device is reflected on every other one polling the same
// calendar. Rendered from App.tsx so it's visible no matter which panel is
// open.
import { useEffect, useMemo, useState } from "react";
import { api, CalendarEvent, useVersionPoll } from "./api";

export interface DueAlarm {
  key: string; // "<id>@<occurrence start_date>" -- stable identity for this occurrence
  id: number;
  title: string;
  calendar_name: string;
  calendar_color: string;
  start_date: string;
  start_time: string | null;
  all_day: boolean;
  recurring: boolean;
}

/** All-day events fire from local midnight of their start_date; timed ones
 *  fire at their start_time. Either way this is just "when did it become
 *  due", not a precise ring instant -- once past, it stays due until acked
 *  or snoozed. */
function dueInstant(e: CalendarEvent): number {
  const time = e.all_day || !e.start_time ? "00:00" : e.start_time;
  return new Date(`${e.start_date}T${time}:00`).getTime();
}

function isAcked(e: CalendarEvent): boolean {
  return e.recurring ? e.alarm_ack === e.start_date : e.alarm_ack === "true";
}

/** Storing *which* occurrence a snooze belongs to (not just a bare
 *  timestamp) is what makes a newer occurrence of a recurring series
 *  immediately override a snooze meant for an older one, rather than
 *  inheriting it -- see calendar.py's _validate_snooze. */
function isSnoozed(e: CalendarEvent, now: number): boolean {
  return (
    e.alarm_snooze_occurrence === e.start_date &&
    e.alarm_snooze_until !== null &&
    e.alarm_snooze_until > now
  );
}

/** A recurring series can appear many times in a month (one row per
 *  occurrence, same id); only the most recent occurrence at-or-before `now`
 *  is ever relevant -- this mirrors the backend's own framing of alarm_ack
 *  ("compared against the series' latest visible occurrence"), so a missed
 *  occurrence from weeks ago never resurfaces once a newer one exists. */
function latestDueOccurrencePerEvent(events: CalendarEvent[], now: number): CalendarEvent[] {
  const latest = new Map<number, CalendarEvent>();
  for (const e of events) {
    if (!e.alarm || dueInstant(e) > now) continue;
    const prev = latest.get(e.id);
    if (!prev || e.start_date > prev.start_date) latest.set(e.id, e);
  }
  return [...latest.values()];
}

export function useDueAlarms() {
  const { calendar } = useVersionPoll();
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [now, setNow] = useState(() => Date.now());

  // The actual "loop every second" -- recomputes `due` below even when
  // nothing in `events` has changed, since simply enough time passing can
  // make something newly due (or a snooze expire).
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  // Recomputed every tick but only actually changes value at local midnight,
  // so this only re-triggers the fetch effect below on a real month rollover
  // (or when `calendar` bumps from an edit anywhere, including another
  // client's snooze/close).
  const month = useMemo(() => new Date(now).toLocaleDateString("en-CA").slice(0, 7), [now]);

  useEffect(() => {
    let alive = true;
    api.calendarMonth(month)
      .then((res) => { if (alive) setEvents(res.events); })
      .catch(() => { /* transient -- keep last known events, retry next trigger */ });
    return () => { alive = false; };
  }, [month, calendar]);

  const due = useMemo<DueAlarm[]>(() => {
    return latestDueOccurrencePerEvent(events, now)
      .filter((e) => !isAcked(e) && !isSnoozed(e, now))
      .map((e) => ({
        key: `${e.id}@${e.start_date}`, id: e.id, title: e.title, calendar_name: e.calendar_name,
        calendar_color: e.calendar_color, start_date: e.start_date, start_time: e.start_time,
        all_day: e.all_day, recurring: e.recurring,
      }))
      .sort((a, b) => a.start_date.localeCompare(b.start_date) || a.id - b.id);
  }, [events, now]);

  // Both actions round-trip through patchEvent, whose reply already carries
  // the fresh month snapshot -- applying that directly keeps every client in
  // sync without waiting for its next version-poll tick.
  const snooze = (a: DueAlarm, minutes: number) =>
    api.patchEvent(a.id, {
      alarm_snooze_occurrence: a.start_date,
      alarm_snooze_until: Date.now() + minutes * 60_000,
    }).then((res) => setEvents(res.events));

  const dismiss = (a: DueAlarm) =>
    api.patchEvent(a.id, {
      alarm_ack: a.recurring ? a.start_date : "true",
      // Nothing left to snooze once it's permanently acknowledged.
      alarm_snooze_occurrence: null,
      alarm_snooze_until: null,
    }).then((res) => setEvents(res.events));

  return { due, snooze, dismiss };
}
