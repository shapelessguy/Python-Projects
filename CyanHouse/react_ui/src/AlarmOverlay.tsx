import { useState } from "react";
import { DueAlarm, useDueAlarms } from "./alarms";
import { Key, useT } from "./i18n";

const SNOOZE_OPTIONS: { minutes: number; label: Key; n: number }[] = [
  { minutes: 5, label: "alarm_minutes", n: 5 },
  { minutes: 10, label: "alarm_minutes", n: 10 },
  { minutes: 30, label: "alarm_minutes", n: 30 },
  { minutes: 120, label: "alarm_hours", n: 2 },
  { minutes: 1440, label: "alarm_day", n: 1 },
  { minutes: 2880, label: "alarm_days", n: 2 },
  { minutes: 10080, label: "alarm_days", n: 7 },
];

function AlarmRow({
  alarm, onSnooze, onClose,
}: {
  alarm: DueAlarm;
  onSnooze: (minutes: number) => void;
  onClose: () => void;
}) {
  const { t } = useT();
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
            <option key={o.minutes} value={o.minutes}>{t(o.label, { n: o.n })}</option>
          ))}
        </select>
        <button className="ghost" onClick={() => onSnooze(minutes)}>{t("alarm_snooze")}</button>
        <button className="danger" onClick={onClose}>{t("close")}</button>
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
  const { t } = useT();
  const { due, snooze, dismiss } = useDueAlarms(enabled);
  const [error, setError] = useState<string | null>(null);
  if (due.length === 0) return null;
  return (
    <div className="modal-backdrop alarm-backdrop">
      <div className="modal alarm-modal">
        <h4>🔔 {due.length > 1 ? t("alarm_many", { n: due.length }) : t("alarm_one")}</h4>
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
