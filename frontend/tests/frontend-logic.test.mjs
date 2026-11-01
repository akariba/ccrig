import assert from "node:assert/strict";
import { test } from "node:test";
import { loadTs } from "./ts-loader.mjs";

const { apiErrorMessage } = await loadTs("src/api/errors.ts");
const { describeBackendStatus } = await loadTs("src/components/healthStatus.ts");

// ------------------------------------------------------------ apiErrorMessage
test("flattens FastAPI validation errors from the HTTP server", () => {
  const err = new Error('422 Unprocessable Entity: {"detail":[{"type":"value_error","loc":["body","weights"],' +
    '"msg":"Value error, at least one weight must be greater than 0","input":{}}]}');
  assert.equal(apiErrorMessage(err), "weights: Value error, at least one weight must be greater than 0");
});

test("flattens the same errors from the in-browser dispatcher", () => {
  const err = new Error('422: {"detail":[{"type":"string_too_short","loc":["query","q"],"msg":"String should have at least 1 character"}]}');
  assert.equal(apiErrorMessage(err), "q: String should have at least 1 character");
});

test("joins several errors and keeps nested field paths", () => {
  const err = new Error('422: {"detail":[{"loc":["body","weights","bogus"],"msg":"bad"},{"loc":["body","top_k"],"msg":"too big"}]}');
  assert.equal(apiErrorMessage(err), "weights.bogus: bad; top_k: too big");
});

test("passes string details through and tolerates an error without a field", () => {
  assert.equal(apiErrorMessage(new Error('404 Not Found: {"detail":"Entity \'X\' not found"}')), "Entity 'X' not found");
  assert.equal(apiErrorMessage(new Error('422: {"detail":[{"loc":["body"],"msg":"Field required"}]}')), "Field required");
});

test("falls back to the raw message for anything that is not a JSON error body", () => {
  assert.equal(apiErrorMessage(new Error("Failed to fetch")), "Failed to fetch");
  assert.equal(apiErrorMessage("plain string"), "plain string");
  assert.equal(apiErrorMessage(new Error("500: {not json")), "500: {not json");
});

// ----------------------------------------------------- describeBackendStatus
test("before the first answer the badge says it is connecting", () => {
  const s = describeBackendStatus(null);
  assert.deepEqual([s.title, s.tone], ["Connecting...", "pending"]);
});

test("an unreachable backend is never described as a working offline mode", () => {
  const s = describeBackendStatus({ unreachable: true });
  assert.equal(s.tone, "error");
  assert.equal(s.title, "Backend unreachable");
  const text = `${s.title} ${s.detail}`;
  assert.doesNotMatch(text, /Offline deterministic/i);
  assert.doesNotMatch(text, /full functionality retained/i);
  assert.doesNotMatch(text, /AI_API_KEY/);
  assert.match(s.detail, /did not respond/);
});

test("a healthy backend still reports its mode exactly as before", () => {
  const offline = describeBackendStatus({ ai_enabled: false, ai_model: null });
  assert.deepEqual([offline.title, offline.tone], ["Offline deterministic mode", "ok"]);
  assert.match(offline.detail, /No AI_API_KEY set/);
  assert.match(offline.detail, /full functionality retained/);

  const enhanced = describeBackendStatus({ ai_enabled: true, ai_model: "some-model" });
  assert.deepEqual([enhanced.title, enhanced.detail, enhanced.tone], ["Enhanced AI mode", "Model: some-model", "ok"]);
});

test("a health payload from the real backend (extra fields) is treated as healthy", () => {
  const s = describeBackendStatus({ status: "ok", ai_mode: "DETERMINISTIC_OFFLINE", ai_enabled: false, ai_model: null });
  assert.equal(s.title, "Offline deterministic mode");
});
