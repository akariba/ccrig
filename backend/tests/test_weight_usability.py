"""Weights placed only on components that cannot produce a score must be an
explicit error that says why - never an empty ranking that reads as "nothing
is related". No formula changes: requests that can be computed return exactly
what they returned before (see also the analytics baseline).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core import weight_usability as wu  # noqa: E402
from app.core.config import DEFAULT_WEIGHTS  # noqa: E402
from app.core.data import STORE  # noqa: E402
from validation import snapshot  # noqa: E402

via_fastapi = snapshot.fastapi_request()
via_dispatch = snapshot.dispatch_request()
BOTH = pytest.mark.parametrize("request_fn", [via_fastapi, via_dispatch], ids=["fastapi", "dispatcher"])


def score(request_fn, entity, weights):
    return request_fn("POST", "/api/model-lab/score", {"entity_id": entity, "weights": weights})


@BOTH
def test_dataset_wide_unusable_weights_name_the_component_and_the_reason(request_fn):
    status, body = score(request_fn, "TSM", {"ownership": 1})
    assert status == 422
    msg = body["detail"][0]["msg"]
    assert "ownership" in msg and "PARENT_OF" in msg and "no data in this dataset" in msg
    assert "sector" in msg                                   # tells the caller what they can use instead
    assert body["detail"][0]["loc"] == ["body", "weights"]


@BOTH
def test_entity_specific_failure_explains_which_entity_and_why(request_fn):
    status, body = score(request_fn, "SSNLF", {"market_positive": 0.5, "market_negative": 0.5})
    assert status == 422
    msg = body["detail"]
    assert isinstance(msg, str)
    assert "SSNLF" in msg and "market_positive" in msg and "no price history" in msg
    assert "Components that do have data" in msg and "sector" in msg

    status, body = score(request_fn, "IBM", {"supply_chain": 1})
    assert status == 422 and "IBM" in body["detail"] and "supply or licence" in body["detail"]


@BOTH
def test_pair_without_any_computable_weighted_component_is_an_error(request_fn):
    status, body = request_fn("POST", "/api/model-lab/pair", {"a": "TSM", "b": "JPM", "weights": {"supply_chain": 1}})
    assert status == 422 and "TSM / JPM" in body["detail"]


@BOTH
def test_computable_requests_are_not_affected(request_fn):
    for entity, weights in (("TSM", {"market_positive": 1}), ("TSM", {"ownership": 1, "sector": 0.2}),
                            ("TSM", {"supply_chain": 1}), ("TSM", None)):
        status, body = score(request_fn, entity, weights) if weights else request_fn(
            "POST", "/api/model-lab/score", {"entity_id": entity})
        assert status == 200 and body["scored_pair_count"] > 0 and body["results"], (entity, weights)


def test_the_error_replaces_a_silent_empty_ranking_without_touching_the_scorer():
    """Same inputs, scored directly: the scorer itself still returns nothing
    (unchanged); the API now refuses to present that as a result."""
    from app.core import candidates, scoring
    cand = candidates.generate_candidates("TSM")
    raw = scoring.rank_candidates("TSM", cand["candidate_ids"], {"ownership": 1.0})
    assert raw["scored_pair_count"] == 0 and raw["results"] == []


def test_dataset_reasons_follow_the_data(monkeypatch):
    assert "ownership" in wu.dataset_unusable_components()
    monkeypatch.setattr(STORE, "has_ownership_data", True)
    assert "ownership" not in wu.dataset_unusable_components()
    assert wu.dataset_problem({"ownership": 1}) is None
    monkeypatch.setattr(wu.scoring, "SUPPLY_RELATIONS", {"NO_SUCH_RELATION"})
    assert "supply_chain" in wu.dataset_unusable_components()


def test_mixed_weights_and_zero_weights():
    assert wu.dataset_problem(DEFAULT_WEIGHTS) is None
    assert wu.dataset_problem({"ownership": 0, "sector": 1}) is None
    assert wu.dataset_problem({"ownership": 1, "sector": 0}) is not None       # weight 0 does not count
    assert wu.weighted_components({"ownership": 1, "sector": 0}) == ["ownership"]
