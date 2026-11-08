import { useCallback, useEffect, useRef, useState } from "react";
import { api, Column, ColType, MonthData, useVersionPoll } from "../api";
import { ColumnManager } from "./ColumnManager";
import { FinancePanel } from "./FinancePanel";
import { Icon } from "./icons";
import { IconPick } from "./IconPick";
import { readCookie, writeCookie } from "../cookies";
import { usePhone } from "../narrow";
import { useBackToClose } from "../backClose";
import { useT } from "../i18n";

// YYYY-MM-DD, local. A function (not a module constant) so a tab left open
// across midnight doesn't keep highlighting the day it was loaded on.
function todayIso(): string {
  return new Date().toLocaleDateString("en-CA");
}

function currentMonth(): string {
  return todayIso().slice(0, 7);
}

function addMonths(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function monthLabel(month: string, lang: string): string {
  const [y, m] = month.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleString(lang, { month: "long", year: "numeric" });
}

function weekdayDay(date: string, lang: string): string {
  const d = new Date(date + "T00:00:00");
  return d.toLocaleDateString(lang, { weekday: "short", day: "2-digit" });
}

function addDays(date: string, delta: number): string {
  const d = new Date(date + "T00:00:00");
  d.setDate(d.getDate() + delta);
  return d.toLocaleDateString("en-CA");
}

// "sabato 7 novembre 2026" on a wide screen, "sab 7 nov 2026" on a phone.
function dayLabel(date: string, lang: string, short: boolean): string {
  const d = new Date(date + "T00:00:00");
  const w = short ? "short" : "long";
  return d.toLocaleDateString(lang, { weekday: w, day: "numeric", month: w, year: "numeric" });
}

type ViewMode = "month" | "day";
const VIEW_COOKIE = "personal_view";

// The remembered view; with none yet, a phone starts on the day (the table is
// too wide for it). The phone class is set before the first render (narrow.ts).
function loadView(): ViewMode {
  const v = readCookie(VIEW_COOKIE);
  if (v === "month" || v === "day") return v;
  return document.documentElement.classList.contains("phone") ? "day" : "month";
}

type Draft = Record<string, Record<string, unknown>>;

type PersonalTab = "tables" | "finance";
const TAB_COOKIE = "personal_tab";
const TABS: { key: PersonalTab; icon: string; label: "personal_tab_tables" | "personal_tab_finance" }[] = [
  { key: "tables", icon: "📋", label: "personal_tab_tables" },
  { key: "finance", icon: "💶", label: "personal_tab_finance" },
];

/** Personal's sections, as tabs over them in the Media panel's style (its
 *  .mv-sources row: a strip of tabs on a wide screen, on a phone a button
 *  naming the current one that opens the list). */
export function PersonalPanel() {
  const { t } = useT();
  const narrow = usePhone();
  const [tab, setTabState] = useState<PersonalTab>(() =>
    readCookie(TAB_COOKIE) === "finance" ? "finance" : "tables");
  const setTab = (v: PersonalTab) => { setTabState(v); writeCookie(TAB_COOKIE, v); };
  const [tabMenu, setTabMenu] = useState(false);
  // The right end of the tab row, where the shown section puts its own buttons.
  const [toolsSlot, setToolsSlot] = useState<HTMLElement | null>(null);
  const rowRef = useRef<HTMLDivElement>(null);
  useBackToClose(() => setTabMenu(false), tabMenu);
  useEffect(() => {
    if (!tabMenu) return;
    const down = (e: PointerEvent) => {
      if (!rowRef.current?.contains(e.target as Node)) setTabMenu(false);
    };
    document.addEventListener("pointerdown", down);
    return () => document.removeEventListener("pointerdown", down);
  }, [tabMenu]);
  useEffect(() => { if (!narrow) setTabMenu(false); }, [narrow]);
  const cur = TABS.find((x) => x.key === tab)!;

  return (
    <div className="personal-shell">
      <div className="mv-sources personal-tabs" ref={rowRef}>
        {narrow && (
          <button className={"mv-tabcurrent" + (tabMenu ? " open" : "")} aria-expanded={tabMenu}
                  onClick={() => setTabMenu(!tabMenu)}>
            <span className="mv-tabicon" aria-hidden>{cur.icon}</span>
            <span className="mv-tablabel">{t(cur.label)}</span>
            <span className="mv-tabcaret" aria-hidden>▾</span>
          </button>
        )}
        <div className={"mv-tabstrip" + (narrow && tabMenu ? " open" : "")}>
          {TABS.map((x) => (
            <button key={x.key} className={tab === x.key ? "active" : ""}
                    onClick={() => { setTab(x.key); setTabMenu(false); }}>
              <span className="mv-tabicon" aria-hidden>{x.icon}</span>
              <span className="mv-tablabel">{t(x.label)}</span>
            </button>
          ))}
        </div>
        <div className="personal-tab-tools" ref={setToolsSlot} />
      </div>
      {tab === "tables" ? <PersonalTables /> : <FinancePanel toolsSlot={toolsSlot} />}
    </div>
  );
}

function PersonalTables() {
  const { t, lang } = useT();
  const { diary } = useVersionPoll();
  const narrow = usePhone();
  const [view, setViewState] = useState<ViewMode>(loadView);
  const [month, setMonth] = useState(currentMonth);
  const [day, setDay] = useState(todayIso);
  const [today, setToday] = useState(todayIso);
  useEffect(() => {
    const id = window.setInterval(() => setToday(todayIso()), 30_000);
    return () => window.clearInterval(id);
  }, []);
  // The month the server snapshot is for: the day view loads its day's month.
  const shown = view === "day" ? day.slice(0, 7) : month;
  // Month -> Day opens today if it is in the month on screen, else its 1st;
  // Day -> Month opens the day's month.
  const setView = (v: ViewMode) => {
    if (v === view) return;
    if (v === "day") setDay(today.startsWith(month) ? today : `${month}-01`);
    else setMonth(day.slice(0, 7));
    setViewState(v);
    writeCookie(VIEW_COOKIE, v);
  };
  const [data, setData] = useState<MonthData | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [error, setError] = useState<string | null>(null);
  const [reordering, setReordering] = useState(false);
  // The column editor: a drawer over the page, opened from the month bar.
  const [managing, setManaging] = useState(false);
  const appliedVersion = useRef(-1);

  // The one place a server month-snapshot becomes the UI state.
  const apply = useCallback((d: MonthData, clearDate?: string) => {
    setData(d);
    appliedVersion.current = d.version;
    setError(null);
    if (clearDate) {
      setDraft((p) => {
        const n = { ...p };
        delete n[clearDate];
        return n;
      });
    }
  }, []);

  const load = useCallback(
    (m: string) => {
      api.month(m).then((d) => apply(d)).catch((e) => setError(String(e)));
    },
    [apply],
  );

  useEffect(() => load(shown), [shown, load]);

  // React only when the POLL reports a diary version we have not processed yet
  // (a change from another client). Our own mutations already advanced
  // appliedVersion from their reply, and the polled `diary` may briefly lag it —
  // without the seenDiary guard that lag would spin an infinite refetch loop.
  const seenDiary = useRef(0);
  useEffect(() => {
    if (diary === seenDiary.current) return;
    seenDiary.current = diary;
    if (data && diary !== appliedVersion.current) load(shown);
  }, [diary, data, shown, load]);

  const setCell = (date: string, key: string, value: unknown) =>
    setDraft((p) => ({ ...p, [date]: { ...(p[date] || {}), [key]: value } }));

  const commitDay = (date: string, extra?: Record<string, unknown>) => {
    const values = { ...(draft[date] || {}), ...(extra || {}) };
    if (Object.keys(values).length === 0) return;
    api
      .putDay(date, values)
      .then((d) => apply(d, date))
      .catch((e) => setError(String(e)));
  };

  if (error) return <div className="panel"><p className="error">{error}</p></div>;
  if (!data) return <div className="panel"><p className="muted">{t("loading")}</p></div>;

  const columns = [...data.columns].sort((a, b) => a.position - b.position);

  return (
    <div className="panel personal">
      <div className="personal-main">
        <div className="month-nav">
          {view === "month" ? (
            <>
              <button onClick={() => setMonth((m) => addMonths(m, -1))}>◀</button>
              {/* The month itself goes back to this month: no Today button. */}
              <h2 className="go-today" role="button" tabIndex={0} title={t("env_today")}
                  onClick={() => setMonth(currentMonth())}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setMonth(currentMonth()); } }}>
                {monthLabel(month, lang)}
              </h2>
              <button onClick={() => setMonth((m) => addMonths(m, 1))}>▶</button>
            </>
          ) : (
            <>
              <button onClick={() => setDay((d) => addDays(d, -1))}>◀</button>
              {/* The day itself goes back to today. */}
              <h2 className="go-today" role="button" tabIndex={0} title={t("env_today")}
                  onClick={() => setDay(todayIso())}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setDay(todayIso()); } }}>
                {dayLabel(day, lang, narrow)}
              </h2>
              <button onClick={() => setDay((d) => addDays(d, 1))}>▶</button>
            </>
          )}
          {/* The table's own tools, held at the right of the bar. */}
          <span className="personal-tools">
            <IconPick
              choices={(["month", "day"] as const).map((v) => ({
                key: v, label: t(v === "month" ? "cal_month" : "personal_day"), icon: <Icon name={v} className="" />,
              }))}
              value={view}
              onChange={(v) => setView(v as ViewMode)}
            />
            <button className="ghost icon-only" onClick={() => setReordering(true)}
                    disabled={columns.length < 2} title={t("personal_reorder")} aria-label={t("personal_reorder")}>
              <Icon name="reorder" className="" />
            </button>
            <button className="ghost icon-only" onClick={() => setManaging(true)}
                    title={t("personal_columns_title")} aria-label={t("cols_title")}>
              <Icon name="columns" className="" />
            </button>
          </span>
        </div>

        {view === "day" ? (
          <DayTable
            columns={columns}
            row={data.rows.find((r) => r.date === day)}
            draft={draft[day]}
            onInput={(key, v) => setCell(day, key, v)}
            onCommit={(extra) => commitDay(day, extra)}
          />
        ) : (
        <div className="table-wrap">
          <table className="grid">
            <thead>
              <tr>
                <th className="sticky-col">{t("personal_date")}</th>
                {columns.map((c) => (
                  <th key={c.key} title={c.description}>
                    {c.name}
                    {c.unit ? <span className="unit"> ({c.unit})</span> : null}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => {
                const merged = { ...row.values, ...(draft[row.date] || {}) };
                return (
                  <tr key={row.date} className={row.date === today ? "today" : ""}>
                    <td className="sticky-col date">{weekdayDay(row.date, lang)}</td>
                    {columns.map((c) => (
                      <td key={c.key} className={c.type === "text" ? "text-col" : "fill-col"}>
                        <Cell
                          type={c.type}
                          value={merged[c.key]}
                          options={c.options}
                          onInput={(v) => setCell(row.date, c.key, v)}
                          onCommit={(v) =>
                            c.type === "bool" || c.type === "enum"
                              ? commitDay(row.date, { [c.key]: v })
                              : commitDay(row.date)
                          }
                        />
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        )}
      </div>

      <ColumnManager
        open={managing}
        onClose={() => setManaging(false)}
        columns={columns}
        units={data.units}
        month={shown}
        onState={apply}
      />

      {reordering && (
        <ColumnOrderModal
          columns={columns}
          onClose={() => setReordering(false)}
          onSave={(keys) => {
            api
              .reorderColumns(keys, shown)
              .then((d) => {
                apply(d);
                setReordering(false);
              })
              .catch((e) => setError(String(e)));
          }}
        />
      )}
    </div>
  );
}

/** The day view: the same cells as a month row, one per line, name on the left. */
function DayTable({
  columns,
  row,
  draft,
  onInput,
  onCommit,
}: {
  columns: Column[];
  row: MonthData["rows"][number] | undefined;
  draft: Record<string, unknown> | undefined;
  onInput: (key: string, v: unknown) => void;
  onCommit: (extra?: Record<string, unknown>) => void;
}) {
  // Between days of different months the old month's snapshot is still up.
  if (!row) return null;
  const merged = { ...row.values, ...(draft || {}) };
  return (
    <div className="table-wrap">
      <table className="grid day-grid">
        <tbody>
          {columns.map((c) => (
            <tr key={c.key}>
              <th title={c.description}>
                {c.name}
                {c.unit ? <span className="unit"> ({c.unit})</span> : null}
              </th>
              <td className={c.type === "text" ? "text-col" : "fill-col"}>
                <Cell
                  type={c.type}
                  value={merged[c.key]}
                  options={c.options}
                  onInput={(v) => onInput(c.key, v)}
                  onCommit={(v) =>
                    c.type === "bool" || c.type === "enum" ? onCommit({ [c.key]: v }) : onCommit()
                  }
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ColumnOrderModal({
  columns,
  onClose,
  onSave,
}: {
  columns: Column[];
  onClose: () => void;
  onSave: (keys: string[]) => void;
}) {
  const { t } = useT();
  useBackToClose(onClose);
  const [order, setOrder] = useState<Column[]>(columns);

  const move = (i: number, delta: number) => {
    const j = i + delta;
    if (j < 0 || j >= order.length) return;
    const next = [...order];
    [next[i], next[j]] = [next[j], next[i]];
    setOrder(next);
  };

  const dirty = order.some((c, i) => c.key !== columns[i]?.key);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h4>{t("personal_reorder")}</h4>
        <ol className="col-order-list">
          {order.map((c, i) => (
            <li key={c.key}>
              <span className="name">{c.name}</span>
              <button className="ghost" disabled={i === 0} onClick={() => move(i, -1)} title={t("personal_move_up")}>
                ▲
              </button>
              <button
                className="ghost"
                disabled={i === order.length - 1}
                onClick={() => move(i, 1)}
                title={t("personal_move_down")}
              >
                ▼
              </button>
            </li>
          ))}
        </ol>
        <div className="row-actions">
          <button className="active" disabled={!dirty} onClick={() => onSave(order.map((c) => c.key))}>
            {t("save")}
          </button>
          <button className="ghost" onClick={onClose}>
            {t("cancel")}
          </button>
        </div>
      </div>
    </div>
  );
}

function Cell({
  type,
  value,
  options,
  onInput,
  onCommit,
}: {
  type: ColType;
  value: unknown;
  options?: string[];
  onInput: (v: unknown) => void;
  onCommit: (v: unknown) => void;
}) {
  if (type === "bool") {
    const checked = value === true || value === "true" || value === 1;
    return (
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => {
          onInput(e.target.checked);
          onCommit(e.target.checked);
        }}
      />
    );
  }
  const str = value === null || value === undefined ? "" : String(value);

  if (type === "enum") {
    return (
      <select
        className={str ? undefined : "empty"}
        value={str}
        onChange={(e) => {
          onInput(e.target.value);
          onCommit(e.target.value);
        }}
      >
        <option value=""></option>
        {(options ?? []).map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    );
  }

  if (type === "text") {
    // Hidden twin flows and gives the <td> its height (matching the wrapped
    // text); the textarea is absolutely positioned to fill that height, so it
    // stays flush even when another column made the row taller.
    return (
      <>
        <div className="text-sizer" aria-hidden="true">{str + " "}</div>
        <textarea
          className="cell-text"
          rows={1}
          value={str}
          onChange={(e) => onInput(e.target.value)}
          onBlur={() => onCommit(undefined)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              (e.target as HTMLTextAreaElement).blur();
            }
          }}
        />
      </>
    );
  }

  return (
    <input
      type="number"
      value={str}
      onChange={(e) => onInput(e.target.value === "" ? null : Number(e.target.value))}
      onBlur={() => onCommit(undefined)}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
      }}
    />
  );
}
