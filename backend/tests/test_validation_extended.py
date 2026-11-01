"""The extended validation harness: difficult cases, entity-disjoint holdout and
baseline comparisons. It must be able to FAIL: a deliberately wrong scorer must
lose, a perfect one must win, and nothing may be claimed that the data cannot
support (e.g. the existing anchor split is not entity-disjoint).
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core import calibration  # noqa: E402
from app.core.data import STORE  # noqa: E402
from validation import harness  # noqa: E402


@pytest.fixture(scope="module")
def extended():
    return harness.hard_cases_extended()


# ------------------------------------------------------------ folds
def test_folds_partition_the_issuers_deterministically():
    folds = harness.entity_folds()
    a, b = harness._fold_universe("A"), harness._fold_universe("B")
    assert set(a) | set(b) == set(STORE.issuer_ids) and not set(a) & set(b)
    assert abs(len(a) - len(b)) <= 1
    assert harness.entity_folds() == folds


def test_fold_retrieval_never_leaves_its_fold():
    ed = harness.entity_disjoint_holdout()
    assert set(ed["folds"]["A"]).isdisjoint(ed["folds"]["B"])
    pos = harness._positives()
    for fold, universe in ed["folds"].items():
        inside = set(universe)
        queries = [a for a in universe if pos[a] & inside]
        assert queries                                        # something to evaluate
        for variant, m in ed["per_fold"][fold].items():
            assert m["n_queries"] == len(queries), variant


def test_fitting_uses_only_anchors_entirely_inside_the_other_fold():
    folds = harness.entity_folds()
    info = harness.fitted_on_other_fold()
    for fold, rec in info.items():
        other = "B" if fold == "A" else "A"
        assert rec["fitted_on_fold"] == other and rec["tested_on_fold"] == fold
        assert all(folds[e] == other for e in rec["train_entities"])      # no entity from the tested fold
        assert not set(rec["train_entities"]) & set(harness._fold_universe(fold))
        if rec["n_anchors_used"] < harness.MIN_ANCHORS_TO_FIT:
            assert rec["status"] == "INSUFFICIENT_ANCHORS" and "weights" not in rec
        else:
            assert rec["status"] in ("fitted", "optimizer_did_not_converge_using_starting_weights")
            assert sum(rec["weights"].values()) == pytest.approx(1.0, abs=1e-3)


def test_the_existing_calibration_holdout_is_not_entity_disjoint():
    """Recorded so nobody reads its 9/9 as evidence of generalisation."""
    ev = harness.anchor_evaluation()
    ind = ev["existing_split_independence"]
    assert ind["holdout_anchors_sharing_an_entity_with_train"] == ind["n_holdout"] == 9
    assert ind["holdout_anchors_sharing_the_query_entity_with_train"] == 3
    cap = ev["entity_disjoint_capacity"]
    assert cap["anchors_fully_inside_fold_A"] + cap["anchors_fully_inside_fold_B"] + cap["anchors_crossing_folds_unusable"] == 34
    # the production calibration anchors/weights are untouched by the harness
    assert calibration.load_anchors()[0]["split"] in ("train", "holdout")


# ---------------------------------------------------------- hard cases
def test_hard_cases_are_derived_from_documented_data(extended):
    sector = lambda e: STORE.entity(e)["sector"]            # noqa: E731
    edges = harness._directed_edges()
    cross = [(a, b) for a, b in edges if sector(a) != sector(b)]
    assert extended["counts"]["directed_edges"] == len(edges) == 68
    assert extended["counts"]["hard_positive_edges"] == len(cross)
    assert extended["counts"]["easy_positive_edges"] == len(edges) - len(cross)
    assert extended["counts"]["hard_negative_triples"] > 0


def test_a_same_sector_ranker_cannot_find_cross_sector_edges(extended):
    sector_only = extended["variants"]["baseline_sector_only"]["hard_positives"]
    assert sector_only["share_in_top10"] == 0.0                       # by construction: it is what makes them hard
    assert extended["variants"]["baseline_random"]["partner_above_lookalike"] == 0.5


def test_harness_can_fail_and_can_win():
    """An oracle that knows the documented edges must beat everything; its mirror
    image must lose. If both scored alike the harness would measure nothing."""
    pairs = harness._pairs()
    issuers = STORE.issuer_ids
    oracle = lambda p: 1.0 if p["comp"]["supply_chain"] is not None else 0.0            # noqa: E731
    inverse = lambda p: 0.0 if p["comp"]["supply_chain"] is not None else 1.0           # noqa: E731
    best, worst = harness._evaluate(oracle, issuers), harness._evaluate(inverse, issuers)
    assert best["map"] == 1.0 and best["hit_at_5"] == 1.0
    assert worst["map"] < harness._evaluate(harness.BASELINES["baseline_random"], issuers)["map"]
    # pairwise on the documented edges themselves
    edges = harness._directed_edges()[:10]
    assert all(oracle(pairs[e]) > inverse(pairs[e]) for e in edges)


def test_expected_rank_handles_ties_like_a_random_tiebreak():
    assert harness._expected_rank({"a": 1, "b": 1, "c": 1, "d": 1}, "a") == 2.5
    assert harness._expected_rank({"a": 3, "b": 1, "c": 2}, "a") == 1
    assert harness._expected_rank({"a": 1, "b": 3, "c": 2}, "a") == 3


def test_pairwise_accuracy_counts_ties_as_half():
    anchors = calibration.load_anchors()[:6]
    assert harness._pairwise_accuracy(lambda p: 0.0, anchors) == 0.5
    assert harness._pairwise_accuracy(lambda p: 0.0, []) is None


def test_anchor_accuracy_shows_the_ceiling_effect():
    acc = harness.anchor_evaluation()["pairwise_accuracy"]
    assert acc["current_composite"]["all_34"] == 1.0
    assert acc["baseline_random"]["all_34"] == 0.5
    # the anchors are so easy that single features nearly match the composite:
    assert acc["baseline_sector_plus_semantic"]["all_34"] >= 0.95
