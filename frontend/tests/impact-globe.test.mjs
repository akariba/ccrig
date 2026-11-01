import assert from "node:assert/strict";
import { test } from "node:test";
import { loadTs } from "./ts-loader.mjs";

const g = await loadTs("src/impactmap/globe.ts");
const near = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} !~ ${b}`);
const berlin = [13.4, 52.52], santaClara = [-121.96, 37.35], seoul = [126.98, 37.57], taipei = [121.57, 25.03];

test("the point at the centre of the view projects to the centre; north is up and east is right", () => {
  const cam = { lon: 13.4, lat: 52.52, k: 300 };
  const c = g.orthoProject(13.4, 52.52, 0, cam, 500, 300);
  near(c.x, 500); near(c.y, 300); assert.ok(c.visible && c.z > 0.999);
  assert.ok(g.orthoProject(13.4, 70, 0, cam, 500, 300).y < 300);               // further north -> higher on screen
  assert.ok(g.orthoProject(40, 52.52, 0, cam, 500, 300).x > 500);              // further east -> right
});

test("the far side of the globe is hidden, the near side is not, and a lifted arc clears the limb", () => {
  const cam = { lon: 0, lat: 0, k: 300 };
  assert.equal(g.orthoProject(180, 0, 0, cam, 0, 0).visible, false);
  assert.equal(g.orthoProject(45, 10, 0, cam, 0, 0).visible, true);
  assert.equal(g.orthoProject(95, 0, 0, cam, 0, 0).visible, false);            // just behind the limb on the surface
  assert.equal(g.orthoProject(95, 0, 0.3, cam, 0, 0).visible, true);           // the same direction lifted high enough to be seen over it
});

test("great-circle arcs start and end exactly at the endpoints and take the short way round", () => {
  const arc = g.greatCircle(santaClara, seoul, 40);
  assert.equal(arc.length, 41);
  near(arc[0][0], santaClara[0], 1e-6); near(arc[0][1], santaClara[1], 1e-6);
  near(arc[40][0], seoul[0], 1e-6); near(arc[40][1], seoul[1], 1e-6);
  assert.ok(Math.max(...arc.map((p) => p[1])) > 45);                           // the real route bows toward the pole (the great circle), not along the parallel
  const d = g.angularDistance(santaClara, seoul);
  for (let i = 1; i < arc.length; i++) near(g.angularDistance(arc[i - 1], arc[i]), d / 40, 1e-6);   // evenly spaced
  assert.equal(g.greatCircle(berlin, berlin, 8).length, 2);                    // degenerate pair does not blow up
});

test("arc height depends on distance only, never on anything else", () => {
  assert.ok(g.arcPeak(0.1) < g.arcPeak(1.5) && g.arcPeak(1.5) < g.arcPeak(3));
  assert.equal(g.arcPeak(10), g.arcPeak(Math.PI)); assert.equal(g.arcPeak(-1), g.arcPeak(0));
  const cam = { lon: 0, lat: 30, k: 200 };
  const poly = g.arcPolyline([-60, 20], [60, 20], cam, 0, 0, 20);
  assert.equal(poly.length, 21);
  const ends = g.orthoProject(-60, 20, 0, cam, 0, 0), top = poly[10];
  near(poly[0].x, ends.x); near(poly[0].y, ends.y);                            // endpoints sit on the surface
  assert.ok(Math.hypot(top.x, top.y) > 0);
});

test("particles follow the polyline from its first point to its last, and vanish where the arc is hidden", () => {
  const poly = [{ x: 0, y: 0, visible: true }, { x: 10, y: 0, visible: true }, { x: 20, y: 10, visible: true }, { x: 30, y: 10, visible: false }];
  assert.deepEqual(g.pointAlong(poly, 0), { x: 0, y: 0, angle: 0 });
  const mid = g.pointAlong(poly, 0.5);
  assert.ok(mid.x > 10 && mid.x < 20);
  assert.equal(g.pointAlong(poly, 1), null);                                   // the last segment ends in a hidden point
  assert.equal(g.pointAlong([poly[0]], 0.5), null);
  assert.equal(g.pointAlong(poly, -3).x, 0);                                   // clamped
});

test("the camera frames a selection: centred on it, never zoomed out past the globe, and zoomed in when the points are close", () => {
  const w = 1000, h = 640, k0 = g.baseRadius(w, h);
  near(k0, Math.min(460, 396.8));
  const wide = g.globeTarget([santaClara, seoul, berlin, taipei], w, h);
  assert.ok(wide.k >= k0 - 1e-9 && wide.k <= k0 * 3 + 1e-9);
  const close = g.globeTarget([[-121.96, 37.35], [-122.4, 37.77], [-121.9, 37.4]], w, h);
  assert.ok(close.k > wide.k * 1.5); near(close.lon, -122.1, 0.5); near(close.lat, 37.5, 0.5);
  const usKorea = g.globeTarget([[-98.6, 39.8], seoul], w, h);                 // two far-apart companies: both stay in front of the horizon
  const cam = { ...usKorea, k: usKorea.k };
  for (const p of [[-98.6, 39.8], seoul]) assert.equal(g.orthoProject(p[0], p[1], 0, cam, 0, 0).visible, true);
  assert.deepEqual(g.globeTarget([], w, h).k, k0);
  assert.ok(Math.abs(g.globeTarget([[0, 89]], w, h).lat) <= 70);               // never tips the pole to the front
});

test("camera easing moves toward the target by the shortest way round, settles exactly, and is frame-rate independent", () => {
  assert.equal(g.lonDelta(170, -170), 20); assert.equal(g.lonDelta(-170, 170), -20); assert.equal(g.lonDelta(10, 10), 0);
  const target = { lon: -170, lat: 40, k: 500 };
  const one = g.stepCam({ lon: 170, lat: 0, k: 300 }, target, 0.1);
  assert.ok(one.cam.lon > 170 || one.cam.lon < -170);                           // crossed the antimeridian, not back through 0
  const slow = (() => { let c = { lon: 170, lat: 0, k: 300 }; for (let i = 0; i < 20; i++) c = g.stepCam(c, target, 0.05).cam; return c; })();
  const fast = (() => { let c = { lon: 170, lat: 0, k: 300 }; for (let i = 0; i < 10; i++) c = g.stepCam(c, target, 0.1).cam; return c; })();
  near(slow.lat, fast.lat, 1e-6); near(slow.k, fast.k, 1e-6);
  let c = { lon: 0, lat: 0, k: 100 }, settled = false, steps = 0;
  while (!settled && steps++ < 400) ({ cam: c, settled } = g.stepCam(c, target, 1 / 60));
  assert.ok(settled && steps < 400); assert.deepEqual(c, target);
});

test("auto projection: globe when everything fits one hemisphere, flat otherwise", () => {
  assert.equal(g.chooseProjection([]), "globe"); assert.equal(g.chooseProjection([berlin]), "globe");
  assert.equal(g.chooseProjection([[-98.6, 39.8], seoul]), "globe");                      // the Seoul event and its US counterpart: a readable globe
  assert.equal(g.chooseProjection([santaClara, [-122.4, 37.77], [-121.9, 37.4]]), "globe");
  assert.equal(g.chooseProjection([berlin, santaClara, seoul, taipei, [-98.6, 39.8]]), "flat");   // the whole register: dispersed
  assert.equal(g.chooseProjection([[0, 0], [180, 0]]), "flat");                          // opposite points have no centre: never a globe
  assert.deepEqual([g.chooseProjection([berlin, seoul]), g.chooseProjection([seoul, berlin])].length, 2);
});
