"""Backtest methodology v2.

The original (v1) numbers are kept, unchanged, beside the corrected ones, and
every correction is tested against the weakness it fixes.
"""
import json
import math
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core import backtest, market  # noqa: E402
from app.core.data import STORE  # noqa: E402
from validation import snapshot  # noqa: E402

BEFORE = json.load(open(os.path.join(snapshot.BASELINE_DIR, "backtest_before_correction.json")))
T0 = date(2026, 7, 6)


@pytest.fixture(scope="module")
def result():
    return backtest.run_backtest("taiwan_earthquake_2026")


# --------------------------------------------------------------- before / after
def test_legacy_procedure_is_preserved_exactly(result):
    legacy = result["legacy"]
    assert legacy["metrics"] == BEFORE["metrics"]
    assert legacy["model_ranking_top_k"] == BEFORE["model_ranking_top_k"]
    assert legacy["observed_subsequent_movers_top_k"] == BEFORE["observed_subsequent_movers_top_k"]
    assert BEFORE["metrics"]["precision_at_5"] == 0.6      # what Phase 1 published


def test_corrections_are_attributed_step_by_step(result):
    steps = result["correction_steps"]
    assert [s["step"] for s in steps] == [0, 1, 2, 3]
    assert steps[0]["precision_at_5"] == BEFORE["metrics"]["precision_at_5"]
    final = steps[-1]
    for key in ("precision_at_5", "recall_at_5", "ndcg_at_5", "universe_size", "n_positive"):
        assert final[key] == result["metrics"][key]


# ------------------------------------------------------------------ the fixes
def test_entities_named_in_the_event_are_inputs_not_predictions(result):
    seeds = set(result["seed_entities"]["entities"])
    assert seeds == {"AAPL", "AMD", "NVDA", "TSM"}
    assert not seeds & set(result["evaluation"]["universe"])
    assert not seeds & {r["entity_id"] for r in result["model_ranking_top_k"]}
    assert not seeds & {r["entity_id"] for r in result["observed_subsequent_movers_top_k"]}
    assert {"AAPL", "AMD", "NVDA", "TSM"} <= {r["entity_id"] for r in result["legacy"]["model_ranking_top_k"]}   # v1 did


def test_every_entity_is_measured_over_the_same_window(result):
    windows = {(r["from_date"], r["to_date"]) for r in result["observed_subsequent_movers_top_k"]}
    assert windows == {("2026-07-06", "2026-07-13")}
    excluded = {e["entity_id"]: e for e in result["evaluation"]["excluded"]}
    assert excluded["SKHY"]["status"] == "HISTORY_STARTS_AFTER_T0"
    assert "SKHY" not in result["evaluation"]["universe"]
    legacy_skhy = [r for r in result["legacy"]["observed_subsequent_movers_top_k"] if r["entity_id"] == "SKHY"][0]
    assert legacy_skhy["from_date"] == "2026-07-10"        # the v1 defect: a window four days late


def test_label_is_market_adjusted(result):
    universe = result["evaluation"]["universe"]
    raw = {e: market.window_return(e, T0, 5)["return"] for e in universe}
    n = len(universe)
    expected = {e: raw[e] - (sum(raw.values()) - raw[e]) / (n - 1) for e in universe}
    assert sum(expected.values()) == pytest.approx(0, abs=1e-12)         # leave-one-out adjustment sums to zero
    shown = {r["entity_id"]: r for r in result["observed_subsequent_movers_top_k"]}
    for e, row in shown.items():
        assert row["abnormal_return"] == pytest.approx(expected[e], abs=1e-5)
        assert row["return"] == pytest.approx(raw[e], abs=1e-5)


def test_positive_set_is_proportional_and_beside_a_random_baseline(result):
    m = result["metrics"]
    n = m["universe_size"]
    assert m["n_positive"] == max(2, round(n / 3)) and m["n_positive"] < n / 2
    for k in (3, 5):
        assert m[f"random_precision_at_{k}"] == pytest.approx(m["n_positive"] / n, abs=1e-4)
        assert 0 <= m[f"p_value_at_{k}"] <= 1
        assert 0 <= m[f"precision_at_{k}"] <= 1 and 0 <= m[f"recall_at_{k}"] <= 1 and 0 <= m[f"ndcg_at_{k}"] <= 1
    positives = [r["entity_id"] for r in result["observed_subsequent_movers_top_k"] if r["is_label_positive"]]
    assert len(positives) == m["n_positive"]


def test_hypergeometric_tail_is_exact():
    assert backtest._hypergeom_tail(9, 3, 5, 0) == pytest.approx(1.0)
    assert backtest._hypergeom_tail(9, 3, 3, 3) == pytest.approx(1 / math.comb(9, 3))
    # P(X>=1), N=9, K=3, n=5  = 1 - C(6,5)/C(9,5)
    assert backtest._hypergeom_tail(9, 3, 5, 1) == pytest.approx(1 - math.comb(6, 5) / math.comb(9, 5))
    tails = [backtest._hypergeom_tail(12, 4, 6, h) for h in range(0, 5)]
    assert tails == sorted(tails, reverse=True)


def test_honest_framing_is_kept(result):
    joined = " ".join(result["warnings"])
    assert "SYNTHETIC" in joined and "SCENARIO REPLAY" in joined
    assert "luck" in joined or "chance" in joined
    assert result["news_source"]["is_synthetic"] is True


# ---------------------------------------------------------------- the model
@pytest.fixture
def prices_scaled_after_t0(monkeypatch):
    """Scale every close AFTER T0 by 1.5, with the derived-returns cache cleared
    before and after so the perturbation can never leak into other tests."""
    market._RETURNS_CACHE.clear()
    monkeypatch.setattr(STORE, "prices",
                        {t: [(d, c * 1.5 if d > T0 else c) for d, c in rows] for t, rows in STORE.prices.items()})
    yield
    monkeypatch.undo()
    market._RETURNS_CACHE.clear()


def test_model_score_is_unchanged_and_look_ahead_safe():
    """The correction touches the evaluation only. Prices AFTER T0 must not move
    a single model score; the labels, of course, do move."""
    narrative = next(d for d in STORE.news_all if d["id"] == "n11")["text"]
    entities, themes = backtest.detect_entities(narrative), backtest.detect_themes(narrative)
    market._RETURNS_CACHE.clear()
    before_scores = backtest._model_scores(entities, themes, T0)
    before_labels = market.window_return("INTC", T0, 5)["return"]

    market._RETURNS_CACHE.clear()
    shifted = {t: [(d, c * 1.5 if d > T0 else c) for d, c in rows] for t, rows in STORE.prices.items()}
    original = STORE.prices
    STORE.prices = shifted
    try:
        after_scores = backtest._model_scores(entities, themes, T0)
        after_labels = market.window_return("INTC", T0, 5)["return"]
    finally:
        STORE.prices = original
        market._RETURNS_CACHE.clear()
    assert before_scores == after_scores
    assert before_labels != after_labels


def test_perturbation_does_not_leak_into_later_tests(prices_scaled_after_t0):
    assert STORE.prices[STORE.entity("INTC")["ticker"]][-1][1] != 0


def test_state_is_restored_after_the_perturbation_fixture():
    market._RETURNS_CACHE.clear()
    assert market.window_return("INTC", T0, 5)["return"] == pytest.approx(-0.15614, abs=1e-4)   # real data again


# --------------------------------------------------- window helper edge cases
def test_window_return_statuses():
    assert market.window_return("INTC", T0)["status"] == "OK"
    assert market.window_return("SKHY", T0)["status"] == "HISTORY_STARTS_AFTER_T0"
    assert market.window_return("SSNLF", T0)["status"] == "NO_PRICE_HISTORY"            # unpriced issuer
    assert market.window_return("INTC", date(2030, 1, 1))["status"] == "NO_CLOSE_AT_T0"      # series ends long before
    last = STORE.prices[STORE.entity("INTC")["ticker"]][-1][0]
    assert market.window_return("INTC", last)["status"] == "INSUFFICIENT_FORWARD_DATA"      # T0 at the end: no forward window
    assert market.window_return("INTC", date(2020, 1, 1))["status"] == "HISTORY_STARTS_AFTER_T0"
    weekend = market.window_return("INTC", date(2026, 7, 4))                              # Saturday: last close <= T0
    assert weekend["status"] == "OK" and weekend["from_date"] <= "2026-07-04"


def test_window_return_requires_a_close_near_t0(monkeypatch):
    rows = [(date(2026, 6, 1) + __import__("datetime").timedelta(days=i), 100.0 + i) for i in range(5)]   # ends 06-05
    rows += [(date(2026, 7, 20) + __import__("datetime").timedelta(days=i), 100.0) for i in range(10)]   # resumes 07-20
    monkeypatch.setitem(STORE.prices, STORE.entity("INTC")["ticker"], rows)
    assert market.window_return("INTC", T0)["status"] == "NO_CLOSE_AT_T0"                 # 4 weeks stale is not "T0"
