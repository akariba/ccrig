import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { geoEqualEarth, geoGraticule, geoGraticule10, geoOrthographic, geoPath } from "d3-geo";
import { feature, mesh } from "topojson-client";
import {
  arcControl, cableStyle, categoryStyle, clampFlat, fitFlat, placeCallout, quadPoint, spreadOverlaps,
  type Cable, type Marker, type Phase, type Pt, type Rect, type Scene,
} from "../impactmap/model";
import { cssVar } from "../design/theme";
import { useThemeVersion } from "../ui/chartTokens";
import { arcPolyline, baseRadius, chooseProjection, globeTarget, orthoProject, pointAlong, stepCam, type ArcPoint, type GlobeCam } from "../impactmap/globe";

// The geospatial stage of the Global Event Impact Map: an interactive globe (default) or a flat Equal Earth map, drawn on a plain 2D canvas
// with real, bundled Natural Earth coastlines (no tiles, no external map service, no WebGL - so it behaves identically in the FastAPI
// deployment and on GitHub Pages, and there is no "WebGL unavailable" failure mode).
//   * every cable comes from an edge in the API graph; the arc follows the real great circle between the two real positions;
//   * a particle travels only along a documented relationship, in its STORED direction; nothing moves otherwise;
//   * glow, size and thickness encode nothing: all event markers are the same size, colour is the event's explicit category;
//   * the loop runs only while something is moving (camera, cable fades, particles) and stops on its own when idle.

export type Mode = "auto" | "globe" | "flat";
interface FlatCam { zoom: number; tx: number; ty: number }
interface Geo { land: any; coast: any; borders: any }

const IDLE_MS = 25_000;            // particles keep running this long after the last interaction, then the map rests
const PARTICLE_SPEED = 0.12;       // cycles per second
const MIN_SPREAD = 38;             // px between markers before they are fanned apart (a hairline still points at the true spot)

function buildGeo(world: any): Geo {
  const obj = { type: "GeometryCollection", geometries: world.objects.countries.geometries.filter((g: any) => String(g.id) !== "010") }; // not Antarctica
  return { land: feature(world, obj as any), coast: mesh(world, obj as any, (a: any, b: any) => a === b), borders: mesh(world, obj as any, (a: any, b: any) => a !== b) };
}

/** Map colours come from the shared tokens (dark and light), read when the base layer is drawn. */
function mapColors() {
  const v = (n: string, f: string) => cssVar(n, f);
  return { sea1: v("--map-sea-1", "#143247"), sea2: v("--map-sea-2", "#0a1c2c"), sea3: v("--map-sea-3", "#050d16"), land: v("--map-land", "#173f56"), coast: v("--map-coast", "rgba(120,215,235,0.55)"),
    border: v("--map-border", "rgba(140,200,235,0.16)"), grat: v("--map-graticule", "rgba(110,175,215,0.075)"), limb: v("--map-limb", "rgba(2,6,12,0.78)"), accent: v("--accent", "#4CC9E0"), dark: document.documentElement.dataset.theme === "dark" || (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches) };
}
const shade = (hex: string, amt: number) => { const m = /^#([0-9a-f]{6})$/i.exec(hex); if (!m) return hex; const n = parseInt(m[1], 16); const c = (sh: number) => Math.max(0, Math.min(255, Math.round(((n >> sh) & 255) + amt))); return `rgb(${c(16)},${c(8)},${c(0)})`; };

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(() => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const mq = matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

const flatScale = (w: number, h: number) => Math.min(w / 5.4132, h / 2.6346);          // Equal Earth is 2 x 2.7066 by 2 x 1.3173 at scale 1
const worldSize = (w: number, h: number): [number, number] => [5.4132 * flatScale(w, h), 2.6346 * flatScale(w, h)];
const flatProjection = (w: number, h: number, f: FlatCam) => geoEqualEarth().scale(flatScale(w, h) * f.zoom).translate([(w / 2) * f.zoom + f.tx, (h / 2) * f.zoom + f.ty]);

interface Props {
  scene: Scene; phase: Phase; selectedEventId: string | null; selectedEntityId: string | null; hoverEventId: string | null;
  mode: Mode; animate: boolean; canInvestigate: boolean;
  onOverview: () => void; onInvestigate: () => void;
  onMode: (m: Mode) => void; onAnimate: (on: boolean) => void;
  onSelectEvent: (id: string | null) => void; onSelectEntity: (id: string) => void; onHoverEvent: (id: string | null) => void;
  /** compact: the embedded map (Today, Counterparty). Same stage, fewer controls: projection and animation stay, the legend and the overview/zoom chrome go. */
  variant?: "full" | "compact";
}

export function GeoStage(props: Props) {
  const { scene, phase, selectedEventId, selectedEntityId, hoverEventId, mode: setting, animate, canInvestigate, onOverview, onInvestigate, onMode, onAnimate, onSelectEvent, onSelectEntity, onHoverEvent } = props;
  const compact = props.variant === "compact", themeKey = useThemeVersion();
  const wrap = useRef<HTMLDivElement>(null), canvasRef = useRef<HTMLCanvasElement>(null), els = useRef(new Map<string, HTMLElement>());
  const [size, setSize] = useState({ w: 900, h: 600 });
  const [geo110, setGeo110] = useState<Geo | null>(null), [geo50, setGeo50] = useState<Geo | null>(null);
  const [unsupported, setUnsupported] = useState(false);
  const [calloutSide, setCalloutSide] = useState<"above" | "below" | "right" | "left">("above");
  const [hiddenCount, setHiddenCount] = useState(0);
  const [, setTick] = useState(0);                       // re-render when the camera target changes (for data-zoom)
  const reduced = usePrefersReducedMotion();
  const investigating = selectedEventId !== null;

  // what the camera frames: the selected event with the companies it is connected to, or - in the overview - every event and company
  const related = useMemo(() => {
    const ids = new Set<string>();
    if (!selectedEventId) return ids;
    for (const m of scene.markers) if (m.kind === "event" && m.eventId === selectedEventId) ids.add(m.id);
    for (const cb of scene.cables) if (cb.eventIds.includes(selectedEventId)) { ids.add(cb.from); ids.add(cb.to); }
    return ids;
  }, [scene, selectedEventId]);

  const framed = useMemo(() => scene.markers.filter((m) => (related.size > 0 ? related.has(m.id) : m.kind !== "region")).map((m) => [m.lon, m.lat] as [number, number]), [scene, related]);
  // "auto" picks the globe when everything framed lies within one readable hemisphere, otherwise the flat map (never a confusing pole-centred globe)
  const mode: "globe" | "flat" = setting === "auto" ? chooseProjection(framed) : setting;
  const documentedEnds = useMemo(() => new Set(scene.cables.filter((c) => c.type === "DOCUMENTED_RELATION").flatMap((c) => [c.from, c.to])), [scene]);

  // the loop reads the latest props through a ref, so it never works from a stale render
  const P = useRef({ scene, phase, selectedEventId, hoverEventId, mode, animate, reduced, size, geo110, geo50, related });
  P.current = { scene, phase, selectedEventId, hoverEventId, mode, animate, reduced, size, geo110, geo50, related };
  const S = useRef({
    cam: null as GlobeCam | null, camT: null as GlobeCam | null, flat: { zoom: 1, tx: 0, ty: 0 } as FlatCam, flatT: { zoom: 1, tx: 0, ty: 0 } as FlatCam,
    offsets: {} as Record<string, Pt>, alphas: new Map<string, number>(), raf: 0, last: 0, lastDraw: 0, lastInteract: 0, moving: false, baseKey: "",
    inView: true, drag: null as null | { x: number; y: number }, base: null as HTMLCanvasElement | null, dpr: 1,
  });

  // ------------------------------------------------------------------ geography assets (lazy; the coarse set paints first)
  useEffect(() => {
    let off = false;
    import("world-atlas/countries-110m.json").then((m) => { if (!off) { setGeo110(buildGeo((m as any).default ?? m)); S.current.baseKey = ""; } });
    import("world-atlas/countries-50m.json").then((m) => { if (!off) { setGeo50(buildGeo((m as any).default ?? m)); S.current.baseKey = ""; } });
    return () => { off = true; };
  }, []);

  // ------------------------------------------------------------------ size
  useEffect(() => {
    const el = wrap.current; if (!el) return;
    const measure = () => setSize({ w: Math.max(300, Math.round(el.clientWidth)), h: Math.max(300, Math.round(el.clientHeight)) });
    const ro = new ResizeObserver(measure); ro.observe(el); measure();
    const io = new IntersectionObserver(([e]) => { S.current.inView = e.isIntersecting; if (e.isIntersecting) schedule(); });
    io.observe(el);
    const vis = () => { if (!document.hidden) schedule(); };
    document.addEventListener("visibilitychange", vis);
    return () => { ro.disconnect(); io.disconnect(); document.removeEventListener("visibilitychange", vis); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const c = canvasRef.current; if (!c) return;
    if (!c.getContext("2d")) { setUnsupported(true); return; }
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    S.current.dpr = dpr;
    c.width = Math.round(size.w * dpr); c.height = Math.round(size.h * dpr);
    S.current.base = null; S.current.baseKey = "";
    schedule();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size]);

  // ------------------------------------------------------------------ projection helpers (current camera)
  const projectAt = (m: "globe" | "flat", w: number, h: number, g: GlobeCam, f: FlatCam, lon: number, lat: number, lift = 0) => {
    // "visible" = on the near side and not far outside the stage; a marker near the edge is drawn clamped inside it (with a hairline to its true spot)
    const edge = -40, inside = (x: number, y: number) => x >= edge && x <= w - edge && y >= edge && y <= h - edge;
    if (m === "globe") { const q = orthoProject(lon, lat, lift, g, w / 2, h / 2); return { ...q, visible: q.visible && inside(q.x, q.y) }; }
    const [x, y] = flatProjection(w, h, f)([lon, lat]) ?? [-9999, -9999];
    return { x, y, z: 1, visible: inside(x, y) };
  };

  // ------------------------------------------------------------------ camera targets, marker fan-out and callout placement
  // A marker tied to the selected event is always drawn (clamped inside the stage if need be). Any other marker is drawn only where it really is,
  // so the edges never pile up with stranded, unrelated markers.
  const showable = (rel: Set<string>, m: Marker, q: { x: number; y: number; visible: boolean }, w: number, h: number) =>
    q.visible && (rel.size === 0 || rel.has(m.id) || (q.x >= 0 && q.x <= w && q.y >= 0 && q.y <= h));

  const frameSelection = useCallback(() => {
    const { scene, mode, size } = P.current, s = S.current, { w, h } = size;
    const lonlat = framed;
    s.camT = globeTarget(lonlat, w, h);
    const base = flatProjection(w, h, { zoom: 1, tx: 0, ty: 0 });
    s.flatT = lonlat.length === 0 || related.size === 0 ? { zoom: 1, tx: 0, ty: 0 } : fitFlat(lonlat.map((p) => (base(p) ?? [0, 0]) as Pt), w, h, worldSize(w, h)[0], worldSize(w, h)[1], Math.max(50, w * 0.1), 3.2);
    // fan out markers that would overlap, measured from where the camera is going to be (so the layout does not shuffle while it moves)
    const shown = scene.markers.filter((m) => m.kind !== "region").map((m) => ({ m, q: projectAt(mode, w, h, s.camT!, s.flatT, m.lon, m.lat) })).filter((x) => showable(related, x.m, x.q, w, h));
    const priority = (m: Marker) => (m.kind === "event" ? (m.eventId === P.current.selectedEventId ? 4 : 3) : m.role === "TARGET" ? 3 : related.has(m.id) ? 2 : 0);   // events and the hub keep their true spot
    const spread = spreadOverlaps(shown.map(({ m, q }) => ({ id: m.id, pt: [q.x, q.y] as Pt, priority: priority(m) })), w < 600 ? MIN_SPREAD - 2 : MIN_SPREAD, { w, h, edge: 18 });
    s.offsets = Object.fromEntries(shown.map(({ m, q }) => [m.id, [spread[m.id][0] - q.x, spread[m.id][1] - q.y] as Pt]));
    setHiddenCount(scene.markers.filter((m) => m.kind !== "region").length - shown.length);
    const sel = shown.find(({ m }) => m.kind === "event" && m.eventId === P.current.selectedEventId);
    if (sel) {
      const boxes: Rect[] = shown.filter((x) => x !== sel).map(({ m }) => {
        const [x, y] = spread[m.id], dim = m.kind === "entity" && related.size > 0 && !related.has(m.id);
        const hub = m.kind === "entity" && m.role === "TARGET", bw = m.kind === "event" ? 30 : hub ? 46 : dim ? 12 : 50, bh = m.kind === "event" ? 30 : hub ? 46 : dim ? 12 : 22;
        return { x: x - bw / 2, y: y - bh / 2, w: bw, h: bh };
      });
      setCalloutSide(placeCallout(spread[sel.m.id], w < 600 ? { w: 184, h: 22 } : { w: 230, h: 70 }, boxes, { w, h }, w < 600 ? 14 : 13, w < 600 ? 6 : 14));
    }
    if (!s.cam || P.current.reduced) { s.cam = { ...s.camT }; s.flat = { ...s.flatT }; }
    s.lastInteract = performance.now();
    setTick((t) => t + 1);
    schedule();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [related, framed]);

  useEffect(() => { frameSelection(); }, [frameSelection, scene, mode, size, framed]);

  // ------------------------------------------------------------------ drawing
  function drawBase(ctx: CanvasRenderingContext2D, w: number, h: number, g: GlobeCam, f: FlatCam, m: "globe" | "flat", geo: Geo | null) {
    ctx.clearRect(0, 0, w, h);
    const C = mapColors();
    const proj: any = m === "globe" ? geoOrthographic().rotate([-g.lon, -g.lat]).scale(g.k).translate([w / 2, h / 2]).clipAngle(90).precision(0.6) : flatProjection(w, h, f).precision(0.6);
    const trace = (obj: any) => { const p = new Path2D(); geoPath(proj, p as any)(obj); return p; };
    if (m === "globe") {
      const cx = w / 2, cy = h / 2, k = g.k;
      const glow = ctx.createRadialGradient(cx, cy, k * 0.98, cx, cy, k * 1.28);
      glow.addColorStop(0, C.dark ? "rgba(80,170,235,0.30)" : "rgba(30,120,170,0.22)"); glow.addColorStop(0.35, C.dark ? "rgba(60,140,210,0.10)" : "rgba(30,120,170,0.07)"); glow.addColorStop(1, "rgba(40,100,180,0)");
      ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(cx, cy, k * 1.28, 0, Math.PI * 2); ctx.fill();
      const sea = ctx.createRadialGradient(cx - k * 0.35, cy - k * 0.4, k * 0.1, cx, cy, k * 1.02);
      sea.addColorStop(0, C.sea1); sea.addColorStop(0.6, C.sea2); sea.addColorStop(1, C.sea3);
      ctx.fillStyle = sea; ctx.beginPath(); ctx.arc(cx, cy, k, 0, Math.PI * 2); ctx.fill();
    } else {
      const sea = ctx.createLinearGradient(0, 0, 0, h);
      sea.addColorStop(0, C.sea1); sea.addColorStop(1, C.sea3);
      ctx.fillStyle = sea; ctx.beginPath(); ctx.rect(0, 0, w, h); ctx.fill();
    }
    ctx.lineWidth = 0.6; ctx.strokeStyle = C.grat; ctx.stroke(trace(geoGraticule10()));
    ctx.lineWidth = 0.8; ctx.strokeStyle = C.grat; ctx.stroke(trace(geoGraticule().step([30, 30]).lines().reduce((acc: any, l: any) => ({ type: "MultiLineString", coordinates: [...(acc.coordinates ?? []), ...l.coordinates] }), {})));
    if (geo) {
      const land = trace(geo.land);
      ctx.save(); ctx.translate(1.6, 2.6); ctx.fillStyle = C.dark ? "rgba(0,0,0,0.5)" : "rgba(20,60,85,0.18)"; ctx.fill(land); ctx.restore();   // raised-land shadow: light from the upper left
      const lit = m === "globe"
        ? (() => { const gr = ctx.createRadialGradient(w / 2 - g.k * 0.4, h / 2 - g.k * 0.45, g.k * 0.05, w / 2, h / 2, g.k * 1.05); gr.addColorStop(0, shade(C.land, C.dark ? 40 : 6)); gr.addColorStop(0.55, C.land); gr.addColorStop(1, shade(C.land, C.dark ? -24 : -18)); return gr; })()
        : C.land;
      ctx.fillStyle = lit; ctx.fill(land);
      ctx.lineWidth = 0.5; ctx.strokeStyle = C.border; ctx.stroke(trace(geo.borders));
      ctx.lineWidth = 1; ctx.strokeStyle = C.coast; ctx.stroke(trace(geo.coast));
    }
    if (m === "globe") {                       // limb darkening and rim light give the sphere its depth
      const cx = w / 2, cy = h / 2, k = g.k;
      const limb = ctx.createRadialGradient(cx, cy, k * 0.55, cx, cy, k);
      limb.addColorStop(0, "rgba(2,6,12,0)"); limb.addColorStop(0.8, C.dark ? "rgba(2,6,12,0.28)" : "rgba(20,60,85,0.10)"); limb.addColorStop(1, C.limb);
      ctx.fillStyle = limb; ctx.beginPath(); ctx.arc(cx, cy, k, 0, Math.PI * 2); ctx.fill();
      ctx.lineWidth = 1.4; ctx.strokeStyle = C.coast; ctx.beginPath(); ctx.arc(cx, cy, k, 0, Math.PI * 2); ctx.stroke();
    }
  }

  const display = useRef<Record<string, { x: number; y: number; ax: number; ay: number; visible: boolean }>>({});

  function polyline(cable: Cable, byId: Map<string, Marker>, m: "globe" | "flat", w: number, h: number, g: GlobeCam, f: FlatCam): ArcPoint[] | null {
    const a = byId.get(cable.from), b = byId.get(cable.to); if (!a || !b) return null;
    if (m === "globe") return arcPolyline([a.lon, a.lat], [b.lon, b.lat], g, w / 2, h / 2, 56);
    const pa = projectAt("flat", w, h, g, f, a.lon, a.lat), pb = projectAt("flat", w, h, g, f, b.lon, b.lat);
    const c = arcControl([pa.x, pa.y], [pb.x, pb.y]);
    return Array.from({ length: 57 }, (_, i) => { const [x, y] = quadPoint([pa.x, pa.y], c, [pb.x, pb.y], i / 56); return { x, y, visible: x > -20 && x < w + 20 && y > -20 && y < h + 20 }; });
  }

  function frame(now: number) {
    const s = S.current, p = P.current, c = canvasRef.current; s.raf = 0;
    if (!c || !s.cam || !s.camT) return;
    const ctx = c.getContext("2d"); if (!ctx) return;
    const { w, h } = p.size, dt = s.last ? Math.min(0.1, (now - s.last) / 1000) : 1 / 60; s.last = now;
    let animating = false;

    if (p.reduced) { s.cam = { ...s.camT }; s.flat = { ...s.flatT }; }
    else {
      const g = stepCam(s.cam, s.camT, dt); s.cam = g.cam;
      const k = 1 - Math.exp(-5.5 * dt);
      const f = { zoom: s.flat.zoom + (s.flatT.zoom - s.flat.zoom) * k, tx: s.flat.tx + (s.flatT.tx - s.flat.tx) * k, ty: s.flat.ty + (s.flatT.ty - s.flat.ty) * k };
      const fs = Math.abs(f.zoom - s.flatT.zoom) < 0.002 && Math.abs(f.tx - s.flatT.tx) < 0.2 && Math.abs(f.ty - s.flatT.ty) < 0.2;
      s.flat = fs ? { ...s.flatT } : f;
      animating = p.mode === "globe" ? !g.settled : !fs;
    }
    s.moving = animating;

    // marker positions for this frame
    const byId = new Map(p.scene.markers.map((m) => [m.id, m] as const));
    const disp: typeof display.current = {};
    for (const m of p.scene.markers) {
      const q = projectAt(p.mode, w, h, s.cam, s.flat, m.lon, m.lat);
      const [ox, oy] = s.offsets[m.id] ?? [0, 0];
      const dx = Math.min(w - 18, Math.max(18, q.x + ox)), dy = Math.min(h - 18, Math.max(18, q.y + oy));       // drawn inside the stage, hairline to the true spot
      disp[m.id] = { x: dx, y: dy, ax: q.x, ay: q.y, visible: showable(p.related, m, q, w, h) };
      const el = els.current.get(m.id);
      if (el) {
        el.style.transform = `translate(${dx.toFixed(1)}px, ${dy.toFixed(1)}px)`;
        el.style.visibility = disp[m.id].visible && (m.kind !== "region" || (p.phase === "ready" && p.selectedEventId !== null)) ? "visible" : "hidden";
        el.style.setProperty("--depth", p.mode === "globe" ? String(Math.max(0.35, Math.min(1, q.z * 2.6 + 0.4))) : "1");
      }
    }
    display.current = disp;

    // static layers (sphere, graticule, coastlines) are re-drawn only when the camera or assets changed
    const lod = !s.moving && p.geo50 ? "50" : p.geo110 ? "110" : "-";
    const key = `${themeKey}|${p.mode}|${w}x${h}|${lod}|${p.mode === "globe" ? `${s.cam.lon.toFixed(2)},${s.cam.lat.toFixed(2)},${s.cam.k.toFixed(1)}` : `${s.flat.zoom.toFixed(3)},${s.flat.tx.toFixed(1)},${s.flat.ty.toFixed(1)}`}`;
    if (key !== s.baseKey) {
      if (!s.base) { s.base = document.createElement("canvas"); s.base.width = c.width; s.base.height = c.height; }
      const bctx = s.base.getContext("2d")!;
      bctx.setTransform(s.dpr, 0, 0, s.dpr, 0, 0);
      drawBase(bctx, w, h, s.cam, s.flat, p.mode, lod === "50" ? p.geo50 : p.geo110);
      s.baseKey = key;
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, c.width, c.height); ctx.drawImage(s.base!, 0, 0);
    ctx.setTransform(s.dpr, 0, 0, s.dpr, 0, 0);

    // crisp geographic anchor under every event marker: the exact position the event is evidenced at
    for (const m of p.scene.markers) {
      if (m.kind !== "event") continue;
      const d = disp[m.id]; if (!d || !d.visible) continue;
      ctx.beginPath(); ctx.arc(d.ax, d.ay, 3.4, 0, Math.PI * 2); ctx.fillStyle = categoryStyle(m.category).color; ctx.fill();
      ctx.lineWidth = 1; ctx.strokeStyle = "rgba(255,255,255,0.85)"; ctx.stroke();
    }
    // hairlines from fanned-out markers back to their true positions
    ctx.lineWidth = 0.8; ctx.strokeStyle = "rgba(200,215,230,0.4)"; ctx.fillStyle = "rgba(220,230,240,0.7)";
    for (const m of p.scene.markers) {
      const d = disp[m.id]; if (!d || !d.visible || Math.hypot(d.x - d.ax, d.y - d.ay) < 5) continue;
      ctx.beginPath(); ctx.moveTo(d.ax, d.ay); ctx.lineTo(d.x, d.y); ctx.stroke(); ctx.beginPath(); ctx.arc(d.ax, d.ay, 1.8, 0, Math.PI * 2); ctx.fill();
    }

    // cables: fade in/out, quiet context, bright selected paths, particles only on documented relationships
    let fading = false, hasParticles = false;
    const styled = p.scene.cables.map((cable) => {
      const st = cableStyle(cable, { phase: p.phase, selectedEventId: p.selectedEventId, reducedMotion: p.reduced || !p.animate, hoverEventId: p.hoverEventId });
      const target = st.draw ? st.alpha : 0, cur = s.alphas.get(cable.id) ?? 0;
      let next = p.reduced ? target : cur + (target - cur) * Math.min(1, dt * 7);
      if (Math.abs(next - target) <= 0.01) next = target; else fading = true;
      s.alphas.set(cable.id, next);
      return { cable, st, a: next };
    }).filter((x) => x.a > 0.01).sort((x, y) => x.a - y.a);
    for (const { cable, st, a } of styled) {
      const poly = polyline(cable, byId, p.mode, w, h, s.cam, s.flat); if (!poly) continue;
      const first = poly.find((q) => q.visible), last = [...poly].reverse().find((q) => q.visible); if (!first || !last) continue;
      const grad = ctx.createLinearGradient(poly[0].x, poly[0].y, poly[poly.length - 1].x, poly[poly.length - 1].y);
      grad.addColorStop(0, `hsla(${st.hueFrom},85%,62%,${a})`); grad.addColorStop(1, `hsla(${st.hueTo},85%,68%,${a})`);
      const stroke = (width: number, style: string | CanvasGradient, alpha = 1, dash: number[] = []) => {
        ctx.save(); ctx.globalAlpha = alpha; ctx.lineWidth = width; ctx.strokeStyle = style; ctx.setLineDash(dash); ctx.lineCap = "round"; ctx.lineJoin = "round";
        ctx.beginPath(); let pen = false;
        for (const q of poly) { if (!q.visible) { pen = false; continue; } if (pen) ctx.lineTo(q.x, q.y); else { ctx.moveTo(q.x, q.y); pen = true; } }
        ctx.stroke(); ctx.restore();
      };
      if (st.glow) {                                               // soft halo (lighter blending) under a bright core
        ctx.save(); ctx.globalCompositeOperation = "lighter";
        stroke(st.width + 12, `hsla(${st.hueTo},90%,60%,1)`, 0.05 * a); stroke(st.width + 6, `hsla(${st.hueTo},90%,62%,1)`, 0.11 * a);
        ctx.restore();
      }
      stroke(st.width, grad, 1, st.dash ?? []);
      if (st.glow && st.kind === "documented") stroke(0.8, "rgba(235,250,255,1)", 0.55 * a);
      if (st.kind === "documented" && a >= 0.25) {                  // arrowhead: the stored direction (source -> target)
        const at = pointAlong(poly, 0.9);
        if (at) {
          ctx.save(); ctx.translate(at.x, at.y); ctx.rotate(at.angle); ctx.fillStyle = `hsla(${st.hueTo},90%,75%,${a})`;
          ctx.beginPath(); ctx.moveTo(6, 0); ctx.lineTo(-4, -4); ctx.lineTo(-4, 4); ctx.closePath(); ctx.fill(); ctx.restore();
        }
      }
      if (st.pulses > 0) {
        hasParticles = true;
        for (let i = 0; i < st.pulses; i++) {
          const t = ((now / 1000) * PARTICLE_SPEED + i / st.pulses) % 1, at = pointAlong(poly, t); if (!at) continue;
          const tail = pointAlong(poly, Math.max(0, t - 0.035));
          if (tail) { ctx.save(); ctx.lineCap = "round"; ctx.lineWidth = 2; ctx.strokeStyle = `hsla(${st.hueTo},100%,85%,${0.45 * a})`; ctx.beginPath(); ctx.moveTo(tail.x, tail.y); ctx.lineTo(at.x, at.y); ctx.stroke(); ctx.restore(); }
          ctx.fillStyle = `hsla(${st.hueTo},100%,92%,${a})`; ctx.shadowColor = `hsla(${st.hueTo},100%,70%,1)`; ctx.shadowBlur = 8;
          ctx.beginPath(); ctx.arc(at.x, at.y, 2.3, 0, Math.PI * 2); ctx.fill(); ctx.shadowBlur = 0;
        }
      }
    }

    const running = hasParticles && p.animate && !p.reduced && !document.hidden && s.inView && now - s.lastInteract < IDLE_MS;
    if (wrap.current) { wrap.current.dataset.animating = String(animating || fading || running); }
    if (animating || fading || running) s.raf = requestAnimationFrame(frame);
    else s.last = 0;
  }

  function schedule() {
    const s = S.current;
    if (!s.raf && s.cam && s.camT) s.raf = requestAnimationFrame(frame);
  }
  useEffect(() => () => { cancelAnimationFrame(S.current.raf); S.current.raf = 0; }, []);   // (reset: React StrictMode runs this once before the real mount)
  useEffect(() => { S.current.lastInteract = performance.now(); S.current.baseKey = ""; schedule(); },     // eslint-disable-next-line react-hooks/exhaustive-deps
    [selectedEventId, hoverEventId, mode, animate, reduced, phase, scene, geo110, geo50, themeKey]);

  // ------------------------------------------------------------------ user camera control
  const touch = () => { S.current.lastInteract = performance.now(); schedule(); };
  const onPointerDown = (e: React.PointerEvent) => {
    if (mode !== "globe" || (e.target as HTMLElement).closest("button, summary, details")) return;
    S.current.drag = { x: e.clientX, y: e.clientY }; (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); touch();
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const s = S.current; if (!s.drag || !s.cam) return;
    const k0 = baseRadius(size.w, size.h), scale = 0.25 * (k0 / s.cam.k);
    const lon = s.cam.lon - (e.clientX - s.drag.x) * scale, lat = Math.max(-70, Math.min(70, s.cam.lat + (e.clientY - s.drag.y) * scale));
    s.drag = { x: e.clientX, y: e.clientY }; s.cam = { ...s.cam, lon, lat }; s.camT = { ...s.cam };
    touch();
  };
  const onPointerUp = () => { S.current.drag = null; };
  const zoomBy = (factor: number) => {
    const s = S.current, { w, h } = size; if (!s.camT) return;
    if (mode === "globe") { const k0 = baseRadius(w, h); s.camT = { ...s.camT, k: Math.max(k0 * 0.8, Math.min(k0 * 5, s.camT.k * factor)) }; }
    else {
      const z = Math.max(1, Math.min(6, s.flatT.zoom * factor)), wx = (w / 2 - s.flatT.tx) / s.flatT.zoom, wy = (h / 2 - s.flatT.ty) / s.flatT.zoom;
      s.flatT = clampFlat({ zoom: z, tx: w / 2 - wx * z, ty: h / 2 - wy * z }, w, h, worldSize(w, h)[0], worldSize(w, h)[1]);
    }
    setTick((t) => t + 1);
    touch();
  };

  // ------------------------------------------------------------------ markup
  const eventMarkers = scene.markers.filter((m) => m.kind === "event");
  const categories = [...new Set(eventMarkers.map((m) => m.category ?? ""))].filter(Boolean);
  const dimmed = (m: Marker) => investigating ? !related.has(m.id) : m.kind === "entity" && m.role !== "TARGET" && !documentedEnds.has(m.id);
  const ref = (id: string) => (el: HTMLElement | null) => { if (el) els.current.set(id, el); else els.current.delete(id); };
  const k0 = baseRadius(size.w, size.h), zoomNow = mode === "globe" ? (S.current.camT?.k ?? k0) / k0 : S.current.flatT.zoom;

  return (
    <div
      ref={wrap} className={`gs-stage ${mode}`} data-testid="impact-map" data-phase={phase} data-projection={mode} data-view={investigating ? "investigation" : "overview"} data-projection-setting={setting} data-zoom={zoomNow.toFixed(2)}
      data-cables={scene.cables.length} data-animated={String(animate && !reduced && phase === "ready")} role="group" aria-busy={phase === "loading"}
      aria-label={`World map: ${eventMarkers.length} event${eventMarkers.length === 1 ? "" : "s"}, ${scene.cables.length} connections`}
      onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp}
    >
      <canvas ref={canvasRef} className="gs-canvas" aria-hidden="true" style={{ width: size.w, height: size.h }} />
      {!unsupported && phase === "ready" && scene.markers.map((m) => {
        const cat = categoryStyle(m.category);
        if (m.kind === "event") {
          const selected = m.eventId === selectedEventId, hovered = m.eventId === hoverEventId, wide = size.w >= 600;
          return (
            <button
              key={m.id} ref={ref(m.id) as any} type="button" style={{ ["--cat" as string]: cat.color, ["--dim" as string]: dimmed(m) ? 0.5 : 1 }}
              className={`gs-marker event${selected ? " selected" : ""}${hovered ? " hover" : ""}`} data-testid="event-marker" data-event-id={m.eventId} data-category={m.category} aria-pressed={selected}
              aria-label={`Event ${m.rank}: ${m.label}. ${cat.label}. Event location: ${m.place}, ${m.precision}. Press to ${selected ? "deselect" : "select"}.`}
              title={`${m.rank}. ${m.label}`} onClick={() => onSelectEvent(selected ? null : (m.eventId as string))}
              onMouseEnter={() => onHoverEvent(m.eventId as string)} onMouseLeave={() => onHoverEvent(null)} onFocus={() => onHoverEvent(m.eventId as string)} onBlur={() => onHoverEvent(null)}
              onKeyDown={(e) => { if (e.key === "Escape") onSelectEvent(null); }}
            >
              <span className="n">{m.rank}</span>
              {selected && wide && <span className={`callout ${calloutSide}`} aria-hidden="true"><i>{cat.label}</i><b>{m.place}</b><span>{m.label}</span></span>}
              {((hovered && !(selected && wide)) || (selected && !wide)) && <span className={`tag ${calloutSide}`} aria-hidden="true">{m.place}</span>}
            </button>
          );
        }
        if (m.kind === "entity") {
          const target = m.role === "TARGET", selected = m.entityId === selectedEntityId, dim = dimmed(m);
          return (
            <button
              key={m.id} ref={ref(m.id) as any} type="button" style={{ ["--dim" as string]: dim ? 0.55 : 1 }}
              className={`gs-marker entity${target ? " target" : ""}${selected ? " selected" : ""}${dim ? " dim" : ""}`} data-testid="entity-marker" data-entity-id={m.entityId} aria-pressed={selected}
              aria-label={`${m.label}${target ? " (searched company)" : ""}, shown at its headquarters country (${m.precision}), not at a facility`}
              title={`${m.label} - headquarters country, approximate`} onClick={() => onSelectEntity(m.entityId as string)}
            ><span className="txt">{m.ticker ?? m.entityId}</span></button>
          );
        }
        if (!investigating) return null;      // countries named in the evidence belong to a selected event; the overview does not draw them
        return <span key={m.id} ref={ref(m.id)} style={{ ["--dim" as string]: dimmed(m) ? 0.35 : 1 }} className="gs-marker region" data-testid="region-marker" role="img" aria-label={`Country named in the evidence: ${m.label}`} title={`${m.label} (named in the evidence; country centroid)`} />;
      })}

      {phase === "loading" && <div className="gs-overlay" data-testid="impact-loading" role="status"><span className="spinner" />Loading verified events…</div>}
      {(phase === "empty" || phase === "error") && <div className="gs-overlay quiet" role="status">{phase === "error" ? "Events could not be loaded." : "No verified events to show for this search."}</div>}
      {unsupported && <div className="gs-overlay quiet" role="status">The map cannot be drawn in this browser. The event list and evidence panel still work.</div>}

      <div className="gs-controls" role="toolbar" aria-label="Map controls">
        {!compact && <div className="seg" role="group" aria-label="View">
          <button type="button" aria-pressed={!investigating} onClick={onOverview}>Overview</button>
          <button type="button" aria-pressed={investigating} disabled={!canInvestigate} onClick={onInvestigate}>Investigation</button>
        </div>}
        <div className="seg" role="group" aria-label="Projection">
          <button type="button" aria-pressed={setting === "auto"} onClick={() => onMode("auto")} title="Globe when everything in view fits one hemisphere, otherwise the flat map">Auto</button>
          <button type="button" aria-pressed={setting === "globe"} onClick={() => onMode("globe")}>Globe</button>
          <button type="button" aria-pressed={setting === "flat"} onClick={() => onMode("flat")}>Flat</button>
        </div>
        {!compact && <>
          <button type="button" aria-label="Zoom in" onClick={() => zoomBy(1.35)}>+</button>
          <button type="button" aria-label="Zoom out" onClick={() => zoomBy(1 / 1.35)}>−</button>
          <button type="button" onClick={() => { frameSelection(); }} title="Re-centre on the selected event and its companies">Frame</button>
        </>}
        <button type="button" aria-pressed={animate && !reduced} disabled={reduced} onClick={() => onAnimate(!animate)} title={reduced ? "Your system asks for reduced motion" : "Particles on documented relationships and camera glides"}>
          {reduced ? "Motion off" : animate ? "Animation on" : "Animation off"}
        </button>
      </div>
      {hiddenCount > 0 && phase === "ready" && <div className="gs-note" data-testid="hidden-note">{hiddenCount} marker{hiddenCount === 1 ? " is" : "s are"} {mode === "globe" ? "on the far side of the globe" : "out of frame"}; use the list{mode === "globe" ? ", drag the globe or switch to Flat" : " or Frame"}.</div>}

      {!compact && <details className="gs-legend" aria-label="Legend" open={size.w >= 900}>
        <summary>Legend</summary>
        <ul>
          {categories.map((c) => <li key={c}><i className="ring" style={{ ["--cat" as string]: categoryStyle(c).color }} />{categoryStyle(c).label}</li>)}
          <li><i className="hq" />Company at its headquarters country (approximate; not a facility)</li>
          <li><i className="doc" />Documented relationship; arrow and particles follow its stored direction</li>
          <li><i className="mention" />Event names the company</li>
          <li><i className="region" />Country named in the evidence</li>
          <li className="muted">Event markers are all one size: no impact is estimated.</li>
        </ul>
      </details>}
    </div>
  );
}
