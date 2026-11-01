import { Fragment, useMemo, useRef, useState, type ReactNode } from "react";
import { filterRows, sortRows, toCsv, windowRange, type Cell, type Sort } from "../lib/tableModel";
import { downloadText } from "../lib/download";
import { EmptyState } from "./primitives";

export interface Column<T> {
  key: string; header: string; value: (row: T) => Cell;      // value is used for sorting, filtering and CSV
  render?: (row: T) => ReactNode; width?: number | string; align?: "left" | "right"; hidden?: boolean; sortable?: boolean; unit?: string;
}
export interface DataTableProps<T> {
  columns: Column<T>[]; rows: T[]; rowKey: (row: T) => string; label: string;     // label names the table for screen readers and the CSV file
  onRowClick?: (row: T) => void; renderExpanded?: (row: T) => ReactNode; expandedKey?: string | null; onToggleExpand?: (key: string | null) => void;
  defaultSort?: Sort; searchable?: boolean; maxHeight?: number; rowHeight?: number; emptyTitle?: string; emptyHint?: string; toolbar?: ReactNode;
}
const VIRTUAL_AFTER = 150;

export function DataTable<T>({ columns, rows, rowKey, label, onRowClick, renderExpanded, expandedKey, onToggleExpand, defaultSort, searchable = true, maxHeight = 520, rowHeight = 38, emptyTitle = "Nothing to show", emptyHint, toolbar }: DataTableProps<T>) {
  const [sort, setSort] = useState<Sort | null>(defaultSort ?? null);
  const [query, setQuery] = useState("");
  const [hidden, setHidden] = useState<Set<string>>(() => new Set(columns.filter((c) => c.hidden).map((c) => c.key)));
  const [menu, setMenu] = useState(false);
  const [scroll, setScroll] = useState(0);
  const wrap = useRef<HTMLDivElement>(null);

  const visible = columns.filter((c) => !hidden.has(c.key));
  const byKey = useMemo(() => Object.fromEntries(columns.map((c) => [c.key, c])), [columns]);
  const value = (row: T, key: string) => byKey[key]?.value(row);
  const shown = useMemo(() => sortRows(filterRows(rows, query, columns.map((c) => c.key), value), sort, value), [rows, query, sort, columns]);  // eslint-disable-line react-hooks/exhaustive-deps
  const virtual = shown.length > VIRTUAL_AFTER && !renderExpanded;
  const win = virtual ? windowRange(shown.length, scroll, maxHeight, rowHeight) : { start: 0, end: shown.length, padTop: 0, padBottom: 0 };

  const toggleSort = (key: string) => setSort((s) => (s?.key !== key ? { key, dir: "asc" } : s.dir === "asc" ? { key, dir: "desc" } : null));
  const exportCsv = () => downloadText(`${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.csv`, toCsv(visible.map((c) => (c.unit ? `${c.header} (${c.unit})` : c.header)), shown.map((r) => visible.map((c) => c.value(r)))), "text/csv");

  return (
    <div className="u-table">
      <div className="u-table-bar">
        {searchable && <input className="input u-table-search" type="search" placeholder="Filter rows…" aria-label={`Filter ${label}`} value={query} onChange={(e) => setQuery(e.target.value)} />}
        <span className="u-table-count" aria-live="polite">{shown.length === rows.length ? `${rows.length} rows` : `${shown.length} of ${rows.length} rows`}</span>
        {toolbar}
        <span className="u-spacer" />
        <div className="u-menu-wrap">
          <button type="button" className="btn secondary" aria-haspopup="true" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>Columns</button>
          {menu && (
            <div className="u-menu" role="group" aria-label="Choose columns">
              {columns.map((c) => <label key={c.key}><input type="checkbox" checked={!hidden.has(c.key)} onChange={(e) => setHidden((h) => { const n = new Set(h); if (e.target.checked) n.delete(c.key); else n.add(c.key); return n; })} /> {c.header}</label>)}
            </div>
          )}
        </div>
        <button type="button" className="btn secondary" onClick={exportCsv} disabled={shown.length === 0}>Export CSV</button>
      </div>
      {shown.length === 0 ? <EmptyState title={emptyTitle} hint={query ? "No row matches this filter." : emptyHint} /> : (
        <div className="u-table-scroll" ref={wrap} style={{ maxHeight }} onScroll={virtual ? (e) => setScroll(e.currentTarget.scrollTop) : undefined}>
          <table className="u-tbl" aria-label={label} aria-rowcount={shown.length}>
            <thead>
              <tr>
                {visible.map((c) => {
                  const on = sort?.key === c.key;
                  return (
                    <th key={c.key} scope="col" style={{ width: c.width, textAlign: c.align }} aria-sort={on ? (sort!.dir === "asc" ? "ascending" : "descending") : undefined}>
                      {c.sortable === false ? c.header : <button type="button" className="u-th" onClick={() => toggleSort(c.key)}>{c.header}{c.unit && <span className="u-unit"> ({c.unit})</span>}<span aria-hidden="true" className="u-sortmark">{on ? (sort!.dir === "asc" ? "▲" : "▼") : ""}</span></button>}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {win.padTop > 0 && <tr aria-hidden="true" style={{ height: win.padTop }}><td colSpan={visible.length} /></tr>}
              {shown.slice(win.start, win.end).map((row) => {
                const k = rowKey(row), open = renderExpanded && expandedKey === k;
                return (
                  <Fragment key={k}>
                    <tr style={virtual ? { height: rowHeight } : undefined} className={onRowClick || renderExpanded ? "clickable" : undefined} aria-expanded={renderExpanded ? !!open : undefined}
                      onClick={() => { if (renderExpanded) onToggleExpand?.(open ? null : k); onRowClick?.(row); }}
                      tabIndex={onRowClick || renderExpanded ? 0 : undefined}
                      onKeyDown={onRowClick || renderExpanded ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); if (renderExpanded) onToggleExpand?.(open ? null : k); onRowClick?.(row); } } : undefined}>
                      {visible.map((c) => <td key={c.key} style={{ textAlign: c.align }} className={c.align === "right" ? "num" : undefined}>{c.render ? c.render(row) : (c.value(row) ?? "—")}</td>)}
                    </tr>
                    {open && <tr className="u-expanded"><td colSpan={visible.length}>{renderExpanded!(row)}</td></tr>}
                  </Fragment>
                );
              })}
              {win.padBottom > 0 && <tr aria-hidden="true" style={{ height: win.padBottom }}><td colSpan={visible.length} /></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
