import { useState } from "react";
import { DueAlarm, useDueAlarms } from "./alarms";

const SNOOZE_OPTIONS = [
  { minutes: 5, label: "5 minutes" },
  { minutes: 10, label: "10 minutes" },
  { minutes: 30, label: "30 minutes" },
  { minutes: 120, label: "2 hours" },
  { minutes: 1440, label: "1 day" },
  { minutes: 2880, label: "2 days" },
  { minutes: 10080, label: "7 days" },
];

function AlarmRow({
  alarm, onSnooze, onClose,
}: {
  alarm: DueAlarm;
  onSnooze: (minutes: number) => void;
  onClose: () => void;
}) {
  const [minutes, setMinutes] = useState(10);
  return (
    <div className="alarm-row">
      <span className="alarm-dot" style={{ background: alarm.calendar_color }} />
      <div className="alarm-info">
        <div className="alarm-title">{alarm.recurring ? "↻ " : ""}{alarm.title}</div>
        <div className="alarm-meta muted small">
          {alarm.calendar_name}
          {!alarm.all_day && alarm.start_time ? ` · ${alarm.start_time}` : ""}
        </div>
      </div>
      <div className="alarm-actions">
        <select value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>
          {SNOOZE_OPTIONS.map((o) => (
            <option key={o.minutes} value={o.minutes}>{o.label}</option>
          ))}
        </select>
        <button className="ghost" onClick={() => onSnooze(minutes)}>Snooze</button>
        <button className="danger" onClick={onClose}>Close</button>
      </div>
    </div>
  );
}

/** Rendered once at the app's top level (see App.tsx) so a due alarm shows
 *  up no matter which panel is open. Deliberately has no backdrop-click /
 *  Escape dismissal -- the only ways off an alarm are its own buttons.
 *  `enabled` should reflect whether the calendar panel is actually visible
 *  to this user -- see useDueAlarms. */
export function AlarmOverlay({ enabled }: { enabled: boolean }) {
  const { due, snooze, dismiss } = useDueAlarms(enabled);
  const [error, setError] = useState<string | null>(null);
  if (due.length === 0) return null;
  return (
    <div className="modal-backdrop alarm-backdrop">
      <div className="modal alarm-modal">
        <h4>🔔 {due.length > 1 ? `${due.length} alarms` : "Alarm"}</h4>
        <div className="alarm-list">
          {due.map((a) => (
            <AlarmRow
              key={a.key}
              alarm={a}
              onSnooze={(minutes) => snooze(a, minutes).catch((e) => setError(String(e)))}
              onClose={() => dismiss(a).catch((e) => setError(String(e)))}
            />
          ))}
        </div>
        {error && <p className="error small">{error}</p>}
      </div>
    </div>
  );
}
