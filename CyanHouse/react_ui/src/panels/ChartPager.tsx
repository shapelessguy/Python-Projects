import { ReactNode, useRef, useState } from "react";
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";
import type { PlotParams } from "react-plotly.js";

const Plot = createPlotlyComponent(Plotly);

export type PagedChart = { key: string; title: ReactNode; data: PlotParams["data"]; layout: PlotParams["layout"] };

/** Plotly charts `perPage` to a page (two by default), sharing the height
 *  the pager is given -- for a phone, where a column of charts would scroll
 *  (Environment's history and forecast). ‹ › or a sideways swipe turns the
 *  page; the charts don't zoom or pan, so a swipe across one is a swipe.
 *  `lead`, if given, is a page of its own before the charts. */
export function ChartPager({ charts, perPage = 2, lead }: { charts: PagedChart[]; perPage?: number; lead?: ReactNode }) {
  const [page, setPage] = useState(0);
  const touch = useRef<{ x: number; y: number } | null>(null);
  const first = lead ? 1 : 0;
  const pages = first + Math.max(lead ? 0 : 1, Math.ceil(charts.length / perPage));
  const p = Math.min(page, pages - 1);
  const onLead = !!lead && p === 0;
  const shown = onLead ? [] : charts.slice((p - first) * perPage, (p - first + 1) * perPage);
  const go = (to: number) => setPage(Math.max(0, Math.min(pages - 1, to)));

  return (
    <div className="chart-pager">
      <div
        className="cp-page"
        onTouchStart={(e) => (touch.current = { x: e.touches[0].clientX, y: e.touches[0].clientY })}
        onTouchEnd={(e) => {
          const s = touch.current;
          touch.current = null;
          if (!s) return;
          const dx = e.changedTouches[0].clientX - s.x;
          const dy = e.changedTouches[0].clientY - s.y;
          if (Math.abs(dx) > 50 && Math.abs(dx) > 2 * Math.abs(dy)) go(p + (dx < 0 ? 1 : -1));
        }}
      >
        {onLead && lead}
        {shown.map((c) => (
          <div key={c.key} className="cp-chart">
            <div className="chart-title">{c.title}</div>
            <div className="cp-plot">
              <Plot
                data={c.data}
                layout={{
                  ...c.layout,
                  height: undefined,
                  autosize: true,
                  dragmode: false,
                  xaxis: { ...c.layout.xaxis, fixedrange: true },
                  yaxis: { ...c.layout.yaxis, fixedrange: true },
                }}
                config={{ displayModeBar: false }}
                style={{ position: "absolute", inset: 0 }}
                useResizeHandler
              />
            </div>
          </div>
        ))}
        {/* A short last page keeps its charts the size of the others'. */}
        {pages > 1 && !onLead && Array.from({ length: perPage - shown.length }, (_, i) => <div key={i} className="cp-chart" />)}
      </div>
      {pages > 1 && (
        <div className="cp-nav">
          <button disabled={p === 0} onClick={() => go(p - 1)} aria-label="‹">‹</button>
          <span>{p + 1} / {pages}</span>
          <button disabled={p === pages - 1} onClick={() => go(p + 1)} aria-label="›">›</button>
        </div>
      )}
    </div>
  );
}
