import assert from "node:assert/strict";
import { test } from "node:test";
import { loadTs } from "./ts-loader.mjs";

const url = await loadTs("src/lib/urlStateCore.ts"), tbl = await loadTs("src/lib/tableModel.ts"), idx = await loadTs("src/lib/searchIndex.ts"), red = await loadTs("src/app/redirects.ts");

// ---------------------------------------------------------------- URL state
const SPEC = { tab: "graph", n: 5, on: false, ids: [], q: "" };
test("URL state: defaults when absent, typed values when present, junk falls back to the default", () => {
  assert.deepEqual(url.parseState(SPEC, new URLSearchParams("")), SPEC);
  const s = url.parseState(SPEC, new URLSearchParams("tab=search&n=12&on=1&ids=a,b,,c&q=hello%20world"));
  assert.deepEqual(s, { tab: "search", n: 12, on: true, ids: ["a", "b", "c"], q: "hello world" });
  assert.equal(url.parseState(SPEC, new URLSearchParams("n=abc")).n, 5);
  assert.equal(url.parseState(SPEC, new URLSearchParams("on=maybe")).on, false);
});
test("URL state: a value equal to its default is not written, unknown keys are kept, null removes", () => {
  const base = new URLSearchParams("keep=1&tab=search&n=12");
  assert.equal(url.applyState(SPEC, base, { tab: "graph" }).toString(), "keep=1&n=12");
  assert.equal(url.applyState(SPEC, base, { n: 20, ids: ["x", "y"] }).toString(), "keep=1&tab=search&n=20&ids=x%2Cy");
  assert.equal(url.applyState(SPEC, base, { n: null }).toString(), "keep=1&tab=search");
  assert.equal(url.applyState(SPEC, base, { nope: "z" }).toString(), base.toString());
  const round = url.applyState(SPEC, new URLSearchParams(), { tab: "x", n: 7, on: true, ids: ["a"], q: "a b" });
  assert.deepEqual(url.parseState(SPEC, round), { tab: "x", n: 7, on: true, ids: ["a"], q: "a b" });
});

// ---------------------------------------------------------------- table model
test("table: sort is stable, numeric, blank-last in both directions", () => {
  const rows = [{ n: "b", v: 2 }, { n: "a", v: null }, { n: "c", v: 10 }, { n: "d", v: 2 }];
  const val = (r, k) => r[k];
  assert.deepEqual(tbl.sortRows(rows, { key: "v", dir: "asc" }, val).map((r) => r.n), ["b", "d", "c", "a"]);
  assert.deepEqual(tbl.sortRows(rows, { key: "v", dir: "desc" }, val).map((r) => r.n), ["c", "b", "d", "a"]);
  assert.deepEqual(tbl.sortRows([{ n: "x10" }, { n: "x9" }], { key: "n", dir: "asc" }, val).map((r) => r.n), ["x9", "x10"]);
  assert.equal(tbl.sortRows(rows, null, val), rows);
});
test("table: filter needs every word, across the chosen columns", () => {
  const rows = [{ a: "Counterparty A", b: "Bank" }, { a: "Counterparty B", b: "Fund" }];
  const val = (r, k) => r[k];
  assert.equal(tbl.filterRows(rows, "counterparty fund", ["a", "b"], val).length, 1);
  assert.equal(tbl.filterRows(rows, "   ", ["a", "b"], val).length, 2);
  assert.equal(tbl.filterRows(rows, "zzz", ["a", "b"], val).length, 0);
});
test("table: the render window covers the viewport plus overscan and the padding adds up to the full height", () => {
  const w = tbl.windowRange(1000, 3800, 400, 38, 5);
  assert.equal(w.start, Math.floor(3800 / 38) - 5); assert.equal(w.end, Math.ceil(4200 / 38) + 5);
  assert.equal(w.padTop + (w.end - w.start) * 38 + w.padBottom, 1000 * 38);
  assert.deepEqual(tbl.windowRange(0, 0, 400, 38), { start: 0, end: 0, padTop: 0, padBottom: 0 });
  const tail = tbl.windowRange(100, 99999, 400, 38); assert.equal(tail.end, 100); assert.equal(tail.padBottom, 0);
});
test("CSV: RFC 4180 quoting, blanks stay empty, and formula-looking text is neutralised", () => {
  assert.equal(tbl.csvField('say "hi", ok'), '"say ""hi"", ok"');
  assert.equal(tbl.csvField(null), ""); assert.equal(tbl.csvField(0), "0"); assert.equal(tbl.csvField(-3.5), "-3.5");
  assert.equal(tbl.csvField("=SUM(A1)"), "'=SUM(A1)"); assert.equal(tbl.csvField("@x"), "'@x");
  assert.equal(tbl.toCsv(["a", "b"], [[1, "x,y"], [null, "z"]]), 'a,b\r\n1,"x,y"\r\n,z\r\n');
});

// ---------------------------------------------------------------- search
const E = (kind, name, extra = {}) => ({ kind, key: `${kind}:${name}`, name, href: `/${name}`, ...extra });
const ENTRIES = [E("page", "Today"), E("page", "Network"), E("counterparty", "Counterparty Alpha", { aliases: ["CP_ALPHA"] }), E("issuer", "Issuer Alpha Corporation", { aliases: ["AAA"] }), E("issuer", "Issuer Beta", { aliases: ["BBB"] }), E("theme", "AI bubble")];
test("search: exact beats prefix beats word-start beats contains; aliases rank lower than names; no match = no hit", () => {
  const names = (q) => idx.search(ENTRIES, q).map((h) => h.name);
  assert.deepEqual(names("network")[0], "Network");
  assert.equal(names("alpha")[0], "Counterparty Alpha");          // word-start, kind order breaks the tie with the issuer
  assert.ok(names("aaa").includes("Issuer Alpha Corporation"));   // a ticker finds the issuer
  assert.equal(idx.scoreEntry(ENTRIES[1], "network"), 100); assert.equal(idx.scoreEntry(ENTRIES[1], "net"), 80); assert.equal(idx.scoreEntry(ENTRIES[3], "corporation"), 60); assert.equal(idx.scoreEntry(ENTRIES[3], "pora"), 40);
  assert.deepEqual(names("zzzz"), []); assert.deepEqual(names("  "), []);
  assert.deepEqual(names("alpha issuer"), ["Issuer Alpha Corporation"]);   // multi-word: every word must hit
});
test("search: a long sentence with no strong match is a headline; a name is not", () => {
  const long = "A major earthquake disrupts chip fabrication in the region";
  assert.equal(idx.looksLikeHeadline(long, idx.search(ENTRIES, long)), true);
  assert.equal(idx.looksLikeHeadline("Issuer Beta", idx.search(ENTRIES, "Issuer Beta")), false);
  assert.equal(idx.looksLikeHeadline("two words", []), false);
});

// ---------------------------------------------------------------- redirects
const go = (p, s = "") => red.redirectFor(p, s);
test("every old route has a new home and keeps its parameters", () => {
  assert.deepEqual(go("/counterparty", "?id=CP_X"), { pathname: "/cp/CP_X", search: "" });
  assert.deepEqual(go("/counterparty", ""), { pathname: "/cp", search: "" });
  assert.deepEqual(go("/entity", "?id=ABC&x=1"), { pathname: "/issuer/ABC", search: "?x=1" });
  assert.deepEqual(go("/inbox"), { pathname: "/", search: "?tab=inbox" });
  assert.deepEqual(go("/exposure-movers"), { pathname: "/", search: "?tab=movers" });
  assert.deepEqual(go("/breaches", "?status=overdue"), { pathname: "/", search: "?status=overdue&tab=controls" });
  assert.deepEqual(go("/graph", "?id=ABC&studio=1"), { pathname: "/network", search: "?id=ABC&studio=1&tab=graph" });
  assert.deepEqual(go("/distance-map", "?id=CP_Y"), { pathname: "/network", search: "?id=CP_Y&tab=distance" });
  assert.deepEqual(go("/event-studio", "?text=a%20b"), { pathname: "/events", search: "?text=a+b&tab=analyse" });
  assert.deepEqual(go("/event-impact-map", "?q=X&days=90&event=e1"), { pathname: "/events", search: "?q=X&days=90&event=e1&tab=map" });
  assert.deepEqual(go("/theme-radar", "?theme=T"), { pathname: "/events", search: "?theme=T&tab=themes" });
  assert.deepEqual(go("/model-lab"), { pathname: "/models", search: "?tab=weights" });
  assert.deepEqual(go("/backtest-lab"), { pathname: "/models", search: "?tab=backtest" });
  assert.deepEqual(go("/provenance"), { pathname: "/admin/sources", search: "" });
  assert.deepEqual(go("/data-studio", "?x=1"), { pathname: "/admin/studio", search: "?x=1" });
  assert.deepEqual(go("/ingest-bench", "?demo=1"), { pathname: "/admin/ingest", search: "?demo=1" });
  assert.deepEqual(go("/inbox/"), { pathname: "/", search: "?tab=inbox" });           // trailing slash
  assert.equal(go("/inbox", "?tab=controls").search, "?tab=controls");                // an explicit tab is never overwritten
});
test("new routes and unknown paths are not redirected (unknown ones become a 404)", () => {
  for (const p of ["/", "/network", "/cp/X", "/issuer/Y", "/rel/a/b", "/events", "/stress", "/comovement", "/models", "/admin/sources", "/nope"]) assert.equal(go(p), null, p);
  assert.equal(red.isOldRoute("/inbox"), true); assert.equal(red.isOldRoute("/network"), false);
});
