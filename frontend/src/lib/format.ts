export const todayISO = (): string => new Date().toISOString().slice(0, 10);
export const signed = (v: number | null | undefined, digits = 1): string => (v === null || v === undefined ? "Unavailable" : `${v > 0 ? "+" : ""}${v.toFixed(digits)}`);
export const pct = (v: number | null | undefined, digits = 0): string => (v === null || v === undefined ? "Unavailable" : `${v.toFixed(digits)}%`);
export const money = (v: number | null | undefined): string => (v === null || v === undefined ? "Unavailable" : `${v.toLocaleString("en-US", { maximumFractionDigits: 1 })} $mm`);
export const niceDate = (iso: string): string => new Date(iso + "T00:00:00Z").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
