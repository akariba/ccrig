// The pure part of DataTable: sort, filter, window (virtualisation) and CSV. No React, so it is unit-tested directly.
export type SortDir = "asc" | "desc";
export interface Sort { key: string; dir: SortDir }
export type Cell = string | number | boolean | null | undefined;

const isBlank = (v: Cell) => v === null || v === undefined || v === "";

/** Blanks sort last in either direction; numbers numerically, everything else by locale-aware text (numeric-aware). */
export function compareCells(a: Cell, b: Cell, dir: SortDir): number {
  if (isBlank(a) && isBlank(b)) return 0;
  if (isBlank(a)) return 1;
  if (isBlank(b)) return -1;
  const r = typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
  return dir === "asc" ? r : -r;
}

export function sortRows<T>(rows: T[], sort: Sort | null, value: (row: T, key: string) => Cell): T[] {
  if (!sort) return rows;
  return rows.map((row, i) => ({ row, i })).sort((x, y) => compareCells(value(x.row, sort.key), value(y.row, sort.key), sort.dir) || x.i - y.i).map((x) => x.row);
}

/** Case-insensitive: every word of the query must appear in one of the row's searchable cells. */
export function filterRows<T>(rows: T[], query: string, keys: string[], value: (row: T, key: string) => Cell): T[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return rows;
  return rows.filter((row) => { const hay = keys.map((k) => String(value(row, k) ?? "")).join(" \u0001 ").toLowerCase(); return words.every((w) => hay.includes(w)); });
}

/** Which rows to render for a scroll position: a fixed row height, with `overscan` extra rows on each side. */
export function windowRange(total: number, scrollTop: number, viewportH: number, rowH: number, overscan = 8): { start: number; end: number; padTop: number; padBottom: number } {
  if (total <= 0 || rowH <= 0) return { start: 0, end: 0, padTop: 0, padBottom: 0 };
  const start = Math.max(0, Math.floor(scrollTop / rowH) - overscan), end = Math.min(total, Math.ceil((scrollTop + viewportH) / rowH) + overscan);
  return { start, end, padTop: start * rowH, padBottom: (total - end) * rowH };
}

const needsQuote = /[",\r\n]/;
/** RFC 4180 field. A leading = + - @ is prefixed with an apostrophe so a spreadsheet never runs a cell as a formula. */
export function csvField(v: Cell): string {
  if (v === null || v === undefined) return "";
  let s = String(v);
  if (typeof v === "string" && /^[=+\-@\t\r]/.test(s)) s = "'" + s;
  return needsQuote.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(headers: string[], rows: Cell[][]): string {
  return [headers, ...rows].map((r) => r.map(csvField).join(",")).join("\r\n") + "\r\n";
}
