import { useEffect, useMemo, useRef, useState } from "react";
import { feature } from "topojson-client";
import {
  arcControl, cableStyle, makeView, quadPoint, spreadOverlaps,
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

const OCEAN = "#0d0e11", LAND = "#191c21", BORDER = "#2a2e34", GRID = "#1a1d22", PULSE_SPEED = 0.16; // cycles per second

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
  scene: Scene; phase: Phase; selectedEventId: string | null; selectedEntityId: string | null;
  onSelectEvent: (id: string | null) => void; onSelectEntity: (id: string) => void;
}) {
  const { scene, phase, selectedEventId, selectedEntityId, onSelectEvent, onSelectEntity } = props;
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
    () => spreadOverlaps(scene.markers.map((m) => ({ id: m.id, pt: view.project(m.lon, m.lat) as Pt })), 24),
    [scene, view],
  );

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
    const styled = scene.cables.map((cable) => ({ cable, s: cableStyle(cable, { phase, selectedEventId, reducedMotion: reduced }) })).filter((x) => x.s.draw);
    const animated = styled.some((x) => x.s.pulses > 0);
    let raf = 0;
    const geometry = (cable: { from: string; to: string }) => {
      const a = positions[cable.from], b = positions[cable.to];
      return a && b ? { a, b, c: arcControl(a, b) } : null;
    };
    const paint = (time: number) => {
      ctx.clearRect(0, 0, view.width, view.height);
      // dim cables first, active ones on top
      for (const { cable, s } of [...styled].sort((x, y) => Number(x.s.glow) - Number(y.s.glow))) {
        const g = geometry(cable); if (!g) continue;
        const grad = ctx.createLinearGradient(g.a[0], g.a[1], g.b[0], g.b[1]);
        grad.addColorStop(0, `hsla(${s.hueFrom},85%,62%,${s.alpha})`); grad.addColorStop(1, `hsla(${s.hueTo},85%,66%,${s.alpha})`);
        ctx.setLineDash(s.dash ?? []); ctx.strokeStyle = grad; ctx.lineWidth = s.width;
        ctx.beginPath(); ctx.moveTo(g.a[0], g.a[1]); ctx.quadraticCurveTo(g.c[0], g.c[1], g.b[0], g.b[1]); ctx.stroke();
        if (s.glow) { ctx.globalAlpha = 0.14; ctx.lineWidth = s.width + 5; ctx.stroke(); ctx.globalAlpha = 1; }
        ctx.setLineDash([]);
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
  }, [scene, positions, phase, selectedEventId, reduced, view]);

  const eventsOnMap = scene.markers.filter((m) => m.kind === "event");
  const related = (m: Marker) => selectedEventId === null || (m.kind === "event" ? m.eventId === selectedEventId
    : scene.cables.some((cb) => cb.eventIds.includes(selectedEventId) && (cb.from === m.id || cb.to === m.id)));

  return (
    <div
      ref={wrap} className="impact-stage" style={{ height: view.height }} data-testid="impact-map" data-phase={phase}
      data-cables={scene.cables.length} data-animated={String(!reduced && phase === "ready")} role="group" aria-busy={phase === "loading"}
      aria-label={`World map: ${eventsOnMap.length} event${eventsOnMap.length === 1 ? "" : "s"}, ${scene.cables.length} connections`}
    >
      <canvas ref={landRef} className="layer-land" aria-hidden="true" />
      <canvas ref={cableRef} className="layer-cables" aria-hidden="true" />
      {phase === "ready" && scene.markers.map((m) => {
        const [x, y] = positions[m.id] ?? view.project(m.lon, m.lat);
        const common = { style: { left: x, top: y } as React.CSSProperties, "data-marker-id": m.id };
        if (m.kind === "event") {
          const selected = m.eventId === selectedEventId;
          return (
            <button
              key={m.id} {...common} type="button" className={`impact-marker event${selected ? " selected" : ""}${related(m) ? "" : " dim"}`}
              data-testid="event-marker" data-event-id={m.eventId} aria-pressed={selected}
              aria-label={`Event ${m.rank}: ${m.label}. Location: ${m.precision}. Press to ${selected ? "deselect" : "select"}.`}
              title={`${m.rank}. ${m.label}`} onClick={() => onSelectEvent(selected ? null : (m.eventId as string))}
              onKeyDown={(e) => { if (e.key === "Escape") onSelectEvent(null); }}
            >{m.rank}</button>
          );
        }
        if (m.kind === "entity") {
          const target = m.role === "TARGET", selected = m.entityId === selectedEntityId;
          return (
            <button
              key={m.id} {...common} type="button" className={`impact-marker entity${target ? " target" : ""}${selected ? " selected" : ""}${related(m) ? "" : " dim"}`}
              data-testid="entity-marker" data-entity-id={m.entityId} aria-pressed={selected}
              aria-label={`${m.label}${target ? " (searched company)" : ""}, positioned at its headquarters country (${m.precision})`}
              title={`${m.label} - headquarters country, approximate`} onClick={() => onSelectEntity(m.entityId as string)}
            >{m.ticker ?? m.entityId}</button>
          );
        }
        return <span key={m.id} {...common} className="impact-marker region" data-testid="region-marker" role="img" aria-label={`Country named in the evidence: ${m.label}`} title={`${m.label} (named in the evidence; country centroid)`} />;
      })}
    </div>
  );
}

