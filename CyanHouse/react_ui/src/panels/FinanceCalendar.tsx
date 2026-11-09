import { CSSProperties, ReactNode, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Currency, FinCategory, FinExecuted, FinForecast, finTotal } from "../api";
import { useBackToClose } from "../backClose";
import { readCookie, writeCookie } from "../cookies";
import { num, useT } from "../i18n";
import { usePhone } from "../narrow";
import {
  addDays, addMonths, dayLabel, isWeekend, monthGrid, monthLabel, weekDays, weekLabel, weekdayNames,
} from "./CalendarPanel";
import { Floating } from "./Floating";
import { Icon } from "./icons";
import { IconPick } from "./IconPick";

const TODAY = new Date().toLocaleDateString("en-CA");
const VIEW_COOKIE = "finance_view";
const UNIT_COOKIE = "finance_unit";
type ViewMode = "month" | "week";

/** One payment on the calendar: written (a payment) or still to come (a
 *  forecast's date not written yet — `planned`). */
export type CalEntry = {
  key: string; date: string; kind: "executed" | "forecasts"; planned: boolean; p: FinExecuted | FinForecast;
};
/** What a payment does to one's own money (the categories of kind
 *  "account"): what its accounts gained on the To side less what they lost
 *  on the From side. More: income, by that much; less: spending, by that
 *  much; even, with accounts in it: a transfer, of its total; no account in
 *  it (a salary straight to a spending): it touches none, its total. */
export type Dir = "in" | "out" | "move" | "none";
export type Effect = { dir: Dir; cents: number };
export const effectBy = (isAccount: (id: number | null) => boolean) =>
  (p: FinExecuted | FinForecast): Effect => {
    let net = 0, accounts = false;
    for (const l of p.lines) {
      if (!isAccount(l.category_id)) continue;
      accounts = true;
      net += l.side === "to" ? l.amount_cents : -l.amount_cents;
    }
    if (net > 0) return { dir: "in", cents: net };
    if (net < 0) return { dir: "out", cents: -net };
    return { dir: accounts ? "move" : "none", cents: finTotal(p) };
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
export function plannedDates(f: FinForecast, from: string, to: string): string[] {
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
export function FinanceCalendar({ executed, forecasts, accounts, effect, money, convert, title, flow, label, onAdd, onOpen, onAccount }: {
  executed: FinExecuted[]; forecasts: FinForecast[]; effect: (p: FinExecuted | FinForecast) => Effect;
  /** An amount of the payment's currency, written out. */
  money: (cents: number, currency: Currency) => string;
  /** An amount put into another currency at the rate of `date` (null: no rate to go by). */
  convert: (cents: number, from: Currency, to: Currency, date: string) => number | null;
  /** The categories of kind "account", whose balances the bar under the calendar shows. */
  accounts: FinCategory[];
  /** A category as drawn there: its icon, or its name when it has none. */
  label: (id: number) => ReactNode;
  /** A payment in words, for its tooltip: its reason, else the other side's names. */
  title: (p: FinExecuted | FinForecast) => string;
  /** From → To, as icons where the categories have one. */
  flow: (p: FinExecuted | FinForecast) => ReactNode;
  onAdd: (date: string) => void; onOpen: (e: CalEntry) => void;
  /** An account in the bar tapped: its payments. */
  onAccount: (id: number) => void;
}) {
  const { t, lang } = useT();
  const narrow = usePhone();
  const [view, setViewState] = useState<ViewMode>(() => (readCookie(VIEW_COOKIE) === "week" ? "week" : "month"));
  const setView = (v: ViewMode) => { setViewState(v); writeCookie(VIEW_COOKIE, v); };
  // The currency the bar's sums are worked out in (picked at the top, remembered).
  const [unit, setUnitState] = useState<Currency>(() => (readCookie(UNIT_COOKIE) === "USD" ? "USD" : "EUR"));
  const setUnit = (c: Currency) => { setUnitState(c); writeCookie(UNIT_COOKIE, c); };
  const [anchor, setAnchor] = useState(TODAY);
  const [openDay, setOpenDay] = useState<string | null>(null);
  useBackToClose(() => setOpenDay(null), openDay != null);
  const touchAt = useRef<{ x: number; y: number } | null>(null);

  // Down to the bottom of the screen, as Calendar's, less the bar under it.
  const bodyRef = useRef<HTMLDivElement>(null);
  const footRef = useRef<HTMLDivElement>(null);
  const [bodyHeight, setBodyHeight] = useState(480);
  useEffect(() => {
    const measure = () => {
      const el = bodyRef.current, foot = footRef.current?.offsetHeight ?? 0;
      if (el) setBodyHeight(Math.max(240, window.innerHeight - el.getBoundingClientRect().top - 32 - foot));
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

  // The bar under the calendar, for the period shown (the month, or the
  // week): each account's balance at its end, and its income and spending —
  // both counting the forecasts' dates still to come, as the calendar does.
  // All in the picked currency (`unit`): a balance's other money at the rate
  // of the period's end (what it's worth then), a payment's at the rate of
  // its own day. Money with no rate to go by stays in its own currency.
  const periodStart = view === "month" ? anchor.slice(0, 7) + "-01" : first;
  const periodEnd = view === "month"
    ? (() => { const [y, m] = anchor.split("-").map(Number); return new Date(y, m, 0).toLocaleDateString("en-CA"); })()
    : last;
  const summary = useMemo(() => {
    const ids = new Set(accounts.map((a) => a.id));
    const balance = new Map<number, Partial<Record<Currency, number>>>();
    const flows: Record<"in" | "out", Partial<Record<Currency, number>>> = { in: {}, out: {} };
    const count = (p: FinExecuted | FinForecast, date: string) => {
      for (const l of p.lines) if (l.category_id != null && ids.has(l.category_id)) {
        const b = balance.get(l.category_id) ?? {};
        b[p.currency] = (b[p.currency] ?? 0) + (l.side === "to" ? l.amount_cents : -l.amount_cents);
        balance.set(l.category_id, b);
      }
      if (date >= periodStart) {
        const { dir, cents } = effect(p);
        if (dir === "in" || dir === "out") {
          const v = convert(cents, p.currency, unit, date), cur = v == null ? p.currency : unit;
          flows[dir][cur] = (flows[dir][cur] ?? 0) + (v ?? cents);
        }
      }
    };
    for (const p of executed) if (p.date <= periodEnd) count(p, p.date);
    for (const f of forecasts) for (const d of plannedDates(f, "", periodEnd)) count(f, d);
    const inUnit = (by: Partial<Record<Currency, number>>, date: string) => {
      const out: Partial<Record<Currency, number>> = {};
      for (const [cur, c] of Object.entries(by) as [Currency, number][]) {
        const v = convert(c, cur, unit, date);
        if (v == null) out[cur] = (out[cur] ?? 0) + c;
        else out[unit] = (out[unit] ?? 0) + v;
      }
      return out;
    };
    for (const [id, b] of balance) balance.set(id, inUnit(b, periodEnd));
    return { balance, flows };
  }, [executed, forecasts, accounts, effect, convert, unit, periodStart, periodEnd]);
  // On a phone, above 200 (either way) whole units only: the bar is narrow.
  const sum = (cents: number, cur: Currency) => narrow && Math.abs(cents) > 20000
    ? num(Math.round(cents / 100), lang, { style: "currency", currency: cur, currencyDisplay: "narrowSymbol", maximumFractionDigits: 0 })
    : money(cents, cur);
  const amounts = (by: Partial<Record<Currency, number>>, sign = "") =>
    (Object.entries(by) as [Currency, number][]).filter(([, c]) => c).map(([cur, c]) => sign + sum(c, cur)).join(" · ");

  // On a phone, accounts whose icon, name and balance don't all fit across
  // drop the name of each one that has an icon (measured with names shown).
  const accountsRef = useRef<HTMLDivElement>(null);
  const [compact, setCompact] = useState(false);
  useLayoutEffect(() => {
    const el = accountsRef.current;
    if (!el) return;
    const measure = () => {
      if (!narrow) return setCompact(false);
      const had = el.classList.contains("compact");
      el.classList.remove("compact");
      const over = el.scrollWidth > el.clientWidth + 1;
      if (had) el.classList.add("compact");
      setCompact(over);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [narrow, accounts, summary]);

  const goPrev = () => setAnchor((a) => (view === "month" ? addMonths(a, -1) : addDays(a, -7)));
  const goNext = () => setAnchor((a) => (view === "month" ? addMonths(a, 1) : addDays(a, 7)));
  const headerLabel = view === "month" ? monthLabel(anchor.slice(0, 7), lang) : weekLabel(days, lang);
  // Months that have payments ("2019-05"): dotted in the month picker.
  const busyMonths = useMemo(() => new Set(executed.map((p) => p.date.slice(0, 7))), [executed]);
  // Picked: that month's 1st (a week view shows the week holding it).
  const goMonth = (year: number, month: number) => setAnchor(`${year}-${String(month).padStart(2, "0")}-01`);

  const chip = (e: CalEntry, big = false) => {
    const { dir, cents } = effect(e.p);
    return (
      <button key={e.key} className={"cal-event fin-cal-event" + (e.planned ? " planned" : "") + (big ? " big" : "")}
              style={{ borderLeftColor: DIR_COLOR[dir], "--cal-color": DIR_COLOR[dir] } as CSSProperties}
              title={`${DIR_SIGN[dir]}${money(cents, e.p.currency)} ${title(e.p)}`}
              onClick={(ev) => { ev.stopPropagation(); setOpenDay(null); onOpen(e); }}>
        <span className="fin-cal-amount" style={{ color: DIR_COLOR[dir] }}>{e.planned ? "↻ " : ""}{DIR_SIGN[dir]}{money(cents, e.p.currency)}</span>
        {/* Its reason, else From → To; with room (a week, a day's window), From → To after a reason too. */}
        <span className="fin-cal-title">{e.p.justification || flow(e.p)}</span>
        {big && e.p.justification && <span className="fin-cal-flow">{flow(e.p)}</span>}
      </button>
    );
  };

  return (
    <div className="fin-calendar">
      <div className="month-nav">
        <button className="nav-arrow" onClick={goPrev}>◀</button>
        <h2 className="go-today" role="button" tabIndex={0} title={t("env_today")} onClick={() => setAnchor(TODAY)}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setAnchor(TODAY); } }}>
          {headerLabel}
        </h2>
        <button className="nav-arrow" onClick={goNext}>▶</button>
        {!narrow && <MonthPicker value={anchor.slice(0, 7)} busy={busyMonths} onPick={goMonth} />}
        <select className="fin-unit" value={unit} title={t("fin_unit")} aria-label={t("fin_unit")}
                onChange={(e) => setUnit(e.target.value as Currency)}>
          <option value="EUR">€</option>
          <option value="USD">$</option>
        </select>
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

      <div className="fin-cal-foot" ref={footRef}>
        <div className={"fin-foot-accounts" + (compact ? " compact" : "")} ref={accountsRef}>
          {accounts.map((a) => {
            const text = amounts(summary.balance.get(a.id) ?? {}) || sum(0, unit);
            return (
              <button key={a.id} type="button" className="ghost fin-foot-account" title={`${a.name}: ${text}`}
                      onClick={() => onAccount(a.id)}>
                {label(a.id)}<span>{text}</span>
              </button>
            );
          })}
        </div>
        {/* The balances are to date; these two are the period shown's own. */}
        <div className="fin-foot-totals" title={headerLabel}>
          {!narrow && <span className="fin-foot-period">{headerLabel}</span>}
          <span style={{ color: DIR_COLOR.in }} title={t("fin_income")}>{amounts(summary.flows.in, "+") || "+" + sum(0, unit)}</span>
          <span style={{ color: DIR_COLOR.out }} title={t("fin_spending")}>{amounts(summary.flows.out, "−") || "−" + sum(0, unit)}</span>
        </div>
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

/** A calendar icon opening a year's twelve months: ‹ › step the year, a
 *  month picked goes there. The shown month is filled, today's ringed, and
 *  one with payments has a dot. */
function MonthPicker({ value, busy, onPick }: {
  value: string; busy: Set<string>; onPick: (year: number, month: number) => void;
}) {
  const { t, lang } = useT();
  const [open, setOpen] = useState(false);
  const [year, setYear] = useState(+value.slice(0, 4));
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLSpanElement>(null);
  useBackToClose(() => setOpen(false), open);
  useEffect(() => {
    if (!open) return;
    const down = (e: PointerEvent) => {
      const at = e.target as Node;
      if (!btn.current?.contains(at) && !pop.current?.contains(at)) setOpen(false);
    };
    document.addEventListener("pointerdown", down);
    return () => document.removeEventListener("pointerdown", down);
  }, [open]);
  const names = useMemo(
    () => Array.from({ length: 12 }, (_, m) => new Date(2000, m, 1).toLocaleDateString(lang, { month: "short" }).replace(".", "")),
    [lang]);
  const key = (m: number) => `${year}-${String(m).padStart(2, "0")}`;
  return <>
    <button ref={btn} className={"icon-only fin-month-btn" + (open ? " active" : "")} title={t("fin_pick_month")}
            aria-label={t("fin_pick_month")} onClick={() => { setYear(+value.slice(0, 4)); setOpen(!open); }}>
      <Icon name="month" size={18} className="" />
    </button>
    {open && (
      <Floating anchor={btn} ref={pop} className="fin-month-pop">
        <span className="fin-month-year">
          <button className="ghost icon-only" aria-label="−1" onClick={() => setYear(year - 1)}>‹</button>
          <strong>{year}</strong>
          <button className="ghost icon-only" aria-label="+1" onClick={() => setYear(year + 1)}>›</button>
        </span>
        <span className="fin-month-grid">
          {names.map((name, i) => (
            <button key={i}
                    className={"ghost" + (key(i + 1) === value ? " active" : "") + (key(i + 1) === TODAY.slice(0, 7) ? " today" : "")}
                    onClick={() => { onPick(year, i + 1); setOpen(false); }}>
              {name}{busy.has(key(i + 1)) && <i className="fin-month-dot" aria-hidden />}
            </button>
          ))}
        </span>
      </Floating>
    )}
  </>;
}
