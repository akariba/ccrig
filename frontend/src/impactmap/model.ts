// Pure, dependency-free logic for the Global Event Impact Map: projection, arcs, the scene built from the API
// response, how each cable looks for each system state, and how a path reads. No React, no canvas, no randomness -
// everything here is a function of the data it is given, which is why it can be tested without a browser.

// ------------------------------------------------------------------ API shapes (the parts the page uses)
export interface Place { key?: string; label: string; lat: number; lon: number; precision: string; kind?: string }
export interface Mention { ref: string; matched_text: string; rule: string; quote: string }
export interface Hop {
  type: "MENTIONS" | "DOCUMENTED_RELATION";
  from: string; to: string;
  relation?: string; traversal?: string; stored_edge?: { source: string; target: string };
  criticality?: number | null; criticality_meaning?: string; evidence_status?: string | null; evidence_url?: string | null; note?: string | null;
  evidence?: Mention;
}
export interface EventPath { id: string; relationship_type: "DIRECT_MENTION" | "DOCUMENTED_DIRECT" | "DOCUMENTED_INDIRECT"; entity_id: string; steps: Hop[] }
export interface EventEntity { entity_id: string; name: string; role: string; relationship_to_target: string; explanation: string; mentions: Mention[] }
export interface ImpactEvent {
  id: string; title: string; category: string; relevance: string;
  published_date: string; event_date: string; event_date_basis: string;
  location: (Place & { mapped: true; basis: string; basis_text?: string }) | { mapped: false; reason: string };
  regions_mentioned: (Place & { matched_text: string; quote: string })[];
  sources: { id: string; publisher: string; url: string; title: string; published_date: string; tier: string; retrieved_at: string }[];
  evidence: { source_id: string; quote: string; url: string }[];
  verification: { status: string; checked_at: string; quotes_found: number; quotes_total: number; date_confirmed: boolean };
  entities: EventEntity[]; paths: EventPath[];
  impact: { status: string; estimate: number | null; reason: string };
  verified_exposure: { status: string; reason: string };
  limitations: string[];
}
export interface GraphNode { id: string; type: "EVENT" | "ENTITY" | "REGION"; label: string; role?: string; ticker?: string; entity_id?: string; event_id?: string; position: Place | null }
export interface GraphEdge {
  id: string; type: "MENTIONS" | "MENTIONS_REGION" | "DOCUMENTED_RELATION"; source: string; target: string; event_ids: string[];
  relation?: string; criticality?: number | null; evidence_status?: string | null;
}
export interface ImpactResponse {
  entity: { entity_id: string; name: string; ticker?: string };
  query: { limit: number; recency_days: number; as_of: string; window: [string, string] };
  as_of_basis: string;
  register: { built_at: string; coverage: string; events_total: number };
  events: ImpactEvent[];
  not_returned: { id: string; title: string; published_date: string; reason: string }[];
  explanation: string;
  graph: { nodes: GraphNode[]; edges: GraphEdge[]; edge_types: Record<string, string> };
  limitations: string[];
}

// ------------------------------------------------------------------ projection (Equal Earth, Savric et al. 2018)
const A1 = 1.340264, A2 = -0.081106, A3 = 0.000893, A4 = 0.003796;
const M = Math.sqrt(3) / 2;

export function equalEarth(lon: number, lat: number): [number, number] {
  const l = (lon * Math.PI) / 180, p = (lat * Math.PI) / 180;
  const t = Math.asin(M * Math.sin(p)), t2 = t * t, t6 = t2 * t2 * t2;
  return [(l * Math.cos(t)) / (M * (A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2))), t * (A1 + A2 * t2 + t6 * (A3 + A4 * t2))];
}

const X_MAX = equalEarth(180, 0)[0];
const Y_MAX = equalEarth(0, 90)[1];

export interface View { width: number; height: number; project: (lon: number, lat: number) => [number, number] }

/** A view that fits the whole Equal Earth world into `width` pixels (with a small margin). */
export function makeView(width: number, margin = 8): View {
  const scale = (width - 2 * margin) / (2 * X_MAX);
  const height = 2 * Y_MAX * scale + 2 * margin;
  return { width, height, project: (lon, lat) => { const [x, y] = equalEarth(lon, lat); return [margin + (x + X_MAX) * scale, margin + (Y_MAX - y) * scale]; } };
}

// ------------------------------------------------------------------ arcs
export type Pt = [number, number];

/** Control point of a curved connection: perpendicular to the chord, bowed upward (towards the north of the map). */
export function arcControl(a: Pt, b: Pt, curvature = 0.22): Pt {
  const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy) || 1;
  let nx = -dy / len, ny = dx / len;
  if (ny > 0 || (ny === 0 && nx > 0)) { nx = -nx; ny = -ny; }   // bow up the screen; an exactly vertical chord bows left, whichever end is "from"
  return [(a[0] + b[0]) / 2 + nx * len * curvature, (a[1] + b[1]) / 2 + ny * len * curvature];
}

export function quadPoint(a: Pt, c: Pt, b: Pt, t: number): Pt {
  const u = 1 - t;
  return [u * u * a[0] + 2 * u * t * c[0] + t * t * b[0], u * u * a[1] + 2 * u * t * c[1] + t * t * b[1]];
}

/** Nudge markers that would sit on top of each other apart, deterministically (by id order), in small rings. Display only. */
export function spreadOverlaps(items: { id: string; pt: Pt }[], minDist = 20, bounds?: { w: number; h: number; edge: number }): Record<string, Pt> {
  const placed: Pt[] = [], out: Record<string, Pt> = {};
  const inside = (q: Pt) => !bounds || (q[0] >= bounds.edge && q[0] <= bounds.w - bounds.edge && q[1] >= bounds.edge && q[1] <= bounds.h - bounds.edge);
  const clamp = (q: Pt): Pt => !bounds ? q : [Math.min(bounds.w - bounds.edge, Math.max(bounds.edge, q[0])), Math.min(bounds.h - bounds.edge, Math.max(bounds.edge, q[1]))];
  for (const item of [...items].sort((x, y) => (x.id < y.id ? -1 : 1))) {
    const home = clamp(item.pt);
    let pt: Pt = home;
    for (let ring = 0, tries = 0; (placed.some((q) => Math.hypot(q[0] - pt[0], q[1] - pt[1]) < minDist) || !inside(pt)) && tries < 120; tries++) {
      ring = 1 + Math.floor(tries / 8);
      const angle = ((tries % 8) / 8) * 2 * Math.PI + (ring % 2) * (Math.PI / 8);
      pt = [home[0] + Math.cos(angle) * minDist * ring * 0.9, home[1] + Math.sin(angle) * minDist * ring * 0.9];
    }
    if (!inside(pt)) pt = home;                          // nowhere free inside the stage: stay put rather than leave it
    placed.push(pt);
    out[item.id] = pt;
  }
  return out;
}

// ------------------------------------------------------------------ scene
export type MarkerKind = "event" | "entity" | "region";
export interface Marker { id: string; kind: MarkerKind; label: string; lat: number; lon: number; precision: string; role?: string; rank?: number; place?: string; eventId?: string; entityId?: string; ticker?: string }
export interface Cable { id: string; type: GraphEdge["type"]; from: string; to: string; eventIds: string[]; relation?: string }
export interface Scene { markers: Marker[]; cables: Cable[]; unmapped: { id: string; label: string; reason: string }[] }

export function buildScene(data: ImpactResponse): Scene {
  const rank = new Map(data.events.map((e, i) => [e.id, i + 1]));
  const markers: Marker[] = [], unmapped: Scene["unmapped"] = [];
  const have = new Set<string>();
  for (const n of data.graph.nodes) {
    if (!n.position) { unmapped.push({ id: n.id, label: n.label, reason: n.type === "EVENT" ? "its location could not be placed" : "its country is not in the gazetteer" }); continue; }
    have.add(n.id);
    markers.push({
      id: n.id, kind: n.type.toLowerCase() as MarkerKind, label: n.label, lat: n.position.lat, lon: n.position.lon, precision: n.position.precision,
      role: n.role, rank: n.event_id ? rank.get(n.event_id) : undefined, place: n.type === "EVENT" ? n.position.label : undefined, eventId: n.event_id, entityId: n.entity_id, ticker: n.ticker,
    });
  }
  const cables: Cable[] = data.graph.edges
    .filter((e) => have.has(e.source) && have.has(e.target))
    .map((e) => ({ id: e.id, type: e.type, from: e.source, to: e.target, eventIds: e.event_ids, relation: e.relation }));
  return { markers, cables, unmapped };
}

// ------------------------------------------------------------------ system state -> what the cables do
export type Phase = "idle" | "loading" | "ready" | "empty" | "error";

export function phaseOf(status: "idle" | "loading" | "error" | "ok", data: ImpactResponse | null): Phase {
  if (status === "loading") return "loading";
  if (status === "error") return "error";
  if (status === "ok") return data && data.events.length > 0 ? "ready" : "empty";
  return "idle";
}

export interface CableStyle {
  kind: "documented" | "mention" | "region"; draw: boolean; alpha: number; width: number; dash: number[] | null;
  pulses: number; glow: boolean; hueFrom: number; hueTo: number;
}

// Fixed colours per kind (hue, 0-360). Not random, not time-varying: colour says WHAT the link is.
const HUES = { documented: [205, 175], mention: [215, 215], region: [38, 38] } as const;

/**
 * How one cable looks. Motion is reserved for DOCUMENTED relationships (a travelling pulse runs in the stored direction of the
 * relationship, source -> target) and never for a mere mention. Nothing is drawn unless there is data to show (phase "ready").
 * With reduced motion there are no pulses at all.
 */
export function cableStyle(cable: Cable, ctx: { phase: Phase; selectedEventId: string | null; reducedMotion: boolean; hoverEventId?: string | null }): CableStyle {
  const kind = cable.type === "DOCUMENTED_RELATION" ? "documented" : cable.type === "MENTIONS" ? "mention" : "region";
  const [hueFrom, hueTo] = HUES[kind];
  const base = { kind, hueFrom, hueTo, dash: kind === "documented" ? null : kind === "mention" ? [5, 4] : [1.5, 5], width: kind === "documented" ? 1.8 : 1.1 } as const;
  if (ctx.phase !== "ready") return { ...base, draw: false, alpha: 0, pulses: 0, glow: false };
  const selected = ctx.selectedEventId !== null;
  const active = selected && cable.eventIds.includes(ctx.selectedEventId as string);
  const hovered = !active && !!ctx.hoverEventId && cable.eventIds.includes(ctx.hoverEventId);
  // A quiet contextual network by default; only the selected event's paths are emphasised (hover previews at medium strength).
  const context = kind === "documented" ? 0.3 : kind === "mention" ? 0.14 : 0.1;
  const alpha = active ? (kind === "documented" ? 1 : kind === "mention" ? 0.85 : 0.5) : hovered ? 0.6 : selected ? (kind === "documented" ? 0.12 : 0.05) : context;
  const pulses = ctx.reducedMotion || kind !== "documented" ? 0 : active ? 3 : selected ? 0 : 1;
  return { ...base, draw: true, alpha, pulses, glow: active, width: active ? base.width + 0.8 : base.width };
}

/** Pan/zoom that frames a set of points inside a w x h stage (zoom 1 = the whole world). Pure; clamped so the map never leaves the stage. */
export function fitView(points: Pt[], w: number, h: number, pad = 110, maxZoom = 2.4): { zoom: number; tx: number; ty: number } {
  if (points.length === 0) return { zoom: 1, tx: 0, ty: 0 };
  const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
  const x0 = Math.min(...xs) - pad, x1 = Math.max(...xs) + pad, y0 = Math.min(...ys) - pad, y1 = Math.max(...ys) + pad;
  const zoom = Math.max(1, Math.min(maxZoom, w / (x1 - x0), h / (y1 - y0)));
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
  return { zoom, tx: clamp(w / 2 - cx * zoom, w - w * zoom, 0), ty: clamp(h / 2 - cy * zoom, h - h * zoom, 0) };
}

export interface Rect { x: number; y: number; w: number; h: number }
export type Side = "above" | "below" | "right" | "left";

const overlap = (a: Rect, b: Rect) => Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));

/**
 * Where to put a label of size `size` next to a marker at `anchor` (screen px): the side whose box overlaps the fewest other markers
 * and leaves the stage least. A general rule, not tied to any place; ties keep the order above, below, right, left. Pure.
 */
export function placeCallout(anchor: Pt, size: { w: number; h: number }, obstacles: Rect[], bounds: { w: number; h: number }, radius = 13, gap = 12): Side {
  const { w, h } = size, d = radius + gap;
  const boxes: Record<Side, Rect> = {
    above: { x: anchor[0] - w / 2, y: anchor[1] - d - h, w, h }, below: { x: anchor[0] - w / 2, y: anchor[1] + d, w, h },
    right: { x: anchor[0] + d, y: anchor[1] - h / 2, w, h }, left: { x: anchor[0] - d - w, y: anchor[1] - h / 2, w, h },
  };
  const world: Rect = { x: 0, y: 0, w: bounds.w, h: bounds.h };
  let best: Side = "above", bestScore = Infinity;
  for (const side of ["above", "below", "right", "left"] as Side[]) {
    const box = boxes[side];
    const score = obstacles.reduce((t, o) => t + overlap(box, o), 0) + 2 * (w * h - overlap(box, world));
    if (score < bestScore - 1e-9) { best = side; bestScore = score; }
  }
  return best;
}

// ------------------------------------------------------------------ reading a path
export interface Chip { kind: "event" | "entity" | "relation"; text: string; detail?: string }

const entityName = (id: string, names: Record<string, string>) => names[id] ?? id;

export function pathChips(path: EventPath, eventTitle: string, names: Record<string, string>): Chip[] {
  const chips: Chip[] = [{ kind: "event", text: eventTitle }];
  for (const step of path.steps) {
    if (step.type === "MENTIONS") {
      chips.push({ kind: "relation", text: "names", detail: `matched "${step.evidence?.matched_text}" (${step.evidence?.rule})` });
      chips.push({ kind: "entity", text: entityName(step.to, names) });
    } else {
      const withStored = step.traversal === "WITH_STORED_DIRECTION";
      chips.push({
        kind: "relation", text: `${step.relation}${withStored ? "" : " (read in reverse)"}`,
        detail: `stored as ${step.stored_edge?.source} → ${step.stored_edge?.target}; evidence: ${step.evidence_status ?? "none stated"}; criticality ${step.criticality ?? "unspecified"} (curated judgement, not exposure)`,
      });
      chips.push({ kind: "entity", text: entityName(step.to, names) });
    }
  }
  return chips;
}

export const RELATIONSHIP_LABEL: Record<string, string> = {
  DIRECT_MENTION: "Named directly in the evidence",
  DOCUMENTED_DIRECT: "Documented relationship (1 hop)",
  DOCUMENTED_INDIRECT: "Documented relationship (2 hops, through other companies)",
  NO_DOCUMENTED_PATH: "Named, but no documented relationship in the data",
  SELF: "The searched company",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function formatDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}` : iso;
}

export function safeHttpsUrl(url: string): string | null {
  try { const u = new URL(url); return u.protocol === "https:" ? u.href : null; } catch { return null; }
}
