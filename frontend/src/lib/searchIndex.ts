// Command-palette search: pure ranking over a list of entries, so the behaviour is tested without a browser.
// Results show names (never raw ids); an id is searchable but only as a weaker match.
export type EntryKind = "counterparty" | "issuer" | "theme" | "event" | "page";

export interface Entry {
  kind: EntryKind; key: string; name: string; href: string;
  detail?: string;          // sector · country, priority, ...
  aliases?: string[];       // ticker, legal name, id: matched, never displayed as the title
}

export interface Hit extends Entry { score: number }

const norm = (s: string) => s.toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, " ").trim();
const KIND_ORDER: Record<EntryKind, number> = { page: 0, counterparty: 1, issuer: 2, theme: 3, event: 4 };

/** 100 exact name, 80 name starts with the query, 60 a word of the name starts with it, 40 name contains it, 25 an alias matches (same tiers, lower); 0 no match. */
export function scoreEntry(entry: Entry, query: string): number {
  const q = norm(query);
  if (!q) return 0;
  const tier = (text: string, exact: number, prefix: number, word: number, within: number) => {
    const t = norm(text);
    if (t === q) return exact;
    if (t.startsWith(q)) return prefix;
    if (t.split(" ").some((w) => w.startsWith(q))) return word;
    if (t.includes(q)) return within;
    return 0;
  };
  let best = tier(entry.name, 100, 80, 60, 40);
  for (const a of entry.aliases ?? []) best = Math.max(best, tier(a, 70, 50, 35, 25));
  // every word of a multi-word query must hit somewhere in the name or aliases
  if (best === 0 && q.includes(" ")) {
    const hay = norm([entry.name, ...(entry.aliases ?? [])].join(" "));
    if (q.split(" ").every((w) => hay.includes(w))) best = 30;
  }
  return best;
}

export function search(entries: Entry[], query: string, limit = 12): Hit[] {
  const hits: Hit[] = [];
  for (const e of entries) { const score = scoreEntry(e, query); if (score > 0) hits.push({ ...e, score }); }
  hits.sort((a, b) => b.score - a.score || KIND_ORDER[a.kind] - KIND_ORDER[b.kind] || a.name.localeCompare(b.name));
  return hits.slice(0, limit);
}

/** A query that reads like a headline rather than a name: four or more words, and nothing matched it strongly. */
export function looksLikeHeadline(query: string, hits: Hit[]): boolean {
  const words = query.trim().split(/\s+/).filter(Boolean);
  return words.length >= 4 && !hits.some((h) => h.score >= 80);
}
