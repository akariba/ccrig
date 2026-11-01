import { useEffect, useRef, useState } from "react";
import type { EChartsCoreOption } from "echarts/core";
import { readChartTokens, useThemeVersion, type ChartTokens } from "./chartTokens";
import { downloadUrl } from "../lib/download";
import { slug } from "../lib/slug";
import type { Cell } from "../lib/tableModel";
import { Skeleton } from "./primitives";

export interface ChartTable { columns: string[]; rows: Cell[][] }
interface Props { label: string; build: (t: ChartTokens) => EChartsCoreOption; table: ChartTable; height?: number; onClick?: (params: unknown) => void; deps?: unknown }

/** Thin ECharts wrapper: lazy-loaded, themed from the CSS tokens, resized with its box, PNG export, and a "View as table" alternative on every chart. */
export function EChart({ label, build, table, height = 280, onClick, deps }: Props) {
  const host = useRef<HTMLDivElement>(null), chart = useRef<{ setOption: (o: EChartsCoreOption, notMerge?: boolean) => void; resize: () => void; dispose: () => void; getDataURL: (o: object) => string; on: (e: string, f: (p: unknown) => void) => void } | null>(null);
  const [ready, setReady] = useState(false), [asTable, setAsTable] = useState(false), [failed, setFailed] = useState<string | null>(null);
  const theme = useThemeVersion();
  const click = useRef(onClick); click.current = onClick;

  useEffect(() => {
    if (asTable || !host.current) return;
    let dead = false; const el = host.current;
    import("./echartsSetup").then(({ echarts }) => {
      if (dead) return;
      const c = echarts.init(el, undefined, { renderer: "canvas" }); chart.current = c; c.on("click", (p) => click.current?.(p)); setReady(true);
    }).catch((e) => !dead && setFailed(String(e?.message ?? e)));
    const ro = new ResizeObserver(() => chart.current?.resize()); ro.observe(el);
    return () => { dead = true; ro.disconnect(); chart.current?.dispose(); chart.current = null; setReady(false); };
  }, [asTable]);

  useEffect(() => { if (ready && chart.current) chart.current.setOption(build(readChartTokens()), true); }, [ready, theme, build, deps]);

  return (
    <figure className="u-chart">
      <div className="u-chart-bar">
        <figcaption>{label}</figcaption><span className="u-spacer" />
        <button type="button" className="u-link" aria-pressed={asTable} onClick={() => setAsTable((t) => !t)}>{asTable ? "View chart" : "View as table"}</button>
        {!asTable && <button type="button" className="u-link" disabled={!ready} onClick={() => chart.current && downloadUrl(`${slug(label)}.png`, chart.current.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: readChartTokens().surface }))}>Export PNG</button>}
      </div>
      {failed ? <p className="u-error">The chart could not be loaded ({failed}). Use “View as table”.</p> : asTable ? (
        <div key="table" className="u-table-scroll" style={{ maxHeight: height }}>
          <table className="u-tbl" aria-label={`${label} (table)`}><thead><tr>{table.columns.map((c) => <th key={c} scope="col">{c}</th>)}</tr></thead>
            <tbody>{table.rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j} className={typeof v === "number" ? "num" : undefined}>{v ?? "—"}</td>)}</tr>)}</tbody></table>
        </div>
      ) : (<>{!ready && <Skeleton lines={4} />}<div key="chart" ref={host} role="img" aria-label={label} style={{ height: ready ? height : 0 }} /></>)}
    </figure>
  );
}
