"""Guards for the validation harness (backend/validation/).

* the analytical snapshot and the validation metrics still equal the
  recorded baselines - i.e. nothing changed a score, rank or priority;
* the comparison machinery itself behaves (tolerances, stabilisation);
* the snapshot does not depend on Python's per-process hash seed.

If a change is MEANT to alter analytics, regenerate with
`python -m validation.run --write-baseline` and justify the diff in the
commit message. Do not loosen these tests to make a change pass.
"""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from validation import harness, snapshot  # noqa: E402

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")


def _fmt(diffs):
    return "\n".join(f"  {p}: expected {e!r}, got {a!r}" for p, e, a in diffs)


def test_analytics_snapshot_matches_baseline():
    actual = snapshot.normalise(snapshot.capture(snapshot.fastapi_request()))
    diffs = snapshot.diff(snapshot.load_snapshot(), actual)
    assert not diffs, "analytical output drifted from the recorded baseline:\n" + _fmt(diffs)


def test_validation_metrics_match_baseline():
    expected = json.loads(snapshot.VALIDATION_FILE.read_text())
    actual = snapshot.normalise(harness.run_validation())
    diffs = snapshot.diff(expected, actual)
    assert not diffs, "validation metrics drifted from the recorded baseline:\n" + _fmt(diffs)


def test_snapshot_independent_of_hash_seed():
    """The snapshot records responses exactly as served (no sorting or
    masking), so it is only a stable baseline if the application itself is
    deterministic across processes. Checked here against a fresh process with
    an unrelated hash seed; the full sweep is tests/test_determinism.py."""
    env = {**os.environ, "PYTHONHASHSEED": "4242", "PYTHONWARNINGS": "ignore"}
    proc = subprocess.run(
        [sys.executable, "-m", "validation.run", "--check"],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_snapshot_covers_the_analytic_surface():
    snap = snapshot.load_snapshot()
    assert all(entry["status"] == 200 for entry in snap.values())
    for must_have in ("entity_360:TSM", "model_lab:default", "backtest:taiwan", "priority_queue",
                      "distance_map:CP_ALPHA", "event_parse:taiwan", "graph_ego:TSM:2"):
        assert must_have in snap


# ------------------------------------------------------------ machinery tests
def test_diff_uses_float_tolerance_and_reports_structure():
    assert snapshot.diff({"a": 1.0}, {"a": 1.0 + 1e-12}) == []
    assert snapshot.diff({"a": 1.0}, {"a": 1.001}) != []
    d = snapshot.diff({"a": [1, 2]}, {"a": [1, 2, 3], "b": 1})
    paths = {p for p, _, _ in d}
    assert "$.a.length" in paths and "$.b" in paths
    assert snapshot.diff({"a": None}, {"a": 0}) != []   # None is not 0
    assert snapshot.diff({"a": True}, {"a": 1}) != []   # bool is not int


def test_harness_reports_the_documented_hard_case_and_masks_edges():
    hc = harness.hard_cases()
    assert set(hc) >= {"tsm_rank_of_nvda_documented_customer_crit_0.95",
                       "tsm_rank_of_ssnlf_no_documented_supply_edge", "expectation_met"}
    # leave-edge-out must hide the edge-derived components from the scorer
    masked = harness._masked_weights()
    assert masked["supply_chain"] == 0.0 and masked["ownership"] == 0.0
    assert masked["sector"] > 0


@pytest.mark.parametrize("variant", ["current_composite", "baseline_random"])
def test_harness_metrics_are_well_formed(variant):
    m = harness.leave_edge_out()["all_issuers"][variant]
    assert 0.0 <= m["map"] <= 1.0 and m["map_ci95"][0] <= m["map"] <= m["map_ci95"][1] + 1e-9
    assert m["n_queries"] == 21
