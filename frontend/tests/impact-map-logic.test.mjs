import assert from "node:assert/strict";
import { test } from "node:test";
import { loadTs } from "./ts-loader.mjs";

const m = await loadTs("src/impactmap/model.ts");
const near = (a, b, eps = 1e-6) => assert.ok(Math.abs(a - b) < eps, `${a} !~ ${b}`);

// ------------------------------------------------------------------ projection
test("Equal Earth: origin, symmetry and monotonic latitude", () => {
  assert.deepEqual(m.equalEarth(0, 0), [0, 0]);
  const [x1, y1] = m.equalEarth(60, 40), [x2, y2] = m.equalEarth(-60, -40);
  near(x1, -x2); near(y1, -y2);
  let previous = -Infinity;
  for (let lat = -90; lat <= 90; lat += 10) { const [, y] = m.equalEarth(30, lat); assert.ok(y > previous); previous = y; }
  near(m.equalEarth(180, 0)[0], 2.7066, 1e-3);                    // the projection's published extent
  near(m.equalEarth(0, 90)[1], 1.3173, 1e-3);
});

test("a view fits the world into the width and puts known places where they belong", () => {
  const v = m.makeView(1000);
  assert.equal(v.width, 1000); assert.ok(v.height > 450 && v.height < 520);
  const [cx, cy] = v.project(0, 0);
  near(cx, 500, 1e-6); near(cy, v.height / 2, 1e-6);
  assert.ok(v.project(-180, 0)[0] < v.project(180, 0)[0]);
  assert.ok(v.project(0, 60)[1] < v.project(0, -60)[1]);         // north is up the screen
  const taipei = v.project(121.57, 25.03), berlin = v.project(13.4, 52.52), sf = v.project(-122.42, 37.77);
  assert.ok(sf[0] < berlin[0] && berlin[0] < taipei[0]);
  assert.ok(berlin[1] < taipei[1]);                               // Berlin (52N) is above Taipei (25N)
});

// ------------------------------------------------------------------ arcs
test("curved connections bow upward whichever way they are drawn", () => {
  for (const [a, b] of [[[100, 300], [400, 320]], [[400, 320], [100, 300]], [[100, 300], [110, 100]]]) {
    const c = m.arcControl(a, b), midY = (a[1] + b[1]) / 2;
    assert.ok(c[1] < midY, `control point must be above the chord (${c[1]} < ${midY})`);
  }
  // an exactly vertical chord has no "up": it bows left, and the SAME way whichever end is the source
  const down = m.arcControl([250, 50], [250, 400]), up = m.arcControl([250, 400], [250, 50]);
  assert.ok(down[0] < 250); assert.deepEqual(down, up);
  const flat = m.arcControl([0, 100], [200, 100], 0.2);
  near(flat[0], 100); near(flat[1], 100 - 40);                    // 20% of the chord length
});

test("quadratic points hit the endpoints and the curve is deterministic", () => {
  const a = [10, 20], b = [210, 120], c = m.arcControl(a, b);
  assert.deepEqual(m.quadPoint(a, c, b, 0), a); assert.deepEqual(m.quadPoint(a, c, b, 1), b);
  assert.deepEqual(m.quadPoint(a, c, b, 0.4), m.quadPoint(a, c, b, 0.4));
});

test("overlapping markers are separated deterministically; others are left alone", () => {
  const items = [{ id: "entity:MSFT", pt: [100, 100] }, { id: "entity:GOOGL", pt: [100, 100] }, { id: "entity:NVDA", pt: [100, 100] }, { id: "event:x", pt: [400, 300] }];
  const out = m.spreadOverlaps(items), reordered = m.spreadOverlaps([...items].reverse());
  assert.deepEqual(out, reordered);                               // independent of input order
  assert.deepEqual(out["event:x"], [400, 300]);
  const ids = ["entity:GOOGL", "entity:MSFT", "entity:NVDA"];
  for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++)
    assert.ok(Math.hypot(out[ids[i]][0] - out[ids[j]][0], out[ids[i]][1] - out[ids[j]][1]) >= 19);
});

// ------------------------------------------------------------------ cable behaviour follows system state
const documented = { id: "d", type: "DOCUMENTED_RELATION", from: "entity:TSM", to: "entity:NVDA", eventIds: ["e1"], relation: "SUPPLIES" };
const mention = { id: "m", type: "MENTIONS", from: "event:e1", to: "entity:NVDA", eventIds: ["e1"] };
const region = { id: "r", type: "MENTIONS_REGION", from: "event:e1", to: "region:country-tw", eventIds: ["e1"] };
const ctx = (over) => ({ phase: "ready", selectedEventId: null, reducedMotion: false, ...over });

test("nothing is drawn or animated unless there is data to show", () => {
  for (const phase of ["idle", "loading", "empty", "error"])
    for (const c of [documented, mention, region]) {
      const s = m.cableStyle(c, ctx({ phase }));
      assert.equal(s.draw, false); assert.equal(s.pulses, 0); assert.equal(s.alpha, 0);
    }
});

test("only documented relationships carry a travelling pulse; mentions and regions never do", () => {
  assert.equal(m.cableStyle(documented, ctx()).pulses, 1);
  assert.equal(m.cableStyle(mention, ctx()).pulses, 0);
  assert.equal(m.cableStyle(region, ctx()).pulses, 0);
  for (const sel of ["e1", "e2"]) for (const c of [mention, region]) assert.equal(m.cableStyle(c, ctx({ selectedEventId: sel })).pulses, 0);
});

test("kinds are visually distinct and the colour encodes what the link is, not randomness", () => {
  const d = m.cableStyle(documented, ctx()), n = m.cableStyle(mention, ctx()), r = m.cableStyle(region, ctx());
  assert.equal(d.dash, null); assert.notDeepEqual(n.dash, r.dash); assert.ok(n.dash && r.dash);
  assert.deepEqual([d.hueFrom, d.hueTo, n.hueFrom], [205, 175, 215]);
  assert.deepEqual(m.cableStyle(documented, ctx()), m.cableStyle(documented, ctx()));         // same input, same output
});

test("selecting an event highlights its cables and dims the rest", () => {
  const on = m.cableStyle(documented, ctx({ selectedEventId: "e1" })), off = m.cableStyle(documented, ctx({ selectedEventId: "e2" }));
  assert.equal(on.alpha, 1); assert.equal(on.glow, true); assert.equal(on.pulses, 3); assert.ok(on.width > m.cableStyle(documented, ctx()).width);
  assert.ok(off.alpha < 0.2); assert.equal(off.glow, false); assert.equal(off.pulses, 0);
});

test("reduced motion removes every pulse but keeps the picture", () => {
  for (const sel of [null, "e1"]) {
    const s = m.cableStyle(documented, ctx({ reducedMotion: true, selectedEventId: sel }));
    assert.equal(s.pulses, 0); assert.equal(s.draw, true); assert.ok(s.alpha > 0);
  }
});

test("the phase is derived from the real request status and result", () => {
  const some = { events: [{}] }, none = { events: [] };
  assert.equal(m.phaseOf("idle", null), "idle");
  assert.equal(m.phaseOf("loading", some), "loading");
  assert.equal(m.phaseOf("error", some), "error");
  assert.equal(m.phaseOf("ok", some), "ready");
  assert.equal(m.phaseOf("ok", none), "empty");
  assert.equal(m.phaseOf("ok", null), "empty");
});

// ------------------------------------------------------------------ scene
const pos = (label, lat, lon, precision = "approximate city point") => ({ label, lat, lon, precision });
const response = {
  entity: { entity_id: "NVDA", name: "NVIDIA" }, events: [{ id: "e1" }, { id: "e2" }],
  graph: {
    nodes: [
      { id: "event:e1", type: "EVENT", label: "E1", event_id: "e1", position: pos("Berlin", 52.5, 13.4) },
      { id: "event:e2", type: "EVENT", label: "E2", event_id: "e2", position: null },
      { id: "entity:NVDA", type: "ENTITY", label: "NVIDIA", role: "TARGET", entity_id: "NVDA", position: pos("United States", 39.8, -98.6, "country centroid") },
      { id: "entity:ORCL", type: "ENTITY", label: "Oracle", entity_id: "ORCL", position: null },
    ],
    edges: [
      { id: "a", type: "MENTIONS", source: "event:e1", target: "entity:NVDA", event_ids: ["e1"] },
      { id: "b", type: "MENTIONS", source: "event:e2", target: "entity:NVDA", event_ids: ["e2"] },
      { id: "c", type: "MENTIONS", source: "event:e1", target: "entity:ORCL", event_ids: ["e1"] },
    ],
  },
};

test("the scene plots only what has a position, reports the rest, and drops cables to nowhere", () => {
  const s = m.buildScene(response);
  assert.deepEqual(s.markers.map((x) => x.id).sort(), ["entity:NVDA", "event:e1"]);
  assert.deepEqual(s.unmapped.map((x) => x.id).sort(), ["entity:ORCL", "event:e2"]);
  assert.deepEqual(s.cables.map((c) => c.id), ["a"]);                               // b and c would end at an unplaced marker
  assert.equal(s.markers.find((x) => x.id === "event:e1").rank, 1);
  assert.equal(s.markers.find((x) => x.id === "entity:NVDA").precision, "country centroid");
});

// ------------------------------------------------------------------ paths read honestly
test("a path reads event -> names -> entity -> relation -> entity, with direction and evidence", () => {
  const path = { id: "p", relationship_type: "DOCUMENTED_DIRECT", entity_id: "MSFT", steps: [
    { type: "MENTIONS", from: "event:e1", to: "MSFT", evidence: { matched_text: "Microsoft", rule: "NAME_MATCH", quote: "..." } },
    { type: "DOCUMENTED_RELATION", relation: "SUPPLIES", from: "MSFT", to: "NVDA", traversal: "AGAINST_STORED_DIRECTION",
      stored_edge: { source: "NVDA", target: "MSFT" }, criticality: 0.55, evidence_status: "WELL_DOCUMENTED_PUBLIC" }] };
  const chips = m.pathChips(path, "Q2 results", { MSFT: "Microsoft", NVDA: "NVIDIA" });
  assert.deepEqual(chips.map((c) => c.kind), ["event", "relation", "entity", "relation", "entity"]);
  assert.equal(chips[2].text, "Microsoft"); assert.equal(chips[4].text, "NVIDIA");
  assert.match(chips[3].text, /SUPPLIES \(read in reverse\)/);
  assert.match(chips[3].detail, /stored as NVDA → MSFT/); assert.match(chips[3].detail, /curated judgement, not exposure/);
  assert.match(chips[1].detail, /NAME_MATCH/);
});

test("dates and links are formatted safely", () => {
  assert.equal(m.formatDate("2026-10-21"), "21 Oct 2026"); assert.equal(m.formatDate("2026-01-05"), "5 Jan 2026"); assert.equal(m.formatDate("soon"), "soon");
  assert.equal(m.safeHttpsUrl("https://investor.nvidia.com/x"), "https://investor.nvidia.com/x");
  for (const bad of ["javascript:alert(1)", "http://example.org", "ftp://x", "not a url", "data:text/html,x"]) assert.equal(m.safeHttpsUrl(bad), null);
});

// ------------------------------------------------------------------ refinement: quiet context, hover preview, camera
test("by default the network is a quiet context; only the selected event's paths are emphasised", () => {
  const ctxQuiet = ctx({});
  for (const c of [documented, mention, region]) assert.ok(m.cableStyle(c, ctxQuiet).alpha <= 0.3);
  const sel = ctx({ selectedEventId: "e1" });
  assert.equal(m.cableStyle(documented, sel).alpha, 1);
  for (const c of [mention, region]) assert.ok(m.cableStyle({ ...c, eventIds: ["e2"] }, sel).alpha <= 0.05);
  assert.ok(m.cableStyle({ ...documented, eventIds: ["e2"] }, sel).alpha <= 0.12);
});

test("hovering an event previews its cables at medium strength without pulses, and never outranks the selection", () => {
  const h = m.cableStyle(documented, ctx({ selectedEventId: "e2", hoverEventId: "e1" }));
  assert.equal(h.alpha, 0.6); assert.equal(h.pulses, 0); assert.equal(h.glow, false);
  assert.equal(m.cableStyle(documented, ctx({ selectedEventId: "e1", hoverEventId: "e1" })).alpha, 1);
});

test("the camera frames a selection, never zooms out past the world, and never leaves the stage", () => {
  assert.deepEqual(m.fitView([], 900, 480), { zoom: 1, tx: 0, ty: 0 });
  const wide = m.fitView([[50, 100], [850, 400]], 900, 480);
  assert.equal(wide.zoom, 1); assert.equal(wide.tx, 0); assert.equal(wide.ty, 0);
  const tight = m.fitView([[200, 200], [240, 230]], 900, 480);
  assert.ok(tight.zoom > 1 && tight.zoom <= 2.4);
  for (const v of [wide, tight, m.fitView([[5, 5]], 900, 480), m.fitView([[895, 475]], 900, 480)]) {
    assert.ok(v.tx <= 0 && v.tx >= 900 - 900 * v.zoom - 1e-9); assert.ok(v.ty <= 0 && v.ty >= 480 - 480 * v.zoom - 1e-9);
  }
  const x = 220 * tight.zoom + tight.tx, y = 215 * tight.zoom + tight.ty;       // the framed centre stays on screen
  assert.ok(x > 0 && x < 900 && y > 0 && y < 480);
});

// ------------------------------------------------------------------ callout collision avoidance (general rule)
test("a callout goes where it overlaps the fewest markers and stays on the stage", () => {
  const size = { w: 190, h: 64 }, bounds = { w: 900, h: 480 };
  assert.equal(m.placeCallout([450, 300], size, [], bounds), "above");                               // free space: the default side
  assert.equal(m.placeCallout([450, 60], size, [], bounds), "below");                                // no room above
  assert.equal(m.placeCallout([40, 240], size, [], bounds), "right");                               // centred above/below would leave the left edge
  const label = { x: 890, y: 230, w: 48, h: 22 };                                                    // a company label beyond the right edge
  assert.notEqual(m.placeCallout([450, 300], size, [{ x: 400, y: 215, w: 100, h: 40 }], bounds), "above");   // blocked above -> another side
  assert.equal(m.placeCallout([450, 300], size, [{ x: 400, y: 215, w: 100, h: 40 }, { x: 400, y: 330, w: 100, h: 30 }], bounds), "right");
  const picked = m.placeCallout([880, 240], size, [label], bounds);
  assert.ok(["above", "below", "left"].includes(picked));                                            // right would leave the stage
  assert.equal(m.placeCallout([450, 300], size, [{ x: 0, y: 0, w: 900, h: 480 }], bounds), "above"); // nothing helps: stable, never throws
});

test("with bounds, spread markers stay inside the stage and still keep apart where there is room", () => {
  const b = { w: 390, h: 200, edge: 18 };
  const items = ["a", "b", "c", "d", "e"].map((id) => ({ id, pt: [4, 6] }));            // all piled into the top-left corner
  const out = m.spreadOverlaps(items, 30, b);
  for (const [x, y] of Object.values(out)) { assert.ok(x >= 18 && x <= 372 && y >= 18 && y <= 182); }
  const pts = Object.values(out);
  for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) assert.ok(Math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]) >= 29);
  assert.deepEqual(m.spreadOverlaps(items, 30, b), m.spreadOverlaps([...items].reverse(), 30, b));
});
