import { useMemo, useState } from "react";
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";
import type { PlotParams } from "react-plotly.js";
import { Currency, FinExecuted, FinForecast, FinSnapshot } from "../api";
import { useBackToClose } from "../backClose";
import { readCookie, writeCookie } from "../cookies";
import { Key, num, plotSeparators, useT } from "../i18n";
import { Icon } from "./icons";
import { addDays } from "./CalendarPanel";
import { DIR_COLOR, Effect, flowOf, plannedDates, Worth, worthOn } from "./FinanceCalendar";

const Plot = createPlotlyComponent(Plotly);

const TODAY = new Date().toLocaleDateString("en-CA");
// What was picked last: the period (a preset, or "from|until"), the
// grouping, the currency (the calendar bar's) and the charts ticked.
const RANGE_COOKIE = "finance_chart_range";
const GROUP_COOKIE = "finance_chart_group";
const SHOWN_COOKIE = "finance_charts";
const UNIT_COOKIE = "finance_unit";

// Months back from today (MAX: from the first payment).
const PRESETS: Record<string, number | null> = { "1M": 1, "6M": 6, "1Y": 12, "5Y": 60, MAX: null };
type Group = "week" | "month" | "year";
const GROUPS: { key: Group; label: Key }[] = [
  { key: "week", label: "fin_by_week" }, { key: "month", label: "fin_by_month" }, { key: "year", label: "fin_by_year" },
];
type ChartKey = "balance" | "flows" | "spending" | "income" | "trend" | "sankey";
const CHARTS: { key: ChartKey; label: Key }[] = [
  { key: "balance", label: "fin_chart_balance" },
  { key: "flows", label: "fin_chart_flows" },
  { key: "spending", label: "fin_chart_spending" },
  { key: "income", label: "fin_chart_income" },
  { key: "trend", label: "fin_chart_trend" },
  { key: "sankey", label: "fin_chart_sankey" },
];
// Spending over time: this many top-level categories, the rest as Other.
const TOP = 8;
const OUTSIDE = "outside";

const monthsBack = (n: number) => {
  const [y, m, d] = TODAY.split("-").map(Number);
  const last = new Date(y, m - 1 - n + 1, 0).getDate();
  return new Date(y, m - 1 - n, Math.min(d, last)).toLocaleDateString("en-CA");
};

/** The first day of the week (Monday), month or year `date` falls in. */
function bucketOf(date: string, group: Group): string {
  if (group === "year") return date.slice(0, 4) + "-01-01";
  if (group === "month") return date.slice(0, 7) + "-01";
  const wd = (new Date(date + "T00:00:00").getDay() + 6) % 7;
  return addDays(date, -wd);
}
function nextBucket(b: string, group: Group): string {
  if (group === "week") return addDays(b, 7);
  const [y, m] = b.split("-").map(Number);
  return group === "year" ? `${y + 1}-01-01` : new Date(y, m, 1).toLocaleDateString("en-CA");
}

type Entry = { date: string; p: FinExecuted | FinForecast; planned: boolean };

/** Finance's charts, over the page: the Charts panels' controls on the left
 *  (the period, the grouping, the currency, which charts), the charts at
 *  their right. Forecasts' dates still to come count as the calendar's do
 *  (the balance's line goes on dashed past today). Amounts in the picked
 *  currency, each at its own day's rate (a balance at the day it's drawn
 *  for); with no rate at all, as they are. */
export function FinanceCharts({ data, worth, effect, convert, onClose }: {
  data: FinSnapshot;
  /** The Stocks portfolio's worth, for the investments' line (null: none). */
  worth: Worth | null;
  effect: (p: FinExecuted | FinForecast) => Effect;
  convert: (cents: number, from: Currency, to: Currency, date: string) => number | null;
  onClose: () => void;
}) {
  const { t, lang } = useT();
  useBackToClose(onClose);
  const first = data.executed.length ? data.executed[data.executed.length - 1].date : TODAY;

  const [range, setRangeState] = useState(() => readCookie(RANGE_COOKIE) ?? "MAX");
  const setRange = (r: string) => { setRangeState(r); writeCookie(RANGE_COOKIE, r); };
  const preset = range in PRESETS ? range : "";
  const [from, until] = preset
    ? [PRESETS[preset] == null ? first : monthsBack(PRESETS[preset]!), TODAY]
    : (range.split("|") as [string, string]);
  const [group, setGroupState] = useState<Group>(() => {
    const g = readCookie(GROUP_COOKIE);
    return g === "week" || g === "year" ? g : "month";
  });
  const setGroup = (g: Group) => { setGroupState(g); writeCookie(GROUP_COOKIE, g); };
  const [unit, setUnitState] = useState<Currency>(() => (readCookie(UNIT_COOKIE) === "USD" ? "USD" : "EUR"));
  const setUnit = (c: Currency) => { setUnitState(c); writeCookie(UNIT_COOKIE, c); };
  const [shown, setShownState] = useState<Set<ChartKey>>(() => {
    const c = readCookie(SHOWN_COOKIE);
    return new Set((c == null ? CHARTS.map((x) => x.key) : c.split(",")) as ChartKey[]);
  });
  const toggle = (k: ChartKey, on: boolean) => {
    const n = new Set(shown);
    if (on) n.add(k); else n.delete(k);
    setShownState(n);
    writeCookie(SHOWN_COOKIE, [...n].join(","));
  };

  const cats = useMemo(() => new Map(data.categories.map((c) => [c.id, c])), [data.categories]);
  // An account's money is in the balance; an investment's is one's own too
  // (paying into it is a transfer), counted at the portfolio's worth.
  const isAccount = (id: number | null) => id != null && cats.get(id)?.kind === "account";
  const isOwn = (id: number | null) => id != null && !!cats.get(id)?.kind;
  const investment = data.categories.find((c) => c.kind === "investment" && !c.archived);
  const nameOf = (id: string) => (id === OUTSIDE ? t("fin_outside") : cats.get(Number(id))?.name ?? "?");
  const rootOf = (id: number | null): string => {
    if (id == null) return OUTSIDE;
    let c = cats.get(id);
    while (c?.parent_id != null && cats.has(c.parent_id)) c = cats.get(c.parent_id);
    return String(c?.id ?? id);
  };
  // An amount in the picked currency, in whole units (what the charts draw).
  const amt = (cents: number, cur: Currency, date: string) => (convert(cents, cur, unit, date) ?? cents) / 100;

  // Every payment up to `until`, oldest first, with the forecasts' dates still to come.
  const all = useMemo(() => {
    const out: Entry[] = [];
    for (const p of data.executed) if (p.date <= until) out.push({ date: p.date, p, planned: false });
    for (const f of data.forecasts) for (const d of plannedDates(f, "", until)) out.push({ date: d, p: f, planned: true });
    return out.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  }, [data.executed, data.forecasts, until]);
  const inRange = useMemo(() => all.filter((e) => e.date >= from), [all, from]);

  const buckets = useMemo(() => {
    const out: string[] = [];
    if (from > until) return out;
    for (let b = bucketOf(from, group); b <= until; b = nextBucket(b, group)) out.push(b);
    return out;
  }, [from, until, group]);
  // Bars on a date axis, each across its week, month or year.
  const period = {
    xperiod: group === "week" ? 7 * 86400000 : group === "month" ? "M1" : "M12", xperiodalignment: "middle" as const,
  };
  const bucketAxis = {
    gridcolor: "#333", type: "date" as const, automargin: true,
    hoverformat: group === "year" ? "%Y" : group === "month" ? "%b %Y" : "%d %b %Y",
  };

  // ── the balance: each account's, and all of them together, day by day ──
  const balance = useMemo(() => {
    const running = new Map<number, Partial<Record<Currency, number>>>();
    const apply = (e: Entry) => {
      for (const l of e.p.lines) if (isAccount(l.category_id)) {
        const b = running.get(l.category_id!) ?? {};
        b[e.p.currency] = (b[e.p.currency] ?? 0) + (l.side === "to" ? l.amount_cents : -l.amount_cents);
        running.set(l.category_id!, b);
      }
    };
    let i = 0;
    while (i < all.length && all[i].date < from) apply(all[i++]);
    const dates = new Set<string>([from, until]);
    if (from < TODAY && TODAY < until) dates.add(TODAY);
    for (let j = i; j < all.length; j++) dates.add(all[j].date);
    // The portfolio's trading days too, so the total follows its worth.
    if (investment && worth) for (const d of worth.index) if (d >= from && d <= until) dates.add(d);
    const series = new Map<number, number[]>();
    const xs = [...dates].sort();
    xs.forEach((d, k) => {
      while (i < all.length && all[i].date <= d) apply(all[i++]);
      for (const [id, b] of running) {
        const s = series.get(id) ?? new Array(xs.length).fill(0);
        s[k] = (Object.entries(b) as [Currency, number][]).reduce((n, [cur, c]) => n + amt(c, cur, d), 0);
        series.set(id, s);
      }
    });
    // The investments' worth on each of those days (null: none).
    const invested = investment && worth ? xs.map((d) => amt(worthOn(worth, d), "EUR", d)) : null;
    return { xs, series, invested };
  }, [all, from, until, unit, cats, worth]);   // eslint-disable-line react-hooks/exhaustive-deps

  // ── income and spending per bucket, by category ──
  const flows = useMemo(() => {
    const index = new Map(buckets.map((b, k) => [b, k]));
    const income = buckets.map(() => 0), spending = buckets.map(() => 0);
    const spentBy = new Map<string, number>(), earnedBy = new Map<string, number>();
    const spentByRoot = new Map<string, number[]>();
    for (const e of inRange) {
      const k = index.get(bucketOf(e.date, group));
      if (k == null) continue;
      const ef = effect(e.p), f = flowOf(ef);
      if (!f) continue;
      (f.as === "in" ? income : spending)[k] += f.sign * amt(ef.cents, e.p.currency, e.date);
      // Where it went (spending: the To side's non-accounts) or came from
      // (income: the From side's); money given back, the other way round.
      for (const l of e.p.lines) {
        if (isOwn(l.category_id) || l.side !== (ef.dir === "out" ? "to" : "from")) continue;
        const v = f.sign * amt(l.amount_cents, e.p.currency, e.date), id = l.category_id == null ? OUTSIDE : String(l.category_id);
        const by = f.as === "out" ? spentBy : earnedBy;
        by.set(id, (by.get(id) ?? 0) + v);
        if (f.as === "out") {
          const root = rootOf(l.category_id), s = spentByRoot.get(root) ?? buckets.map(() => 0);
          s[k] += v;
          spentByRoot.set(root, s);
        }
      }
    }
    return { income, spending, spentBy, earnedBy, spentByRoot };
  }, [inRange, buckets, group, unit, cats, effect]);   // eslint-disable-line react-hooks/exhaustive-deps

  // ── from income, through the accounts, to spending (top-level categories) ──
  const sankey = useMemo(() => {
    const links = new Map<string, number>();
    for (const e of inRange) {
      const f = flowOf(effect(e.p));
      if (!f) continue;
      const total = e.p.lines.reduce((n, l) => n + (l.side === "from" ? l.amount_cents : 0), 0);
      if (!total) continue;
      // A side's lines share the other's in proportion.
      for (const a of e.p.lines) for (const b of e.p.lines) {
        if (a.side !== "from" || b.side !== "to") continue;
        const accA = isOwn(a.category_id), accB = isOwn(b.category_id);
        if (accA === accB) continue;   // a transfer, or no money of one's own
        // Money given back takes off the link it would have gone the other way.
        const acc = accA ? a.category_id : b.category_id, other = rootOf(accA ? b.category_id : a.category_id);
        const key = f.as === "out" ? `a${acc}>o${other}` : `i${other}>a${acc}`;
        links.set(key, (links.get(key) ?? 0) + f.sign * amt(a.amount_cents * b.amount_cents / total, e.p.currency, e.date));
      }
    }
    return links;
  }, [inRange, unit, cats, effect]);   // eslint-disable-line react-hooks/exhaustive-deps

  // ── drawing ──
  const [pre, suf] = unit === "USD" ? ["$", ""] : ["", " €"];
  const money = `${pre}%{VALUE:,.2f}${suf}`;
  // Where Plotly's number formats skip the language's separators (Sankey):
  // written out here, the app's way.
  const write = (v: number) => num(v, lang, { style: "currency", currency: unit, currencyDisplay: "narrowSymbol" });
  // Tooltips in the app's colours (Plotly's take the trace's otherwise).
  const tip = { bgcolor: "#1c2029", bordercolor: "#2a2f3a", font: { color: "#e6e6e6" } };
  const base: Partial<PlotParams["layout"]> = {
    margin: { l: 64, r: 16, t: 36, b: 36 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#bbb" },
    separators: plotSeparators(),
    xaxis: { gridcolor: "#333", automargin: true },
    yaxis: { gridcolor: "#333", automargin: true, tickprefix: pre, ticksuffix: suf, tickformat: ",.0f", zerolinecolor: "#555" },
    showlegend: true,
    legend: { orientation: "h", x: 1, xanchor: "right", y: 1, yanchor: "bottom" },
    hovermode: "x unified",
    hoverlabel: tip,
  };
  const plot = (key: ChartKey, plotData: PlotParams["data"], layout: Partial<PlotParams["layout"]>, height: number) => (
    <div key={key} className="chart-block">
      <div className="chart-title">{t(CHARTS.find((c) => c.key === key)!.label)}</div>
      <Plot data={plotData} layout={{ ...base, ...layout, height } as PlotParams["layout"]}
            config={{ displayModeBar: false }} style={{ width: "100%" }} useResizeHandler />
    </div>
  );

  const balanceChart = () => {
    const { xs, series, invested } = balance;
    const past = xs.filter((d) => d <= TODAY).length;
    const traces: PlotParams["data"] = [];
    const line = (name: string, ys: number[], style: object, extra: object) => {
      traces.push({ x: xs.slice(0, past), y: ys.slice(0, past), name, type: "scatter", mode: "lines",
                    line: { shape: "hv", ...style }, legendgroup: name,
                    hovertemplate: money.replace("VALUE", "y"), ...extra });
      if (past < xs.length)
        traces.push({ x: xs.slice(Math.max(0, past - 1)), y: ys.slice(Math.max(0, past - 1)), name, type: "scatter",
                      mode: "lines", line: { shape: "hv", dash: "dash", ...style }, legendgroup: name,
                      showlegend: false, hovertemplate: money.replace("VALUE", "y"), ...extra });
    };
    // Archived accounts are in the total; their own lines start hidden (a
    // tap on the legend shows one).
    const ids = [...series.keys()].filter((id) => series.get(id)!.some((v) => Math.abs(v) >= 0.005))
      .sort((a, b) => (cats.get(a)?.sort ?? 0) - (cats.get(b)?.sort ?? 0));
    const total = xs.map((_, k) => [...series.values()].reduce((n, s) => n + s[k], invested?.[k] ?? 0));
    line(t("fin_total"), total, { color: "#e6edf3", width: 2.5 }, {});
    for (const id of ids)
      line(cats.get(id)?.name ?? "?", series.get(id)!, { width: 1.5 }, cats.get(id)?.archived ? { visible: "legendonly" } : {});
    // The investments: the portfolio's worth, in the total too.
    if (investment && invested) line(investment.name, invested, { width: 1.5, color: "#bc8cff" }, {});
    return plot("balance", traces, { xaxis: { gridcolor: "#333", type: "date", automargin: true } }, 380);
  };

  const flowsChart = () => {
    const x = buckets;
    const net = flows.income.map((v, k) => v - flows.spending[k]);
    return plot("flows", [
      { x, y: flows.income, name: t("fin_income"), type: "bar", ...period, marker: { color: DIR_COLOR.in }, hovertemplate: money.replace("VALUE", "y") },
      { x, y: flows.spending, name: t("fin_spending"), type: "bar", ...period, marker: { color: DIR_COLOR.out }, hovertemplate: money.replace("VALUE", "y") },
      { x, y: net, name: t("fin_net"), type: "scatter", mode: "lines+markers", ...period, line: { color: DIR_COLOR.move, width: 2 },
        hovertemplate: money.replace("VALUE", "y") },
    ], { barmode: "group", xaxis: bucketAxis }, 340);
  };

  // A sunburst of the category tree: each one's own amount and its sub-categories'.
  const sunburst = (key: ChartKey, by: Map<string, number>) => {
    const total = new Map<string, number>();
    // A category given back more than was spent on it in the period counts as none.
    for (const [id, net] of by) {
      const v = Math.max(net, 0);
      let c: string | undefined = id;
      while (c) {
        total.set(c, (total.get(c) ?? 0) + v);
        const parent: number | null | undefined = c === OUTSIDE ? null : cats.get(Number(c))?.parent_id;
        c = parent != null && cats.has(parent) ? String(parent) : undefined;
      }
    }
    const ids = [...total.keys()].filter((id) => total.get(id)! >= 0.005);
    const parentOf = (id: string) => {
      const p = id === OUTSIDE ? null : cats.get(Number(id))?.parent_id;
      return p != null && total.has(String(p)) ? String(p) : "";
    };
    return plot(key, [{
      type: "sunburst", ids, labels: ids.map(nameOf), parents: ids.map(parentOf), values: ids.map((id) => total.get(id)!),
      branchvalues: "total", textinfo: "label+percent root", insidetextorientation: "radial",
      hovertemplate: `%{label}<br>${money.replace("VALUE", "value")}<br>%{percentRoot:.1%}<extra></extra>`,
      marker: { line: { color: "#161b22", width: 1 } }, hoverlabel: tip,
    }], { margin: { l: 0, r: 0, t: 4, b: 4 }, showlegend: false }, 620);
  };

  const trendChart = () => {
    const x = buckets;
    const sum = (s: number[]) => s.reduce((n, v) => n + v, 0);
    const roots = [...flows.spentByRoot.entries()].sort((a, b) => sum(b[1]) - sum(a[1]));
    const top = roots.slice(0, TOP), rest = roots.slice(TOP);
    const traces: PlotParams["data"] = top.map(([id, ys]) => ({
      x, y: ys.map((v) => v || null), name: nameOf(id), type: "bar", ...period, hovertemplate: money.replace("VALUE", "y"),
    }));
    if (rest.length) traces.push({
      x, y: buckets.map((_, k) => rest.reduce((n, [, ys]) => n + ys[k], 0) || null), name: t("fin_other"), type: "bar", ...period,
      marker: { color: "#6e7681" }, hovertemplate: money.replace("VALUE", "y"),
    });
    return plot("trend", traces, { barmode: "stack", xaxis: bucketAxis }, 380);
  };

  const sankeyChart = () => {
    const nodes: string[] = [], index = new Map<string, number>(), colors: string[] = [];
    const node = (key: string) => {
      if (!index.has(key)) {
        index.set(key, nodes.length);
        const id = key.slice(1);
        nodes.push(key[0] === "a" ? cats.get(Number(id))?.name ?? "?" : nameOf(id));
        colors.push(key[0] === "i" ? DIR_COLOR.in : key[0] === "o" ? DIR_COLOR.out : DIR_COLOR.move);
      }
      return index.get(key)!;
    };
    const source: number[] = [], target: number[] = [], value: number[] = [], linkColors: string[] = [];
    const into: number[] = [], out: number[] = [];
    for (const [key, v] of [...sankey.entries()].sort((a, b) => b[1] - a[1])) {
      if (v < 0.005) continue;
      const [a, b] = key.split(">");
      const sa = node(a), tb = node(b);
      source.push(sa); target.push(tb); value.push(v);
      out[sa] = (out[sa] ?? 0) + v; into[tb] = (into[tb] ?? 0) + v;
      linkColors.push(a[0] === "i" ? "rgba(63,185,80,0.25)" : "rgba(248,81,73,0.25)");
    }
    // A node's amount as Plotly sizes it: the bigger of what comes in and goes out.
    const nodeAmounts = nodes.map((_, k) => write(Math.max(into[k] ?? 0, out[k] ?? 0)));
    const height = Math.max(420, Math.min(1000, nodes.length * 22));
    return plot("sankey", [{
      type: "sankey", arrangement: "fixed",
      node: { label: nodes, color: colors, pad: 12, thickness: 14, line: { width: 0 },
              customdata: nodeAmounts, hoverlabel: tip, hovertemplate: "%{label}<br>%{customdata}<extra></extra>" },
      link: { source, target, value, color: linkColors, customdata: value.map(write), hoverlabel: tip,
              hovertemplate: "%{source.label} → %{target.label}<br>%{customdata}<extra></extra>" },
    // Room below for a bottom node's tooltip (the charts' last; nothing under it to spill on).
    }], { margin: { l: 8, r: 8, t: 8, b: 56 }, showlegend: false, hovermode: "closest" }, height);
  };

  const short = (iso: string) =>
    new Date(iso + "T00:00:00").toLocaleDateString(lang, { day: "2-digit", month: "2-digit", year: "2-digit" });
  const has = (k: ChartKey) => shown.has(k);
  const empty = !inRange.length && !balance.series.size;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal fin-charts" onClick={(e) => e.stopPropagation()}>
        <div className="env-tab-body">
          <aside className="env-controls">
            <section>
              <h3>{t("env_date_range")}</h3>
              <div className="presets">
                {Object.keys(PRESETS).map((label) => (
                  <button key={label} className={preset === label ? "active" : ""} onClick={() => setRange(label)}>{label}</button>
                ))}
              </div>
              <div className="dates">
                <input type="date" value={from} max={until} onChange={(e) => e.target.value && setRange(`${e.target.value}|${until}`)} />
                <input type="date" value={until} min={from} onChange={(e) => e.target.value && setRange(`${from}|${e.target.value}`)} />
              </div>
            </section>
            <section>
              <h3>{t("env_resample")}</h3>
              <select value={group} onChange={(e) => setGroup(e.target.value as Group)}>
                {GROUPS.map((g) => <option key={g.key} value={g.key}>{t(g.label)}</option>)}
              </select>
            </section>
            <section>
              <h3>{t("fin_unit")}</h3>
              <select value={unit} onChange={(e) => setUnit(e.target.value as Currency)}>
                <option value="EUR">€</option>
                <option value="USD">$</option>
              </select>
            </section>
            <section>
              <h3>{t("fin_charts")}</h3>
              {CHARTS.map((c) => (
                <label key={c.key} className="check">
                  <input type="checkbox" checked={has(c.key)} onChange={(e) => toggle(c.key, e.target.checked)} />
                  {t(c.label)}
                </label>
              ))}
            </section>
          </aside>

          <div className="env-charts">
            <div className="env-title">
              <h1>{t("fin_charts")} {short(from)} – {short(until)}</h1>
              <button className="ghost icon-only" title={t("close")} aria-label={t("close")} onClick={onClose}>
                <Icon name="close" size={18} className="" />
              </button>
            </div>
            <p className="muted env-range">{t(GROUPS.find((g) => g.key === group)!.label)}</p>
            {empty && <p className="muted">{t("fin_no_payments")}</p>}
            {!empty && <>
              {has("balance") && balanceChart()}
              {has("flows") && flowsChart()}
              {(has("spending") || has("income")) && (
                <div className="fin-charts-pair">
                  {has("spending") && sunburst("spending", flows.spentBy)}
                  {has("income") && sunburst("income", flows.earnedBy)}
                </div>
              )}
              {has("trend") && trendChart()}
              {has("sankey") && sankeyChart()}
            </>}
          </div>
        </div>
      </div>
    </div>
  );
}
