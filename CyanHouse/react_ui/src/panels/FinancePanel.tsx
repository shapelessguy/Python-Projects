import { CSSProperties, ReactNode, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  api, Calendar, Currency, FinCalendarLink, FinCategory, FinExecuted, FinForecast, FinKind, FinLine, FinSnapshot,
  finSide, RecurFreq, useVersionPoll,
} from "../api";
import { ALARM_LEADS, alarmLeadLabel } from "../alarms";
import { useBackToClose } from "../backClose";
import { readCookie, writeCookie } from "../cookies";
import { Key, num, useT } from "../i18n";
import { ConfirmDialog } from "../ConfirmDialog";
import { usePhone } from "../narrow";
import { Icon, IconName } from "./icons";
import { CatIcon, IconPicker } from "./IconPicker";
import { Floating } from "./Floating";
import { CalEntry, Dir, DIR_COLOR, DIR_SIGN, effectBy, FinanceCalendar, Worth } from "./FinanceCalendar";
import { FinanceCharts } from "./FinanceCharts";
import { TimeField } from "./TimeField";

// The currency picked last, offered first on the next new payment or
// forecast (EUR until one is picked).
const CURRENCY_COOKIE = "finance_currency";
const lastCurrency = (): Currency => (readCookie(CURRENCY_COOKIE) === "USD" ? "USD" : "EUR");
const CURRENCIES: Currency[] = ["EUR", "USD"];
const SYMBOL: Record<Currency, string> = { EUR: "€", USD: "$" };
// A line with no category (money from or to the world outside one's own
// categories: a shop, an employer) is drawn as this icon, with no word.
const OUTSIDE_ICON = "fluent:globe-with-meridians";
const FREQS: RecurFreq[] = ["daily", "weekly", "monthly", "yearly"];
// "Every 4 weeks" when the step is above one, else "Weekly" (as Calendar's).
const EVERY: Record<RecurFreq, Key> = {
  daily: "cal_every_days", weekly: "cal_every_weeks", monthly: "cal_every_months", yearly: "cal_every_years",
};
const repeatText = (t: ReturnType<typeof useT>["t"], freq: RecurFreq, n: number) =>
  n > 1 ? t(EVERY[freq], { n }) : t(`cal_${freq}`);

const today = () => new Date().toLocaleDateString("en-CA");
// All payments are loaded (for searching and totals); the list draws this
// many at a time, newest first, and "Load more" draws the next lot.
const PAGE = 30;
// An account's payments (tapped in the calendar's bar): this many, then "Show all".
const STATEMENT_PAGE = 50;

// "12,50" or "12.50" -> 1250; anything else -> NaN.
function toCents(text: string): number {
  const n = Number(text.trim().replace(",", "."));
  return text.trim() && Number.isFinite(n) ? Math.round(n * 100) : NaN;
}

/** Categories in tree order (parents first, siblings by sort), each with
 *  its path ("Home › Rent") for lists and pickers. */
function useCategoryTree(cats: FinCategory[]) {
  return useMemo(() => {
    const byId = new Map(cats.map((c) => [c.id, c]));
    const label = (c: FinCategory): string => {
      const parent = c.parent_id != null ? byId.get(c.parent_id) : undefined;
      return parent ? label(parent) + " › " + c.name : c.name;
    };
    const ordered: { cat: FinCategory; depth: number; label: string }[] = [];
    const walk = (parent: number | null, depth: number) => {
      cats.filter((c) => c.parent_id === parent).forEach((c) => {
        ordered.push({ cat: c, depth, label: label(c) });
        walk(c.id, depth + 1);
      });
    };
    walk(null, 0);
    const name = (id: number | null) => {
      const o = id == null ? undefined : ordered.find((x) => x.cat.id === id);
      return id == null ? null : o ? <><CatIcon icon={o.cat.icon} /> {o.label}</> : "?";
    };
    return { ordered, name };
  }, [cats]);
}

type Tree = ReturnType<typeof useCategoryTree>;
type Editing = { kind: FinKind; id: number | null } | null;   // id null: a new one

// The three lists, each opened over the page from its button.
// Two lists: categories, and payments (the recurring ones — forecasts — in a
// drawer at the payments' top).
const SHEETS: { kind: FinKind; icon: IconName }[] = [
  { kind: "categories", icon: "categories" },
  { kind: "executed", icon: "payments" },
];
// The payments sheet's filters: what a payment does to the accounts' money.
// A payment touching no account ("none") goes with the transfers.
type Shown = "in" | "move" | "out";
const FILTERS: { dir: Shown; icon: IconName; label: Key }[] = [
  { dir: "in", icon: "income", label: "fin_income" },
  { dir: "move", icon: "transfer", label: "fin_transfers" },
  { dir: "out", icon: "spending", label: "fin_spending" },
];
const shownAs = (d: Dir): Shown => (d === "none" ? "move" : d);

/** Personal's Finance section. The three lists — categories, forecasts, the
 *  payments — open over the page from buttons on Personal's tab row
 *  (`toolsSlot`, where they are portalled); behind them, the payments'
 *  calendar (still to come). */
export function FinancePanel({ toolsSlot }: { toolsSlot: HTMLElement | null }) {
  const { t, lang } = useT();
  const versions = useVersionPoll("finance");
  const [shown, setShown] = useState(PAGE);
  const [recurringOpen, setRecurringOpen] = useState(false);
  // A payment opened from the calendar — a new one on a day, or one tapped
  // (a recurring one's date edits its rule) — in a window of its own.
  const [quick, setQuick] = useState<{ date: string } | { entry: CalEntry } | null>(null);
  // An account tapped in the calendar's bar: its payments, in a window.
  const [statement, setStatement] = useState<number | null>(null);
  // Its first STATEMENT_PAGE payments, until "Show all".
  const [statementAll, setStatementAll] = useState(false);
  const [data, setData] = useState<FinSnapshot | null>(null);
  const [editing, setEditing] = useState<Editing>(null);
  const [sheet, setSheet] = useState<FinKind | null>(null);
  const [charts, setCharts] = useState(false);
  // The payments sheet's filters (all on) and search (closed).
  const [dirs, setDirs] = useState<Set<Shown>>(new Set(["in", "move", "out"]));
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  useEffect(() => setShown(PAGE), [dirs, query]);
  const [error, setError] = useState("");

  useEffect(() => {
    // Already this new (a change of ours brought it back): nothing to fetch.
    if (data && versions.finance <= data.version) return;
    api.finance().then(setData).catch((e) => setError(String(e.message ?? e)));
  }, [versions.finance]);   // eslint-disable-line react-hooks/exhaustive-deps

  // With an investment category: the Stocks portfolio's worth day by day,
  // fetched again with every change here.
  const investing = !!data?.categories.some((c) => c.kind === "investment");
  const [worth, setWorth] = useState<Worth | null>(null);
  useEffect(() => {
    if (!investing) return;
    api.portfolio().then((p) => setWorth({ index: p.history.index, value: p.history.value })).catch(() => {});
  }, [investing, data?.version]);

  const tree = useCategoryTree(data?.categories ?? []);
  // Every tag in use, most used first: what the tag field suggests.
  const allTags = useMemo(() => {
    const n = new Map<string, number>();
    for (const p of [...(data?.executed ?? []), ...(data?.forecasts ?? [])])
      for (const tag of p.tags) n.set(tag, (n.get(tag) ?? 0) + 1);
    return [...n.keys()].sort((a, b) => n.get(b)! - n.get(a)! || a.localeCompare(b));
  }, [data?.executed, data?.forecasts]);
  // An amount into another currency at a day's rate: the one in force then
  // (the latest published on or before it; a day still to come, the newest).
  const convert = useMemo(() => {
    const rates = data?.eur_usd ?? [];   // dollars per euro
    return (cents: number, from: Currency, to: Currency, date: string): number | null => {
      if (from === to) return cents;
      let lo = 0, hi = rates.length - 1, rate: number | null = null;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (rates[mid][0] <= date) { rate = rates[mid][1]; lo = mid + 1; } else hi = mid - 1;
      }
      rate ??= rates.length ? rates[0][1] : null;
      if (!rate) return null;
      return Math.round(from === "EUR" ? cents * rate : cents / rate);
    };
  }, [data?.eur_usd]);
  // Income, spending, transfer: by what a payment does to the accounts' money.
  // A category one spends on: one whose top-level category has, over every
  // payment, had more money sent to it from the accounts than back from it
  // (Auto: what Mara gives back for the car is less spending, not income).
  const effect = useMemo(() => {
    const cats = data?.categories ?? [];
    const accounts = new Set(cats.filter((c) => c.kind !== "").map((c) => c.id));
    const isAccount = (id: number | null) => id != null && accounts.has(id);
    const parent = new Map(cats.map((c) => [c.id, c.parent_id]));
    const rootOf = (id: number) => { let r = id; while (parent.get(r) != null) r = parent.get(r)!; return r; };
    const spent = new Map<number, number>();   // per top-level category: sent to it less given back
    for (const p of data?.executed ?? []) {
      if (!p.lines.some((l) => isAccount(l.category_id))) continue;
      for (const l of p.lines) if (l.category_id != null && !isAccount(l.category_id)) {
        const r = rootOf(l.category_id);
        spent.set(r, (spent.get(r) ?? 0) + (l.side === "to" ? l.amount_cents : -l.amount_cents));
      }
    }
    return effectBy(isAccount, (id) => (spent.get(rootOf(id)) ?? 0) > 0);
  }, [data?.categories, data?.executed]);

  const phone = usePhone();
  // True when it went through (a form over the calendar then closes).
  const apply = (p: Promise<FinSnapshot>) =>
    p.then((d) => { setData(d); setEditing(null); setError(""); return true; })
      .catch((e) => { setError(String(e.message ?? e)); return false; });
  const save = (kind: FinKind, id: number | null, body: object) =>
    apply(id == null ? api.financeCreate(kind, body) : api.financeUpdate(kind, id, body));
  // Deleting asks first, in the app's own dialog.
  const [deleting, setDeleting] = useState<{ kind: FinKind; id: number } | null>(null);
  const remove = (kind: FinKind, id: number) => setDeleting({ kind, id });
  const money = (cents: number, currency: Currency) =>
    num(cents / 100, lang, { style: "currency", currency, currencyDisplay: "narrowSymbol" });
  const day = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString(lang);
  // A card's from or to: the category's own icon and name, its full path
  // ("Home › Rent") on hover. `small` (under a reason): just the icon, when
  // it has one.
  const side = (id: number | null, small = false) => {
    const o = id == null ? undefined : tree.ordered.find((x) => x.cat.id === id);
    if (id == null) return <span className="fin-pay-side" title={t("fin_outside")}><CatIcon icon={OUTSIDE_ICON} /></span>;
    if (!o) return <span className="fin-pay-side"><span className="fin-pay-name">?</span></span>;
    return (
      <span className="fin-pay-side" title={o.label}>
        <CatIcon icon={o.cat.icon} />{!(small && o.cat.icon) && <span className="fin-pay-name">{o.cat.name}</span>}
      </span>
    );
  };
  // A payment or a forecast as a card, its total at its right. On top its
  // reason, when it has one, with `when` (its date, or how it repeats) and
  // from → to under it, smaller; without one, from → to on top. Split (a
  // side with more lines than one): a line more, each one's amount.
  // A recurring one (a forecast: a rule, not a payment) is drawn apart:
  // dashed, see-through, with ↻ by its amount.
  // From → To: each side's categories, as icons where they have one.
  const flowOf = (p: FinExecuted | FinForecast, small = true) => (
    <span className="fin-pay-flow">
      {finSide(p, "from").map((l) => <span key={`f${l.category_id}`} className="fin-pay-side-wrap">{side(l.category_id, small)}</span>)}
      <span className="fin-pay-arrow" aria-hidden>→</span>
      {finSide(p, "to").map((l) => <span key={`t${l.category_id}`} className="fin-pay-side-wrap">{side(l.category_id, small)}</span>)}
    </span>
  );
  const payCard = (p: FinExecuted | FinForecast, when: (string | null | false)[], buttons: () => ReactNode, recurring = false) => {
    const from = finSide(p, "from"), to = finSide(p, "to");
    const flow = (small: boolean) => flowOf(p, small);
    const split = [from, to].filter((ls) => ls.length > 1).flat();
    const whenText = when.filter(Boolean).join(" · ");
    return (
      <div key={p.id} className={"fin-cat-card fin-pay-card" + (recurring ? " recurring" : "")}>
        <div className="fin-pay-main">
          {p.justification ? <div className="fin-pay-title">{p.justification}</div> : flow(true)}
          <div className="fin-pay-meta">
            <span className="fin-pay-when">{whenText}</span>
            {p.justification && <>{whenText && <span aria-hidden>·</span>}{flow(true)}</>}
          </div>
          {p.tags.length > 0 && (
            <div className="fin-pay-tags">{p.tags.map((tag) => <span key={tag} className="fin-tag">{tag}</span>)}</div>
          )}
          {split.length > 0 && (
            <div className="fin-pay-split">
              {split.map((l) => (
                <span key={`${l.side}${l.category_id}`} className="fin-pay-split-line">
                  {side(l.category_id, true)}<span>{money(l.amount_cents, p.currency)}</span>
                </span>
              ))}
            </div>
          )}
        </div>
        <span className="fin-pay-amount" style={{ color: DIR_COLOR[effect(p).dir] }}>
          {recurring && <span className="fin-pay-recur" aria-hidden>↻{(p as FinForecast).calendar?.alarm && "🔔"}</span>}{DIR_SIGN[effect(p).dir]}{money(effect(p).cents, p.currency)}
        </span>
        <span className="fin-cat-actions">{buttons()}</span>
      </div>
    );
  };
  const isEditing = (kind: FinKind, id: number | null) => editing?.kind === kind && editing.id === id;
  const close = () => setEditing(null);

  const sheetTitle: Record<FinKind, string> = {
    categories: t("fin_categories"), forecasts: t("fin_forecasts"), executed: t("fin_payments"),
  };
  const openSheet = (kind: FinKind) => { setEditing(null); setError(""); setSheet(kind); };
  const catName = (id: number | null) =>
    id == null ? t("fin_outside") : data?.categories.find((c) => c.id === id)?.name ?? "?";
  const closeSheet = () => { setEditing(null); setError(""); setSheet(null); };

  // On Personal's tab row, pushed to its right: icon + name on a wide
  // screen, the icon alone on a phone.
  const tools = (
    <span className="fin-tools">
      {SHEETS.map((s) => (
        <button key={s.kind} className={sheet === s.kind ? "active" : ""} title={sheetTitle[s.kind]}
                aria-label={sheetTitle[s.kind]} onClick={() => openSheet(s.kind)}>
          <Icon name={s.icon} size={phone ? 20 : 16} className="mv-tabicon" />
          <span className="mv-tablabel">{sheetTitle[s.kind]}</span>
        </button>
      ))}
      <button className={charts ? "active" : ""} title={t("fin_charts")} aria-label={t("fin_charts")}
              onClick={() => setCharts(true)}>
        <Icon name="chart" size={phone ? 20 : 16} className="mv-tabicon" />
        <span className="mv-tablabel">{t("fin_charts")}</span>
      </button>
    </span>
  );

  // Edit and delete: words on a wide screen, icons on a phone.
  const actions = (kind: FinKind, id: number) => phone ? <>
    <button className="ghost icon-only" title={t("edit")} aria-label={t("edit")}
            onClick={() => setEditing({ kind, id })}><Icon name="edit" size={18} className="" /></button>
    <button className="ghost icon-only" title={t("delete")} aria-label={t("delete")}
            onClick={() => remove(kind, id)}><Icon name="trash" size={18} className="" /></button>
  </> : <>
    <button className="ghost" onClick={() => setEditing({ kind, id })}>{t("edit")}</button>
    <button className="ghost" onClick={() => remove(kind, id)}>{t("delete")}</button>
  </>;

  // A payment or forecast the sheet's filters let through: its kind of
  // effect switched on, and the search (every word) in its reason, its tags
  // or one of its categories' paths ("Home" finds "Home › Rent").
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const passes = (p: FinExecuted | FinForecast) => {
    if (!dirs.has(shownAs(effect(p).dir))) return false;
    if (!words.length) return true;
    const text = [p.justification ?? "", ...p.tags,
      ...p.lines.map((l) => tree.ordered.find((o) => o.cat.id === l.category_id)?.label ?? t("fin_outside"))]
      .join(" ").toLowerCase();
    return words.every((w) => text.includes(w));
  };
  const filtering = dirs.size < FILTERS.length || words.length > 0;
  const toggleDir = (d: Shown) => {
    const next = new Set(dirs);
    if (next.has(d)) next.delete(d); else next.add(d);
    setDirs(next);
  };
  // At the payments sheet's title: the three filters, the search, the "+".
  // On a phone, a row of their own under the title, the filters wide.
  const payTools = (
    <span className="fin-sheet-tools">
      {FILTERS.map((f) => (
        <button key={f.dir} className={"ghost icon-only fin-filter" + (dirs.has(f.dir) ? " on" : "")}
                style={{ "--fin-dir": DIR_COLOR[f.dir] } as CSSProperties}
                title={t(f.label)} aria-label={t(f.label)} aria-pressed={dirs.has(f.dir)}
                onClick={() => toggleDir(f.dir)}>
          <Icon name={f.icon} size={18} className="" />
        </button>
      ))}
      <span className="fin-sheet-tools-gap" aria-hidden />
      <button className={"ghost icon-only fin-filter-search" + (searchOpen || query ? " active" : "")}
              title={t("search")} aria-label={t("search")} aria-expanded={searchOpen || !!query}
              onClick={() => { if (searchOpen || query) { setQuery(""); setSearchOpen(false); } else setSearchOpen(true); }}>
        <Icon name="search" size={18} className="" />
      </button>
    </span>
  );

  const body = (kind: FinKind) => {
    if (!data) return <p className="muted">{error || t("loading")}</p>;
    if (kind === "categories") return <>
      {isEditing("categories", null) &&
        <CategoryForm tree={tree} onSave={(b) => save("categories", null, b)} onCancel={close} />}
      <CategoryCards
        cats={data.categories}
        actions={(id) => actions("categories", id)}
        form={(cat) => isEditing("categories", cat.id) &&
          <CategoryForm cat={cat} tree={tree} onSave={(b) => save("categories", cat.id, b)} onCancel={close} />}
        onMove={(parent, ids) => apply(api.financeMove(parent, ids))}
      />
    </>;
    // Payments, under a closed drawer of the recurring ones. One "+" and one
    // form for both: what it repeats (and when) decides which it saves.
    const forecastCard = (fc: FinForecast) => isEditing("forecasts", fc.id) ? (
      <PaymentForm key={fc.id} kind="forecasts" row={fc} tree={tree} allTags={allTags}
                   onSave={(_, b) => save("forecasts", fc.id, b)} onCancel={close} />
    ) : payCard(fc, [
      fc.recur_freq ? repeatText(t, fc.recur_freq, fc.recur_interval) : day(fc.start_date),
      fc.recur_freq && `${t("fin_since")} ${day(fc.start_date)}` + (fc.recur_until ? ` → ${day(fc.recur_until)}` : ""),
      fc.generated_until && `${t("fin_written_until")} ${day(fc.generated_until)}`,
    ], () => actions("forecasts", fc.id), true);
    const forecasts = data.forecasts.filter(passes);
    const executed = data.executed.filter(passes);
    return <>
      {phone && payTools}
      {(searchOpen || query) && (
        <input type="search" className="fin-search" placeholder={t("fin_search")} aria-label={t("fin_search")}
               value={query} onChange={(e) => setQuery(e.target.value)}
               onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); setQuery(""); setSearchOpen(false); } }} />
      )}
      {isEditing("executed", null) &&
        <PaymentForm tree={tree} allTags={allTags} onSave={(k, b) => save(k, null, b)} onCancel={close} />}
      {forecasts.length > 0 && (
        <div className="fin-drawer fin-drawer-top">
          <button className="fin-drawer-head" aria-expanded={recurringOpen} onClick={() => setRecurringOpen(!recurringOpen)}>
            <span className="fin-drawer-icon" aria-hidden>🔁</span>
            <span className="fin-drawer-label">{t("fin_recurring")}</span>
            <span className="fin-drawer-count">{forecasts.length}</span>
            <span className={"fin-drawer-caret" + (recurringOpen ? " open" : "")} aria-hidden>▾</span>
          </button>
          {recurringOpen && <div className="fin-cats fin-recurring">{forecasts.map(forecastCard)}</div>}
        </div>
      )}
      <div className="fin-cats">
        {executed.slice(0, shown).map((ex) => isEditing("executed", ex.id) ? (
          <PaymentForm key={ex.id} kind="executed" row={ex} tree={tree} allTags={allTags}
                       onSave={(_, b) => save("executed", ex.id, b)} onCancel={close} />
        ) : payCard(ex, [day(ex.date)], () => actions("executed", ex.id)))}
        {!executed.length && !isEditing("executed", null) &&
          <p className="muted">{t(filtering && data.executed.length ? "fin_no_match" : "fin_no_payments")}</p>}
        {shown < executed.length && (
          <button className="ghost fin-more" onClick={() => setShown(shown + PAGE)}>
            {t("fin_load_more", { n: executed.length - shown })}
          </button>
        )}
      </div>
    </>;
  };

  return (
    <div className="panel finance">
      {data ? (
        <FinanceCalendar
          executed={data.executed} forecasts={data.forecasts}
          money={money}
          convert={convert}
          effect={effect}
          flow={flowOf}
          accounts={tree.ordered.map((o) => o.cat).filter((c) => c.kind !== "" && !c.archived)}
          worth={worth}
          label={(id) => side(id)}
          title={(p) => p.justification ||
            finSide(p, effect(p).dir === "in" ? "from" : "to").map((l) => catName(l.category_id)).join(", ")}
          onAdd={(date) => { setError(""); setQuick({ date }); }}
          onOpen={(entry) => { setError(""); setQuick({ entry }); }}
          onAccount={(id) => { setStatementAll(false); setStatement(id); }}
        />
      ) : <p className="muted">{error || t("loading")}</p>}
      {toolsSlot && createPortal(tools, toolsSlot)}
      {statement != null && data && (() => {
        // Every payment touching the account, newest first: what it did to
        // the account (+ in, − out, its own lines' amounts) and the balance
        // after it, per currency.
        const cat = data.categories.find((c) => c.id === statement);
        const ascending = [...data.executed].reverse().filter((p) => p.lines.some((l) => l.category_id === statement));
        const running: Partial<Record<Currency, number>> = {};
        const rows = ascending.map((p) => {
          const own = p.lines.filter((l) => l.category_id === statement)
            .reduce((n, l) => n + (l.side === "to" ? l.amount_cents : -l.amount_cents), 0);
          running[p.currency] = (running[p.currency] ?? 0) + own;
          return { p, own, after: running[p.currency]! };
        }).reverse();
        return (
          <FinSheet title={cat?.name ?? "?"} onClose={() => setStatement(null)}>
            <div className="fin-cats">
              {(statementAll ? rows : rows.slice(0, STATEMENT_PAGE)).map(({ p, own, after }) => (
                <button key={p.id} type="button" className="fin-cat-card fin-pay-card fin-statement-row"
                        onClick={() => { setError(""); setQuick({ entry: { key: `x${p.id}`, date: p.date, kind: "executed", planned: false, p } }); }}>
                  <div className="fin-pay-main">
                    {p.justification ? <div className="fin-pay-title">{p.justification}</div> : flowOf(p)}
                    <div className="fin-pay-meta">
                      <span className="fin-pay-when">{day(p.date)}</span>
                      {p.justification && <><span aria-hidden>·</span>{flowOf(p)}</>}
                    </div>
                  </div>
                  <span className="fin-statement-amounts">
                    <span className="fin-pay-amount" style={{ color: DIR_COLOR[own >= 0 ? "in" : "out"] }}>
                      {own >= 0 ? "+" : "−"}{money(Math.abs(own), p.currency)}
                    </span>
                    <span className="fin-statement-after">{money(after, p.currency)}</span>
                  </span>
                </button>
              ))}
              {!rows.length && <p className="muted">{t("fin_no_payments")}</p>}
              {!statementAll && rows.length > STATEMENT_PAGE && (
                <button className="ghost fin-more" onClick={() => setStatementAll(true)}>
                  {t("fin_show_all", { n: rows.length })}
                </button>
              )}
            </div>
          </FinSheet>
        );
      })()}
      {quick && data && (() => {
        const close = () => { setQuick(null); setError(""); };
        const done = (ok: boolean) => { if (ok) setQuick(null); };
        const e = "entry" in quick ? quick.entry : null;
        return (
          <FinSheet wide onClose={close} title={
            !e ? t("fin_new_payment") : e.kind === "forecasts" ? t("fin_edit_recurring") : t("fin_edit_payment")}>
            {error && <p className="fin-error">{error}</p>}
            {e ? (
              <PaymentForm kind={e.kind} row={e.p} tree={tree} allTags={allTags} onCancel={close}
                           onSave={(k, b) => apply(api.financeUpdate(k, e.p.id, b)).then(done)}
                           onDelete={() => remove(e.kind, e.p.id)} />
            ) : (
              <PaymentForm tree={tree} allTags={allTags} date={"date" in quick ? quick.date : undefined} onCancel={close}
                           onSave={(k, b) => apply(api.financeCreate(k, b)).then(done)} />
            )}
          </FinSheet>
        );
      })()}
      {charts && data && (
        <FinanceCharts data={data} ordered={tree.ordered} tags={allTags} worth={worth} effect={effect} convert={convert} onClose={() => setCharts(false)} />
      )}
      {sheet && (
        <FinSheet title={sheetTitle[sheet]} onClose={closeSheet} action={<>
          {sheet === "executed" && !phone && payTools}
          <button className="ghost icon-only fin-add" title={t("fin_new")} aria-label={t("fin_new")}
                  onClick={() => { setError(""); setEditing({ kind: sheet, id: null }); }}>+</button>
        </>}>
          {error && <p className="fin-error">{error}</p>}
          {body(sheet)}
        </FinSheet>
      )}
      {/* Last, so it sits over a sheet or the form it was asked from. */}
      {deleting && (
        <ConfirmDialog message={t("fin_confirm_delete")} yesLabel={t("delete")} danger onNo={() => setDeleting(null)}
                       onYes={() => {
                         apply(api.financeDelete(deleting.kind, deleting.id));
                         setDeleting(null); setEditing(null); setQuick(null);
                       }} />
      )}
    </div>
  );
}

/** One list over the page: a dialog on a wide screen, the whole screen with
 *  a back bar on a phone. Back closes it either way. `action` sits at the
 *  title's right (a "+" for a new one). */
function FinSheet({ title, onClose, action, wide, children }: {
  title: string; onClose: () => void; action?: ReactNode; wide?: boolean; children: ReactNode;
}) {
  const { t } = useT();
  const narrow = usePhone();
  useBackToClose(onClose);
  if (narrow) return (
    <div className="modal-backdrop settings-full">
      <div className="settings-full-page fin-sheet-page">
        <div className="fin-back-row">
          <button className="ghost back-bar" onClick={onClose}>
            <Icon name="left" size={16} className="back-bar-arrow" />
            <span className="back-bar-name">{title}</span>
          </button>
          {action}
        </div>
        <div className="fin-sheet-body">{children}</div>
      </div>
    </div>
  );
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className={"modal fin-sheet" + (wide ? " wide" : "")} onClick={(e) => e.stopPropagation()}>
        <div className="fin-sheet-head">
          <h4>{title}</h4>
          {action}
          <button className="ghost icon-only" title={t("close")} aria-label={t("close")} onClick={onClose}>
            <Icon name="close" size={16} className="" />
          </button>
        </div>
        <div className="fin-sheet-body">{children}</div>
      </div>
    </div>
  );
}

type Kind = FinCategory["kind"];
const KIND_LABEL: Record<Exclude<Kind, "">, Key> = { account: "fin_kind_account", investment: "fin_kind_investment" };
const NEXT_KIND: Record<Kind, Kind> = { "": "account", account: "investment", investment: "" };

function CategoryForm({ cat, tree, onSave, onCancel }: {
  cat?: FinCategory; tree: Tree; onSave: (body: object) => void; onCancel: () => void;
}) {
  const { t } = useT();
  const [name, setName] = useState(cat?.name ?? "");
  const [icon, setIcon] = useState(cat?.icon ?? "");
  const [parent, setParent] = useState<number | null>(cat?.parent_id ?? null);
  const [kind, setKind] = useState<FinCategory["kind"]>(cat?.kind ?? "");
  const values = { name, icon, parent_id: parent, kind };
  // A new one put under an account is most likely an account too.
  const pickParent = (id: number | null) => {
    setParent(id);
    if (!cat && id != null) setKind(tree.ordered.find((o) => o.cat.id === id)?.cat.kind ?? "");
  };
  // Archiving asks first (in the app's dialog); bringing one back doesn't.
  // Either saves the form too.
  const [asking, setAsking] = useState(false);
  const archive = () => {
    if (cat?.archived) onSave({ ...values, archived: false });
    else setAsking(true);
  };
  return (
    <form className="fin-form fin-cat-form" onSubmit={(e) => {
      e.preventDefault();
      onSave(values);
    }}>
      <div className="fin-field">{t("fin_icon")}<IconPicker value={icon} onChange={setIcon} /></div>
      <label>{t("fin_name")}<input value={name} onChange={(e) => setName(e.target.value)} /></label>
      {/* The type, a tap stepping through them: none, account, investment.
          Its initial, lit when it's one (an account's when it's none). */}
      <div className="fin-cat-under">
        <label>{t("fin_parent")}
          <CategorySelect tree={tree} value={parent} onChange={pickParent} empty="—" exclude={cat?.id} />
        </label>
        <button type="button" className={"fin-kind-toggle" + (kind ? " on " + kind : "")}
                aria-pressed={kind !== ""} title={t(KIND_LABEL[kind || "account"])} aria-label={t(KIND_LABEL[kind || "account"])}
                onClick={() => setKind(NEXT_KIND[kind])}>{t(KIND_LABEL[kind || "account"])[0]}</button>
      </div>
      <FormButtons onCancel={onCancel} archive={cat && { archived: cat.archived, onClick: archive }} />
      {asking && (
        <ConfirmDialog message={t("fin_confirm_archive")} yesLabel={t("fin_archive")} onNo={() => setAsking(false)}
                       onYes={() => { setAsking(false); onSave({ ...values, archived: true }); }} />
      )}
    </form>
  );
}

/** A form's buttons: Cancel and Save at the right, and — editing a category —
 *  Archive (or Restore) at the left. A form in its own sheet (a payment
 *  opened from the calendar) has Delete in Cancel's place: the sheet's
 *  close button cancels. Icons on a phone, icon and word on a wide screen. */
function FormButtons({ onCancel, archive, onDelete }: {
  onCancel: () => void; archive?: { archived: boolean; onClick: () => void }; onDelete?: () => void;
}) {
  const { t } = useT();
  const phone = usePhone();
  const button = (cls: string, icon: IconName, label: string, props: object) => (
    <button className={"fin-btn " + cls + (phone ? " icon-only" : "")} title={label} aria-label={label} {...props}>
      <Icon name={icon} size={phone ? 20 : 16} className="" />
      {!phone && <span>{label}</span>}
    </button>
  );
  return (
    <div className="fin-form-actions">
      {archive && (archive.archived
        ? button("fin-btn-archive", "unarchive", t("fin_unarchive"), { type: "button", onClick: archive.onClick })
        : button("fin-btn-archive", "archive", t("fin_archive"), { type: "button", onClick: archive.onClick }))}
      <span className="fin-form-actions-end">
        {onDelete
          ? button("fin-btn-delete", "trash", t("delete"), { type: "button", onClick: onDelete })
          : button("fin-btn-cancel", "close", t("cancel"), { type: "button", onClick: onCancel })}
        {button("fin-btn-save", "tick", t("save"), { type: "submit" })}
      </span>
    </div>
  );
}

// A card's indent per level, and how far sideways a drag goes for one level.
const INDENT = 24;

type Row = { cat: FinCategory; depth: number };
type Drop = { index: number; depth: number; min: number; max: number };

/** Depth-first rows under `parent`, each with its depth; `skip` leaves a
 *  category out with everything under it. */
function flatten(cats: FinCategory[], parent: number | null, depth: number, keep: (c: FinCategory) => boolean,
                 skip?: number): Row[] {
  return cats.filter((c) => c.parent_id === parent && c.id !== skip && keep(c))
    .flatMap((c) => [{ cat: c, depth }, ...flatten(cats, c.id, depth + 1, keep, skip)]);
}

/** The categories as cards, a sub-category indented under its parent.
 *  Dragging one (with the mouse, or after a long press on a phone) takes it
 *  and everything under it along: up and down picks its place, sideways its
 *  level — the anchors on its gap show the levels it can take there (a
 *  category at the top, under the card above, or under one of that card's
 *  parents). Saved on drop. Archived ones (with whatever sits under them)
 *  wait in a closed drawer at the bottom. `form` is a card's edit form while
 *  it is open. */
function CategoryCards({ cats, actions, form, onMove }: {
  cats: FinCategory[]; actions: (id: number) => ReactNode; form: (cat: FinCategory) => ReactNode;
  onMove: (parent: number | null, ids: number[]) => Promise<unknown>;
}) {
  const { t } = useT();
  // The categories as moved, from the drop until the saved ones come back.
  const [moved, setMoved] = useState<FinCategory[] | null>(null);
  const [drag, setDrag] = useState<{ id: number; drop: Drop; top: number; height: number } | null>(null);
  const [drawer, setDrawer] = useState(false);
  const list = useRef<HTMLDivElement>(null);
  const cards = useRef(new Map<number, HTMLDivElement>());
  // While a drag is on, a finger moving must not scroll the page. Chrome
  // only waits for a touchmove listener that was there when the touch began,
  // so this one stays on the list for good and acts only during a drag.
  const dragging = useRef(false);
  useEffect(() => {
    const box = list.current;
    if (!box) return;
    const touchMove = (ev: TouchEvent) => { if (dragging.current && ev.cancelable) ev.preventDefault(); };
    box.addEventListener("touchmove", touchMove, { passive: false });
    return () => box.removeEventListener("touchmove", touchMove);
  }, []);

  const shown = moved ?? cats;
  const byId = new Map(shown.map((c) => [c.id, c]));
  const active = (c: FinCategory) => !c.archived;
  const rows = flatten(shown, null, 0, active);
  const dragged = drag ? [{ cat: byId.get(drag.id)!, depth: 0 }, ...flatten(shown, drag.id, 1, active)] : [];
  const draggedIds = new Set(dragged.map((r) => r.cat.id));
  // The drawer's: archived ones with nothing archived above them, each with all under it.
  const archivedTops = shown.filter((c) => {
    if (!c.archived) return false;
    for (let p = c.parent_id; p != null; p = byId.get(p)?.parent_id ?? null) if (byId.get(p)?.archived) return false;
    return true;
  });

  const startDrag = (e: React.PointerEvent, cat: FinCategory, depth: number) => {
    if (e.button !== 0 || (e.target as HTMLElement).closest("button, input, select, a, form")) return;
    const box = list.current, card = cards.current.get(cat.id);
    if (!box || !card) return;
    const id = e.pointerId, x0 = e.clientX, y0 = e.clientY, touch = e.pointerType !== "mouse";
    const grab = y0 - card.getBoundingClientRect().top;
    // It floats with everything under it: the gap is that tall.
    const under = flatten(shown, cat.id, 1, active);
    const last = under.length ? cards.current.get(under[under.length - 1].cat.id) : card;
    const height = (last ?? card).getBoundingClientRect().bottom - card.getBoundingClientRect().top;
    // The rows it can go between: everything but itself and what is under it.
    const others = flatten(shown, null, 0, active, cat.id);
    let drop: Drop | null = null;

    const project = (x: number, y: number) => {
      // Its gap: after every card whose middle is above the pointer.
      const index = others.filter((r) => {
        const b = cards.current.get(r.cat.id)?.getBoundingClientRect();
        return b && b.top + b.height / 2 < y;
      }).length;
      const prev = others[index - 1], next = others[index];
      const max = prev ? prev.depth + 1 : 0;
      const min = next ? next.depth : 0;
      const want = depth + Math.round((x - x0) / INDENT);
      const d = Math.min(max, Math.max(min, want));
      const r = box.getBoundingClientRect();
      const top = Math.min(Math.max(y - grab - r.top, 0), Math.max(r.height - height, 0));
      drop = { index, depth: d, min, max };
      setDrag({ id: cat.id, drop, top, height });
    };
    // Held near the top or bottom of the list's scrolling box, the box
    // scrolls by itself (faster nearer the edge), so a card can go anywhere.
    const scroller = (() => {
      for (let n = box.parentElement; n; n = n.parentElement)
        if (/(auto|scroll)/.test(getComputedStyle(n).overflowY) && n.scrollHeight > n.clientHeight) return n;
      return null;
    })();
    let at = { x: x0, y: y0 }, frame = 0;
    const EDGE = 56;
    const autoScroll = () => {
      frame = requestAnimationFrame(autoScroll);
      if (!scroller) return;
      const r = scroller.getBoundingClientRect();
      const up = at.y - r.top, down = r.bottom - at.y;
      const step = up < EDGE ? -Math.ceil((EDGE - Math.max(up, 0)) / 4)
        : down < EDGE ? Math.ceil((EDGE - Math.max(down, 0)) / 4) : 0;
      if (!step) return;
      const before = scroller.scrollTop;
      scroller.scrollTop += step;
      if (scroller.scrollTop !== before) project(at.x, at.y);
    };
    const begin = () => {
      dragging.current = true; project(x0, y0); navigator.vibrate?.(15);
      frame = requestAnimationFrame(autoScroll);
    };
    const timer = touch ? window.setTimeout(begin, 350) : 0;
    const move = (ev: PointerEvent) => {
      if (ev.pointerId !== id) return;
      if (!dragging.current) {
        if (Math.hypot(ev.clientX - x0, ev.clientY - y0) < (touch ? 8 : 4)) return;
        if (touch) { stop(); return; }   // moved before the long press: a scroll
        begin();
      }
      at = { x: ev.clientX, y: ev.clientY };
      project(ev.clientX, ev.clientY);
    };
    const noMenu = (ev: Event) => ev.preventDefault();
    const stop = () => {
      window.clearTimeout(timer);
      cancelAnimationFrame(frame);
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", up);
      document.removeEventListener("pointercancel", cancel);
      document.removeEventListener("contextmenu", noMenu);
      dragging.current = false;
      setDrag(null);
    };
    const up = (ev: PointerEvent) => {
      if (ev.pointerId !== id) return;
      stop();
      if (!drop) return;
      // Its new parent: the nearest card above one level up.
      const { index, depth: d } = drop;
      let parent: number | null = null;
      if (d > 0) for (let i = index - 1; i >= 0; i--) if (others[i].depth === d - 1) { parent = others[i].cat.id; break; }
      const before = others.slice(0, index).filter((r) => r.cat.parent_id === parent && r.depth === d).map((r) => r.cat.id);
      const after = others.slice(index).filter((r) => r.cat.parent_id === parent && r.depth === d).map((r) => r.cat.id);
      const ids = [...before, cat.id, ...after];
      const siblings = shown.filter((c) => c.parent_id === parent && active(c)).map((c) => c.id);
      if (parent === cat.parent_id && ids.join() === siblings.join()) return;
      setMoved(shown.map((c) => {
        const n = ids.indexOf(c.id);
        return n < 0 ? c : { ...c, parent_id: c.id === cat.id ? parent : c.parent_id, sort: n };
      }).sort((a, b) => a.sort - b.sort || a.id - b.id));
      onMove(parent, ids).finally(() => setMoved(null));
    };
    const cancel = (ev: PointerEvent) => { if (ev.pointerId === id) stop(); };
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", up);
    document.addEventListener("pointercancel", cancel);
    if (touch) document.addEventListener("contextmenu", noMenu);
  };

  // `hidden`: the dragged ones' own cards stay in the page while it floats
  // (a touch's events keep going to the card it began on).
  const card = (r: Row, draggable: boolean, ghost = false, hidden = false) => (
    <div key={r.cat.id} className="fin-cat-row" style={{ paddingLeft: r.depth * INDENT, display: hidden ? "none" : undefined }}>
      {form(r.cat) || (
        <div ref={ghost ? undefined : (el) => { if (el) cards.current.set(r.cat.id, el); else cards.current.delete(r.cat.id); }}
             className={"fin-cat-card" + (draggable ? " draggable" : "")}
             onPointerDown={draggable ? (e) => startDrag(e, r.cat, r.depth) : undefined}>
          <CatIcon icon={r.cat.icon} />
          <span className="fin-cat-name">{r.cat.name}</span>
          {r.cat.kind &&
            <span className={"fin-kind-badge " + r.cat.kind} title={t(KIND_LABEL[r.cat.kind])}
                  aria-label={t(KIND_LABEL[r.cat.kind])}>{t(KIND_LABEL[r.cat.kind])[0]}</span>}
          <span className="fin-cat-actions">{actions(r.cat.id)}</span>
        </div>
      )}
    </div>
  );

  // Where it would land: a gap the size of its card, with an anchor for
  // every level it can take there, the picked one lit.
  const gap = drag && (
    <div key="gap" className="fin-cat-gap" style={{ height: drag.height }}>
      {Array.from({ length: drag.drop.max - drag.drop.min + 1 }, (_, i) => drag.drop.min + i).map((d) => (
        <span key={d} className={"fin-cat-anchor" + (d === drag.drop.depth ? " on" : "")} style={{ left: d * INDENT + 8 }} />
      ))}
      <span className="fin-cat-slot" style={{ left: drag.drop.depth * INDENT }} />
    </div>
  );
  // The gap goes before the drop.index-th card not being dragged.
  const body: ReactNode[] = [];
  let n = 0;
  for (const r of rows) {
    const hidden = draggedIds.has(r.cat.id);
    if (drag && !hidden && n++ === drag.drop.index) body.push(gap);
    body.push(card(r, true, false, hidden));
  }
  if (drag && n <= drag.drop.index) body.push(gap);

  return (
    <div className={"fin-cats" + (drag ? " dragging" : "")}>
      <div className="fin-cat-list-box" ref={list}>
        {body}
        {drag && (
          <div className="fin-cat-float" style={{ top: drag.top, left: drag.drop.depth * INDENT }}>
            {dragged.map((r) => card(r, false, true))}
          </div>
        )}
      </div>
      {archivedTops.length > 0 && (
        <div className="fin-drawer">
          <button className="fin-drawer-head" aria-expanded={drawer} onClick={() => setDrawer(!drawer)}>
            <span className="fin-drawer-icon" aria-hidden>🗄️</span>
            <span className="fin-drawer-label">{t("fin_archived_list")}</span>
            <span className="fin-drawer-count">{archivedTops.length}</span>
            <span className={"fin-drawer-caret" + (drawer ? " open" : "")} aria-hidden>▾</span>
          </button>
          {drawer && (
            <div className="fin-cats fin-archived">
              {archivedTops.flatMap((c) => [{ cat: c, depth: 0 }, ...flatten(shown, c.id, 1, () => true)])
                .map((r) => card(r, false))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

type Side = "from" | "to";
// A line being edited: its category and amount as typed.
type LineDraft = { cat: number | null; amount: string };
const cents2text = (c: number) => (c / 100).toFixed(2);

/** A payment (kind "executed") or a forecast: the same template, plus a date
 *  for one and a start and repetition for the other. A new one (no `kind`)
 *  offers the repetition too, and saves as a forecast when it repeats or its
 *  date is still to come, else as a payment.
 *  Its two sides, From and To, are lists of lines, each a category and an
 *  amount. From's amounts make the total; To's last line takes what its
 *  others leave of it (so the sides always match, and a plain payment is one
 *  amount typed). Picking a category with sub-categories offers to split the
 *  line into them, in its place. */
function PaymentForm({ kind, row, tree, allTags, date: startDate, onSave, onCancel, onDelete }: {
  kind?: "executed" | "forecasts"; row?: FinExecuted | FinForecast; tree: Tree; allTags: string[]; date?: string;
  onSave: (kind: "executed" | "forecasts", body: object) => void; onCancel: () => void; onDelete?: () => void;
}) {
  const { t, lang } = useT();
  const fc = kind === "forecasts" ? (row as FinForecast | undefined) : undefined;
  const ex = kind === "executed" ? (row as FinExecuted | undefined) : undefined;
  const [date, setDate] = useState(ex?.date ?? fc?.start_date ?? startDate ?? today());
  // Opened from the calendar, it may sit far down the list: bring it into view.
  const formRef = useRef<HTMLFormElement>(null);
  useEffect(() => { formRef.current?.scrollIntoView({ block: "nearest" }); }, []);
  const [lines, setLines] = useState<Record<Side, LineDraft[]>>(() => {
    const of = (side: Side): LineDraft[] => {
      const ls = row ? finSide(row, side) : [];
      return ls.length ? ls.map((l) => ({ cat: l.category_id, amount: cents2text(l.amount_cents) })) : [{ cat: null, amount: "" }];
    };
    return { from: of("from"), to: of("to") };
  });
  const [currency, setCurrency] = useState<Currency>(row?.currency ?? lastCurrency());
  const [why, setWhy] = useState(row?.justification ?? "");
  const [tags, setTags] = useState<string[]>(row?.tags ?? []);
  const [tagDraft, setTagDraft] = useState("");
  const [freq, setFreq] = useState<RecurFreq | null>(fc ? fc.recur_freq : null);
  const [interval, setInterval] = useState(String(fc?.recur_interval ?? 1));
  const [until, setUntil] = useState(fc?.recur_until ?? "");
  // A repeating one's event in the Calendar: ticked, where, and its alarm.
  // The calendars it may go in (null: the Calendar isn't open to this user,
  // so no offer — and, as its panel is hidden, its API is never asked).
  const [calendars, setCalendars] = useState<Calendar[] | null>(null);
  useEffect(() => {
    let alive = true;
    api.me()
      .then((me) => (me.visible_panels == null || me.visible_panels.includes("calendar") ? api.calendars() : null))
      .then((cs) => alive && setCalendars(cs && cs.filter((c) => c.level !== "see")), () => alive && setCalendars(null));
    return () => { alive = false; };
  }, []);
  const [inCal, setInCal] = useState(!!fc?.calendar);
  const [link, setLink] = useState<FinCalendarLink>(() => fc?.calendar
    ? { ...fc.calendar, time: fc.calendar.time ?? "09:00" }
    : { calendar_id: 0, alarm: true, alarm_lead: 0, time: "09:00" });
  // A new link goes in the first calendar offered (one's Default).
  const calId = calendars?.some((c) => c.id === link.calendar_id) ? link.calendar_id : calendars?.[0]?.id;
  const [error, setError] = useState("");

  const fromCents = lines.from.map((l) => toCents(l.amount));
  const total = fromCents.reduce((n, c) => n + (c || 0), 0);
  // Each side's lines in cents: From's as typed; To's last is the rest.
  const centsOf = (side: Side): number[] => {
    if (side === "from") return fromCents;
    const firsts = lines.to.slice(0, -1).map((l) => toCents(l.amount));
    return [...firsts, total - firsts.reduce((n, c) => n + (c || 0), 0)];
  };
  const isRest = (side: Side, i: number) => side === "to" && i === lines.to.length - 1;
  const setSide = (side: Side, ls: LineDraft[]) => setLines((cur) => ({ ...cur, [side]: ls }));
  const setLine = (side: Side, i: number, patch: Partial<LineDraft>) =>
    setSide(side, lines[side].map((l, j) => (j === i ? { ...l, ...patch } : l)));
  // A new line. On To, the one that was last (the rest) keeps the amount it
  // had, now typed, and the new one takes the rest.
  const addLine = (side: Side) => {
    const now = centsOf(side), ls = lines[side];
    setSide(side, [...ls.map((l, i) => (isRest(side, i) ? { ...l, amount: now[i] > 0 ? cents2text(now[i]) : "" } : l)),
                   { cat: null, amount: "" }]);
  };
  const removeLine = (side: Side, i: number) => setSide(side, lines[side].filter((_, j) => j !== i));
  const children = (id: number | null) =>
    id == null ? [] : tree.ordered.filter((o) => o.cat.parent_id === id && !o.cat.archived).map((o) => o.cat);
  // Split a line into its category's sub-categories, in its place (their
  // amounts to fill in).
  const splitLine = (side: Side, i: number) => {
    const ls = lines[side];
    const kids = children(ls[i].cat).filter((c) => !ls.some((l) => l.cat === c.id))
      .map((c) => ({ cat: c.id, amount: "" }));
    setSide(side, [...ls.slice(0, i), ...kids, ...ls.slice(i + 1)]);
  };

  const submit = () => {
    if (!(total > 0)) return setError(t("fin_err_amount"));
    // A line left empty or at zero is just left out; a side needs one above zero.
    const out: FinLine[] = [];
    for (const side of ["from", "to"] as Side[]) {
      const cs = centsOf(side).map((c) => (Number.isNaN(c) ? 0 : c));
      if (cs.some((c) => c < 0)) return setError(t("fin_err_lines"));
      const kept = lines[side].map((l, i) => ({ cat: l.cat, cents: cs[i] })).filter((l) => l.cents > 0);
      if (!kept.length) return setError(t("fin_err_lines"));
      if (new Set(kept.map((l) => l.cat)).size !== kept.length) return setError(t("fin_err_dup"));
      kept.forEach((l) => out.push({ side, category_id: l.cat, amount_cents: l.cents }));
    }
    const fromCats = out.filter((l) => l.side === "from").map((l) => l.category_id);
    if (out.some((l) => l.side === "to" && fromCats.includes(l.category_id))) return setError(t("fin_err_dup"));
    setError("");
    writeCookie(CURRENCY_COOKIE, currency);
    // A tag still being typed counts too.
    const body = { lines: out, currency, justification: why, tags: addTag(tags, tagDraft) };
    // A new one: repeating, or still to come, makes a forecast (it writes
    // the payments as they fall due); anything else is a payment now.
    const as = kind ?? (freq || date > today() ? "forecasts" : "executed");
    // Its event: only a repeating one's, and only while there is a calendar
    // to put it in (left as it is when the Calendar couldn't be asked).
    // Its body: the reason, the tags, then each side's lines one under the other.
    const eventText = () => {
      const name = (id: number | null) =>
        id == null ? t("fin_outside") : tree.ordered.find((o) => o.cat.id === id)?.cat.name ?? "?";
      const amount = (c: number) =>
        num(c / 100, lang, { style: "currency", currency, currencyDisplay: "narrowSymbol" });
      const side = (s: Side) => [`${t(s === "from" ? "fin_from" : "fin_to")}:`,
        ...out.filter((l) => l.side === s).map((l) => `${name(l.category_id)}: ${amount(l.amount_cents)}`)];
      return [
        ...(why.trim() ? [`${t("fin_justification")}: ${why.trim()}`] : []),
        ...(body.tags.length ? [`${t("fin_tags")}: ${body.tags.join(", ")}`] : []),
        ...(why.trim() || body.tags.length ? [""] : []),
        ...side("from"), "", ...side("to"),
      ].join("\n");
    };
    const calendar = !(freq && inCal) ? { calendar: null } : calId != null ? {
      calendar: { ...link, calendar_id: calId, title: t("fin_event_title"), description: eventText() },
    } : {};
    onSave(as, as === "executed" ? { ...body, date } : {
      ...body, start_date: date, recur_freq: freq,
      recur_interval: parseInt(interval, 10) || 1, recur_until: freq && until ? until : null, ...calendar,
    });
  };

  // A side: its lines (category, amount, ✕ once there are two), and under
  // each the offer to split it (cut short if long) — and under the last, at
  // the right, the "+" for another line.
  const sideBlock = (side: Side) => {
    const ls = lines[side], cs = centsOf(side);
    return (
      <div className="fin-lines">
        <div className="fin-lines-head">{t(side === "from" ? "fin_from" : "fin_to")}</div>
        {ls.map((ln, i) => {
          const last = i === ls.length - 1;
          const kids = children(ln.cat).filter((c) => !ls.some((l) => l.cat === c.id));
          return (
            <div key={i} className="fin-line-wrap">
              <div className="fin-line">
                <CategorySelect tree={tree} value={ln.cat} empty={<span title={t("fin_outside")}><CatIcon icon={OUTSIDE_ICON} /> —</span>}
                                onChange={(cat) => setLine(side, i, { cat })} />
                {/* The payment's currency shown in each amount, typed or worked out. */}
                {isRest(side, i)
                  ? <span className="fin-line-rest" title={t("fin_line_rest")}>
                      <span className="fin-money-sym">{SYMBOL[currency]}</span>{cs[i] > 0 ? cents2text(cs[i]) : "—"}
                    </span>
                  : <span className="fin-money">
                      <span className="fin-money-sym" aria-hidden>{SYMBOL[currency]}</span>
                      <input className="fin-amount fin-line-amount" inputMode="decimal" value={ln.amount} placeholder="0,00"
                             aria-label={`${t("fin_amount")} (${currency})`} onChange={(e) => setLine(side, i, { amount: e.target.value })} />
                    </span>}
                {ls.length > 1 && (
                  <button type="button" className="ghost icon-only fin-line-del" title={t("fin_remove_line")}
                          aria-label={t("fin_remove_line")} onClick={() => removeLine(side, i)}>
                    <Icon name="close" size={14} className="" />
                  </button>
                )}
              </div>
              {(kids.length > 0 || last) && (
                <div className="fin-line-tools">
                  {kids.length > 0 && (
                    <button type="button" className="ghost fin-line-split" onClick={() => splitLine(side, i)}
                            title={t("fin_split_into", { names: kids.map((c) => c.name).join(", ") })}>
                      {t("fin_split_into", { names: kids.map((c) => c.name).join(", ") })}
                    </button>
                  )}
                  {last && (
                    <button type="button" className="ghost icon-only fin-line-add" title={t("fin_add_line")}
                            aria-label={t("fin_add_line")} onClick={() => addLine(side)}>
                      <Icon name="plus" size={16} className="" />
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <form className="fin-form fin-pay-form" ref={formRef} onSubmit={(e) => { e.preventDefault(); submit(); }}>
      {/* The date and the currency share a row. */}
      <label className="fin-f-date">{freq && kind !== "executed" ? t("fin_start") : t("fin_date")}
        <span className="fin-pair">
          <input className="fin-pair-main" type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
          <select className="fin-pair-side" value={currency} aria-label={t("fin_currency")} onChange={(e) => setCurrency(e.target.value as Currency)}>
            {CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </span>
      </label>
      <label className="fin-f-why">{t("fin_justification")}<input value={why} onChange={(e) => setWhy(e.target.value)} /></label>
      <TagField tags={tags} onChange={setTags} draft={tagDraft} onDraft={setTagDraft} all={allTags} />
      {kind !== "executed" && <>
        {/* How often, and every how many of those: the choices read "Every 4
            weeks" as the number changes. */}
        <label className={"fin-f-repeat" + (freq ? " on" : "")}>{t("cal_repeat")}
          <span className="fin-pair">
            <select className="fin-pair-main" value={freq ?? ""} onChange={(e) => setFreq((e.target.value || null) as RecurFreq | null)}>
              <option value="">{t("cal_no_repeat")}</option>
              {FREQS.map((f) => <option key={f} value={f}>{repeatText(t, f, Math.max(1, parseInt(interval, 10) || 1))}</option>)}
            </select>
            {freq && <>
              <input type="number" min={1} className="fin-pair-side" aria-label={t("fin_every")} value={interval}
                     onChange={(e) => setInterval(e.target.value)} />
            </>}
          </span>
        </label>
        {freq && <label className="fin-f-until">{t("cal_until_label")}
          <input type="date" className={until ? "" : "fin-date-empty"} value={until} onChange={(e) => setUntil(e.target.value)} />
        </label>}
        {/* A repeating one can be an event in the Calendar too: which
            calendar, and its alarm (at a time of day, so it rings then). */}
        {freq && calendars && calendars.length > 0 && <>
          <label className="fin-f-incal" title={t("fin_in_calendar_hint")}>
            <input type="checkbox" checked={inCal} onChange={(e) => setInCal(e.target.checked)} />
            {t("fin_in_calendar")}
          </label>
          {inCal && <div className="fin-f-calrow">
            <label className="fin-f-calendar">{t("panel_calendar")}
              <select value={calId} onChange={(e) => setLink({ ...link, calendar_id: Number(e.target.value) })}>
                {calendars.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </label>
            <div className="fin-field fin-f-alarm">{t("alarm_one")}
              <span className="fin-pair">
                <select className="fin-pair-main" aria-label={t("alarm_one")}
                        title={link.alarm ? t("alarm_before") : t("alarm_none")}
                        value={link.alarm ? String(link.alarm_lead) : "off"}
                        onChange={(e) => setLink(e.target.value === "off"
                          ? { ...link, alarm: false }
                          : { ...link, alarm: true, alarm_lead: Number(e.target.value) })}>
                  <option value="off">🔕</option>
                  {ALARM_LEADS.map((m) => <option key={m} value={m}>🔔 {alarmLeadLabel(m, t)}</option>)}
                </select>
                {link.alarm && <TimeField value={link.time ?? "09:00"} onChange={(time) => setLink({ ...link, time })} />}
              </span>
            </div>
          </div>}
        </>}
      </>}
      <div className="fin-sides">{sideBlock("from")}{sideBlock("to")}</div>
      {error && <span className="fin-error">{error}</span>}
      <FormButtons onCancel={onCancel} onDelete={onDelete} />
    </form>
  );
}

// The tag box's typing room kept beside the chips, and the gap between them (px, as the CSS).
const TAG_INPUT_MIN = 96, TAG_GAP = 4;

/** `tags` with `text` added: trimmed, and not when empty or already there
 *  (letter case aside — the server keeps one spelling of a tag too). */
function addTag(tags: string[], text: string): string[] {
  const tag = text.trim();
  return !tag || tags.some((x) => x.toLowerCase() === tag.toLowerCase()) ? tags : [...tags, tag];
}

/** A payment's tags as chips (✕ takes one off), then a box to type another:
 *  Enter or ";" adds it, Backspace in the empty box takes the last one off.
 *  Tags already used elsewhere that hold what is typed are offered under it:
 *  ↑ ↓ move through them, Enter takes the one lit, Esc closes them.
 *  Collapsed to one line: the chips that fit, then "+N" for the rest, which
 *  opens them all (wrapping) until "−" folds them back. */
function TagField({ tags, onChange, draft, onDraft, all }: {
  tags: string[]; onChange: (tags: string[]) => void; draft: string; onDraft: (text: string) => void; all: string[];
}) {
  const { t } = useT();
  const id = useId();
  const [open, setOpen] = useState(false);
  const [lit, setLit] = useState(-1);   // the offer ↑ ↓ are on (-1: none, Enter adds what is typed)
  const box = useRef<HTMLSpanElement>(null);
  const pop = useRef<HTMLSpanElement>(null);
  const measure = useRef<HTMLSpanElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [fit, setFit] = useState(tags.length);   // chips shown while collapsed
  // How many chips fit on the line beside the typing box (and "+N", if any
  // are left out), from an unseen copy of them all.
  useLayoutEffect(() => {
    const el = box.current, m = measure.current;
    if (!el || !m) return;
    const count = () => {
      const cs = getComputedStyle(el);
      const room = el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) - TAG_INPUT_MIN;
      const kids = [...m.children] as HTMLElement[];
      const plus = kids.pop()!.offsetWidth + TAG_GAP;
      let used = 0, k = 0;
      for (; k < kids.length; k++) {
        const next = used + kids[k].offsetWidth + TAG_GAP;
        if (next + (k + 1 < kids.length ? plus : 0) > room) break;
        used = next;
      }
      setFit(k);
    };
    count();
    const ro = new ResizeObserver(count);
    ro.observe(el);
    return () => ro.disconnect();
  }, [tags]);
  const visible = expanded ? tags : tags.slice(0, fit);
  useEffect(() => { pop.current?.children[lit]?.scrollIntoView({ block: "nearest" }); }, [lit]);
  const q = draft.trim().toLowerCase();
  const offers = q ? all.filter((x) => x.toLowerCase().includes(q) && !tags.some((y) => y.toLowerCase() === x.toLowerCase())).slice(0, 8) : [];
  const shown = open && offers.length > 0;
  useBackToClose(() => setOpen(false), shown);
  const add = (text: string) => { onChange(addTag(tags, text)); onDraft(""); setLit(-1); };
  return (
    <label htmlFor={id} className="fin-f-tags">{t("fin_tags")}
      <span className={"fin-tags-box" + (expanded ? " expanded" : "")} ref={box}>
        <span className="fin-tags-measure" ref={measure} aria-hidden>
          {tags.map((tag) => <span key={tag} className="fin-tag">{tag}<span className="fin-tag-del"><Icon name="close" size={12} className="" /></span></span>)}
          <span className="fin-tag fin-tag-more">+{tags.length}</span>
        </span>
        {visible.map((tag) => (
          <span key={tag} className="fin-tag">
            {tag}
            <button type="button" className="fin-tag-del" title={t("fin_remove_tag")} aria-label={t("fin_remove_tag")}
                    onClick={() => onChange(tags.filter((x) => x !== tag))}>
              <Icon name="close" size={12} className="" />
            </button>
          </span>
        ))}
        {!expanded && fit < tags.length && (
          <button type="button" className="fin-tag fin-tag-more" title={tags.slice(fit).join(", ")}
                  onClick={() => setExpanded(true)}>+{tags.length - fit}</button>
        )}
        {expanded && fit < tags.length && (
          <button type="button" className="fin-tag fin-tag-more" title={t("fin_tags_fold")} aria-label={t("fin_tags_fold")}
                  onClick={() => setExpanded(false)}>−</button>
        )}
        <input id={id} className="fin-tags-input" value={draft} autoComplete="off"
               onChange={(e) => {
                 // Typed or pasted ";" ends a tag ("Dodi; 2" makes two).
                 const parts = e.target.value.split(";");
                 if (parts.length > 1) {
                   onChange(parts.slice(0, -1).reduce(addTag, tags));
                   onDraft(parts[parts.length - 1]);
                 } else onDraft(e.target.value);
                 setOpen(true);
                 setLit(-1);
               }}
               onKeyDown={(e) => {
                 if (shown && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
                   e.preventDefault();
                   const n = offers.length, step = e.key === "ArrowDown" ? 1 : -1;
                   setLit((i) => (i < 0 ? (step > 0 ? 0 : n - 1) : (i + step + n) % n));
                 } else if (e.key === "Escape" && shown) { e.preventDefault(); e.stopPropagation(); setOpen(false); setLit(-1); }
                 else if (e.key === "Enter") { e.preventDefault(); add(shown && offers[lit] ? offers[lit] : draft); }
                 else if (e.key === "Backspace" && !draft && tags.length) onChange(tags.slice(0, -1));
               }}
               onBlur={(e) => { if (!pop.current?.contains(e.relatedTarget as Node)) { setOpen(false); setLit(-1); } }} />
      </span>
      {shown && (
        <Floating anchor={box} ref={pop} className="fin-cat-list">
          {offers.map((x, i) => (
            <button type="button" key={x} className={i === lit ? "active" : ""} onMouseEnter={() => setLit(i)} onMouseDown={(e) => e.preventDefault()} onClick={() => { add(x); setOpen(false); }}>{x}</button>
          ))}
        </Floating>
      )}
    </label>
  );
}

/** A category dropdown that draws each one's icon (a native <select> can only
 *  hold text): a button with the current one's icon and path, opening the
 *  tree of them all. `empty` names the no-category choice; `exclude` drops
 *  a category and everything under it (a category's own parent picker). */
function CategorySelect({ tree, value, onChange, empty, exclude }: {
  tree: Tree; value: number | null; onChange: (id: number | null) => void; empty: ReactNode; exclude?: number;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLSpanElement>(null);
  useBackToClose(() => setOpen(false), open);
  useEffect(() => {
    if (!open) return;
    const down = (e: PointerEvent) => {
      const at = e.target as Node;
      if (!box.current?.contains(at) && !pop.current?.contains(at)) setOpen(false);
    };
    document.addEventListener("pointerdown", down);
    return () => document.removeEventListener("pointerdown", down);
  }, [open]);

  // tree.ordered is depth-first, so a category's descendants are the rows
  // right after it that sit deeper.
  const shown = useMemo(() => {
    const out: Tree["ordered"] = [];
    let skipDepth: number | null = null;
    for (const o of tree.ordered) {
      if (skipDepth != null && o.depth > skipDepth) continue;
      skipDepth = null;
      if (o.cat.id === exclude) { skipDepth = o.depth; continue; }
      out.push(o);
    }
    return out;
  }, [tree, exclude]);

  const pick = (id: number | null) => { onChange(id); setOpen(false); };
  return (
    <span className="fin-cat-select" ref={box}>
      <button type="button" ref={btn} className={"fin-cat-btn" + (open ? " active" : "")} onClick={() => setOpen(!open)}>
        {value == null ? <span className="muted">{empty}</span> : (() => {
          const o = tree.ordered.find((x) => x.cat.id === value);
          return o ? <><CatIcon icon={o.cat.icon} /><span className="fin-cat-btn-name" title={o.label}>{o.cat.name}</span></> : "?";
        })()}
        <span className="fin-caret" aria-hidden>▾</span>
      </button>
      {open && (
        <Floating anchor={btn} ref={pop} className="fin-cat-list">
          <button type="button" className={value == null ? "active" : ""} onClick={() => pick(null)}>
            <span className="muted">{empty}</span>
          </button>
          {shown.map((o) => (
            <button type="button" key={o.cat.id} className={o.cat.id === value ? "active" : ""}
                    style={{ paddingLeft: 8 + o.depth * 18 }} onClick={() => pick(o.cat.id)}>
              <CatIcon icon={o.cat.icon} /> {o.cat.name}
            </button>
          ))}
        </Floating>
      )}
    </span>
  );
}
