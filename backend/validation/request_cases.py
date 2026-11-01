"""Shared request cases for the validation-parity checks.

Plain data (no pytest, no TestClient) so the same table can run natively
(tests/test_dispatcher_parity.py, FastAPI vs dispatcher) and inside a real
Pyodide runtime (frontend/scripts/verify-static-backend.mjs).
"""
from app import request_validation as validation

TOO_LONG = "x" * (validation.MAX_TEXT_CHARS + 1)
ALL_ZERO = {k: 0 for k in validation.WEIGHT_KEYS}

INGEST_DOC = {"id": "case_doc", "date": "2026-08-01", "title": "A title", "snippet": "A snippet."}

# (id, method, path, body, expected_status)
INVALID = [
    ("search-empty", "GET", "/api/search?q=", None, 422),
    ("search-missing", "GET", "/api/search", None, 422),
    ("search-too-long", "GET", f"/api/search?q={TOO_LONG}", None, 422),
    ("search-hops-0", "GET", "/api/search?q=hello&max_hops=0", None, 422),
    ("search-min-score-2", "GET", "/api/search?q=hello&min_score=2", None, 422),
    ("entities-limit-neg", "GET", "/api/entities?limit=-1", None, 422),
    ("entities-limit-0", "GET", "/api/entities?limit=0", None, 422),
    ("entities-limit-nan", "GET", "/api/entities?limit=abc", None, 422),
    ("entities-limit-huge", "GET", "/api/entities?limit=1001", None, 422),
    ("entity360-topk-neg", "GET", "/api/entities/TSM?top_k=-4", None, 422),
    ("entity360-topk-over-max", "GET", "/api/entities/TSM?top_k=51", None, 422),
    ("graph-topk-0", "GET", "/api/graph/ego/TSM?top_k=0", None, 422),
    ("graph-min-score-neg", "GET", "/api/graph/ego/TSM?min_score=-1", None, 422),
    ("distance-min-rho-5", "GET", "/api/distance-map/counterparty/CP_ALPHA?min_rho=5", None, 422),
    ("distance-hops-abc", "GET", "/api/distance-map/counterparty/CP_ALPHA?max_hops=abc", None, 422),
    ("distance-hops-9", "GET", "/api/distance-map/counterparty/CP_ALPHA?max_hops=9", None, 422),
    ("score-no-body-fields", "POST", "/api/model-lab/score", {}, 422),
    ("score-topk-str", "POST", "/api/model-lab/score", {"entity_id": "TSM", "top_k": "x"}, 422),
    ("score-topk-0", "POST", "/api/model-lab/score", {"entity_id": "TSM", "top_k": 0}, 422),
    ("score-topk-over-max", "POST", "/api/model-lab/score", {"entity_id": "TSM", "top_k": 10**9}, 422),
    ("score-negative-weight", "POST", "/api/model-lab/score",
     {"entity_id": "TSM", "weights": {"sector": -1, "supply_chain": 2}}, 422),
    ("score-weight-over-1", "POST", "/api/model-lab/score", {"entity_id": "TSM", "weights": {"sector": 1.5}}, 422),
    ("score-unknown-weight-key", "POST", "/api/model-lab/score", {"entity_id": "TSM", "weights": {"bogus": 1}}, 422),
    ("score-all-zero-weights", "POST", "/api/model-lab/score", {"entity_id": "TSM", "weights": ALL_ZERO}, 422),
    ("score-unknown-preset", "POST", "/api/model-lab/score", {"entity_id": "TSM", "preset": "nope"}, 422),
    ("score-empty-entity", "POST", "/api/model-lab/score", {"entity_id": ""}, 422),
    ("pair-missing-b", "POST", "/api/model-lab/pair", {"a": "TSM"}, 422),
    ("pair-bad-weights", "POST", "/api/model-lab/pair", {"a": "TSM", "b": "NVDA", "weights": {"bogus": 1}}, 422),
    ("calibration-gamma-0", "POST", "/api/model-lab/calibration/run", {"gamma": 0}, 422),
    ("calibration-bad-start", "POST", "/api/model-lab/calibration/run", {"starting_weights": {"x": 1}}, 422),
    ("market-agreement-topk-0", "POST", "/api/model-lab/calibration/market-agreement", {"top_k": 0}, 422),
    ("event-no-text", "POST", "/api/event/parse", {}, 422),
    ("event-empty-text", "POST", "/api/event/parse", {"text": ""}, 422),
    ("event-blank-text", "POST", "/api/event/parse", {"text": "   \n\t "}, 422),
    ("event-too-long", "POST", "/api/event/parse", {"text": TOO_LONG}, 422),
    ("event-hops-0", "POST", "/api/event/parse", {"text": "x", "max_hops": 0}, 422),
    ("event-hops-9", "POST", "/api/event/parse", {"text": "x", "max_hops": 9}, 422),
    ("event-min-score-2", "POST", "/api/event/parse", {"text": "x", "min_score": 2}, 422),
    ("event-topk-0", "POST", "/api/event/parse", {"text": "x", "top_k": 0}, 422),
    ("event-non-object-body", "POST", "/api/event/parse", ["not", "an", "object"], 422),
    # weights placed only on components that have no usable data: an explicit error, never an empty ranking
    ("score-ownership-only", "POST", "/api/model-lab/score", {"entity_id": "TSM", "weights": {"ownership": 1}}, 422),
    ("score-market-only-unpriced-entity", "POST", "/api/model-lab/score",
     {"entity_id": "SSNLF", "weights": {"market_positive": 0.5, "market_negative": 0.5}}, 422),
    ("score-supply-only-entity-without-edges", "POST", "/api/model-lab/score",
     {"entity_id": "IBM", "weights": {"supply_chain": 1}}, 422),
    ("pair-ownership-only", "POST", "/api/model-lab/pair",
     {"a": "TSM", "b": "NVDA", "weights": {"ownership": 1}}, 422),
    ("pair-supply-only-unlinked-pair", "POST", "/api/model-lab/pair",
     {"a": "TSM", "b": "JPM", "weights": {"supply_chain": 1}}, 422),
    ("calibration-ownership-only", "POST", "/api/model-lab/calibration/run",
     {"starting_weights": {"ownership": 1}}, 422),
    ("market-agreement-ownership-only", "POST", "/api/model-lab/calibration/market-agreement",
     {"weights": {"ownership": 1}}, 422),
    ("ingest-forged-synthetic-flag", "POST", "/api/themes/ingest", {**INGEST_DOC, "is_synthetic": False}, 422),
    ("ingest-javascript-url", "POST", "/api/themes/ingest", {**INGEST_DOC, "url": "javascript:alert(1)"}, 422),
    ("ingest-poison-keywords", "POST", "/api/themes/ingest", {**INGEST_DOC, "keywords": [[1]]}, 422),
    ("ingest-bad-date", "POST", "/api/themes/ingest", {**INGEST_DOC, "date": "soon"}, 422),
    ("ingest-missing-fields", "POST", "/api/themes/ingest", {"id": "only-an-id"}, 422),
]

# Valid requests that previously worked (or must keep working) - bodies must match too.
VALID = [
    ("distance-map-no-params", "GET", "/api/distance-map/counterparty/CP_ALPHA", None, 200),
    ("distance-map-min-rho-only", "GET", "/api/distance-map/counterparty/CP_ALPHA?min_rho=0", None, 200),
    ("entities-defaults", "GET", "/api/entities", None, 200),
    ("entities-limit-5", "GET", "/api/entities?limit=5", None, 200),
    ("entity360-defaults", "GET", "/api/entities/TSM", None, 200),
    ("graph-defaults", "GET", "/api/graph/ego/TSM", None, 200),
    ("graph-hops-clamped", "GET", "/api/graph/ego/TSM?hops=99", None, 200),
    ("search-entity", "GET", "/api/search?q=IBM", None, 200),
    ("themes-list", "GET", "/api/themes", None, 200),
    ("themes-filter", "GET", "/api/themes?kind=curated_theme", None, 200),
    ("priority-queue", "GET", "/api/priority-queue", None, 200),
    ("priority-queue-filter", "GET", "/api/priority-queue?priority=high", None, 200),
    ("breaches", "GET", "/api/breaches", None, 200),
    ("backtest-default", "GET", "/api/backtest/run", None, 200),
    ("backtest-unimplemented", "GET", "/api/backtest/run?scenario_id=svb_collapse", None, 400),
    ("score-defaults", "POST", "/api/model-lab/score", {"entity_id": "TSM"}, 200),
    ("score-lowercase-id", "POST", "/api/model-lab/score", {"entity_id": "tsm"}, 200),
    ("score-preset", "POST", "/api/model-lab/score", {"entity_id": "TSM", "preset": "supply_chain_shock"}, 200),
    ("score-partial-weights", "POST", "/api/model-lab/score",
     {"entity_id": "TSM", "weights": {"sector": 0.3, "supply_chain": 0.2}}, 200),
    ("score-boundary-weights", "POST", "/api/model-lab/score",
     {"entity_id": "TSM", "weights": {"sector": 0, "news": 1}, "top_k": 50}, 200),
    ("pair", "POST", "/api/model-lab/pair", {"a": "TSM", "b": "NVDA"}, 200),
    ("event-parse", "POST", "/api/event/parse", {"text": "TSMC fab outage in Taiwan"}, 200),
    ("event-parse-bounds", "POST", "/api/event/parse",
     {"text": "TSMC fab outage in Taiwan", "max_hops": 3, "min_score": 0, "top_k": 50}, 200),
    ("event-unicode", "POST", "/api/event/parse", {"text": "台積電 地震 NVDA"}, 200),
    # unknown things stay 404/405, not 422
    ("unknown-entity", "GET", "/api/entities/NOPE", None, 404),
    ("unknown-counterparty", "GET", "/api/counterparties/NOPE", None, 404),
    ("unknown-path", "GET", "/api/nope", None, 404),
    ("wrong-method", "POST", "/api/health", None, 405),
    ("score-unknown-entity", "POST", "/api/model-lab/score", {"entity_id": "NOPE"}, 404),
    # weight on a component without data is fine as long as another weighted component can be computed
    ("score-market-only-priced-entity", "POST", "/api/model-lab/score",
     {"entity_id": "TSM", "weights": {"market_positive": 1}}, 200),
    ("score-ownership-plus-sector", "POST", "/api/model-lab/score",
     {"entity_id": "TSM", "weights": {"ownership": 1, "sector": 0.2}}, 200),
    ("score-supply-only-entity-with-edges", "POST", "/api/model-lab/score",
     {"entity_id": "TSM", "weights": {"supply_chain": 1}}, 200),
    # ingestion is off unless CCRIG_ENABLE_INGEST=1, so a well-formed document is refused, not stored
    ("ingest-disabled-by-default", "POST", "/api/themes/ingest", INGEST_DOC, 403),
]
