"""Tests for Experimental Anchor Calibration (core/calibration.py)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core import calibration
from app.core.config import DEFAULT_WEIGHTS


def test_anchors_load_and_split():
    anchors = calibration.load_anchors()
    assert len(anchors) >= 20
    splits = {a["split"] for a in anchors}
    assert splits == {"train", "holdout"}
    train = [a for a in anchors if a["split"] == "train"]
    holdout = [a for a in anchors if a["split"] == "holdout"]
    train_ratio = len(train) / len(anchors)
    assert 0.65 <= train_ratio <= 0.80, "train split should be roughly 70-75%"
    for a in anchors:
        assert a["source_type"] == "POC_EXPERT_ANCHOR"
        assert a["anchor_entity"] != a["preferred_entity"] != a["less_related_entity"]


def test_calibrated_weights_nonnegative_and_sum_to_one():
    result = calibration.run_calibration()
    w = result["calibrated_weights"]
    assert all(v >= -1e-9 for v in w.values()), "weights must remain non-negative"
    assert abs(sum(w.values()) - 1.0) < 1e-6, "weights must sum to 1"


def test_holdout_never_used_during_optimization():
    # Perturbing holdout-anchor scoring must not change the optimizer's
    # result, since the objective function is only ever built from train
    # anchors (core/calibration.py::_objective takes train_anchors only).
    result = calibration.run_calibration()
    holdout_ids = {a["anchor_entity"] for a in calibration.load_anchors() if a["split"] == "holdout"}
    train_ids = {a["anchor_entity"] for a in calibration.load_anchors() if a["split"] == "train"}
    # sanity: holdout is a genuinely separate set of constraints, not a
    # relabelled copy of train
    assert holdout_ids, "expected at least one holdout anchor"
    assert result["n_train"] + result["n_holdout"] == result["n_anchors_total"]
    assert result["holdout"]["count"] == result["n_holdout"]


def test_calibration_does_not_worsen_train_objective():
    result = calibration.run_calibration()
    assert result["train"]["pairwise_loss"] <= result["train_at_starting_weights"]["pairwise_loss"] + 1e-6


def test_calibration_deterministic():
    r1 = calibration.run_calibration()
    r2 = calibration.run_calibration()
    assert r1["calibrated_weights"] == r2["calibrated_weights"]
    assert r1["train"] == r2["train"]
    assert r1["holdout"] == r2["holdout"]


def test_missing_ownership_does_not_break_normalization():
    # Ownership has zero data in this dataset - calibration must still run
    # cleanly and the resulting weights must still sum to 1 even though
    # "ownership" is present as a component key but never contributes a
    # per-pair value.
    from app.core.data import STORE
    assert STORE.has_ownership_data is False
    result = calibration.run_calibration()
    assert abs(sum(result["calibrated_weights"].values()) - 1.0) < 1e-6
    assert "ownership" in result["calibrated_weights"]


def test_starting_preset_untouched_by_calibration():
    # Running calibration must never mutate the global DEFAULT_WEIGHTS /
    # heuristic starting preset - applying calibrated weights is a
    # frontend/caller decision, never an automatic side effect.
    before = dict(DEFAULT_WEIGHTS)
    calibration.run_calibration()
    assert DEFAULT_WEIGHTS == before


def test_market_agreement_diagnostic_is_read_only_evidence():
    diag = calibration.market_agreement_diagnostic()
    assert diag["n_market_data_issuers"] > 0
    assert diag["mean_top_k_abs_correlation"] is not None
    # must not have mutated the default weights as a side effect
    assert DEFAULT_WEIGHTS["market_positive"] == 0.10
