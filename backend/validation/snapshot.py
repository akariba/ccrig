"""Golden snapshot of the application's analytical outputs.

Records what a fixed set of endpoints returns for fixed inputs, so a change
that is *not meant* to alter analytics (validation, CORS, dependencies, ...)
can be proven not to have moved a score, a rank, or a priority.

`capture(request)` is client-agnostic: `request(method, path, body)` returns
`(status, json_body)`. The tests drive it through both the FastAPI app and
the in-browser (Pyodide) dispatcher and require identical output.

Responses are recorded exactly as served: nothing is sorted, masked or
reduced. The application's output is deterministic across processes and
Python hash seeds (see validation/determinism.py and tests/test_determinism.py),
so list ORDER is part of what the baseline pins.

Deliberately excluded: anything time- or environment-dependent (the
scalability benchmark's timings) and the SLSQP calibration endpoints (their
last digits depend on the scipy build).
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable

Request = Callable[[str, str, Any], "tuple[int, Any]"]

BASELINE_DIR = Path(__file__).resolve().parent / "baseline"
SNAPSHOT_FILE = BASELINE_DIR / "analytics_snapshot.json"
VALIDATION_FILE = BASELINE_DIR / "validation_baseline.json"

FLOAT_TOLERANCE = 1e-9

_EVENT_TEXT = (
    "A magnitude 7.2 earthquake struck near Hsinchu, Taiwan, disrupting semiconductor "
    "fabrication at several TSMC plants and raising concerns for NVIDIA, AMD and Apple chip supply."
)
_ENTITY_KEYS = [
    "header", "relationship_summary", "fact_links", "supply_chain", "ownership",
    "corporate_hierarchy", "counterparty_materiality", "theme_exposure", "counterparties_exposed",
]

# (name, method, path, body, keys_to_keep | None for the whole response)
REQUESTS: list = [
    *[(f"entity_360:{e}", "GET", f"/api/entities/{e}", None, _ENTITY_KEYS)
      for e in ("TSM", "NVDA", "JPM", "IBM", "SSNLF", "SKHY")],
    ("explain:TSM->NVDA", "GET", "/api/entities/TSM/explain/NVDA", None, None),
    ("explain:TSM->SSNLF", "GET", "/api/entities/TSM/explain/SSNLF", None, None),
    ("model_lab:default", "POST", "/api/model-lab/score", {"entity_id": "TSM", "top_k": 15}, None),
    *[(f"model_lab:{p}", "POST", "/api/model-lab/score", {"entity_id": "TSM", "preset": p, "top_k": 15}, None)
      for p in ("general", "supply_chain_shock", "market_funding_shock", "thematic_tech_shock")],
    ("model_lab:pair", "POST", "/api/model-lab/pair", {"a": "TSM", "b": "NVDA"}, None),
    ("backtest:taiwan", "GET", "/api/backtest/run?scenario_id=taiwan_earthquake_2026", None, None),
    ("priority_queue", "GET", "/api/priority-queue", None, None),
    ("breaches", "GET", "/api/breaches", None, None),
    ("distance_map:CP_ALPHA", "GET", "/api/distance-map/counterparty/CP_ALPHA?min_rho=0&max_hops=2", None, None),
    ("distance_map:CP_CASCADE", "GET", "/api/distance-map/counterparty/CP_CASCADE?min_rho=0&max_hops=2", None, None),
    ("graph_ego:TSM:2", "GET", "/api/graph/ego/TSM?hops=2", None, None),
    ("counterparty_360:CP_ALPHA", "GET", "/api/counterparties/CP_ALPHA", None, None),
    ("event_parse:taiwan", "POST", "/api/event/parse", {"text": _EVENT_TEXT}, None),
    ("search:IBM", "GET", "/api/search?q=IBM", None, None),
    ("search:event", "GET", "/api/search?q=TSMC supply disruption after Taiwan earthquake", None, None),
    ("themes", "GET", "/api/themes", None, None),
    ("provenance", "GET", "/api/provenance", None, None),
    ("model_lab:presets", "GET", "/api/model-lab/presets", None, None),
]


def capture(request: Request) -> dict:
    out = {}
    for name, method, path, body, keys in REQUESTS:
        status, data = request(method, path, body)
        if keys is not None and isinstance(data, dict):
            data = {k: data[k] for k in keys if k in data}
        if name == "provenance" and isinstance(data, dict) and "generated_at" in data:
            data = {**data, "generated_at": "<clock>"}       # wall-clock output (today's date): masked, so the baseline does not expire at midnight
        out[name] = {"status": status, "body": data}
    return out


def fastapi_request() -> Request:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    def request(method: str, path: str, body):
        resp = client.request(method, path, json=body) if body is not None else client.request(method, path)
        return resp.status_code, resp.json()

    return request


def dispatch_request() -> Request:
    """Same contract as `fastapi_request`, but through the in-browser
    (Pyodide) dispatcher: no HTTP, query values arrive as strings exactly as
    the frontend's URLSearchParams would deliver them."""
    from urllib.parse import parse_qsl, urlsplit

    from app.browser_dispatch import dispatch

    def request(method: str, path: str, body):
        parts = urlsplit(path)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        status, data = dispatch(method, parts.path, query, body)
        return status, json.loads(json.dumps(data))

    return request


def normalise(data: Any) -> Any:
    """JSON round-trip, so tuples/dataclass output compare like HTTP bodies."""
    return json.loads(json.dumps(data))


def diff(expected: Any, actual: Any, path: str = "$", limit: int = 20) -> list:
    """Structural diff with a float tolerance. Returns up to `limit` differences."""
    diffs: list = []

    def walk(e, a, p):
        if len(diffs) >= limit:
            return
        if isinstance(e, bool) or isinstance(a, bool) or e is None or a is None:
            # `True == 1` in Python, so compare types too: a bool/None changing
            # into a number (or vice versa) is a real difference.
            if type(e) is not type(a) or e != a:
                diffs.append((p, e, a))
        elif isinstance(e, (int, float)) and isinstance(a, (int, float)):
            if not math.isclose(e, a, rel_tol=FLOAT_TOLERANCE, abs_tol=FLOAT_TOLERANCE):
                diffs.append((p, e, a))
        elif isinstance(e, dict) and isinstance(a, dict):
            for k in sorted(set(e) | set(a)):
                if k not in e:
                    diffs.append((f"{p}.{k}", "<absent>", a[k]))
                elif k not in a:
                    diffs.append((f"{p}.{k}", e[k], "<absent>"))
                else:
                    walk(e[k], a[k], f"{p}.{k}")
        elif isinstance(e, list) and isinstance(a, list):
            if len(e) != len(a):
                diffs.append((f"{p}.length", len(e), len(a)))
            for i, (x, y) in enumerate(zip(e, a)):
                walk(x, y, f"{p}[{i}]")
        elif e != a:
            diffs.append((p, e, a))

    walk(expected, actual, path)
    return diffs


def load_snapshot() -> dict:
    return json.loads(SNAPSHOT_FILE.read_text())


def write_snapshot(snapshot: dict) -> None:
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_FILE.write_text(json.dumps(snapshot, indent=1, sort_keys=True) + "\n")
