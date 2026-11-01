"""Layer separation at the source: relatedness (Layer B) candidates for an
issuer are issuers only. Counterparties (Layer C) and metadata nodes
(sectors, countries) are not "related" peers - counterparties reach an
issuer's view through the exposure join, search and the Graph Explorer's
exposure layer, all of which are unchanged.

No scoring formula changed: a pair scores the same whatever pool it came from.
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core import candidates, scoring  # noqa: E402
from app.core.config import DEFAULT_WEIGHTS  # noqa: E402
from app.core.data import STORE  # noqa: E402
from app.core.graph_store import counterparties_exposed_to  # noqa: E402
from app.core.semantic import SEMANTIC  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
ISSUERS = set(STORE.issuer_ids)


@pytest.mark.parametrize("issuer", STORE.issuer_ids)
def test_every_issuer_pool_is_issuers_only(issuer):
    c = candidates.generate_candidates(issuer)
    assert c["pool"] == "ISSUER_ONLY"
    assert issuer not in c["candidate_ids"]
    assert set(c["candidate_ids"]) <= ISSUERS, set(c["candidate_ids"]) - ISSUERS
    for source, ids in c["sources"].items():
        assert set(ids) <= ISSUERS, (source, set(ids) - ISSUERS)
    assert c["instrumentation"]["theoretical_pair_count"] == len(ISSUERS) - 1


def test_counterparty_centred_generation_is_unchanged_pending_authorisation():
    """The Distance Map's method is out of scope: it still sees the legacy pool."""
    seen_other_counterparty = False
    for cp in STORE.counterparty_ids:
        c = candidates.generate_candidates(cp)
        assert c["pool"] == "LEGACY_ALL_BROWSABLE"
        assert c["instrumentation"]["theoretical_pair_count"] == len(STORE.browsable_ids) - 1
        seen_other_counterparty |= any(i in STORE.counterparty_ids for i in c["candidate_ids"])
    assert seen_other_counterparty


def test_restricted_semantic_neighbours_still_return_k_and_keep_similarity_values():
    unrestricted = dict(SEMANTIC.nearest("JPM", 60))
    restricted = SEMANTIC.nearest("JPM", 15, among=ISSUERS)
    assert len(restricted) == 15 and all(i in ISSUERS for i, _ in restricted)
    for ident, sim in restricted:                       # the TF-IDF space is fitted on everything, as before
        assert sim == pytest.approx(unrestricted[ident])
    assert SEMANTIC.nearest("JPM", 15) == SEMANTIC.nearest("JPM", 15, among=None)   # default unchanged


def test_scores_do_not_depend_on_the_pool():
    """Formula untouched: every ranked pair equals a direct score of that pair."""
    for issuer in STORE.issuer_ids:
        body = client.get(f"/api/entities/{issuer}").json()
        for row in body["relationship_summary"]["top_related"]:
            direct = scoring.score_pair(issuer, row["entity_id"], DEFAULT_WEIGHTS)["composite"]
            assert row["composite_score"] == direct["score"]
            assert row["component_values"] == direct["component_values"]


def test_no_view_presents_a_non_issuer_as_related_to_an_issuer():
    for issuer in STORE.issuer_ids:
        rel = client.get(f"/api/entities/{issuer}").json()["relationship_summary"]["top_related"]
        assert {r["entity_id"] for r in rel} <= ISSUERS
        res = client.post("/api/model-lab/score", json={"entity_id": issuer}).json()["results"]
        assert {r["entity_id"] for r in res} <= ISSUERS
    for cp in STORE.counterparty_ids:
        rows = client.get(f"/api/counterparties/{cp}").json()["indirect_relationships"]
        assert {r["indirect_entity"] for r in rows} <= ISSUERS


def test_counterparties_remain_in_search_and_in_the_graph_explorer():
    for cp in STORE.counterparty_ids:
        r = client.get(f"/api/search?q={cp}").json()
        assert r["resolved_as"] == "counterparty" and r["resolved_id"] == cp

    for issuer in STORE.issuer_ids:
        graph = client.get(f"/api/graph/ego/{issuer}").json()                    # 1 hop, all layers
        exposed = {c["counterparty"] for c in counterparties_exposed_to(issuer)}
        shown = {n["id"] for n in graph["nodes"] if STORE.entity(n["id"])["node_type"] == "Counterparty"}
        assert shown == exposed, issuer                                          # exposure layer intact
        derived = [e for e in graph["edges"] if e.get("layer") == "DERIVED"]
        assert all(STORE.entity(e["source"])["node_type"] == "Company/Issuer" and
                   STORE.entity(e["target"])["node_type"] == "Company/Issuer" for e in derived)

    cp_graph = client.get("/api/graph/ego/CP_ALPHA?hops=1").json()
    assert {e["layer"] for e in cp_graph["edges"]} >= {"EXPOSURE"}               # counterparty centre unchanged
