import { CSSProperties, useEffect, useMemo, useRef, useState } from "react";
import { FinExecuted, FinForecast } from "../api";
import { useBackToClose } from "../backClose";
import { readCookie, writeCookie } from "../cookies";
import { useT } from "../i18n";
import { usePhone } from "../narrow";
import {
  addDays, addMonths, dayLabel, isWeekend, monthGrid, monthLabel, weekDays, weekLabel, weekdayNames,
} from "./CalendarPanel";
import { Icon } from "./icons";
import { IconPick } from "./IconPick";

const TODAY = new Date().toLocaleDateString("en-CA");
const VIEW_COOKIE = "finance_view";
type ViewMode = "month" | "week";

/** One payment on the calendar: written (a payment) or still to come (a
 *  forecast's date not written yet — `planned`). */
export type CalEntry = {
  key: string; date: string; kind: "executed" | "forecasts"; planned: boolean; p: FinExecuted | FinForecast;
};
/** What a payment does to one's own money, by which side is an account (a
 *  category of kind "account"): into one from elsewhere is income, out of
 *  one to elsewhere spending, from one to another a transfer; between two
 *  that aren't (a salary straight to a spending) it touches none. */
export type Dir = "in" | "out" | "move" | "none";
export const directionBy = (isAccount: (id: number | null) => boolean) =>
  (p: FinExecuted | FinForecast): Dir => {
    const from = isAccount(p.from_id), to = isAccount(p.to_id);
    return from && to ? "move" : to ? "in" : from ? "out" : "none";
  };
export const DIR_COLOR: Record<Dir, string> = { in: "#3fb950", out: "#f85149", move: "#58a6ff", none: "#8b93a1" };
export const DIR_SIGN: Record<Dir, string> = { in: "+", out: "−", move: "", none: "" };

function addMonthsTo(d: string, months: number): string {
  // As the server's _add_months: the same day, or the month's last if shorter.
  const [y, m, day] = d.split("-").map(Number);
  const last = new Date(y, m - 1 + months + 1, 0).getDate();
  const t = new Date(y, m - 1 + months, Math.min(day, last));
  return t.toLocaleDateString("en-CA");
}

/** A forecast's dates in [from, to] not written yet — each counted from the
 *  start, as the server does, so a monthly on the 31st returns to the 31st. */
function plannedDates(f: FinForecast, from: string, to: string): string[] {
  const out: string[] = [];
  const after = f.generated_until ?? "";
  for (let k = 0; ; k++) {
    let d: string;
    if (!f.recur_freq) d = f.start_date;
    else if (f.recur_freq === "daily" || f.recur_freq === "weekly")
      d = addDays(f.start_date, k * f.recur_interval * (f.recur_freq === "daily" ? 1 : 7));
    else d = addMonthsTo(f.start_date, k * f.recur_interval * (f.recur_freq === "monthly" ? 1 : 12));
    if (d > to || (f.recur_until && d > f.recur_until)) break;
    if (d >= from && d > after) out.push(d);
    if (!f.recur_freq) break;
  }
  return out;
}

/** The Finance page: the payments on a month or a week, as Calendar's (the
 *  same bar, views and swipe). Forecasts' dates still to come show too,
 *  dashed. A day's "+" (or its window's, on a phone) adds one on that day;
 *  a payment opens it in the Payments list. */
export function FinanceCalendar({ executed, forecasts, direction, money, title, onAdd, onOpen }: {
  executed: FinExecuted[]; forecasts: FinForecast[]; direction: (p: FinExecuted | FinForecast) => Dir;
  money: (p: FinExecuted | FinForecast) => string;
  /** What a payment is called on the calendar: its reason, else the other side's name. */
  title: (p: FinExecuted | FinForecast) => string;
  onAdd: (date: string) => void; onOpen: (e: CalEntry) => void;
}) {
  const { t, lang } = useT();
  const narrow = usePhone();
  const [view, setViewState] = useState<ViewMode>(() => (readCookie(VIEW_COOKIE) === "week" ? "week" : "month"));
  const setView = (v: ViewMode) => { setViewState(v); writeCookie(VIEW_COOKIE, v); };
  const [anchor, setAnchor] = useState(TODAY);
  const [openDay, setOpenDay] = useState<string | null>(null);
  useBackToClose(() => setOpenDay(null), openDay != null);
  const touchAt = useRef<{ x: number; y: number } | null>(null);

  // Down to the bottom of the screen, as Calendar's.
  const bodyRef = useRef<HTMLDivElement>(null);
  const [bodyHeight, setBodyHeight] = useState(480);
  useEffect(() => {
    const measure = () => {
      const el = bodyRef.current;
      if (el) setBodyHeight(Math.max(240, window.innerHeight - el.getBoundingClientRect().top - 32));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(document.body);
    window.addEventListener("resize", measure);
    return () => { ro.disconnect(); window.removeEventListener("resize", measure); };
  }, [view]);

  const days = view === "month" ? monthGrid(anchor.slice(0, 7)) : weekDays(anchor);
  const first = days[0], last = days[days.length - 1];
  const byDate = useMemo(() => {
    const m: Record<string, CalEntry[]> = {};
    const put = (e: CalEntry) => { (m[e.date] ??= []).push(e); };
    for (const p of executed) if (p.date >= first && p.date <= last)
      put({ key: `x${p.id}`, date: p.date, kind: "executed", planned: false, p });
    for (const f of forecasts) for (const d of plannedDates(f, first, last))
      put({ key: `f${f.id}-${d}`, date: d, kind: "forecasts", planned: true, p: f });
    return m;
  }, [executed, forecasts, first, last]);

  const goPrev = () => setAnchor((a) => (view === "month" ? addMonths(a, -1) : addDays(a, -7)));
  const goNext = () => setAnchor((a) => (view === "month" ? addMonths(a, 1) : addDays(a, 7)));
  const headerLabel = view === "month" ? monthLabel(anchor.slice(0, 7), lang) : weekLabel(days, lang);

  const chip = (e: CalEntry, big = false) => {
    const dir = direction(e.p);
    return (
      <button key={e.key} className={"cal-event fin-cal-event" + (e.planned ? " planned" : "") + (big ? " big" : "")}
              style={{ borderLeftColor: DIR_COLOR[dir], "--cal-color": DIR_COLOR[dir] } as CSSProperties}
              title={`${DIR_SIGN[dir]}${money(e.p)} ${title(e.p)}`}
              onClick={(ev) => { ev.stopPropagation(); setOpenDay(null); onOpen(e); }}>
        <span className="fin-cal-amount" style={{ color: DIR_COLOR[dir] }}>{e.planned ? "↻ " : ""}{DIR_SIGN[dir]}{money(e.p)}</span>
        <span className="fin-cal-title">{title(e.p)}</span>
      </button>
    );
  };

  return (
    <div className="fin-calendar">
      <div className="month-nav">
        <button onClick={goPrev}>◀</button>
        <h2 className="go-today" role="button" tabIndex={0} title={t("env_today")} onClick={() => setAnchor(TODAY)}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setAnchor(TODAY); } }}>
          {headerLabel}
        </h2>
        <button onClick={goNext}>▶</button>
        <div className="cal-view-toggle">
          {narrow ? (
            <IconPick
              choices={(["month", "week"] as const).map((v) => ({
                key: v, label: t(v === "month" ? "cal_month" : "cal_week"), icon: <Icon name={v} className="" />,
              }))}
              value={view} onChange={(v) => setView(v as ViewMode)}
            />
          ) : <>
            <button className={view === "month" ? "active" : ""} title={t("cal_month")} onClick={() => setView("month")}>
              <span className="nav-text">{t("cal_month")}</span><Icon name="month" />
            </button>
            <button className={view === "week" ? "active" : ""} title={t("cal_week")} onClick={() => setView("week")}>
              <span className="nav-text">{t("cal_week")}</span><Icon name="week" />
            </button>
          </>}
        </div>
      </div>

      <div
        className="cal-body" ref={bodyRef} style={{ height: bodyHeight }}
        onTouchStart={(e) => { touchAt.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }; }}
        onTouchEnd={(e) => {
          if (touchAt.current === null) return;
          const dx = e.changedTouches[0].clientX - touchAt.current.x;
          const dy = e.changedTouches[0].clientY - touchAt.current.y;
          touchAt.current = null;
          if (Math.abs(dx) > 70 && Math.abs(dx) > 2 * Math.abs(dy)) (dx < 0 ? goNext : goPrev)();
        }}
      >
        {view === "month" ? <>
          <div className="cal-weekdays">
            {weekdayNames(lang).map((d, i) => <div key={i} className={i >= 5 ? "weekend" : ""}>{d}</div>)}
          </div>
          <div className="cal-grid">
            {days.map((date) => (
              <div key={date}
                   className={"cal-day" + (date.slice(0, 7) === anchor.slice(0, 7) ? "" : " out") +
                     (date === TODAY ? " today" : "") + (isWeekend(date) ? " weekend" : "")}
                   onClick={narrow ? () => setOpenDay(date) : undefined}
                   onDoubleClick={narrow ? undefined : (e) => e.target === e.currentTarget && setOpenDay(date)}>
                <div className="cal-day-head">
                  <span className="cal-daynum">{Number(date.slice(8))}</span>
                  <button className="cal-add" title={t("fin_new")} onClick={() => onAdd(date)}>+</button>
                </div>
                <div className="cal-events">{(byDate[date] ?? []).map((e) => chip(e))}</div>
              </div>
            ))}
          </div>
        </> : (
          // A week: a column a day (a row a day on a phone), each with its payments in full.
          <div className="fin-week">
            {days.map((date) => {
              const { weekday, num } = dayLabel(date, lang);
              const list = byDate[date] ?? [];
              return (
                <div key={date} className={"fin-week-day" + (date === TODAY ? " today" : "") + (isWeekend(date) ? " weekend" : "")}>
                  <div className="fin-week-head">
                    <span className="fin-week-label">{weekday} <b>{num}</b></span>
                    <button className="cal-add fin-week-add" title={t("fin_new")} onClick={() => onAdd(date)}>+</button>
                  </div>
                  <div className="fin-week-list">
                    {list.map((e) => chip(e, true))}
                    {!list.length && <span className="fin-week-empty">{t("fin_no_payments_day")}</span>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {openDay && (
        <div className="modal-backdrop" onClick={() => setOpenDay(null)}>
          <div className="modal cal-agenda" onClick={(e) => e.stopPropagation()}>
            <div className="cal-agenda-head">
              <span>{new Date(openDay + "T00:00:00").toLocaleDateString(lang, { weekday: "long", day: "numeric", month: "long" })}</span>
              <button className="ghost fin-add" title={t("fin_new")} aria-label={t("fin_new")}
                      onClick={() => { const d = openDay; setOpenDay(null); onAdd(d); }}>+</button>
            </div>
            {!(byDate[openDay] ?? []).length && <p className="muted small">{t("fin_no_payments")}</p>}
            {(byDate[openDay] ?? []).map((e) => chip(e, true))}
          </div>
        </div>
      )}
    </div>
  );
}
