// A 24-hour time as plain text with a clock icon, like the date field beside
// it; tapping it brings up a small overlay: an hour, then the minutes.
import { useState } from "react";
import { useBackToClose } from "../backClose";
import { useT } from "../i18n";
import { Icon } from "./icons";

const HOURS = Array.from({ length: 24 }, (_, h) => h);
const MINUTES = Array.from({ length: 12 }, (_, i) => i * 5);
const pad = (n: number) => String(n).padStart(2, "0");

function TimeOverlay({ value, onPick, onClose }: {
  value: string; onPick: (v: string) => void; onClose: () => void;
}) {
  const { t } = useT();
  const [h0, m0] = value.split(":").map(Number);
  const [hour, setHour] = useState(h0);
  useBackToClose(onClose);
  return (
    <div
      className="modal-backdrop time-overlay-backdrop"
      // Inside the event form: a click here must not reach the form's own backdrop.
      onClick={(e) => { e.stopPropagation(); if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="modal time-overlay">
        <div className="time-overlay-now">{pad(hour)}:{pad(m0)}</div>
        <div className="muted small">{t("cal_hour")}</div>
        <div className="time-grid hours">
          {HOURS.map((h) => (
            <button key={h} className={h === hour ? "" : "ghost"} onClick={() => setHour(h)}>{pad(h)}</button>
          ))}
        </div>
        <div className="muted small">{t("cal_minutes")}</div>
        <div className="time-grid minutes">
          {MINUTES.map((m) => (
            <button key={m} className={m === m0 ? "" : "ghost"} onClick={() => onPick(`${pad(hour)}:${pad(m)}`)}>
              :{pad(m)}
            </button>
          ))}
        </div>
        <div className="row-actions">
          <button onClick={() => onPick(`${pad(hour)}:${pad(m0)}`)}>{t("cal_set")}</button>
          <button className="ghost" onClick={onClose}>{t("cancel")}</button>
        </div>
      </div>
    </div>
  );
}

export function TimeField({ value, disabled, onChange }: {
  value: string; disabled?: boolean; onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className="time-field" disabled={disabled} onClick={() => setOpen(true)}>
        <span>{value}</span>
        <Icon name="clock" size={15} className="time-field-icon" />
      </button>
      {open && (
        <TimeOverlay
          value={value}
          onPick={(v) => { onChange(v); setOpen(false); }}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
