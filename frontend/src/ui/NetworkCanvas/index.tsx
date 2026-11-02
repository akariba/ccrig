// NetworkCanvas: the relationship graph renderer. Canvas 2D, deterministic layouts, pure draw functions (see ./drawNodes, ./drawEdges, ./labels, ./hitTest, ./layout).
// Interaction: hover focus (non-neighbours fade), click selects (never navigates), drag to pan (mouse only: touch keeps page scroll), Ctrl/Cmd+wheel zooms,
// double-click resets, arrow keys walk the nodes. Animation (particles, shimmer, pulses, ripples) runs only while the canvas is on screen and the tab is
// visible, and not at all under prefers-reduced-motion. A list view (nodes and edges as tables) is the non-visual alternative.
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { CHANNELS, type Channel } from "../channels";
import { useThemeVersion } from "../chartTokens";
import { DataTable } from "../DataTable";
import { mergeParallel, parallelIndex, controlPoint, drawEdge } from "./drawEdges";
import { channelMix, drawGlyph, glyphRadius, groupColor, priorityColor } from "./drawNodes";
import { hitEdge, hitNode } from "./hitTest";
import { placeLabels, tagWidth, type LabelItem } from "./labels";
import { forceLayout, radialEgo } from "./layout";
import { readPalette } from "./palette";
import type { Camera, Cluster, GEdge, GNode, HeatMap, Palette, Pt } from "./types";

export type NetSelection = { type: "node"; id: string } | { type: "edge"; id: string } | null;
export interface NetworkHandle { highlight: (ids: string[]) => void; zoomIn: () => void; zoomOut: () => void; reset: () => void }
export interface NetworkProps {
  nodes: GNode[]; edges: GEdge[]; clusters?: Cluster[]; layout?: "force" | "radial"; centerId?: string; fixedCenter?: boolean;
  selected?: NetSelection; onSelect?: (s: NetSelection) => void; visibleChannels?: ReadonlySet<Channel>; heat?: HeatMap | null; shock?: string[]; highlightIds?: string[];
  height?: number; label: string; guide?: React.ReactNode; labelTop?: number;
}
const WORLD = { width: 1100, height: 680 };

function useReducedMotion(): boolean {
  const [r, setR] = useState(() => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => { const mq = matchMedia("(prefers-reduced-motion: reduce)"), on = () => setR(mq.matches); mq.addEventListener("change", on); return () => mq.removeEventListener("change", on); }, []);
  return r;
}


const clip = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
export const NetworkCanvas = forwardRef<NetworkHandle, NetworkProps>(function NetworkCanvas(props, ref) {
  const { nodes, edges, clusters = [], layout = "force", centerId, fixedCenter = false, selected = null, onSelect, visibleChannels, heat = null, shock = [], height = 560, label, labelTop = 14 } = props;
  const wrap = useRef<HTMLDivElement>(null), canvas = useRef<HTMLCanvasElement>(null), theme = useThemeVersion(), reduced = useReducedMotion();
  const [list, setList] = useState(false), [tip, setTip] = useState<{ x: number; y: number; id: string } | null>(null), [live, setLive] = useState("");
  const [highlight, setHighlight] = useState<string[]>(props.highlightIds ?? []);
  const cam = useRef<Camera>({ k: 1, x: 0, y: 0 }), size = useRef({ w: 800, h: height }), hover = useRef<string | null>(null), dirty = useRef(true), visible = useRef(true), drag = useRef<{ x: number; y: number; cx: number; cy: number; moved: boolean } | null>(null);
  const st = useRef({ nodes, edges, selected, heat, shock, highlight, visibleChannels, palette: null as Palette | null, reduced });
  useImperativeHandle(ref, () => ({ highlight: (ids) => { setHighlight(ids); dirty.current = true; }, zoomIn: () => zoom(1.3), zoomOut: () => zoom(1 / 1.3), reset: () => fit() }));

  const shown = useMemo(() => mergeParallel(edges.filter((e) => !visibleChannels || visibleChannels.has(e.channel))), [edges, visibleChannels]);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const pos = useMemo<Record<string, Pt>>(() => {
    if (layout === "radial" && centerId) return radialEgo(nodes, mergeParallel(edges), centerId, WORLD).pos;
    const fixed = fixedCenter && centerId ? { [centerId]: { x: WORLD.width / 2, y: WORLD.height / 2 } } : undefined;
    return forceLayout(nodes, mergeParallel(edges), { width: WORLD.width, height: WORLD.height, fixed, clusters: clusters.map((c) => c.members) });
  }, [nodes, edges, layout, centerId, fixedCenter, clusters]);
  const par = useMemo(() => parallelIndex(shown), [shown]);
  const mixOf = useMemo(() => { const m = new Map<string, ReturnType<typeof channelMix>>(); for (const n of nodes) if (n.kind === "counterparty") m.set(n.id, channelMix(shown.filter((e) => e.source === n.id || e.target === n.id))); return m; }, [nodes, shown]);
  const neighbours = useMemo(() => { const m = new Map<string, Set<string>>(); for (const e of shown) { (m.get(e.source) ?? m.set(e.source, new Set()).get(e.source)!).add(e.target); (m.get(e.target) ?? m.set(e.target, new Set()).get(e.target)!).add(e.source); } return m; }, [shown]);
  const degree = useMemo(() => new Map(nodes.map((n) => [n.id, neighbours.get(n.id)?.size ?? 0])), [nodes, neighbours]);
  const sortedIds = useMemo(() => [...nodes].sort((a, b) => a.label.localeCompare(b.label)).map((n) => n.id), [nodes]);
  const m = useRef({ shown, pos, par, mixOf, neighbours, degree, clusters, byId, centerId });
  m.current = { shown, pos, par, mixOf, neighbours, degree, clusters, byId, centerId };
  st.current = { nodes, edges, selected, heat, shock, highlight, visibleChannels, palette: st.current.palette, reduced };

  const toScreen = (p: Pt): Pt => ({ x: p.x * cam.current.k + cam.current.x, y: p.y * cam.current.k + cam.current.y });
  const toWorld = (p: Pt): Pt => ({ x: (p.x - cam.current.x) / cam.current.k, y: (p.y - cam.current.y) / cam.current.k });
  /** Fit the drawing (not the empty world around it) into the box, so a small graph fills its map instead of floating in it. */
  function fit() {
    const { w, h } = size.current, pts = Object.values(m.current.pos);
    const x0 = pts.length ? Math.min(...pts.map((p) => p.x)) - 70 : 0, x1 = pts.length ? Math.max(...pts.map((p) => p.x)) + 70 : WORLD.width, y0 = pts.length ? Math.min(...pts.map((p) => p.y)) - 70 : 0, y1 = pts.length ? Math.max(...pts.map((p) => p.y)) + 70 : WORLD.height;
    const bw = Math.max(200, x1 - x0), bh = Math.max(200, y1 - y0), k = Math.max(0.2, Math.min(2.2, Math.min(w / bw, h / bh)));
    cam.current = { k, x: (w - bw * k) / 2 - x0 * k, y: (h - bh * k) / 2 - y0 * k }; dirty.current = true;
  }
  function zoom(f: number, at?: Pt) { const { w, h } = size.current, c = at ?? { x: w / 2, y: h / 2 }, w0 = toWorld(c), k = Math.max(0.25, Math.min(5, cam.current.k * f)); cam.current = { k, x: c.x - w0.x * k, y: c.y - w0.y * k }; dirty.current = true; }

  // ------------------------------------------------------------------ drawing
  const draw = useCallback((time: number) => {
    const cv = canvas.current; if (!cv) return;
    const ctx = cv.getContext("2d"); if (!ctx) return;
    cv.dataset.frames = String(Number(cv.dataset.frames ?? 0) + 1);          // a test hook: how many frames this canvas has actually drawn
    const s = st.current, g = m.current, c = s.palette ?? (s.palette = readPalette()), { w, h } = size.current, dpr = Math.min(2, window.devicePixelRatio || 1);
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); cv.style.width = `${w}px`; cv.style.height = `${h}px`; }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
    const hov = hover.current, focus = hov ?? null, near = focus ? g.neighbours.get(focus) : null, hl = new Set(s.highlight), anyHl = hl.size > 0;
    const isDim = (id: string) => (focus ? id !== focus && !near?.has(id) : anyHl ? !hl.has(id) : false);
    ctx.save(); ctx.setTransform(dpr * cam.current.k, 0, 0, dpr * cam.current.k, dpr * cam.current.x, dpr * cam.current.y);
    for (const cl of g.clusters) {                                                    // cluster halos (from the backend's clusters)
      const pts = cl.members.map((id) => g.pos[id]).filter(Boolean); if (pts.length < 2) continue;
      const cx = pts.reduce((a, p) => a + p.x, 0) / pts.length, cy = pts.reduce((a, p) => a + p.y, 0) / pts.length, r = Math.max(...pts.map((p) => Math.hypot(p.x - cx, p.y - cy))) + 42;
      ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fillStyle = c.accent; ctx.globalAlpha = 0.055; ctx.fill(); ctx.globalAlpha = 0.28; ctx.strokeStyle = c.accent; ctx.lineWidth = 1; ctx.setLineDash([5, 5]); ctx.stroke(); ctx.setLineDash([]); ctx.globalAlpha = 1;
    }
    for (const e of g.shown) {
      const a = g.pos[e.source], b = g.pos[e.target]; if (!a || !b) continue;
      const { index, count } = g.par.get(e.id) ?? { index: 0, count: 1 }, cp = controlPoint(a, b, index, count);
      const isSel = s.selected?.type === "edge" && s.selected.id === e.id, dim = focus ? !(e.source === focus || e.target === focus) : anyHl ? !(hl.has(e.source) && hl.has(e.target)) : false;
      drawEdge(ctx, { e, a, c: cp, b, dim, time, reduced: s.reduced || g.shown.length > 1500, selected: isSel, k: cam.current.k }, c);
    }
    for (const n of s.nodes) {
      const p = g.pos[n.id]; if (!p) continue;
      drawGlyph(ctx, n, p, { selected: s.selected?.type === "node" && s.selected.id === n.id, hover: hov === n.id, dim: isDim(n.id), time, reduced: s.reduced, heat: s.heat?.[n.id], shock: s.shock.includes(n.id), highlight: hl.has(n.id), mix: g.mixOf.get(n.id) ?? [] }, c);
    }
    ctx.restore(); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    // screen-space: cluster names and boxed tags at a constant size
    ctx.font = '500 11px "JetBrains Mono", monospace'; ctx.textBaseline = "middle";
    for (const cl of g.clusters) {
      const pts = cl.members.map((id) => g.pos[id]).filter(Boolean); if (pts.length < 2) continue;
      const cx = pts.reduce((a, p) => a + p.x, 0) / pts.length, cy = pts.reduce((a, p) => a + p.y, 0) / pts.length, r = Math.max(...pts.map((p) => Math.hypot(p.x - cx, p.y - cy))) + 42, at = toScreen({ x: cx, y: cy - r });
      ctx.fillStyle = c.accent; ctx.globalAlpha = 0.8; ctx.textAlign = "center"; ctx.fillText(cl.name.toUpperCase(), at.x, at.y - 8); ctx.globalAlpha = 1;
    }
    const sel = s.selected?.type === "node" ? s.selected.id : null, items: LabelItem[] = [], glyphs: { at: Pt; radius: number }[] = [], zoomedIn = cam.current.k > 1.5;
    const ranked = [...s.nodes].sort((a, b) => (g.degree.get(b.id) ?? 0) - (g.degree.get(a.id) ?? 0) || a.id.localeCompare(b.id)), top = new Set(ranked.slice(0, labelTop).map((n) => n.id));
    for (const n of s.nodes) {
      const p = g.pos[n.id]; if (!p) continue; const at = toScreen(p), radius = glyphRadius(n) * cam.current.k;
      glyphs.push({ at, radius });
      const show = n.id === sel || n.id === hov || (focus && near?.has(n.id)) || hl.has(n.id) || n.id === g.centerId || (n.kind === "counterparty" && (n.cp?.priority === "CRITICAL" || n.cp?.priority === "HIGH")) || top.has(n.id) || zoomedIn;
      if (!show || at.x < -20 || at.y < -20 || at.x > w + 20 || at.y > h + 20) continue;
      const text = clip(n.kind === "counterparty" ? n.label : n.tag, n.kind === "counterparty" ? 24 : 10);
      items.push({ id: n.id, text, at, radius, priority: (n.id === sel ? 1000 : 0) + (n.id === hov ? 900 : 0) + (hl.has(n.id) ? 500 : 0) + (n.id === g.centerId ? 400 : 0) + (g.degree.get(n.id) ?? 0), w: tagWidth(text), h: 18 });
    }
    const placed = placeLabels(items, { x: 2, y: 2, w: w - 4, h: h - 4 }, glyphs);
    ctx.textAlign = "left";
    for (const it of items) {
      const r = placed.get(it.id); if (!r) continue;
      const n = g.byId.get(it.id)!, edge = n.kind === "counterparty" ? priorityColor(n.cp?.priority ?? null, c) : n.kind === "issuer" ? groupColor(n.group, c) : c.text3;
      ctx.globalAlpha = isDim(n.id) ? 0.3 : 1; ctx.fillStyle = c.bg; ctx.globalAlpha *= 0.9; ctx.fillRect(r.x, r.y, r.w, r.h); ctx.globalAlpha = isDim(n.id) ? 0.3 : 1;
      ctx.strokeStyle = n.id === sel ? c.accent : edge; ctx.lineWidth = n.id === sel ? 1.4 : 1; ctx.strokeRect(r.x + 0.5, r.y + 0.5, r.w - 1, r.h - 1);
      ctx.fillStyle = c.text; ctx.fillText(it.text, r.x + 6, r.y + r.h / 2 + 0.5); ctx.globalAlpha = 1;
    }
  }, [labelTop]);   // eslint-disable-line react-hooks/exhaustive-deps -- everything else is read from refs on every frame

  // loop: runs only while visible and the tab is shown; animates only when motion is allowed
  useEffect(() => {
    let raf = 0, last = 0, io: IntersectionObserver | null = null;
    const tick = (now: number) => {
      raf = 0;
      if (document.hidden || !visible.current) return;
      const animate = !st.current.reduced, heavy = st.current.nodes.length > 800, minGap = heavy ? 33 : 0;
      if ((animate || dirty.current) && now - last >= minGap) { last = now; dirty.current = false; draw(now); }
      if (animate) raf = requestAnimationFrame(tick); else if (dirty.current) raf = requestAnimationFrame(tick);
    };
    const kick = () => { if (!raf && !document.hidden && visible.current) raf = requestAnimationFrame(tick); };
    const ping = setInterval(() => { if (dirty.current) kick(); }, 60);
    io = new IntersectionObserver(([e]) => { visible.current = e.isIntersecting; if (visible.current) { dirty.current = true; kick(); } }, { threshold: 0.01 });
    if (wrap.current) io.observe(wrap.current);
    const vis = () => { if (!document.hidden) { dirty.current = true; kick(); } };
    document.addEventListener("visibilitychange", vis); kick();
    return () => { cancelAnimationFrame(raf); clearInterval(ping); io?.disconnect(); document.removeEventListener("visibilitychange", vis); };
  }, [draw, list, reduced]);

  useEffect(() => { st.current.palette = null; dirty.current = true; }, [theme]);
  useEffect(() => { dirty.current = true; }, [nodes, shown, selected, heat, highlight, shock, pos]);
  useEffect(() => { setHighlight(props.highlightIds ?? []); }, [props.highlightIds]);
  useEffect(() => {
    const el = wrap.current; if (!el || list) return;
    const ro = new ResizeObserver(() => { const w = Math.max(280, el.clientWidth), h = height; const first = size.current.w === 800; size.current = { w, h }; if (first || cam.current.k === 1) fit(); else dirty.current = true; });
    ro.observe(el); size.current = { w: Math.max(280, el.clientWidth), h: height }; fit();
    return () => ro.disconnect();
  }, [height, list, pos]);   // eslint-disable-line react-hooks/exhaustive-deps

  // ------------------------------------------------------------------ pointer and keyboard
  const nodeHits = () => st.current.nodes.map((n) => ({ id: n.id, at: toScreen(m.current.pos[n.id] ?? { x: -999, y: -999 }), radius: glyphRadius(n) * cam.current.k }));
  const edgeHits = () => m.current.shown.flatMap((e) => { const a = m.current.pos[e.source], b = m.current.pos[e.target]; if (!a || !b) return []; const { index, count } = m.current.par.get(e.id) ?? { index: 0, count: 1 }; return [{ id: e.id, a: toScreen(a), c: toScreen(controlPoint(a, b, index, count)), b: toScreen(b), width: 3 }]; });
  const local = (e: React.PointerEvent | React.MouseEvent | React.WheelEvent): Pt => { const r = canvas.current!.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  const onMove = (e: React.PointerEvent) => {
    const p = local(e);
    if (drag.current) { const d = drag.current; if (Math.hypot(p.x - d.x, p.y - d.y) > 3) d.moved = true; cam.current = { ...cam.current, x: d.cx + (p.x - d.x), y: d.cy + (p.y - d.y) }; dirty.current = true; setTip(null); return; }
    const id = hitNode(nodeHits(), p);
    if (id !== hover.current) { hover.current = id; dirty.current = true; }
    setTip(id ? { x: p.x, y: p.y, id } : null);
    canvas.current!.style.cursor = id ? "pointer" : "grab";
  };
  const onDown = (e: React.PointerEvent) => { if (e.pointerType !== "mouse") return; const p = local(e); drag.current = { x: p.x, y: p.y, cx: cam.current.x, cy: cam.current.y, moved: false }; (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); };
  const onUp = (e: React.PointerEvent) => {
    const d = drag.current; drag.current = null;
    if (d?.moved) return;
    const p = local(e), id = hitNode(nodeHits(), p);
    if (id) { onSelect?.({ type: "node", id }); setLive(`Selected ${m.current.byId.get(id)?.label}`); return; }
    const eid = hitEdge(edgeHits(), p); onSelect?.(eid ? { type: "edge", id: eid } : null);
  };
  const onWheel = (e: React.WheelEvent) => { if (!(e.ctrlKey || e.metaKey)) return; e.preventDefault(); zoom(e.deltaY < 0 ? 1.12 : 1 / 1.12, local(e)); };
  const onKey = (e: React.KeyboardEvent) => {
    const cur = selected?.type === "node" ? sortedIds.indexOf(selected.id) : -1;
    if (["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(e.key) && sortedIds.length) { e.preventDefault(); const next = sortedIds[(cur + (e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : -1) + sortedIds.length) % sortedIds.length]; onSelect?.({ type: "node", id: next }); setLive(`Selected ${byId.get(next)?.label}`); }
    else if (e.key === "Escape") onSelect?.(null); else if (e.key === "+" || e.key === "=") zoom(1.3); else if (e.key === "-") zoom(1 / 1.3); else if (e.key === "0") fit();
  };
  useEffect(() => { const el = canvas.current; if (!el) return; const stop = (e: WheelEvent) => { if (e.ctrlKey || e.metaKey) e.preventDefault(); }; el.addEventListener("wheel", stop, { passive: false }); return () => el.removeEventListener("wheel", stop); }, [list]);

  const tipNode = tip ? byId.get(tip.id) : null;
  const nameOf = (id: string) => byId.get(id)?.label ?? id;
  return (
    <div className="nc">
      <div className="nc-bar">
        <span className="u-muted">{nodes.length} nodes · {shown.length} links{clusters.length ? ` · ${clusters.length} clusters` : ""}</span><span className="u-spacer" />
        {!list && <><button type="button" className="btn secondary" aria-label="Zoom in" onClick={() => zoom(1.3)}>＋</button><button type="button" className="btn secondary" aria-label="Zoom out" onClick={() => zoom(1 / 1.3)}>−</button><button type="button" className="btn secondary" onClick={fit}>Reset</button></>}
        <button type="button" className="btn secondary" aria-pressed={list} onClick={() => setList((v) => !v)}>{list ? "View graph" : "List view"}</button>
      </div>
      {list ? (
        <div className="nc-list">
          <DataTable label={`${label}: nodes`} rows={nodes} rowKey={(n) => n.id} maxHeight={260} onRowClick={(n) => onSelect?.({ type: "node", id: n.id })}
            columns={[{ key: "label", header: "Name", value: (n) => n.label }, { key: "kind", header: "Type", value: (n) => n.kind }, { key: "deg", header: "Links", align: "right", value: (n) => degree.get(n.id) ?? 0 }, { key: "util", header: "Utilisation", unit: "%", align: "right", value: (n) => n.cp?.utilisation ?? null }]} />
          <DataTable label={`${label}: links`} rows={shown} rowKey={(e) => e.id} maxHeight={260} onRowClick={(e) => onSelect?.({ type: "edge", id: e.id })}
            columns={[{ key: "a", header: "From", value: (e) => nameOf(e.source) }, { key: "b", header: "To", value: (e) => nameOf(e.target) }, { key: "c", header: "Channel", value: (e) => CHANNELS[e.channel].label }, { key: "s", header: "Strength", align: "right", value: (e) => e.strength }, { key: "k", header: "Confidence", align: "right", value: (e) => e.confidence }]} />
        </div>
      ) : (
        <div className="nc-stage" ref={wrap} style={{ height }} data-testid="network-canvas" data-nodes={nodes.length} data-highlighted={highlight.length} data-selected={selected?.id ?? ""}>
          <canvas ref={canvas} className="nc-canvas" tabIndex={0} role="application" aria-label={`${label}. Arrow keys move between nodes, Enter or click selects, plus and minus zoom, zero resets. The list view is a text alternative.`}
            onPointerMove={onMove} onPointerDown={onDown} onPointerUp={onUp} onPointerLeave={() => { hover.current = null; drag.current = null; dirty.current = true; setTip(null); }} onWheel={onWheel} onDoubleClick={fit} onKeyDown={onKey} />
          {tipNode && tip && <NodeTip n={tipNode} x={tip.x} y={tip.y} w={size.current.w} links={m.current.neighbours.get(tipNode.id)?.size ?? 0} />}
          {props.guide}
          <div className="u-sr" aria-live="polite">{live}</div>
        </div>
      )}
    </div>
  );
});

function NodeTip({ n, x, y, w, links }: { n: GNode; x: number; y: number; w: number; links: number }) {
  const cp = n.cp;
  return (
    <div className="nc-tip" role="tooltip" style={{ left: Math.min(x + 14, w - 230), top: y + 14 }}>
      <b>{n.label}</b><span className="u-muted">{n.kind === "counterparty" ? (cp?.holdingsOnly ? "Counterparty (holdings only)" : "Counterparty") : n.kind === "issuer" ? `Issuer · ${n.tag}` : "Risk factor"}</span>
      {cp && !cp.holdingsOnly && <dl><dt>Priority</dt><dd>{cp.priority ?? "—"}</dd><dt>Utilisation</dt><dd>{cp.utilisation === null ? "Unavailable" : `${cp.utilisation}%`}</dd><dt>Rating</dt><dd>{cp.rating ?? "Unavailable"}</dd></dl>}
      <span className="u-muted">{links} link{links === 1 ? "" : "s"}</span>
    </div>
  );
}

