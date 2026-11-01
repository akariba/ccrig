// Pure globe geometry for the impact map: orthographic projection, great-circle arcs lifted above the surface, camera framing and
// easing. No React, no canvas, no imports - everything is a function of its arguments, so it is tested without a browser.
// The arcs follow the real great-circle between two real positions; "lift" only lets the line clear the surface and is NOT a data
// encoding (it depends on the distance between the endpoints, never on any impact or confidence).

export type LonLat = [number, number];
export interface GlobeCam { lon: number; lat: number; k: number }          // centre of view (degrees) and globe radius in px
export interface Projected { x: number; y: number; z: number; visible: boolean }

const RAD = Math.PI / 180;
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export const unit = ([lon, lat]: LonLat): [number, number, number] => {
  const l = lon * RAD, p = lat * RAD;
  return [Math.cos(p) * Math.cos(l), Math.cos(p) * Math.sin(l), Math.sin(p)];
};
export const fromUnit = ([x, y, z]: [number, number, number]): LonLat => [Math.atan2(y, x) / RAD, Math.asin(clamp(z / (Math.hypot(x, y, z) || 1), -1, 1)) / RAD];

/** Angle in radians between two positions on the sphere. */
export function angularDistance(a: LonLat, b: LonLat): number {
  const u = unit(a), v = unit(b);
  return Math.acos(clamp(u[0] * v[0] + u[1] * v[1] + u[2] * v[2], -1, 1));
}

/** n+1 positions along the great circle from a to b (inclusive). */
export function greatCircle(a: LonLat, b: LonLat, n = 48): LonLat[] {
  const u = unit(a), v = unit(b), d = angularDistance(a, b);
  if (d < 1e-9) return [a, b];
  const s = Math.sin(d);
  const out: LonLat[] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n, f = Math.sin((1 - t) * d) / s, g = Math.sin(t * d) / s;
    out.push(fromUnit([f * u[0] + g * v[0], f * u[1] + g * v[1], f * u[2] + g * v[2]]));
  }
  return out;
}

/** Peak height of an arc above the surface, as a fraction of the globe radius: longer connections rise higher, so they clear the surface. */
export const arcPeak = (distance: number) => 0.04 + 0.2 * clamp(distance / Math.PI, 0, 1);

/** Orthographic projection of (lon, lat) lifted `lift` globe-radii above the surface, onto a stage centred at (cx, cy). North stays up. */
export function orthoProject(lon: number, lat: number, lift: number, cam: GlobeCam, cx: number, cy: number): Projected {
  const l = (lon - cam.lon) * RAD, p = lat * RAD, p0 = cam.lat * RAD;
  const x = Math.cos(p) * Math.sin(l);
  const y = Math.cos(p0) * Math.sin(p) - Math.sin(p0) * Math.cos(p) * Math.cos(l);
  const z = Math.sin(p0) * Math.sin(p) + Math.cos(p0) * Math.cos(p) * Math.cos(l);
  const r = 1 + lift;
  // in front of the globe, or high enough above the limb to be seen past it
  const visible = z >= 0 || Math.hypot(x, y) * r > 1;
  return { x: cx + cam.k * r * x, y: cy - cam.k * r * y, z, visible };
}

export interface ArcPoint { x: number; y: number; visible: boolean }
/** The screen polyline of one connection between two positions. */
export function arcPolyline(a: LonLat, b: LonLat, cam: GlobeCam, cx: number, cy: number, n = 48): ArcPoint[] {
  const peak = arcPeak(angularDistance(a, b));
  return greatCircle(a, b, n).map((p, i) => {
    const q = orthoProject(p[0], p[1], peak * Math.sin((i / n) * Math.PI), cam, cx, cy);
    return { x: q.x, y: q.y, visible: q.visible };
  });
}

/** Point a fraction t (0..1) of the way along a polyline (by index), plus the direction there. Null when that part of the arc is hidden. */
export function pointAlong(poly: ArcPoint[], t: number): { x: number; y: number; angle: number } | null {
  if (poly.length < 2) return null;
  const f = clamp(t, 0, 1) * (poly.length - 1), i = Math.min(poly.length - 2, Math.floor(f)), u = f - i;
  const a = poly[i], b = poly[i + 1];
  if (!a.visible || !b.visible) return null;
  return { x: a.x + (b.x - a.x) * u, y: a.y + (b.y - a.y) * u, angle: Math.atan2(b.y - a.y, b.x - a.x) };
}

/** Base globe radius for a stage: large enough that the globe is the centrepiece, cropped top and bottom on wide stages. */
export const baseRadius = (w: number, h: number) => Math.min(w * 0.46, h * 0.62);

/**
 * Camera that frames a set of positions: centred on their mean direction, zoomed so the farthest stays comfortably inside the disc.
 * Never zooms out past the whole globe; when the points span more than a hemisphere the extras sit behind the horizon.
 */
export function globeTarget(points: LonLat[], w: number, h: number, maxZoom = 3): GlobeCam {
  const k0 = baseRadius(w, h);
  if (points.length === 0) return { lon: 10, lat: 20, k: k0 };
  const sum = points.map(unit).reduce((s, v) => [s[0] + v[0], s[1] + v[1], s[2] + v[2]] as [number, number, number], [0, 0, 0]);
  const centre: LonLat = Math.hypot(...sum) < 1e-6 ? points[0] : fromUnit(sum);
  const spread = Math.max(...points.map((p) => angularDistance(centre, p)));
  const zoom = clamp(0.72 / Math.sin(clamp(spread + 0.2, 0.2, Math.PI / 2)), 1, maxZoom);
  return { lon: centre[0], lat: clamp(centre[1], -70, 70), k: k0 * zoom };
}

/** Signed shortest longitude change from a to b, in degrees. */
export const lonDelta = (a: number, b: number) => ((((b - a) % 360) + 540) % 360) - 180;

/** One easing step of the camera toward a target (exponential, frame-rate independent). */
export function stepCam(cur: GlobeCam, target: GlobeCam, dtSeconds: number, rate = 5.5): { cam: GlobeCam; settled: boolean } {
  const f = 1 - Math.exp(-rate * Math.max(0, dtSeconds));
  const cam = { lon: cur.lon + lonDelta(cur.lon, target.lon) * f, lat: cur.lat + (target.lat - cur.lat) * f, k: cur.k + (target.k - cur.k) * f };
  const settled = Math.abs(lonDelta(cam.lon, target.lon)) < 0.03 && Math.abs(target.lat - cam.lat) < 0.03 && Math.abs(target.k - cam.k) < 0.15;
  return settled ? { cam: { ...target }, settled: true } : { cam, settled: false };
}
