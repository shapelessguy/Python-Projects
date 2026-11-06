import { CSSProperties, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";
import { api, Portfolio, PortfolioTotals, Stock, StockBars, StockResample, StocksList, StockTicks, Transaction, useVersionPoll } from "../api";
import { useT } from "../i18n";
import { useBackToClose } from "../backClose";
import { ConfirmDialog } from "../ConfirmDialog";
import { Icon } from "./icons";
import { ChartPager } from "./ChartPager";
import { usePhone } from "../narrow";

const Plot = createPlotlyComponent(Plotly);

// 1D is every trade of today; the rest are daily (or weekly) bars ending
// today, today's bar being the current price.
const TODAY = "1D";
const PRESETS: Record<string, number | null> = {
  "1W": 7,
  "1M": 30,
  "3M": 91,
  "1Y": 365,
  "5Y": 1826,
  MAX: null,
};
const WEEKENDS = { bounds: ["sat", "mon"] as [string, string] };
const UP = "#4caf50";
const DOWN = "#e05555";

const PRESET_KEY = "environment.stocks.preset";
const RESAMPLE_KEY = "environment.stocks.resample";
const HIDDEN_KEY = "environment.stocks.hidden";

function load(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function save(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode: just not remembered */
  }
}

function shiftDays(iso: string, days: number): string {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** "2025-11-03" -> "03/11/25", in the UI's language. */
function shortDate(iso: string, lang: string): string {
  if (!iso) return "";
  return new Date(iso + "T00:00:00").toLocaleDateString(lang, { day: "2-digit", month: "2-digit", year: "2-digit" });
}

/** The Monday of an ISO date's week. */
function monday(iso: string): string {
  const day = new Date(iso + "T00:00:00Z").getUTCDay();
  return shiftDays(iso, -((day + 6) % 7));
}

// ── what the client holds ─────────────────────────────────────────────────
// Kept for the life of the page, not the tab, and only ever extended: a
// request asks for just what is missing from it -- the days before what is
// held when the range grows, today's bar or the trades after the last one
// held when the stock trades. Weeks are summed from the daily bars here.

interface HeldBars extends StockBars {
  lo: string;          // the days asked for, inclusive (a day without trades has no bar)
  hi: string;
  rev: number;         // the stock's rev when today's bar was last fetched
  partial: boolean;    // fetched while its history was still downloading
}

interface HeldTicks extends StockTicks {
  rev: number;
}

const heldBars: Record<string, HeldBars> = {};
const heldTicks: Record<string, HeldTicks> = {};
const pending = new Set<string>();   // ISINs with a request out

/** The day ranges a stock's chart lacks for [a, b], and whether what is
 *  held should be dropped (none yet, too far from the range to join it,
 *  or fetched before its history arrived). */
function barsNeeded(s: Stock, a: string, b: string, today: string): { ranges: [string, string][]; fresh: boolean } {
  const h = heldBars[s.isin];
  if (!h || (h.partial && !s.loading) || b < shiftDays(h.lo, -1) || a > shiftDays(h.hi, 1)) {
    return { ranges: [[a, b]], fresh: true };
  }
  const ranges: [string, string][] = [];
  if (a < h.lo) ranges.push([a, shiftDays(h.lo, -1)]);
  if (b > h.hi) ranges.push([shiftDays(h.hi, 1), b]);
  else if (b >= today && h.rev !== s.rev) ranges.push([today, today]);   // today's price moved
  return { ranges, fresh: false };
}

function putBars(isin: string, a: string, b: string, got: StockBars, rev: number, fresh: boolean, partial: boolean) {
  const h = heldBars[isin];
  if (fresh || !h) {
    heldBars[isin] = { ...got, lo: a, hi: b, rev, partial };
    return;
  }
  const rows: [string, number | null, number | null][] = [];
  h.index.forEach((d, k) => { if (d < a || d > b) rows.push([d, h.close[k], h.volume[k]]); });
  got.index.forEach((d, k) => rows.push([d, got.close[k], got.volume[k]]));
  rows.sort((x, y) => (x[0] < y[0] ? -1 : x[0] > y[0] ? 1 : 0));
  heldBars[isin] = {
    index: rows.map((r) => r[0]),
    close: rows.map((r) => r[1]),
    volume: rows.map((r) => r[2]),
    lo: a < h.lo ? a : h.lo,
    hi: b > h.hi ? b : h.hi,
    rev,
    partial: h.partial || partial,
  };
}

function putTicks(isin: string, got: StockTicks, rev: number) {
  const h = heldTicks[isin];
  heldTicks[isin] = h && h.day === got.day
    ? { ...got, time: [...h.time, ...got.time], close: [...h.close, ...got.close],
        volume: [...h.volume, ...got.volume], rev }
    : { ...got, rev };
}

/** What a chart draws: the held bars of [a, b], summed into weeks if asked. */
function barsOf(isin: string, a: string, b: string, weekly: boolean): StockBars | null {
  const h = heldBars[isin];
  if (!h) return null;
  const k0 = h.index.findIndex((d) => d >= a);
  const lo = k0 < 0 ? h.index.length : k0;
  let hi = h.index.length;
  while (hi > lo && h.index[hi - 1] > b) hi--;
  const out: StockBars = { index: h.index.slice(lo, hi), close: h.close.slice(lo, hi), volume: h.volume.slice(lo, hi) };
  if (!weekly) return out;
  const w: StockBars = { index: [], close: [], volume: [] };
  let week = "";
  out.index.forEach((d, k) => {
    const m = monday(d);
    if (m !== week) {
      week = m;
      w.index.push(d);
      w.close.push(out.close[k]);
      w.volume.push(out.volume[k] ?? 0);
    } else {
      const n = w.index.length - 1;
      w.index[n] = d;   // a week is dated by its last trading day
      w.close[n] = out.close[k];
      w.volume[n] = (w.volume[n] ?? 0) + (out.volume[k] ?? 0);
    }
  });
  return w;
}

function ticksOf(isin: string, today: string): StockBars | null {
  const h = heldTicks[isin];
  if (!h || h.day !== today) return null;
  return { index: h.time.map((x) => `${h.day} ${x}`), close: h.close, volume: h.volume };
}

function price(v: number, lang: string): string {
  return v.toLocaleString(lang, { minimumFractionDigits: 2, maximumFractionDigits: v < 1 ? 4 : 2 });
}

/** Euros with a sign: "+1.234,50 €", "−987,00 €" (whole euros if `round`). */
function signed(v: number, lang: string, round = false): string {
  const digits = round ? 0 : 2;
  const abs = Math.abs(v).toLocaleString(lang, { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return `${v < 0 ? "−" : "+"}${abs} €`;
}

function shares(v: number, lang: string): string {
  return v.toLocaleString(lang, { maximumFractionDigits: 4 });
}

const PF_REFRESH_MS = 60_000;
const MARK = "#4dd0e1";   // the transactions' markers: the cyan of the title's price
const ms = (day: string) => Date.parse(day.slice(0, 10));

/** The overview's cards. With `fit` (a phone's page) they fill its height:
 *  one column while every card gets at least OV_ROOMY px, else two columns,
 *  their cards squeezed down to OV_TIGHT px, and only below that a scroll.
 *  Never taller than OV_MAX. Elsewhere, as many columns as fit the width. */
const OV_ROOMY = 60, OV_TIGHT = 48, OV_MAX = 110, OV_GAP = 4;   // OV_TIGHT: a name and a price line
function OverviewCards({ n, fit, children }: { n: number; fit: boolean; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [h, setH] = useState(0);
  useEffect(() => {
    if (!fit || !ref.current) return;
    const ro = new ResizeObserver(([e]) => setH(e.contentRect.height));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, [fit]);
  let style: CSSProperties | undefined;
  if (fit && h > 0) {
    const each = (rows: number) => (h - (rows - 1) * OV_GAP) / rows;
    const one = each(n) >= OV_ROOMY;
    const rows = one ? n : Math.ceil(n / 2);
    style = {
      gridTemplateColumns: one ? "1fr" : "1fr 1fr",
      gridAutoRows: `${Math.min(OV_MAX, Math.max(OV_TIGHT, each(rows)))}px`,
      gap: OV_GAP,
    };
  }
  return <div ref={ref} className={"stk-ov-cards" + (fit ? " stk-ov-cards--fit" : "")} style={style}>{children}</div>;
}

/** The portfolio's buys and sells on a chart. Transactions closer together
 *  than a tenth of the chart's width are one marker -- a group starts at its
 *  first transaction and takes every one within that tenth after it:
 *    * at the group's mean date (on the bar it falls on: a weekend's on the
 *      Friday before; in weekly bars, its week's),
 *    * at its average price, shares-weighted (all € / all shares), so a buy
 *      and a sale of as many shares sit halfway between their prices,
 *    * ▲ if it bought more shares than it sold, ▼ if fewer, ◆ (grey) if
 *      they cancel out; labelled with the net cash (and ×n if merged),
 *      every transaction listed in its tooltip.
 *  `span` is the width shown, in ms: the whole range, or what the chart is
 *  zoomed to -- zooming in splits the groups. Cyan, not green and red: those
 *  are the price line's own colours. */
function markers(txs: Transaction[], d: StockBars, weekly: boolean, span: number, lang: string,
                 t: ReturnType<typeof useT>["t"]) {
  const at = (day: string) => {
    if (weekly) return d.index.find((x) => x >= day && monday(x) === monday(day)) ?? day;
    let x = day;
    for (const i of d.index) { if (i > day) break; x = i; }
    return x;
  };
  const sorted = txs.filter((tx) => tx.price != null && tx.amount != null)
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  const groups: Transaction[][] = [];
  for (const tx of sorted) {
    const g = groups[groups.length - 1];
    if (g && ms(tx.date) - ms(g[0].date) <= span / 10) g.push(tx);
    else groups.push([tx]);
  }

  const kinds = { buy: [] as Transaction[][], sell: [] as Transaction[][], flat: [] as Transaction[][] };
  for (const g of groups) {
    const net = g.reduce((n, tx) => n + tx.shares, 0);
    kinds[Math.abs(net) < 1e-9 ? "flat" : net > 0 ? "buy" : "sell"].push(g);
  }
  const FLAT = "#999";
  const look = {
    buy: { color: MARK, symbol: "triangle-up", pos: "top center" },
    sell: { color: MARK, symbol: "triangle-down", pos: "bottom center" },
    flat: { color: FLAT, symbol: "diamond", pos: "top center" },
  } as const;
  const line = (tx: Transaction) => `${shortDate(tx.date, lang)} · ${t(tx.shares > 0 ? "pf_bought" : "pf_sold",
    { n: shares(Math.abs(tx.shares), lang), p: price(tx.price!, lang) })} = ${price(tx.amount!, lang)} €`;
  const MAX_LINES = 12;
  return (["buy", "sell", "flat"] as const).filter((k) => kinds[k].length).map((k) => {
    const these = kinds[k];
    return {
      x: these.map((g) => at(new Date(g.reduce((m, tx) => m + ms(tx.date), 0) / g.length).toISOString().slice(0, 10))),
      y: these.map((g) => g.reduce((m, tx) => m + tx.amount!, 0) / g.reduce((n, tx) => n + Math.abs(tx.shares), 0)),
      // Bought shows what went in (+), sold what came out (-), as before.
      text: these.map((g) => signed(g.reduce((m, tx) => m + (tx.shares > 0 ? tx.amount! : -tx.amount!), 0), lang, true)
        + (g.length > 1 ? ` ×${g.length}` : "")),
      customdata: these.map((g) => (g.length > MAX_LINES
        ? [...g.slice(0, MAX_LINES).map(line), `… +${g.length - MAX_LINES}`]
        : g.map(line)).join("<br>")),
      type: "scatter" as const,
      mode: "text+markers" as const,
      textposition: look[k].pos as "top center" | "bottom center",
      // Bold, with a dark halo so it reads over the line and the grid.
      textfont: { size: 11, color: look[k].color, weight: 700,
                  shadow: "0 0 2px #111, 0 0 3px #111, 0 0 4px #111" } as { size: number; color: string },
      marker: { symbol: look[k].symbol as "triangle-up" | "triangle-down" | "diamond", size: 10, color: look[k].color,
                line: { width: 1, color: "#111" } },
      cliponaxis: false,
      hovertemplate: "%{customdata}<extra></extra>",
    };
  });
}

/** The Stocks tab: the user's Tradegate watchlist, one chart per stock --
 *  every trade of today (1D), or daily/weekly bars from the store with
 *  today's last tick as the latest close. The picker of shown stocks is
 *  drawn into `pickerSlot`, the tab row's spot where the city picker sits on
 *  the weather tabs. */
export function StocksView({ pickerSlot }: { pickerSlot: HTMLElement | null }) {
  const { t, lang } = useT();
  const { stocks: version } = useVersionPoll();
  const narrow = usePhone();
  const [list, setList] = useState<StocksList | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(load(HIDDEN_KEY) ?? "[]") as string[]);
    } catch {
      return new Set();
    }
  });
  const [preset, setPreset] = useState<string>(() => {
    const p = load(PRESET_KEY);
    return p === TODAY || (p && p in PRESETS) ? p : "1M";
  });
  const [resample, setResample] = useState<StockResample>(() =>
    load(RESAMPLE_KEY) === "weekly" ? "weekly" : "daily");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  // Bumped when a reply lands in the held data (module level), to redraw.
  const [tick, setTick] = useState(0);
  const [isin, setIsin] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState("");
  const [removing, setRemoving] = useState<Stock | null>(null);
  const [controlsOpen, setControlsOpen] = useState(false);
  useBackToClose(() => setControlsOpen(false), controlsOpen);
  // The portfolio is private: hidden on every load (the eye shows its
  // summary and markers), and not even asked for until it is shown or its
  // panel opened. Neither any more drops what was fetched.
  const [showPf, setShowPf] = useState(false);
  const [pf, setPf] = useState<Portfolio | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [txOpen, setTxOpen] = useState(false);
  const [closedOpen, setClosedOpen] = useState(false);
  const [pfMetric, setPfMetric] = useState<Metric>("profit");
  const [pfYear, setPfYear] = useState("");   // "": all years
  const needPf = showPf || panelOpen;

  useEffect(() => {
    api.stocks().then(setList).catch(() => {});
  }, [version]);

  const needPfRef = useRef(false);
  needPfRef.current = needPf;
  // A reply landing after the portfolio was put away again is dropped.
  const pfAt = useRef(0);
  const reloadPf = () => {
    pfAt.current = Date.now();
    return api.portfolio().then((p) => { if (needPfRef.current) setPf(p); });
  };
  useEffect(() => {
    if (!needPf) {
      setPf(null);
      pfAt.current = 0;
      return;
    }
    // `version` moves with every trade of any followed stock -- every few
    // seconds while the market is open. The portfolio (a few hundred KB and
    // every chart redrawn) follows those at most once a minute; the user's
    // own changes reload it at once (reloadPf).
    const wait = pfAt.current + PF_REFRESH_MS - Date.now();
    if (wait <= 0) {
      reloadPf().catch(() => {});
      return;
    }
    const id = window.setTimeout(() => reloadPf().catch(() => {}), wait);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needPf, version]);
  const shownPf = showPf ? pf : null;
  // Each chart's transactions, grouped once rather than filtered per chart.
  const txsBy = useMemo(() => {
    const by = new Map<string, Transaction[]>();
    for (const tx of shownPf?.transactions ?? []) {
      const l = by.get(tx.isin);
      if (l) l.push(tx); else by.set(tx.isin, [tx]);
    }
    return by;
  }, [shownPf]);

  const today = list?.today ?? "";
  const minDate = useMemo(() => {
    const dates = (list?.stocks ?? []).map((s) => s.min_date).filter((d): d is string => !!d);
    return dates.length ? dates.reduce((a, b) => (a < b ? a : b)) : today;
  }, [list, today]);

  // The range the preset stands for, or the dates typed in.
  // Nothing until the list has come with the server's today.
  let from = start;
  let to = end;
  if (!today) {
    from = to = "";
  } else if (preset === TODAY) {
    from = to = today;
  } else if (preset in PRESETS) {
    const days = PRESETS[preset];
    from = days === null ? minDate : shiftDays(today, -days);
    to = today;
  }
  const mode: StockResample = preset === TODAY ? "ticks" : resample;
  const shown = (list?.stocks ?? []).filter((s) => !hidden.has(s.isin));
  const rangeKey = `${from}|${to}|${mode}`;
  // What each chart is zoomed to (desktop: the phone's charts don't zoom),
  // from Plotly's relayout; forgotten with the range.
  const [zoom, setZoom] = useState<Record<string, [string, string]>>({});
  useEffect(() => setZoom({}), [rangeKey]);
  const onRelayout = (isin: string) => (e: Record<string, unknown>) => {
    const r = (e["xaxis.range"] as [string, string] | undefined)
      ?? (e["xaxis.range[0]"] != null ? [String(e["xaxis.range[0]"]), String(e["xaxis.range[1]"])] as [string, string] : undefined);
    if (r) setZoom((z) => ({ ...z, [isin]: [String(r[0]), String(r[1])] }));
    else if (e["xaxis.autorange"]) setZoom((z) => { const { [isin]: _, ...rest } = z; return rest; });
  };
  // A stock's rev moves only with its own new ticks or history.
  const revKey = shown.map((s) => `${s.isin}@${s.rev}${s.loading ? "L" : ""}`).join(",");

  // Ask for what the shown charts lack, and nothing else: stocks needing
  // the same days share one request.
  useEffect(() => {
    if (!today || !from || !to || from > to) return;
    // A reply redraws, and looks again for anything still missing; a failure
    // waits for the next change rather than asking again at once.
    const send = (isins: string[], req: () => Promise<void>) => {
      const free = () => isins.forEach((i) => pending.delete(i));
      isins.forEach((i) => pending.add(i));
      req().then(() => { free(); setTick((n) => n + 1); }, free);
    };
    const idle = shown.filter((s) => !pending.has(s.isin));
    if (mode === "ticks") {
      const stale = idle.filter((s) => {
        const h = heldTicks[s.isin];
        return !h || h.day !== today || h.rev !== s.rev;
      });
      if (!stale.length) return;
      const revs = Object.fromEntries(stale.map((s) => [s.isin, s.rev]));
      const since = stale.map((s) => {
        const h = heldTicks[s.isin];
        return `${s.isin}:${h && h.day === today ? h.last_id : 0}`;
      }).join(",");
      const isins = stale.map((s) => s.isin);
      send(isins, () => api.stockTicks({ isins: isins.join(","), since })
        .then((r) => Object.entries(r.series).forEach(([i, got]) => putTicks(i, got, revs[i]))));
      return;
    }
    // One range per stock per round; a second one (older days and today's
    // price both) goes out when the first is back.
    const groups = new Map<string, { a: string; b: string; fresh: boolean; stocks: Stock[] }>();
    for (const s of idle) {
      const need = barsNeeded(s, from, to, today);
      if (!need.ranges.length) continue;
      const [a, b] = need.ranges[0];
      const key = `${a}|${b}|${need.fresh}`;
      if (!groups.has(key)) groups.set(key, { a, b, fresh: need.fresh, stocks: [] });
      groups.get(key)!.stocks.push(s);
    }
    for (const g of groups.values()) {
      const isins = g.stocks.map((s) => s.isin);
      const meta = Object.fromEntries(g.stocks.map((s) => [s.isin, { rev: s.rev, partial: s.loading }]));
      send(isins, () => api.stockBars({ isins: isins.join(","), start: g.a, end: g.b })
        .then((r) => Object.entries(r.series).forEach(([i, got]) =>
          putBars(i, g.a, g.b, got, meta[i].rev, g.fresh, meta[i].partial))));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [today, rangeKey, revKey, tick]);

  const choosePreset = (p: string) => {
    setPreset(p);
    save(PRESET_KEY, p);
  };
  const typeDates = (s: string, e: string) => {
    setPreset("");
    setStart(s);
    setEnd(e);
  };
  const chooseResample = (r: StockResample) => {
    setResample(r);
    save(RESAMPLE_KEY, r);
  };
  const toggle = (key: string, on: boolean) =>
    setHidden((prev) => {
      const next = new Set(prev);
      on ? next.delete(key) : next.add(key);
      save(HIDDEN_KEY, JSON.stringify([...next]));
      return next;
    });

  const add = () => {
    const value = isin.trim();
    if (!value || adding) return;
    setAdding(true);
    setAddError("");
    api
      .addStock(value)
      .then(() => {
        setIsin("");
        return api.stocks().then(setList);
      })
      .catch((e: Error) => setAddError(e.message))
      .finally(() => setAdding(false));
  };
  // Shown in the new order at once; the server's list follows.
  const reorder = (isins: string[]) => {
    const by = new Map(list!.stocks.map((s) => [s.isin, s]));
    setList({ ...list!, stocks: isins.map((i) => by.get(i)!) });
    api.reorderStocks(isins).then(() => api.stocks().then(setList)).catch(() => api.stocks().then(setList));
  };
  const remove = (s: Stock) => {
    setRemoving(null);
    api.removeStock(s.isin).then(() => api.stocks().then(setList)).catch(() => {});
  };

  if (!list) return <p className="muted">{t("loading")}</p>;

  const ticks = mode === "ticks";
  const chart = (s: Stock) => {
    const d = ticks ? ticksOf(s.isin, today) : barsOf(s.isin, from, to, mode === "weekly");
    if (!d || !d.index.length) return null;
    const txs = !ticks ? (txsBy.get(s.isin) ?? []).filter((tx) => tx.date >= from && tx.date <= to) : [];
    const closes = d.close.filter((v): v is number => v != null);
    const color = closes.length && closes[closes.length - 1] < closes[0] ? DOWN : UP;
    return {
      data: [
        {
          x: d.index,
          y: d.close,
          type: "scatter" as const,
          mode: "lines" as const,
          name: t("stk_price"),
          line: { width: 1.5, color },
          hovertemplate: "%{x}<br>%{y:.2f} €<extra></extra>",
        },
        {
          x: d.index,
          y: d.volume,
          type: "bar" as const,
          name: t("stk_volume"),
          yaxis: "y2",
          marker: { color: "#888" },
          opacity: 0.5,
          hovertemplate: "%{y:,}<extra></extra>",
        },
        ...(txs.length ? markers(txs, d, mode === "weekly",
          zoom[s.isin] ? ms(zoom[s.isin][1]) - ms(zoom[s.isin][0]) : ms(d.index[d.index.length - 1]) - ms(d.index[0]),
          lang, t) : []),
      ],
      layout: {
        height: 240,
        margin: { l: 48, r: 12, t: 8, b: 40 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: "#bbb" },
        showlegend: false,
        bargap: 0,
        // Weekends have no bars: leave them out rather than drawing a
        // straight line across them. The dates sit under the volume bars,
        // where Plotly's second line (the year) has room, not between the panes.
        xaxis: {
          anchor: "y2" as const,
          gridcolor: "#333",
          rangebreaks: ticks ? [] : [WEEKENDS],
          // Redrawn with every tick: keep the zoom.
          ...(zoom[s.isin] ? { range: zoom[s.isin], autorange: false } : {}),
        },
        yaxis: { gridcolor: "#333", domain: [0.27, 1] as [number, number] },
        yaxis2: { gridcolor: "#333", domain: [0, 0.22] as [number, number], showticklabels: false, fixedrange: true },
      },
    };
  };
  // Every chart's title ends with the range it shows: the preset, or the
  // dates typed in.
  const rangeTag = preset === TODAY ? "1D" : preset in PRESETS ? preset
    : `${shortDate(from, lang)} – ${shortDate(to, lang)}`;
  // The price on the left, the name and range in the middle (the name cut
  // when too long), the day's change on the right, bold in its colour.
  // The day's change, bold in its colour.
  const change = (s: Stock) => {
    const pct = s.last != null && s.prev_close ? ((s.last - s.prev_close) / s.prev_close) * 100 : null;
    return (
      <b className={pct == null ? "" : pct < 0 ? "pf-down" : "pf-up"}>
        {pct == null ? "" : `${pct < 0 ? "−" : "+"}${Math.abs(pct).toLocaleString(lang, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`}
      </b>
    );
  };
  const title = (s: Stock) => (
    <span className="stk-title" title={s.isin}>
      <span className="stk-title-price">{s.last != null ? `${price(s.last, lang)} €` : ""}</span>
      <span className="stk-title-name"><span>{s.name}</span> ({rangeTag})</span>
      {change(s)}
    </span>
  );
  const note = (s: Stock) =>
    t(s.loading ? "stk_loading_history"
      : (ticks ? heldTicks[s.isin]?.day === today : !!heldBars[s.isin]) ? "stk_no_data" : "loading");
  const summary = (fill: boolean) => shownPf && shownPf.transactions.length > 0
    ? <PortfolioSummary pf={shownPf} metric={pfMetric} onMetric={setPfMetric} year={pfYear} onYear={setPfYear}
                        fill={fill} />
    : null;
  // With the portfolio hidden (or empty), its place shows every stock on
  // the list at a glance: price and the day's change.
  const overview = (fill: boolean) => list.stocks.length > 0 && (
    <div className={(fill ? "cp-chart" : "chart-block") + " stk-overview"}>
      <div className="chart-title">{t("stk_overview")}</div>
      <OverviewCards n={list.stocks.length} fit={fill}>
        {list.stocks.map((s) => (
          <div key={s.isin} className="stk-ov-card" title={s.isin}>
            <span className="stk-ov-name">{s.name}</span>
            <span className="stk-ov-row">
              <span className="stk-title-price">{s.last != null ? `${price(s.last, lang)} €` : "—"}</span>
              {change(s)}
            </span>
          </div>
        ))}
      </OverviewCards>
    </div>
  );
  const lead = (fill: boolean) => summary(fill) ?? (overview(fill) || null);
  const resampleKey = ticks ? "stk_ticks" : mode === "weekly" ? "stk_weekly" : "stk_daily";

  return (
    <>
      {pickerSlot && createPortal(
        <>
          <button className="pf-btn pf-eye" onClick={() => setShowPf(!showPf)}
                  title={t(showPf ? "pf_hide" : "pf_show")} aria-label={t(showPf ? "pf_hide" : "pf_show")}>
            <Icon name={showPf ? "eye" : "eyeOff"} size={18} className="" />
          </button>
          <button className="pf-btn" onClick={() => setPanelOpen(true)} title={t("pf_title")} aria-label={t("pf_title")}>
            <Icon name="pie" size={18} className="" />
          </button>
          {list.stocks.length > 0 && <StockPicker stocks={list.stocks} hidden={hidden} onToggle={toggle} />}
          <button className="env-controls-btn" onClick={() => setControlsOpen(true)}
                  title={t("settings")} aria-label={t("settings")}>
            <Icon name="settings" size={20} className="" />
          </button>
        </>, pickerSlot)}
      {panelOpen && (
        <PortfolioPanel pf={pf} onClose={() => setPanelOpen(false)} reload={reloadPf}
                        onTransactions={() => setTxOpen(true)} onClosed={() => setClosedOpen(true)} />
      )}
      {panelOpen && closedOpen && pf && <ClosedPositions pf={pf} onClose={() => setClosedOpen(false)} />}
      {panelOpen && txOpen && pf && (
        <PortfolioTransactions pf={pf} stocks={list.stocks} today={today} reload={reloadPf}
                               onClose={() => setTxOpen(false)} />
      )}

      <aside className={"env-controls stk-controls" + (controlsOpen ? " env-controls--open" : "")}>
        <div className="env-controls-head">
          <span>{t("settings")}</span>
          <button className="env-controls-close" onClick={() => setControlsOpen(false)}
                  title={t("close")} aria-label={t("close")}>
            <Icon name="close" size={18} className="" />
          </button>
        </div>
        <section>
          <h3>{t("env_date_range")}</h3>
          <div className="presets">
            <button className={preset === TODAY ? "active" : ""} onClick={() => choosePreset(TODAY)}>
              {t("env_today")}
            </button>
            {Object.keys(PRESETS).map((label) => (
              <button key={label} className={preset === label ? "active" : ""} onClick={() => choosePreset(label)}>
                {label}
              </button>
            ))}
          </div>
          <div className="dates">
            <input type="date" value={from} min={minDate} max={today}
                   onChange={(e) => typeDates(e.target.value, to)} />
            <input type="date" value={to} min={minDate} max={today}
                   onChange={(e) => typeDates(from, e.target.value)} />
          </div>
        </section>

        <section>
          <h3>{t("env_resample")}</h3>
          <select value={mode} disabled={preset === TODAY}
                  onChange={(e) => chooseResample(e.target.value as StockResample)}>
            {preset === TODAY && <option value="ticks">{t("stk_ticks")}</option>}
            <option value="daily">{t("stk_daily")}</option>
            <option value="weekly">{t("stk_weekly")}</option>
          </select>
        </section>

        <section className="stk-list">
          <h3>{t("stk_list")}</h3>
          <StockCards stocks={list.stocks} onRemove={setRemoving} onReorder={reorder} />
          <form className="stk-add" onSubmit={(e) => { e.preventDefault(); add(); }}>
            <input value={isin} placeholder="ISIN" maxLength={12} spellCheck={false}
                   onChange={(e) => setIsin(e.target.value.toUpperCase())} />
            <button type="submit" disabled={adding || !isin.trim()}>
              {adding ? "…" : t("stk_add")}
            </button>
          </form>
          {addError && <p className="error small">{addError}</p>}
        </section>
      </aside>

      <div className="env-charts">
        <div className="env-title">
          <h1>
            {preset === TODAY
              ? t("stk_ticks_of", { date: shortDate(from, lang) })
              : `${t("env_stocks")} ${shortDate(from, lang)} – ${shortDate(to, lang)}`}
          </h1>
        </div>
        <p className="muted env-range">{t(resampleKey)}</p>

        {list.stocks.length === 0 && <p className="muted">{t("stk_none")}</p>}
        {list.stocks.length > 0 && shown.length === 0 && <p className="muted">{t("stk_pick")}</p>}
        {narrow && (shown.length > 0 || lead(true)) && (
          <ChartPager
            lead={lead(true)}
            charts={shown.flatMap((s) => {
              const c = chart(s);
              return c ? [{ key: s.isin, title: title(s), ...c }] : [];
            })}
          />
        )}
        {!narrow && (
          <div className="stk-grid">
          {lead(false)}
          {shown.map((s) => {
            const c = chart(s);
            return (
              <div key={s.isin} className="chart-block">
                <div className="chart-title">{title(s)}</div>
                {c ? (
                  <Plot data={c.data} layout={c.layout} config={{ displayModeBar: false }}
                        style={{ width: "100%" }} useResizeHandler
                        onRelayout={onRelayout(s.isin) as never} />
                ) : (
                  <p className="muted stk-note">{note(s)}</p>
                )}
              </div>
            );
          })}
          </div>
        )}
      </div>

      {removing && (
        <ConfirmDialog message={t("stk_remove_confirm", { name: removing.name })} yesLabel={t("stk_remove")} danger
                       onYes={() => remove(removing)} onNo={() => setRemoving(null)} />
      )}
    </>
  );
}

/** The stocks as cards, in the user's order: drag one by its grip (mouse or
 *  finger) to move it; the others make room as it passes. */
function StockCards({ stocks, onRemove, onReorder }: {
  stocks: Stock[]; onRemove: (s: Stock) => void; onReorder: (isins: string[]) => void;
}) {
  const { t } = useT();
  // The card being dragged: where it was, where the pointer started, how far
  // it has gone, and one card's height plus the gap (the step between slots).
  const [drag, setDrag] = useState<{ from: number; y0: number; dy: number; step: number } | null>(null);
  const to = drag ? Math.max(0, Math.min(stocks.length - 1, drag.from + Math.round(drag.dy / drag.step))) : -1;

  const start = (e: React.PointerEvent, i: number) => {
    const card = (e.currentTarget as HTMLElement).closest(".stk-card") as HTMLElement;
    const gap = parseFloat(getComputedStyle(card.parentElement!).rowGap) || 0;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    setDrag({ from: i, y0: e.clientY, dy: 0, step: card.offsetHeight + gap });
  };
  const move = (e: React.PointerEvent) => drag && setDrag({ ...drag, dy: e.clientY - drag.y0 });
  const end = () => {
    if (drag && to !== drag.from) {
      const isins = stocks.map((s) => s.isin);
      const [moved] = isins.splice(drag.from, 1);
      isins.splice(to, 0, moved);
      onReorder(isins);
    }
    setDrag(null);
  };
  // Where each card is drawn while one is dragged: the dragged one under the
  // pointer, the ones it has passed one slot towards where it came from.
  const shift = (i: number) => {
    if (!drag) return 0;
    if (i === drag.from) return drag.dy;
    if (drag.from < i && i <= to) return -drag.step;
    if (to <= i && i < drag.from) return drag.step;
    return 0;
  };

  return (
    <div className="stk-cards">
      {stocks.map((s, i) => (
        <div key={s.isin} className={"stk-card" + (drag?.from === i ? " stk-card--drag" : "")}
             style={drag ? { transform: `translateY(${shift(i)}px)` } : undefined}>
          <span className="stk-grip" onPointerDown={(e) => start(e, i)} onPointerMove={move}
                onPointerUp={end} onPointerCancel={() => setDrag(null)}
                title={t("stk_drag")} aria-label={t("stk_drag")}>⠿</span>
          <span className="stk-card-text" title={s.isin}>
            <span className="stk-name">{s.name}</span>
            <span className="unit">{s.isin}</span>
          </span>
          <button className="ghost stk-remove" onClick={() => onRemove(s)}
                  title={t("stk_remove")} aria-label={t("stk_remove")}>
            <Icon name="close" size={14} className="" />
          </button>
        </div>
      ))}
    </div>
  );
}

/** Which of the stocks are drawn: like the weather tabs' city picker. */
function StockPicker({ stocks, hidden, onToggle }: {
  stocks: Stock[]; hidden: Set<string>; onToggle: (isin: string, on: boolean) => void;
}) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useBackToClose(() => setOpen(false), open);
  useEffect(() => {
    if (!open) return;
    const down = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", down);
    return () => document.removeEventListener("pointerdown", down);
  }, [open]);
  const count = stocks.filter((s) => !hidden.has(s.isin)).length;
  return (
    <div className="env-citypick" ref={box}>
      <button className={open ? "active" : ""} onClick={() => setOpen(!open)}
              title={t("env_stocks")} aria-label={t("env_stocks")}>
        📊 {count}/{stocks.length} ▾
      </button>
      {open && (
        <div className="env-citypop">
          {stocks.map((s) => (
            <label key={s.isin} className="check">
              <input type="checkbox" checked={!hidden.has(s.isin)}
                     onChange={(e) => onToggle(s.isin, e.target.checked)} />
              <span>{s.name}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

type Metric = keyof PortfolioTotals;
const METRICS: { key: Metric; label: string; big?: boolean; money?: boolean }[] = [
  { key: "value", label: "pf_value", big: true, money: true },
  { key: "net", label: "pf_net", big: true },
  { key: "invested", label: "pf_invested", money: true },
  { key: "profit", label: "pf_profit" },
  { key: "realised", label: "pf_realised" },
  { key: "unrealised", label: "pf_unrealised" },
];
const VALUE_LINE = "#5aa9e6";

/** The portfolio's summary, in the first two chart slots (a phone's first
 *  page): the totals as buttons, and the chart of the one picked -- day by
 *  day over the tab's range (all of it on the 1D tab). The tax rides in the
 *  net's button. Value also draws what was invested, dashed, and net the
 *  tax. `fill`: in the phone's pager. */
/** One year of the portfolio out of its daily history: where it stood at
 *  the year's end (value, invested) and what the year itself made (realised,
 *  unrealised and profit since the end of the year before). Its tax is on
 *  what it realised only -- a year is taxed on its sales, not on what is
 *  still held -- and net is its profit less that. The current year ends with
 *  the live totals. */
function yearOf(pf: Portfolio, year: string): { totals: PortfolioTotals; history: Portfolio["history"] } {
  const h = pf.history;
  const lo = h.index.findIndex((d) => d >= `${year}-01-01`);
  let hi = h.index.length;
  while (hi > 0 && h.index[hi - 1] > `${year}-12-31`) hi--;
  const from = lo < 0 ? hi : lo;
  const base = (m: Metric) => (from > 0 ? h[m][from - 1] : 0);
  const rate = pf.tax_rate / 100;
  const keys: Metric[] = ["value", "invested", "realised", "unrealised", "profit"];
  const history = { index: h.index.slice(from, hi) } as Portfolio["history"];
  for (const m of keys) {
    const b = m === "value" || m === "invested" ? 0 : base(m);
    history[m] = h[m].slice(from, hi).map((v) => v - b);
  }
  history.tax = history.realised.map((v) => Math.max(v, 0) * rate);
  history.net = history.profit.map((v, i) => v - history.tax[i]);
  const live = hi === h.index.length;
  const end = (m: Metric) => (live ? pf.totals[m] - (m === "value" || m === "invested" ? 0 : base(m))
    : history[m][history[m].length - 1] ?? 0);
  const totals = Object.fromEntries(keys.map((m) => [m, end(m)])) as unknown as PortfolioTotals;
  totals.tax = Math.max(totals.realised, 0) * rate;
  totals.net = totals.profit - totals.tax;
  return { totals, history };
}

function PortfolioSummary({ pf, metric, onMetric, year, onYear, fill }: {
  pf: Portfolio; metric: Metric; onMetric: (m: Metric) => void;
  year: string; onYear: (y: string) => void; fill: boolean;
}) {
  const { t, lang } = useT();
  // From the first transaction's year to today's, newest first.
  const years: string[] = [];
  if (pf.history.index.length) {
    for (let y = +pf.history.index[pf.history.index.length - 1].slice(0, 4); y >= +pf.history.index[0].slice(0, 4); y--)
      years.push(String(y));
  }
  const yr = years.includes(year) ? year : "";
  const { totals, history: h } = yr ? yearOf(pf, yr) : { totals: pf.totals, history: pf.history };
  const x = h.index;
  const y = (m: Metric) => h[m];
  const last = y(metric)[x.length - 1] ?? 0;
  const color = metric === "value" ? VALUE_LINE : last < 0 ? DOWN : UP;
  const label = (m: (typeof METRICS)[number]) => t(m.label as "pf_value");
  const taxLabel = `${t("pf_tax_due")} ${pf.tax_rate.toLocaleString(lang)}%`;

  const data = [
    ...(metric === "value" ? [{
      x, y: y("invested"), type: "scatter" as const, mode: "lines" as const, name: t("pf_invested"),
      line: { width: 1, color: "#999", dash: "dash" as const, shape: "hv" as const },
      hovertemplate: `%{x}<br>${t("pf_invested")} %{y:,.2f} €<extra></extra>`,
    }] : []),
    ...(metric === "net" ? [{
      x, y: y("tax"), type: "scatter" as const, mode: "lines" as const, name: taxLabel,
      line: { width: 1, color: "#999", dash: "dash" as const },
      hovertemplate: `%{x}<br>${taxLabel} %{y:,.2f} €<extra></extra>`,
    }] : []),
    {
      x, y: y(metric), type: "scatter" as const, mode: "lines" as const, name: label(METRICS.find((m) => m.key === metric)!),
      line: { width: 1.5, color },
      hovertemplate: "%{x}<br>%{y:,.2f} €<extra></extra>",
    },
  ];
  const layout = {
    margin: { l: 56, r: 12, t: 8, b: 40 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#bbb" },
    showlegend: false,
    xaxis: { gridcolor: "#333", rangebreaks: [WEEKENDS], ...(fill ? { fixedrange: true } : {}) },
    yaxis: { gridcolor: "#333", zerolinecolor: "#666", ...(fill ? { fixedrange: true } : {}) },
    ...(fill ? { autosize: true, dragmode: false as const } : { height: 240 }),
  };

  const buttons = (
    <div className="pf-tiles">
      {METRICS.map((m) => {
        const v = totals[m.key];
        return (
          <button key={m.key} className={"pf-tile" + (m.big ? " pf-tile--big" : "") + (metric === m.key ? " active" : "")}
                  onClick={() => onMetric(m.key)}>
            <span className="pf-tile-label">{label(m)}</span>
            <span className="pf-tile-value">{m.money ? `${price(v, lang)} €` : <PL v={v} />}</span>
            {m.key === "net" && <span className="pf-tile-label">{taxLabel}: {price(totals.tax, lang)} €</span>}
          </button>
        );
      })}
    </div>
  );
  const plot = x.length
    ? <Plot data={data} layout={layout} config={{ displayModeBar: false }} useResizeHandler
            style={fill ? { position: "absolute", inset: 0 } : { width: "100%" }} />
    : <p className="muted stk-note">{t("stk_no_data")}</p>;
  const chartTitle = `${label(METRICS.find((m) => m.key === metric)!)} (${yr || t("pf_all_years")})`;
  const head = (
    <div className="chart-title pf-summary-head">
      <span>{t("pf_summary")}</span>
      <select value={yr} onChange={(e) => onYear(e.target.value)} aria-label={t("pf_year")}>
        <option value="">{t("pf_all_years")}</option>
        {years.map((y) => <option key={y} value={y}>{y}</option>)}
      </select>
    </div>
  );

  return fill ? (
    <>
      <div className="cp-chart pf-card">
        {head}
        {buttons}
        {pf.incomplete && <p className="muted small">{t("pf_incomplete")}</p>}
      </div>
      <div className="cp-chart">
        <div className="chart-title">{chartTitle}</div>
        <div className="cp-plot">{plot}</div>
      </div>
    </>
  ) : (
    <>
      <div className="chart-block pf-card">
        {head}
        {buttons}
        {pf.incomplete && <p className="muted small">{t("pf_incomplete")}</p>}
      </div>
      <div className="chart-block">
        <div className="chart-title">{chartTitle}</div>
        {plot}
      </div>
    </>
  );
}

/** The portfolio's panel, from the tab row's 💼: each stock held (a list
 *  that scrolls), the tax rate, and the way to the transactions. */
function PortfolioPanel({ pf, reload, onClose, onTransactions, onClosed }: {
  pf: Portfolio | null; reload: () => Promise<void>; onClose: () => void;
  onTransactions: () => void; onClosed: () => void;
}) {
  const { t, lang } = useT();
  const [tax, setTax] = useState(pf ? String(pf.tax_rate) : "");
  useBackToClose(onClose);
  useEffect(() => { if (pf) setTax(String(pf.tax_rate)); }, [pf?.tax_rate]);

  const saveTax = () => {
    if (!pf) return;
    const r = parseFloat(tax.replace(",", "."));
    if (!(r >= 0 && r <= 100) || r === pf.tax_rate) return setTax(String(pf.tax_rate));
    api.setTaxRate(r).then(reload).catch(() => setTax(String(pf.tax_rate)));
  };
  const money = (v: number | null) => (v == null ? "—" : `${price(v, lang)} €`);
  // Sold out: in their own panel (Closed positions), not among these.
  const open = pf ? pf.holdings.filter((h) => h.shares) : [];
  const closed = pf ? pf.holdings.length - open.length : 0;

  return (
    <PfPanel title={t("pf_title")} onClose={onClose}>
      <section className="pf-grow">
        <h3>{t("pf_holdings")}</h3>
        {!pf && <p className="muted small">{t("loading")}</p>}
        {pf && open.length === 0 && <p className="muted small">{t("pf_none")}</p>}
        {open.length > 0 && (
          <div className="pf-scroll">
            {open.map((h) => (
              <div key={h.isin} className="pf-holding" title={h.isin}>
                <span className="stk-name">{h.name}</span>
                <span>{money(h.value)}</span>
                <span className="unit">
                  {`${shares(h.shares, lang)} × ${h.last == null ? "—" : price(h.last, lang)}`}
                </span>
                <PL v={h.realised == null || h.unrealised == null ? null : h.realised + h.unrealised} />
              </div>
            ))}
          </div>
        )}
      </section>
      {pf && (
        <section>
          <h3>{t("pf_tax_title")}</h3>
          <label className="pf-tax">
            <span>{t("pf_tax")}</span>
            <input type="number" min={0} max={100} step="any" value={tax}
                   onChange={(e) => setTax(e.target.value)} onBlur={saveTax}
                   onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
          </label>
        </section>
      )}
      <section className="pf-actions">
        <button disabled={!closed} onClick={onClosed}>{t("pf_closed")} ({closed}) ›</button>
        <button className="active" disabled={!pf} onClick={onTransactions}>{t("pf_transactions")} ›</button>
      </section>
    </PfPanel>
  );
}

/** Stocks sold out: what each one made in the end. */
function ClosedPositions({ pf, onClose }: { pf: Portfolio; onClose: () => void }) {
  const { t } = useT();
  useBackToClose(onClose);
  return (
    <PfPanel title={t("pf_closed")} onClose={onClose}>
      <section className="pf-grow">
        <div className="pf-scroll">
          {pf.holdings.filter((h) => !h.shares).map((h) => (
            <div key={h.isin} className="pf-holding">
              <span className="stk-name">{h.name}</span>
              <PL v={h.realised} />
              <span className="unit">{h.isin}</span>
              <span />
            </div>
          ))}
        </div>
      </section>
    </PfPanel>
  );
}

/** The portfolio's overlays look like the tabs' settings panel: a title and
 *  ✕, sections under small headings; over the whole screen on a phone. */
function PfPanel({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const { t } = useT();
  return createPortal(
    <div className="modal-backdrop pf-backdrop" onClick={onClose}>
      <aside className="pf-panel" onClick={(e) => e.stopPropagation()}>
        <div className="pf-head">
          <span>{title}</span>
          <button className="pf-close" onClick={onClose} title={t("close")} aria-label={t("close")}>
            <Icon name="close" size={18} className="" />
          </button>
        </div>
        {children}
      </aside>
    </div>,
    document.body,
  );
}

/** A profit or loss, green or red. */
function PL({ v }: { v: number | null }) {
  const { lang } = useT();
  return v == null ? <span>—</span> : <span className={v < 0 ? "pf-down" : "pf-up"}>{signed(v, lang)}</span>;
}

/** How many shares of `isin` can still be sold on `day`: what is held
 *  after that day's transactions, and no more than any later balance (a
 *  later sale must still be covered). Counts as the server does: by date,
 *  a day's buys before its sells, a new one after those already there. */
function sellable(txs: Transaction[], isin: string, day: string): number {
  const rows = txs.filter((tx) => tx.isin === isin)
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : (a.shares < 0 ? 1 : 0) - (b.shares < 0 ? 1 : 0) || a.id - b.id));
  let held = 0;
  let max = Infinity;
  let before = 0;
  for (const r of rows) {
    held += r.shares;
    if (r.date <= day) before = held;
    else max = Math.min(max, held);
  }
  return Math.max(0, Math.round(Math.min(before, max) * 1e6) / 1e6);
}

/** The transactions' overlay, over the summary: the form for a new one and
 *  every one so far, newest first. */
function PortfolioTransactions({ pf, stocks, today, reload, onClose }: {
  pf: Portfolio; stocks: Stock[]; today: string; reload: () => Promise<void>; onClose: () => void;
}) {
  const { t, lang } = useT();
  // The stocks one can pick: the watchlist and anything held off it.
  const choices = useMemo(() => {
    const out = stocks.map((s) => ({ isin: s.isin, name: s.name }));
    for (const h of pf.holdings) if (!out.some((c) => c.isin === h.isin)) out.push({ isin: h.isin, name: h.name });
    return out;
  }, [stocks, pf.holdings]);
  const [pick, setPick] = useState(() => choices[0]?.isin ?? "");
  const [newIsin, setNewIsin] = useState("");
  const [day, setDay] = useState(today);
  const [buy, setBuy] = useState(true);
  const [count, setCount] = useState("");
  const [total, setTotal] = useState("");
  const [all, setAll] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState<Transaction | null>(null);
  useBackToClose(onClose);

  const isNew = pick === "" || !choices.some((c) => c.isin === pick);
  const isin = isNew ? newIsin.trim() : pick;
  const max = isNew ? 0 : sellable(pf.transactions, isin, day);
  const selling = !buy && !isNew;
  const n = selling && all ? max : parseFloat(count.replace(",", "."));
  const amount = parseFloat(total.replace(",", "."));
  const ready = !!isin && !!day && n > 0 && amount > 0 && !busy && !(selling && n > max + 1e-9) && !(!buy && isNew);

  const submit = () => {
    if (!ready) return;
    setBusy(true);
    setError("");
    api.addTransaction({ isin, date: day, shares: buy ? n : -n, amount })
      .then(() => {
        setCount("");
        setTotal("");
        setAll(false);
        if (isNew) { setNewIsin(""); setPick(isin.toUpperCase()); }
        return reload();
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };
  const remove = (tx: Transaction) => {
    setDeleting(null);
    setError("");
    api.deleteTransaction(tx.id).then(reload).catch((e: Error) => setError(e.message));
  };
  const describe = (tx: Transaction) =>
    `${shortDate(tx.date, lang)} · ${tx.name} · ${t(tx.shares > 0 ? "pf_bought" : "pf_sold",
      { n: shares(Math.abs(tx.shares), lang), p: tx.price == null ? "—" : price(tx.price, lang) })}`;

  return (
    <PfPanel title={t("pf_transactions")} onClose={onClose}>
      <section>
        <h3>{t("pf_new")}</h3>
        <form className="pf-add" onSubmit={(e) => { e.preventDefault(); submit(); }}>
          <select value={isNew ? "" : pick} onChange={(e) => setPick(e.target.value)}>
            {choices.map((c) => <option key={c.isin} value={c.isin}>{c.name}</option>)}
            <option value="">{t("pf_new_isin")}</option>
          </select>
          {isNew && (
            <input value={newIsin} placeholder="ISIN" maxLength={12} spellCheck={false}
                   onChange={(e) => setNewIsin(e.target.value.toUpperCase())} />
          )}
          <div className="pf-add-row">
            <input type="date" value={day} max={today} onChange={(e) => setDay(e.target.value)} />
            <select value={buy ? "buy" : "sell"} onChange={(e) => setBuy(e.target.value === "buy")}>
              <option value="buy">{t("pf_buy")}</option>
              <option value="sell">{t("pf_sell")}</option>
            </select>
            <button type="button" className={"pf-icon-btn" + (selling && all ? " active" : "")}
                    disabled={!selling || max <= 0} onClick={() => setAll(!all)}
                    title={t("pf_all", { n: shares(max, lang) })} aria-label={t("pf_all", { n: shares(max, lang) })}
                    aria-pressed={selling && all}>
              <Icon name="all" size={16} className="" />
            </button>
          </div>
          <div className="pf-add-row">
            <input type="number" min={0} max={selling ? max : undefined} step="any" inputMode="decimal"
                   value={selling && all ? String(max) : count} disabled={selling && all}
                   placeholder={t("pf_shares")}
                   onChange={(e) => setCount(e.target.value)} />
            <input type="number" min={0} step="any" inputMode="decimal" value={total}
                   placeholder={t("pf_total")} onChange={(e) => setTotal(e.target.value)} />
            <button type="submit" className="pf-icon-btn" disabled={!ready} title={t("stk_add")} aria-label={t("stk_add")}>
              {busy ? "…" : <Icon name="plus" size={16} className="" />}
            </button>
          </div>
        </form>
        {error && <p className="error small">{error}</p>}
      </section>

      <section className="pf-grow">
        <h3>{t("pf_history")}</h3>
        <div className="pf-txlist pf-scroll">
        {pf.transactions.length === 0 && <p className="muted small pf-empty">{t("pf_none")}</p>}
        {pf.transactions.map((tx) => (
          <div key={tx.id} className="pf-tx">
            <span className="pf-tx-what" title={tx.isin}>
              <span className="stk-name">{tx.name}</span>
              <span className="unit">
                {shortDate(tx.date, lang)}
                {tx.price != null && ` · ${tx.exact ? "@" : "≈"} ${price(tx.price, lang)} €`}
              </span>
            </span>
            <span className={tx.shares > 0 ? "pf-up" : "pf-down"}>
              {tx.shares > 0 ? "+" : "−"}{shares(Math.abs(tx.shares), lang)}
            </span>
            <span>{tx.amount == null ? "—" : signed(tx.shares > 0 ? tx.amount : -tx.amount, lang, true)}</span>
            <button className="ghost stk-remove" onClick={() => setDeleting(tx)}
                    title={t("pf_delete")} aria-label={t("pf_delete")}>
              <Icon name="close" size={14} className="" />
            </button>
          </div>
        ))}
        </div>
      </section>

      {deleting && (
        <ConfirmDialog message={t("pf_delete_confirm", { what: describe(deleting) })} yesLabel={t("pf_delete")} danger
                       onYes={() => remove(deleting)} onNo={() => setDeleting(null)} />
      )}
    </PfPanel>
  );
}
