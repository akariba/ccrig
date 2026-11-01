"""Request validation, enforced identically by FastAPI and by the in-browser
(Pyodide) dispatcher.

Each case is sent through BOTH paths. We require the expected status, and -
for 422s - identical error locations and types; for successes, identical
bodies. This is what keeps the static GitHub Pages build honest: it must
reject exactly what the server rejects, and accept what the server accepts.
"""
import math
import os
import sys

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import request_validation as validation  # noqa: E402
from app.browser_dispatch import _ROUTES, _iter_routes, dispatch  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.event import EventParseRequest  # noqa: E402
from app.routers.model_lab import CalibrateRequest, ScoreRequest  # noqa: E402
from validation import request_cases, snapshot  # noqa: E402

client = TestClient(app)
via_fastapi = snapshot.fastapi_request()
via_dispatch = snapshot.dispatch_request()

INVALID, VALID = request_cases.INVALID, request_cases.VALID


def _error_signature(body):
    return sorted((tuple(e["loc"]), e["type"]) for e in body["detail"])


@pytest.mark.parametrize("case", INVALID, ids=[c[0] for c in INVALID])
def test_invalid_input_rejected_identically(case):
    _, method, path, body, expected = case
    s1, b1 = via_fastapi(method, path, body)
    s2, b2 = via_dispatch(method, path, body)
    assert (s1, s2) == (expected, expected), (s1, s2, b1, b2)
    assert _error_signature(b1) == _error_signature(b2)


@pytest.mark.parametrize("case", VALID, ids=[c[0] for c in VALID])
def test_valid_input_accepted_identically(case):
    _, method, path, body, expected = case
    s1, b1 = via_fastapi(method, path, body)
    s2, b2 = via_dispatch(method, path, body)
    assert (s1, s2) == (expected, expected), (s1, s2)
    if expected == 200 and "event" not in path:
        # Event Studio list ordering is process-dependent in the app (see
        # validation/snapshot.py); its bodies are covered by the snapshot test.
        assert snapshot.diff(b1, b2) == [], snapshot.diff(b1, b2)


def test_analytics_snapshot_via_dispatcher_matches_baseline():
    """The in-browser path returns the same analytical outputs as the
    recorded server-side baseline (scores, ranks, priorities)."""
    actual = snapshot.normalise(snapshot.capture(via_dispatch))
    diffs = snapshot.diff(snapshot.load_snapshot(), actual)
    assert not diffs, "dispatcher output differs from the baseline:\n" + "\n".join(
        f"  {p}: expected {e!r}, got {a!r}" for p, e, a in diffs)


def test_dispatcher_never_leaks_query_marker_objects():
    """Regression: an omitted `Query(default=...)` used to reach the endpoint as
    the Query object itself, so e.g. the Distance Map 422'd in the static build."""
    status, body = dispatch("GET", "/api/distance-map/counterparty/CP_ALPHA", {"min_rho": "0"}, None)
    assert status == 200 and body["counterparty_id"] == "CP_ALPHA"


def test_unexpected_endpoint_errors_are_500_not_422(monkeypatch):
    import app.routers.entities as entities_router

    def boom(*a, **k):
        raise TypeError("a genuine bug, not a validation problem")

    monkeypatch.setattr(entities_router.STORE, "entity", boom)
    status, body = dispatch("GET", "/api/entities/TSM", {}, None)
    assert status == 500 and body == {"detail": "Internal Server Error"}


def test_every_application_route_is_served_by_the_dispatcher():
    """Adding an endpoint with an unsupported parameter kind (Depends, Header,
    Request, ...) makes the dispatcher raise at import; adding any endpoint
    must also make it reachable in the static build."""
    served = set()
    for methods, regex, _conv, endpoint, plan in _ROUTES:
        assert all(p.kind in {"path", "query", "body"} for p in plan)
        served |= {(endpoint.__module__ + "." + endpoint.__name__, m) for m in methods}
    declared_eps = {(r.endpoint.__module__ + "." + r.endpoint.__name__, m) for r in _iter_routes(app.router.routes)
                    if r.endpoint.__module__.startswith("app.") for m in r.methods}
    assert declared_eps and declared_eps == served, declared_eps ^ served


# ------------------------------------------------------------ unit: validators
def test_weight_validation_rules():
    for bad in ({"bogus": 1}, {"sector": -0.1}, {"sector": 1.01}, {"sector": math.nan},
                {"sector": math.inf}, {k: 0 for k in validation.WEIGHT_KEYS}, {}):
        with pytest.raises(ValidationError):
            ScoreRequest(entity_id="TSM", weights=bad)
    assert ScoreRequest(entity_id="TSM", weights={"sector": 0.15, "news": 0}).weights["news"] == 0
    assert ScoreRequest(entity_id="TSM").weights is None            # optional stays optional
    assert ScoreRequest(entity_id="TSM", preset="general").preset == "general"


def test_event_and_calibration_request_bounds():
    with pytest.raises(ValidationError):
        EventParseRequest(text="ok", min_score=math.nan)
    with pytest.raises(ValidationError):
        CalibrateRequest(gamma=math.inf)
    assert EventParseRequest(text="ok").max_hops == 2               # defaults unchanged
    assert EventParseRequest(text="a" * validation.MAX_TEXT_CHARS).top_k == 15
    assert CalibrateRequest().gamma == 8.0 and CalibrateRequest().lam == 2.0
