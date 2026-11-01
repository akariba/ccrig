import { useEffect, useMemo, useRef, useState } from "react";
import { feature } from "topojson-client";
import {
  arcControl, cableStyle, fitView, makeView, quadPoint, spreadOverlaps,
  type Marker, type Phase, type Pt, type Scene,
} from "../impactmap/model";

// World map with animated cables, driven entirely by real state:
//  * land / graticule: bundled Natural Earth geometry (offline, works in the static build);
//  * cables: one per edge in the API's graph. Colour says what the link IS (documented relationship / mention / region).
//    A pulse travels ONLY along a documented relationship, in the stored direction of that relationship (source -> target).
//    Nothing is drawn while loading, empty or in error; with reduced motion there are no pulses.
//  * markers: real, focusable buttons positioned over the canvas (so they are keyboard- and screen-reader-accessible).
// The cable technique (gradient bezier strokes, travelling pulses, glow on the selected routes) is adapted from the supplied
// "Neural Cable Graph", with its random colours, jitter and invented readouts removed.

const OCEAN = "#060d12", LAND = "#112029", BORDER = "#1f3b49", GRID = "#0e1a22", PULSE_SPEED = 0.16; // cycles per second

type Feature = { geometry: { type: string; coordinates: any } };

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

export function ImpactMapCanvas(props: {
  scene: Scene; phase: Phase; selectedEventId: string | null; selectedEntityId: string | null; hoverEventId: string | null;
  onSelectEvent: (id: string | null) => void; onSelectEntity: (id: string) => void; onHoverEvent: (id: string | null) => void;
}) {
  const { scene, phase, selectedEventId, selectedEntityId, hoverEventId, onSelectEvent, onSelectEntity, onHoverEvent } = props;
  const wrap = useRef<HTMLDivElement>(null), landRef = useRef<HTMLCanvasElement>(null), cableRef = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(900);
  const [land, setLand] = useState<Feature[] | null>(null);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    if (!wrap.current) return;
    const ro = new ResizeObserver(() => wrap.current && setWidth(Math.max(320, Math.round(wrap.current.clientWidth))));
    ro.observe(wrap.current);
    setWidth(Math.max(320, Math.round(wrap.current.clientWidth)));
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    import("world-atlas/countries-110m.json").then((mod) => {
      const world: any = (mod as any).default ?? mod;
      const fc: any = feature(world, world.objects.countries);
      if (!cancelled) setLand(fc.features.filter((f: any) => String(f.id) !== "010")); // not Antarctica
    });
    return () => { cancelled = true; };
  }, []);

  const view = useMemo(() => makeView(width), [width]);
  const positions = useMemo(
    () => spreadOverlaps(scene.markers.map((m) => ({ id: m.id, pt: view.project(m.lon, m.lat) as Pt })), 30),
    [scene, view],
  );

  // Everything connected to the selected event: its own marker plus the far end of each of its cables.
  const relatedIds = useMemo(() => {
    const ids = new Set<string>();
    if (!selectedEventId) return ids;
    for (const m of scene.markers) if (m.kind === "event" && m.eventId === selectedEventId) ids.add(m.id);
    for (const cb of scene.cables) if (cb.eventIds.includes(selectedEventId)) { ids.add(cb.from); ids.add(cb.to); }
    return ids;
  }, [scene, selectedEventId]);

  // Camera: frame the selected event's markers (never below "whole world"); the user can step back out.
  const [wholeMap, setWholeMap] = useState(false);
  useEffect(() => setWholeMap(false), [selectedEventId]);
  const camera = useMemo(() => {
    if (wholeMap || !selectedEventId) return { zoom: 1, tx: 0, ty: 0 };
    const pts = [...relatedIds].map((id) => positions[id]).filter(Boolean);
    return fitView(pts, view.width, view.height, Math.max(40, view.width * 0.09));
  }, [wholeMap, selectedEventId, relatedIds, positions, view]);

  function sizeCanvas(c: HTMLCanvasElement) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    c.width = Math.round(view.width * dpr); c.height = Math.round(view.height * dpr);
    const ctx = c.getContext("2d")!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return ctx;
  }

  // ---- static layer: ocean, graticule, land
  useEffect(() => {
    const c = landRef.current; if (!c) return;
    const ctx = sizeCanvas(c);
    ctx.fillStyle = OCEAN; ctx.fillRect(0, 0, view.width, view.height);
    ctx.strokeStyle = GRID; ctx.lineWidth = 1;
    for (let lon = -180; lon <= 180; lon += 30) { ctx.beginPath(); for (let lat = -90; lat <= 90; lat += 3) { const [x, y] = view.project(lon, lat); if (lat === -90) ctx.moveTo(x, y); else ctx.lineTo(x, y); } ctx.stroke(); }
    for (let lat = -60; lat <= 60; lat += 30) { ctx.beginPath(); for (let lon = -180; lon <= 180; lon += 3) { const [x, y] = view.project(lon, lat); if (lon === -180) ctx.moveTo(x, y); else ctx.lineTo(x, y); } ctx.stroke(); }
    if (land) {
      ctx.fillStyle = LAND; ctx.strokeStyle = BORDER; ctx.lineWidth = 0.7;
      for (const f of land) {
        const g = f.geometry;
        const polys = g.type === "Polygon" ? [g.coordinates] : g.type === "MultiPolygon" ? g.coordinates : [];
        for (const poly of polys) {
          ctx.beginPath();
          for (const ring of poly) ring.forEach(([lon, lat]: [number, number], i: number) => { const [x, y] = view.project(lon, lat); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y); });
          ctx.fill("evenodd"); ctx.stroke();
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, land]);

  // ---- cable layer
  useEffect(() => {
    const c = cableRef.current; if (!c) return;
    const ctx = sizeCanvas(c);
    const styled = scene.cables.map((cable) => ({ cable, s: cableStyle(cable, { phase, selectedEventId, reducedMotion: reduced, hoverEventId }) })).filter((x) => x.s.draw);
    const animated = styled.some((x) => x.s.pulses > 0);
    let raf = 0;
    const geometry = (cable: { from: string; to: string }) => {
      const a = positions[cable.from], b = positions[cable.to];
      return a && b ? { a, b, c: arcControl(a, b) } : null;
    };
    const paint = (time: number) => {
      ctx.clearRect(0, 0, view.width, view.height);
      // a marker nudged apart from its neighbours stays tied to its true position by a hairline
      ctx.lineWidth = 0.8; ctx.strokeStyle = "rgba(200,210,225,0.35)"; ctx.fillStyle = "rgba(200,210,225,0.55)";
      for (const m of scene.markers) {
        const at = positions[m.id]; if (!at) continue;
        const [tx, ty] = view.project(m.lon, m.lat);
        if (Math.hypot(at[0] - tx, at[1] - ty) < 6) continue;
        ctx.beginPath(); ctx.moveTo(tx, ty); ctx.lineTo(at[0], at[1]); ctx.stroke();
        ctx.beginPath(); ctx.arc(tx, ty, 1.6, 0, Math.PI * 2); ctx.fill();
      }
      // dim cables first, active ones on top
      for (const { cable, s } of [...styled].sort((x, y) => Number(x.s.glow) - Number(y.s.glow))) {
        const g = geometry(cable); if (!g) continue;
        const grad = ctx.createLinearGradient(g.a[0], g.a[1], g.b[0], g.b[1]);
        grad.addColorStop(0, `hsla(${s.hueFrom},85%,62%,${s.alpha})`); grad.addColorStop(1, `hsla(${s.hueTo},85%,66%,${s.alpha})`);
        ctx.setLineDash(s.dash ?? []); ctx.strokeStyle = grad; ctx.lineWidth = s.width;
        ctx.beginPath(); ctx.moveTo(g.a[0], g.a[1]); ctx.quadraticCurveTo(g.c[0], g.c[1], g.b[0], g.b[1]); ctx.stroke();
        if (s.glow) { ctx.globalAlpha = 0.14; ctx.lineWidth = s.width + 6; ctx.stroke(); ctx.globalAlpha = 0.07; ctx.lineWidth = s.width + 12; ctx.stroke(); ctx.globalAlpha = 1; }
        ctx.setLineDash([]);
        if (s.kind === "documented" && s.alpha >= 0.25) {   // arrowhead: the stored direction of the relationship (source -> target)
          const [hx, hy] = quadPoint(g.a, g.c, g.b, 0.9), [ex, ey] = quadPoint(g.a, g.c, g.b, 0.93);
          const ang = Math.atan2(ey - hy, ex - hx);
          ctx.fillStyle = `hsla(${s.hueTo},90%,70%,${s.alpha})`;
          ctx.beginPath(); ctx.moveTo(ex + Math.cos(ang) * 5, ey + Math.sin(ang) * 5);
          ctx.lineTo(ex + Math.cos(ang + 2.5) * 5, ey + Math.sin(ang + 2.5) * 5); ctx.lineTo(ex + Math.cos(ang - 2.5) * 5, ey + Math.sin(ang - 2.5) * 5); ctx.fill();
        }
        for (let k = 0; k < s.pulses; k++) {           // a pulse = the direction of a documented relationship (source -> target)
          const t = (((time / 1000) * PULSE_SPEED) + k / s.pulses) % 1;
          const [px, py] = quadPoint(g.a, g.c, g.b, t);
          ctx.fillStyle = `hsla(${s.hueTo},100%,82%,${Math.min(1, s.alpha + 0.1)})`;
          ctx.beginPath(); ctx.arc(px, py, s.glow ? 2.8 : 2.1, 0, Math.PI * 2); ctx.fill();
        }
      }
    };
    if (animated) {
      const loop = (now: number) => { paint(now); raf = requestAnimationFrame(loop); };
      raf = requestAnimationFrame(loop);
    } else {
      paint(0);                                          // nothing moves: draw once
    }
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene, positions, phase, selectedEventId, hoverEventId, reduced, view]);

  const eventsOnMap = scene.markers.filter((m) => m.kind === "event");
  const related = (m: Marker) => selectedEventId === null || relatedIds.has(m.id);
  const world: React.CSSProperties = { width: view.width, height: view.height, transform: `translate(${camera.tx}px, ${camera.ty}px) scale(${camera.zoom})`, ["--z" as string]: camera.zoom };

  return (
    <div
      ref={wrap} className="impact-stage" style={{ height: view.height }} data-testid="impact-map" data-phase={phase} data-zoom={camera.zoom.toFixed(2)}
      data-cables={scene.cables.length} data-animated={String(!reduced && phase === "ready")} role="group" aria-busy={phase === "loading"}
      aria-label={`World map: ${eventsOnMap.length} event${eventsOnMap.length === 1 ? "" : "s"}, ${scene.cables.length} connections`}
    >
      <div className="impact-world" style={world}>
        <canvas ref={landRef} className="layer-land" aria-hidden="true" />
        <canvas ref={cableRef} className="layer-cables" aria-hidden="true" />
        {phase === "ready" && scene.markers.map((m) => {
          const [x, y] = positions[m.id] ?? view.project(m.lon, m.lat);
          const common = { style: { left: x, top: y } as React.CSSProperties, "data-marker-id": m.id };
          if (m.kind === "event") {
            const selected = m.eventId === selectedEventId, hovered = m.eventId === hoverEventId;
            return (
              <button
                key={m.id} {...common} type="button" className={`impact-marker event${selected ? " selected" : ""}${hovered ? " hover" : ""}${related(m) ? "" : " dim"}`}
                data-testid="event-marker" data-event-id={m.eventId} aria-pressed={selected}
                aria-label={`Event ${m.rank}: ${m.label}. Event location: ${m.precision}. Press to ${selected ? "deselect" : "select"}.`}
                title={`${m.rank}. ${m.label}`} onClick={() => onSelectEvent(selected ? null : (m.eventId as string))}
                onMouseEnter={() => onHoverEvent(m.eventId as string)} onMouseLeave={() => onHoverEvent(null)}
                onFocus={() => onHoverEvent(m.eventId as string)} onBlur={() => onHoverEvent(null)}
                onKeyDown={(e) => { if (e.key === "Escape") onSelectEvent(null); }}
              >{m.rank}
                {selected && <span className={`callout${y * camera.zoom + camera.ty < 130 ? " below" : ""}`} aria-hidden="true"><b>{m.place}</b><span>{m.label}</span></span>}
                {hovered && !selected && <span className="tag" aria-hidden="true">{m.place ?? ""}</span>}</button>
            );
          }
          if (m.kind === "entity") {
            const target = m.role === "TARGET", selected = m.entityId === selectedEntityId, dim = !related(m);
            return (
              <button
                key={m.id} {...common} type="button" className={`impact-marker entity${target ? " target" : ""}${selected ? " selected" : ""}${dim ? " dim" : ""}`}
                data-testid="entity-marker" data-entity-id={m.entityId} aria-pressed={selected}
                aria-label={`${m.label}${target ? " (searched company)" : ""}, positioned at its headquarters country (${m.precision})`}
                title={`${m.label} - headquarters country, approximate`} onClick={() => onSelectEntity(m.entityId as string)}
              ><span className="txt">{m.ticker ?? m.entityId}</span></button>
            );
          }
          return <span key={m.id} {...common} className={`impact-marker region${related(m) ? "" : " dim"}`} data-testid="region-marker" role="img" aria-label={`Country named in the evidence: ${m.label}`} title={`${m.label} (named in the evidence; country centroid)`} />;
        })}
      </div>
      {phase === "loading" && <div className="impact-overlay" data-testid="impact-loading" role="status"><span className="spinner" />Loading verified events…</div>}
      {(phase === "empty" || phase === "error") && <div className="impact-overlay quiet" role="status">{phase === "error" ? "Events could not be loaded." : "No verified events to show for this search."}</div>}
      {camera.zoom > 1.01 && <button type="button" className="impact-reset" onClick={() => setWholeMap(true)}>Show whole map</button>}
      {wholeMap && selectedEventId && <button type="button" className="impact-reset" onClick={() => setWholeMap(false)}>Frame selection</button>}
    </div>
  );
}
