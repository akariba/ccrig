import assert from "node:assert/strict";
import { test } from "node:test";
import { loadTs } from "./ts-loader.mjs";

// the modules import each other with relative paths, so they are loaded as one: bundle them with the TypeScript compiler API into a temp dir
import { mkdtempSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const root = decodeURIComponent(new URL("../", import.meta.url).pathname);
const dir = mkdtempSync(join(tmpdir(), "ccrig-nc-"));
mkdirSync(join(dir, "ui", "NetworkCanvas"), { recursive: true });
for (const f of ["ui/channels.ts", "ui/NetworkCanvas/types.ts", "ui/NetworkCanvas/layout.ts", "ui/NetworkCanvas/labels.ts", "ui/NetworkCanvas/hitTest.ts", "ui/NetworkCanvas/drawNodes.ts", "ui/NetworkCanvas/drawEdges.ts", "ui/NetworkCanvas/adapters.ts"]) {
  const out = ts.transpileModule(readFileSync(join(root, "src", f), "utf8"), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText.replace(/(from\s+"\.{1,2}\/[^"]+?)"/g, '$1.mjs"');
  writeFileSync(join(dir, f.replace(/\.ts$/, ".mjs")), out);
}
const load = (f) => import(pathToFileURL(join(dir, f)).href);
const lay = await load("ui/NetworkCanvas/layout.mjs"), lab = await load("ui/NetworkCanvas/labels.mjs"), hit = await load("ui/NetworkCanvas/hitTest.mjs"), nodes = await load("ui/NetworkCanvas/drawNodes.mjs"), edg = await load("ui/NetworkCanvas/drawEdges.mjs"), ad = await load("ui/NetworkCanvas/adapters.mjs");
void loadTs;

const N = (id, kind = "issuer") => ({ id, kind, label: id, tag: id });
const E = (a, b, channel = "supply", strength = 0.5, directed = true) => ({ id: `${channel}:${a}>${b}`, source: a, target: b, channel, strength, confidence: 0.9, directed });

// ------------------------------------------------------------ glyph math
test("utilisation arc: zones are green to 85%, amber to 100%, red when it reaches 100%, a tick only when over", () => {
  assert.equal(nodes.utilisationArc(null), null); assert.equal(nodes.utilisationArc(undefined), null); assert.equal(nodes.utilisationArc(-3), null); assert.equal(nodes.utilisationArc(NaN), null);
  const low = nodes.utilisationArc(40); assert.equal(low.frac, 0.4); assert.deepEqual(low.zones, [{ from: 0, to: 0.4, level: "ok" }]); assert.equal(low.over, false);
  const warn = nodes.utilisationArc(92); assert.deepEqual(warn.zones, [{ from: 0, to: 0.85, level: "ok" }, { from: 0.85, to: 0.92, level: "warn" }]); assert.equal(warn.over, false);
  const edge = nodes.utilisationArc(100); assert.equal(edge.frac, 1); assert.equal(edge.zones[1].level, "crit"); assert.equal(edge.over, false);
  const over = nodes.utilisationArc(129.3); assert.equal(over.frac, 1); assert.equal(over.over, true); assert.equal(over.zones.at(-1).level, "crit");
  assert.equal(nodes.utilisationArc(0).zones.length, 0, "zero utilisation draws no arc");
  assert.equal(nodes.utilisationArc(85).zones.length, 1, "exactly 85% has not entered amber");
});
test("channel mix: shares sum to 1, follow the fixed channel order, treat a missing strength as 0.5, and are empty without links", () => {
  const mix = nodes.channelMix([{ channel: "shared", strength: 0.2 }, { channel: "exposure", strength: 0.6 }, { channel: "exposure", strength: null }, { channel: "supply", strength: 0.2 }]);
  assert.deepEqual(mix.map((m) => m.channel), ["exposure", "supply", "shared"]);
  assert.ok(Math.abs(mix.reduce((a, m) => a + m.share, 0) - 1) < 1e-12);
  assert.ok(Math.abs(mix[0].share - 1.1 / 1.5) < 1e-12);
  assert.deepEqual(nodes.channelMix([]), []);
});
test("badges and pulse come only from what the data says; an unknown outlook or score shows nothing", () => {
  const base = { utilisation: 50, rating: null, outlook: null, priority: "HIGH", ews: null, holdingsOnly: false, flags: { wwr: false, overdue: false, nearLimit: false, negativeOutlook: null } };
  assert.deepEqual(nodes.badges(base), []); assert.equal(nodes.pulsing(base), false);
  assert.deepEqual(nodes.badges({ ...base, flags: { wwr: true, overdue: true, nearLimit: true, negativeOutlook: true } }).map((b) => b.glyph), ["W", "!", "▲", "↓"]);
  assert.deepEqual(nodes.badges({ ...base, outlook: "negative" }).map((b) => b.glyph), ["↓"]);
  assert.equal(nodes.pulsing({ ...base, ews: nodes.EWS_THRESHOLD }), false); assert.equal(nodes.pulsing({ ...base, ews: 0.61 }), true);
});
test("colours: priority and sector are stable, heat warms with distress", () => {
  const pal = { crit: "C", high: "H", med: "M", low: "L", info: "I", text3: "T", groups: ["g0", "g1", "g2"] };
  assert.deepEqual(["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL", null].map((p) => nodes.priorityColor(p, pal)), ["C", "H", "M", "L", "I", "T"]);
  assert.equal(nodes.groupColor("Energy", pal), nodes.groupColor("Energy", pal)); assert.equal(nodes.groupColor(null, pal), "T");
  assert.deepEqual([0.05, 0.2, 0.5, 0.9].map((d) => nodes.heatColor(d, pal)), ["I", "M", "H", "C"]);
  assert.equal(nodes.hexPoints(0, 0, 10).length, 6);
});

// ------------------------------------------------------------ edges
test("edges: parallel duplicates merge to the strongest, self-loops vanish, parallel links of different channels fan out", () => {
  const merged = edg.mergeParallel([E("a", "b", "supply", 0.2), { ...E("a", "b", "supply", 0.9), id: "dup" }, E("a", "a"), E("a", "b", "exposure", 0.4), E("b", "c", "shared", 0.3, false), E("c", "b", "shared", 0.5, false)]);
  assert.equal(merged.length, 3); assert.ok(!merged.some((e) => e.source === e.target));
  assert.equal(merged.find((e) => e.channel === "supply").strength, 0.9); assert.equal(merged.find((e) => e.channel === "shared").strength, 0.5, "an undirected pair is one pair whichever way it is written");
  const idx = edg.parallelIndex(merged), ab = merged.filter((e) => e.source === "a" && e.target === "b");
  assert.deepEqual(ab.map((e) => idx.get(e.id).count), [2, 2]); assert.deepEqual(new Set(ab.map((e) => idx.get(e.id).index)), new Set([0, 1]));
  const c0 = edg.controlPoint({ x: 0, y: 0 }, { x: 100, y: 0 }, 0, 2), c1 = edg.controlPoint({ x: 0, y: 0 }, { x: 100, y: 0 }, 1, 2);
  assert.notDeepEqual(c0, c1);
});
test("edge style: width follows strength, opacity follows confidence, particles only on directed moving channels", () => {
  assert.ok(edg.edgeWidth({ strength: 1 }) > edg.edgeWidth({ strength: 0.1 })); assert.equal(edg.edgeWidth({ strength: null }), edg.edgeWidth({ strength: 0.4 }));
  assert.ok(edg.edgeOpacity({ confidence: 1 }) > edg.edgeOpacity({ confidence: 0.2 })); assert.ok(edg.edgeOpacity({ confidence: 1 }) <= 0.9 + 1e-9);
  const a = { x: 0, y: 0 }, b = { x: 100, y: 0 }, c = { x: 50, y: 10 };
  assert.ok(edg.particleAt(E("a", "b", "supply"), a, c, b, 1234, 0)); assert.ok(edg.particleAt(E("a", "b", "exposure"), a, c, b, 1234, 0));
  assert.equal(edg.particleAt(E("a", "b", "shared", 0.5, false), a, c, b, 1234, 0), null); assert.equal(edg.particleAt({ ...E("a", "b", "supply"), directed: false }, a, c, b, 1, 0), null);
  const p = edg.particleAt(E("a", "b", "supply"), a, c, b, 99999, 1); assert.ok(p.x >= -1 && p.x <= 101, "a particle stays on its edge");
  assert.equal(edg.showsArrow(E("a", "b", "supply", 0.4)), false); assert.equal(edg.showsArrow(E("a", "b", "supply", 0.6)), true); assert.equal(edg.showsArrow(E("a", "b", "shared", 0.9, false)), false);
});

// ------------------------------------------------------------ layout
const ring = (n) => Array.from({ length: n }, (_, i) => N(`n${String(i).padStart(2, "0")}`));
test("force layout is deterministic, bounded, honours a fixed centre, and pulls linked nodes closer than strangers", () => {
  const ns = ring(30), es = ns.slice(1, 10).map((n) => E("n00", n.id)), opt = { width: 1100, height: 680 };
  const a = lay.forceLayout(ns, es, opt), b = lay.forceLayout(ns, es, opt);
  assert.deepEqual(a, b);
  for (const p of Object.values(a)) { assert.ok(p.x >= 24 && p.x <= 1076 && p.y >= 24 && p.y <= 656); assert.ok(Number.isFinite(p.x) && Number.isFinite(p.y)); }
  const fixed = lay.forceLayout(ns, es, { ...opt, fixed: { n00: { x: 550, y: 340 } } }); assert.deepEqual(fixed.n00, { x: 550, y: 340 });
  const d = (u, v) => Math.hypot(a[u].x - a[v].x, a[u].y - a[v].y);
  const linked = es.map((e) => d(e.source, e.target)).reduce((s, x) => s + x) / es.length, strangers = [d("n20", "n25"), d("n21", "n27"), d("n22", "n29")].reduce((s, x) => s + x) / 3;
  assert.ok(linked < strangers * 1.6, `linked ${linked.toFixed(0)} vs strangers ${strangers.toFixed(0)}`);
  assert.notDeepEqual(lay.forceLayout(ns, es, { ...opt, seed: 99 }), a, "a different seed gives a different (still valid) picture");
  assert.deepEqual(lay.forceLayout([], [], opt), {});
});
test("force layout stays fast for a couple of thousand nodes", () => {
  const ns = ring(2000), es = ns.slice(1).map((n, i) => E(ns[(i * 7) % (i + 1)].id, n.id)); const t = performance.now();
  const p = lay.forceLayout(ns, es, { width: 2200, height: 1400 }); assert.equal(Object.keys(p).length, 2000); assert.ok(performance.now() - t < 6000, `${(performance.now() - t).toFixed(0)} ms`);
});
test("radial ego: centre in the middle, ring 1 = direct, ring 2 = second hop, radii grow, nothing overlaps its ring neighbour", () => {
  const ns = ["c", "a", "b", "d", "x", "y", "z", "far"].map((i) => N(i)), es = [E("c", "a"), E("c", "b"), E("c", "d"), E("a", "x"), E("a", "y"), E("b", "z")];
  const { pos, hops } = lay.radialEgo(ns, es, "c", { width: 1000, height: 600 });
  assert.deepEqual(pos.c, { x: 500, y: 300 }); assert.deepEqual([hops.a, hops.b, hops.d, hops.x, hops.y, hops.z, hops.far], [1, 1, 1, 2, 2, 2, 3]);
  const r = (id) => Math.hypot(pos[id].x - 500, pos[id].y - 300);
  assert.ok(r("a") > 0 && r("x") > r("a") && r("far") >= r("x")); assert.ok(Math.abs(r("a") - r("b")) < 1e-6);
  const ids = Object.keys(pos); for (const u of ids) for (const v of ids) if (u < v) assert.ok(Math.hypot(pos[u].x - pos[v].x, pos[u].y - pos[v].y) > 8, `${u}/${v}`);
  assert.deepEqual(lay.radialEgo(ns, es, "c", { width: 1000, height: 600 }), { pos, hops }, "deterministic");
  assert.deepEqual(lay.radialEgo([], [], "c", { width: 10, height: 10 }), { pos: {}, hops: {} });
});

// ------------------------------------------------------------ labels
test("label collision: no two tags overlap, none leaves the bounds, none covers a node glyph, and the higher priority wins a contested spot", () => {
  const bounds = { x: 0, y: 0, w: 400, h: 300 };
  const items = Array.from({ length: 40 }, (_, i) => ({ id: `n${i}`, text: `NODE${i}`, at: { x: 40 + (i % 8) * 45, y: 40 + Math.floor(i / 8) * 45 }, radius: 12, priority: i, w: lab.tagWidth(`NODE${i}`), h: 18 }));
  const glyphs = items.map((i) => ({ at: i.at, radius: i.radius })), placed = lab.placeLabels(items, bounds, glyphs), rects = [...placed.values()];
  assert.ok(rects.length > 0 && rects.length <= 40);
  for (let i = 0; i < rects.length; i++) { assert.ok(lab.inside(rects[i], bounds)); for (let j = i + 1; j < rects.length; j++) assert.ok(!lab.overlaps(rects[i], rects[j], 0), `labels ${i}/${j} overlap`); for (const g of glyphs) assert.ok(!lab.overlaps(rects[i], { x: g.at.x - g.radius, y: g.at.y - g.radius, w: g.radius * 2, h: g.radius * 2 }, 0) || [...placed.entries()].every(([id, r]) => r !== rects[i] || items.find((q) => q.id === id).at !== g.at)); }
  const two = lab.placeLabels([{ id: "lo", text: "AAAAAAAAAAAA", at: { x: 100, y: 100 }, radius: 10, priority: 1, w: 90, h: 18 }, { id: "hi", text: "BBBBBBBBBBBB", at: { x: 100, y: 100 }, radius: 10, priority: 9, w: 90, h: 18 }], bounds);
  assert.ok(two.has("hi")); assert.deepEqual(two.get("hi"), { x: 55, y: 114, w: 90, h: 18 }, "the higher priority takes the first position (below)");
  assert.ok(two.has("lo") ? !lab.overlaps(two.get("lo"), two.get("hi"), 0) : true);
  assert.equal(lab.placeLabels([{ id: "edge", text: "X", at: { x: 2, y: 2 }, radius: 100, priority: 1, w: 500, h: 18 }], bounds).size, 0, "a tag that fits nowhere is dropped");
  assert.equal(lab.tagWidth("ABCD"), Math.ceil(4 * 11 * 0.6 + 12));
});

// ------------------------------------------------------------ hit testing
test("hit test: nearest node within its radius wins; edges are hit near the curve only", () => {
  const ns = [{ id: "a", at: { x: 50, y: 50 }, radius: 20 }, { id: "b", at: { x: 80, y: 50 }, radius: 20 }];
  assert.equal(hit.hitNode(ns, { x: 52, y: 50 }), "a"); assert.equal(hit.hitNode(ns, { x: 79, y: 50 }), "b"); assert.equal(hit.hitNode(ns, { x: 300, y: 300 }), null); assert.equal(hit.hitNode(ns, { x: 50, y: 73 }, 3), "a");
  const e = [{ id: "e", a: { x: 0, y: 0 }, c: { x: 50, y: 40 }, b: { x: 100, y: 0 }, width: 2 }];
  assert.equal(hit.hitEdge(e, hit.quadPoint(e[0].a, e[0].c, e[0].b, 0.5)), "e"); assert.equal(hit.hitEdge(e, { x: 50, y: -30 }), null);
  assert.deepEqual(hit.quadPoint({ x: 0, y: 0 }, { x: 50, y: 40 }, { x: 100, y: 0 }, 0), { x: 0, y: 0 }); assert.deepEqual(hit.quadPoint({ x: 0, y: 0 }, { x: 50, y: 40 }, { x: 100, y: 0 }, 1), { x: 100, y: 0 });
});

// ------------------------------------------------------------ adapters
test("adapter: a counterparty keeps null for what the API did not know; a holdings-only one is marked", () => {
  const n = ad.toNode({ id: "cp:X", kind: "counterparty", label: "Counterparty X", tag: "Counterparty X", priority: "HIGH", utilisation_pct: 92, rating: null, outlook: null, ews: null, flags: { wwr: true, near_limit: true, negative_outlook: null } });
  assert.deepEqual(n.cp, { utilisation: 92, rating: null, outlook: null, priority: "HIGH", ews: null, holdingsOnly: false, flags: { wwr: true, overdue: false, nearLimit: true, negativeOutlook: null } });
  assert.equal(ad.toNode({ id: "cp:Y", kind: "counterparty", label: "Y", tag: "Y", holdings_only: true }).cp.holdingsOnly, true);
  assert.equal(ad.toNode({ id: "is:Z", kind: "issuer", label: "Z", tag: "Z", sector: "Energy" }).group, "Energy");
  assert.equal(ad.toGraph([{ id: "is:Z", kind: "issuer", label: "Z", tag: "Z" }], [{ id: "e", source: "is:Z", target: "is:Z", channel: "supply", strength: 1, confidence: null, directed: true }], [{ id: "cl:1", name: "n", members: [] }]).clusters.length, 1);
});
