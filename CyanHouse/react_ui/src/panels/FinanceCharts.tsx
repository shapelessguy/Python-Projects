import { useMemo, useRef, useState } from "react";
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";
import type { PlotParams } from "react-plotly.js";
import { Currency, FinCategory, FinExecuted, FinForecast, FinSnapshot } from "../api";
import { useBackToClose } from "../backClose";
import { readCookie, writeCookie } from "../cookies";
import { Key, num, plotSeparators, useT } from "../i18n";
import { usePhone } from "../narrow";
import { Icon, IconName } from "./icons";
import { addDays } from "./CalendarPanel";
import { DIR_COLOR, Effect, flowOf, plannedDates, Worth, worthOn } from "./FinanceCalendar";

const Plot = createPlotlyComponent(Plotly);

const TODAY = new Date().toLocaleDateString("en-CA");
// What was picked last: the period (a preset, or "from|until"), the
// grouping, the currency (the calendar bar's) and the charts ticked.
const RANGE_COOKIE = "finance_chart_range";
const GROUP_COOKIE = "finance_chart_group";
// The charts unticked (a chart added later starts shown); before, the ticked
// ones were kept, in the old cookie.
const HIDDEN_COOKIE = "finance_charts_hidden";
const OLD_SHOWN_COOKIE = "finance_charts";
const UNIT_COOKIE = "finance_unit";
// The categories (ids, or "outside") and tags left out of every chart, as JSON.
const EX_CATS_COOKIE = "finance_chart_ex_cats";
const EX_TAGS_COOKIE = "finance_chart_ex_tags";
const readSet = (name: string) => {
  try { return new Set<string>(JSON.parse(readCookie(name) ?? "[]")); } catch { return new Set<string>(); }
};

// Months back from today (MAX: from the first payment).
const PRESETS: Record<string, number | null> = { "1M": 1, "6M": 6, "1Y": 12, "5Y": 60, MAX: null };
type Group = "week" | "month" | "year";
const GROUPS: { key: Group; label: Key }[] = [
  { key: "week", label: "fin_by_week" }, { key: "month", label: "fin_by_month" }, { key: "year", label: "fin_by_year" },
];
type ChartKey = "balance" | "flows" | "income" | "spending" | "trendIn" | "trend" | "sankey";
const CHARTS: { key: ChartKey; label: Key }[] = [
  { key: "balance", label: "fin_chart_balance" },
  { key: "flows", label: "fin_chart_flows" },
  { key: "income", label: "fin_chart_income" },
  { key: "spending", label: "fin_chart_spending" },
  { key: "trendIn", label: "fin_chart_trend_in" },
  { key: "trend", label: "fin_chart_trend" },
  { key: "sankey", label: "fin_chart_sankey" },
];
// A phone: the charts two to a page, a tab each (an icon); no Sankey there.
const PAGES: { icon: IconName; label: Key; charts: ChartKey[] }[] = [
  { icon: "chart", label: "fin_chart_balance", charts: ["balance", "flows"] },
  { icon: "pie", label: "fin_chart_income", charts: ["income", "spending"] },
  { icon: "clock", label: "fin_chart_trend_in", charts: ["trendIn", "trend"] },
];
// Income and spending over time: this many top-level categories, the rest as Other.
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
 *  (a search, the period, the grouping, which charts), the charts at
 *  their right, the currency at their title. A phone: over the whole
 *  screen, the charts two to a page (a tab each, or a swipe), the settings
 *  from the gear. Forecasts' dates still to come count as the calendar's do
 *  (the balance's line goes on dashed past today). Amounts in the picked
 *  currency, each at its own day's rate (a balance at the day it's drawn
 *  for); with no rate at all, as they are. */
export function FinanceCharts({ data, ordered, tags, worth, effect, convert, onClose }: {
  data: FinSnapshot;
  /** The categories in tree order, for the filter's list. */
  ordered: { cat: FinCategory; depth: number }[];
  /** Every tag in use, most used first. */
  tags: string[];
  /** The Stocks portfolio's worth, for the investments' line (null: none). */
  worth: Worth | null;
  effect: (p: FinExecuted | FinForecast) => Effect;
  convert: (cents: number, from: Currency, to: Currency, date: string) => number | null;
  onClose: () => void;
}) {
  const { t, lang } = useT();
  useBackToClose(onClose);
  const phone = usePhone();
  // A phone: the settings (the period, the filters) over the screen, from the gear.
  const [controlsOpen, setControlsOpen] = useState(false);
  useBackToClose(() => setControlsOpen(false), controlsOpen);
  const [page, setPage] = useState(0);
  const touch = useRef<{ x: number; y: number } | null>(null);
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
  const [hidden, setHiddenState] = useState<Set<ChartKey>>(() => {
    const h = readCookie(HIDDEN_COOKIE);
    if (h != null) return new Set(h.split(",").filter(Boolean) as ChartKey[]);
    const old = readCookie(OLD_SHOWN_COOKIE)?.split(",");
    return new Set(old ? CHARTS.map((x) => x.key).filter((k) => k !== "trendIn" && !old.includes(k)) : []);
  });
  const toggle = (k: ChartKey, on: boolean) => {
    const n = new Set(hidden);
    if (on) n.delete(k); else n.add(k);
    setHiddenState(n);
    writeCookie(HIDDEN_COOKIE, [...n].join(","));
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

  // The filter: a payment with a line in a category left out (or in one of
  // its sub-categories), or with a tag left out, counts in no chart at all --
  // not even the balance.
  const [exCats, setExCatsState] = useState(() => readSet(EX_CATS_COOKIE));
  const [exTags, setExTagsState] = useState(() => readSet(EX_TAGS_COOKIE));
  const setExCats = (n: Set<string>) => { setExCatsState(n); writeCookie(EX_CATS_COOKIE, JSON.stringify([...n])); };
  const setExTags = (n: Set<string>) => { setExTagsState(n); writeCookie(EX_TAGS_COOKIE, JSON.stringify([...n])); };
  const flip = (set: Set<string>, key: string, on: boolean) => {
    const n = new Set(set);
    if (on) n.delete(key); else n.add(key);
    return n;
  };
  /** Whether a category is left out: itself, or a parent of it. */
  const catOut = (id: number | null): boolean => {
    if (id == null) return exCats.has(OUTSIDE);
    for (let c = cats.get(id); c; c = c.parent_id != null ? cats.get(c.parent_id) : undefined)
      if (exCats.has(String(c.id))) return true;
    return false;
  };
  const parentOut = (c: FinCategory) => c.parent_id != null && catOut(c.parent_id);

  // Every payment up to `until` the filter lets through, oldest first, with
  // the forecasts' dates still to come.
  const all = useMemo(() => {
    const kept = (p: FinExecuted | FinForecast) =>
      !p.lines.some((l) => catOut(l.category_id)) && !p.tags.some((tag) => exTags.has(tag));
    const out: Entry[] = [];
    for (const p of data.executed) if (p.date <= until && kept(p)) out.push({ date: p.date, p, planned: false });
    for (const f of data.forecasts) if (kept(f)) for (const d of plannedDates(f, "", until)) out.push({ date: d, p: f, planned: true });
    return out.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  }, [data.executed, data.forecasts, until, exCats, exTags, cats]);   // eslint-disable-line react-hooks/exhaustive-deps
  // The search (every word) in a payment's reason, its tags or one of its
  // categories' paths ("Home" finds "Home › Rent"), as the payments sheet's.
  // Not the balance: an account's balance from some of its payments means nothing.
  const [query, setQuery] = useState("");
  const words = useMemo(() => query.trim().toLowerCase().split(/\s+/).filter(Boolean), [query]);
  const inRange = useMemo(() => {
    const path = (id: number | null): string => {
      const c = id == null ? undefined : cats.get(id);
      if (!c) return id == null ? t("fin_outside") : "";
      return (c.parent_id != null && cats.has(c.parent_id) ? path(c.parent_id) + " › " : "") + c.name;
    };
    return all.filter((e) => {
      if (e.date < from) return false;
      if (!words.length) return true;
      const text = [e.p.justification ?? "", ...e.p.tags, ...e.p.lines.map((l) => path(l.category_id))].join(" ").toLowerCase();
      return words.every((w) => text.includes(w));
    });
  }, [all, from, words, cats]);   // eslint-disable-line react-hooks/exhaustive-deps

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
    const spentByRoot = new Map<string, number[]>(), earnedByRoot = new Map<string, number[]>();
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
        const byRoot = f.as === "out" ? spentByRoot : earnedByRoot;
        const root = rootOf(l.category_id), s = byRoot.get(root) ?? buckets.map(() => 0);
        s[k] += v;
        byRoot.set(root, s);
      }
    }
    return { income, spending, spentBy, earnedBy, spentByRoot, earnedByRoot };
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
  // A phone's chart fills its half of the page and doesn't zoom or pan (a
  // swipe across it turns the page).
  const plot = (key: ChartKey, plotData: PlotParams["data"], layout: Partial<PlotParams["layout"]>, height: number) => {
    const title = <div className="chart-title">{t(CHARTS.find((c) => c.key === key)!.label)}</div>;
    if (!phone) return (
      <div key={key} className="chart-block">
        {title}
        <Plot data={plotData} layout={{ ...base, ...layout, height } as PlotParams["layout"]}
              config={{ displayModeBar: false }} style={{ width: "100%" }} useResizeHandler />
      </div>
    );
    const l = { ...base, ...layout } as PlotParams["layout"];
    return (
      <div key={key} className="cp-chart">
        {title}
        <div className="cp-plot">
          <Plot data={plotData} config={{ displayModeBar: false }} style={{ position: "absolute", inset: 0 }} useResizeHandler
                layout={{ ...l, autosize: true, dragmode: false, legend: { ...l.legend, font: { size: 10 } },
                          xaxis: { ...l.xaxis, fixedrange: true }, yaxis: { ...l.yaxis, fixedrange: true } }} />
        </div>
      </div>
    );
  };

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
  // One ring at a time round the total: a category tapped is the centre, its
  // sub-categories the ring (the centre tapped goes back up).
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
    const ROOT = "root";
    const ids = [...total.keys()].filter((id) => total.get(id)! >= 0.005);
    const parentOf = (id: string) => {
      const p = id === OUTSIDE ? null : cats.get(Number(id))?.parent_id;
      return p != null && total.has(String(p)) ? String(p) : ROOT;
    };
    const parents = ids.map(parentOf);
    const sum = ids.reduce((n, id, k) => n + (parents[k] === ROOT ? total.get(id)! : 0), 0);
    return plot(key, [{
      type: "sunburst", ids: [ROOT, ...ids], labels: [t("fin_total"), ...ids.map(nameOf)], parents: ["", ...parents],
      values: [sum, ...ids.map((id) => total.get(id)!)], maxdepth: 2,
      branchvalues: "total", textinfo: "label+percent entry", insidetextorientation: "radial",
      hovertemplate: `%{label}<br>${money.replace("VALUE", "value")}<br>%{percentEntry:.1%}<extra></extra>`,
      marker: { line: { color: "#161b22", width: 1 } }, hoverlabel: tip,
    }], { margin: { l: 0, r: 0, t: 4, b: 4 }, showlegend: false }, 620);
  };

  // Income or spending per bucket, stacked by top-level category.
  const trendChart = (key: ChartKey, byRoot: Map<string, number[]>) => {
    const x = buckets;
    const sum = (s: number[]) => s.reduce((n, v) => n + v, 0);
    const roots = [...byRoot.entries()].sort((a, b) => sum(b[1]) - sum(a[1]));
    const top = roots.slice(0, TOP), rest = roots.slice(TOP);
    const traces: PlotParams["data"] = top.map(([id, ys]) => ({
      x, y: ys.map((v) => v || null), name: nameOf(id), type: "bar", ...period, hovertemplate: money.replace("VALUE", "y"),
    }));
    if (rest.length) traces.push({
      x, y: buckets.map((_, k) => rest.reduce((n, [, ys]) => n + ys[k], 0) || null), name: t("fin_other"), type: "bar", ...period,
      marker: { color: "#6e7681" }, hovertemplate: money.replace("VALUE", "y"),
    });
    return plot(key, traces, { barmode: "stack", xaxis: bucketAxis }, 380);
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
  const has = (k: ChartKey) => !hidden.has(k);
  const empty = !inRange.length && !balance.series.size;
  const draw = (k: ChartKey) =>
    k === "balance" ? balanceChart() : k === "flows" ? flowsChart()
    : k === "income" ? sunburst("income", flows.earnedBy) : k === "spending" ? sunburst("spending", flows.spentBy)
    : k === "trendIn" ? trendChart("trendIn", flows.earnedByRoot) : k === "trend" ? trendChart("trend", flows.spentByRoot)
    : sankeyChart();
  const unitPick = (
    <select className="fin-unit" value={unit} title={t("fin_unit")} aria-label={t("fin_unit")}
            onChange={(e) => setUnit(e.target.value as Currency)}>
      <option value="EUR">€</option>
      <option value="USD">$</option>
    </select>
  );
  const go = (to: number) => setPage(Math.max(0, Math.min(PAGES.length - 1, to)));

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal fin-charts" onClick={(e) => e.stopPropagation()}>
        <div className="env-tab-body">
          <aside className={"env-controls" + (controlsOpen ? " env-controls--open" : "")}>
            <div className="env-controls-head">
              <span>{t("settings")}</span>
              <button className="env-controls-close" onClick={() => setControlsOpen(false)}
                      title={t("close")} aria-label={t("close")}>
                <Icon name="close" size={18} className="" />
              </button>
            </div>
            <section>
              <h3>{t("search")}</h3>
              <input type="search" className="fin-search" placeholder={t("fin_search")} aria-label={t("fin_search")}
                     value={query} onChange={(e) => setQuery(e.target.value)}
                     onKeyDown={(e) => { if (e.key === "Escape" && query) { e.stopPropagation(); setQuery(""); } }} />
            </section>
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
            <section className="fin-filter-section">
              <h3>{t("fin_categories")}</h3>
              <div className="fin-chart-filter-all">
                <button className="ghost" onClick={() => setExCats(new Set())}>{t("fin_filter_all")}</button>
                <button className="ghost" onClick={() => setExCats(new Set([OUTSIDE, ...ordered.filter((o) => o.depth === 0).map((o) => String(o.cat.id))]))}>
                  {t("fin_filter_none")}
                </button>
              </div>
              <div className="fin-chart-filter">
                {ordered.map(({ cat, depth }) => (
                  <label key={cat.id} className={"check" + (cat.archived ? " muted" : "")} style={{ paddingLeft: depth * 16 }}>
                    <input type="checkbox" checked={!catOut(cat.id)} disabled={parentOut(cat)}
                           onChange={(e) => setExCats(flip(exCats, String(cat.id), e.target.checked))} />
                    {cat.name}
                  </label>
                ))}
                <label className="check">
                  <input type="checkbox" checked={!exCats.has(OUTSIDE)}
                         onChange={(e) => setExCats(flip(exCats, OUTSIDE, e.target.checked))} />
                  {t("fin_outside")}
                </label>
              </div>
            </section>
            {tags.length > 0 && (
              <section className="fin-filter-section">
                <h3>{t("fin_tags")}</h3>
                <div className="fin-chart-filter-all">
                  <button className="ghost" onClick={() => setExTags(new Set())}>{t("fin_filter_all")}</button>
                  <button className="ghost" onClick={() => setExTags(new Set(tags))}>{t("fin_filter_none")}</button>
                </div>
                <div className="fin-chart-filter">
                  {tags.map((tag) => (
                    <label key={tag} className="check">
                      <input type="checkbox" checked={!exTags.has(tag)}
                             onChange={(e) => setExTags(flip(exTags, tag, e.target.checked))} />
                      {tag}
                    </label>
                  ))}
                </div>
              </section>
            )}
            {!phone && <section>
              <h3>{t("fin_charts")}</h3>
              {CHARTS.map((c) => (
                <label key={c.key} className="check">
                  <input type="checkbox" checked={has(c.key)} onChange={(e) => toggle(c.key, e.target.checked)} />
                  {t(c.label)}
                </label>
              ))}
            </section>}
          </aside>

          <div className="env-charts">
            <div className="env-title">
              <h1>{t("fin_charts")} {short(from)} – {short(until)}</h1>
              {unitPick}
              <button className="ghost icon-only" title={t("close")} aria-label={t("close")} onClick={onClose}>
                <Icon name="close" size={18} className="" />
              </button>
            </div>
            <p className="muted env-range">{t(GROUPS.find((g) => g.key === group)!.label)}</p>
            {phone && (
              <div className="fin-charts-phone-head">
                <div className="fin-charts-tabs">
                  {PAGES.map((pg, k) => (
                    <button key={pg.icon} className={"icon-only" + (k === page ? " active" : "")}
                            title={t(pg.label)} aria-label={t(pg.label)} aria-pressed={k === page} onClick={() => setPage(k)}>
                      <Icon name={pg.icon} size={20} className="" />
                    </button>
                  ))}
                </div>
                {unitPick}
                <button className="ghost icon-only" title={t("settings")} aria-label={t("settings")}
                        onClick={() => setControlsOpen(true)}>
                  <Icon name="settings" size={20} className="" />
                </button>
                <button className="ghost icon-only" title={t("close")} aria-label={t("close")} onClick={onClose}>
                  <Icon name="close" size={20} className="" />
                </button>
              </div>
            )}
            {empty && <p className="muted">{t("fin_no_payments")}</p>}
            {!empty && phone && (
              <div className="cp-page"
                   onTouchStart={(e) => (touch.current = { x: e.touches[0].clientX, y: e.touches[0].clientY })}
                   onTouchEnd={(e) => {
                     const st = touch.current;
                     touch.current = null;
                     if (!st) return;
                     const dx = e.changedTouches[0].clientX - st.x, dy = e.changedTouches[0].clientY - st.y;
                     if (Math.abs(dx) > 50 && Math.abs(dx) > 2 * Math.abs(dy)) go(page + (dx < 0 ? 1 : -1));
                   }}>
                {PAGES[page].charts.map(draw)}
              </div>
            )}
            {!empty && !phone && <>
              {has("balance") && balanceChart()}
              {has("flows") && flowsChart()}
              {(has("income") || has("spending")) && (
                <div className="fin-charts-pair">
                  {has("income") && sunburst("income", flows.earnedBy)}
                  {has("spending") && sunburst("spending", flows.spentBy)}
                </div>
              )}
              {(has("trendIn") || has("trend")) && (
                <div className="fin-charts-pair">
                  {has("trendIn") && trendChart("trendIn", flows.earnedByRoot)}
                  {has("trend") && trendChart("trend", flows.spentByRoot)}
                </div>
              )}
              {has("sankey") && sankeyChart()}
            </>}
          </div>
        </div>
      </div>
    </div>
  );
}
