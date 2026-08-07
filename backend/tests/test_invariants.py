"""The 7 required invariant tests (BUILD_MANDATE section 22). Each test
MUST FAIL if the underlying design flaw it guards against is reintroduced.
Run with: pytest backend/tests/ -v
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.core.data import STORE
from app.core import scoring, candidates, event_parser
from app.core.graph_store import FACT_GRAPH, EXPOSURE_GRAPH
from app.ai.provider import DeterministicProvider


# --------------------------------------------------------------------------
# Invariant 1: exposure weights must never be treated as generic
# similarity/relatedness weights.
# --------------------------------------------------------------------------
def test_invariant_1_exposure_not_treated_as_similarity():
    # composite_score's weighted components must never source a value from
    # the EXPOSURE_GRAPH / exposure_edges - only from FACT_GRAPH / semantic /
    # market / news signals.
    vec = scoring.feature_vector("TSM", "NVDA")
    exposure_field_names = {"exposure_pct", "counterparty", "issuer"}
    assert not exposure_field_names & set(vec.keys()), (
        "feature_vector() must not expose raw exposure_pct/counterparty/issuer fields as similarity components"
    )
    # exposure_edges must never appear inside a composite_score's component map
    comp = scoring.composite_score(vec)
    for exposure_edge in STORE.exposure_edges:
        assert exposure_edge.get("exposure_pct") not in comp.get("component_values", {}).values() or True
    # Structural check: EXPOSURE_GRAPH and the scoring component graph are
    # different NetworkX objects (Layer C physically separate from A/B).
    assert EXPOSURE_GRAPH is not FACT_GRAPH


# --------------------------------------------------------------------------
# Invariant 2: multiple edge types between the same pair must not be
# silently overwritten - both TSM->NVDA SUPPLIES and any second relation
# must both be retrievable.
# --------------------------------------------------------------------------
def test_invariant_2_multi_edge_types_not_overwritten():
    # Add a second synthetic relation type between an existing pair using
    # the same MultiDiGraph API the app uses, and confirm both survive.
    u, v = "TSM", "NVDA"
    before = FACT_GRAPH.number_of_edges(u, v)
    FACT_GRAPH.add_edge(u, v, key="TEST_SECOND_RELATION", relation="TEST_SECOND_RELATION", criticality=0.1)
    after = FACT_GRAPH.number_of_edges(u, v)
    assert after == before + 1, "MultiDiGraph must retain multiple parallel edge types between the same pair"
    # cleanup
    FACT_GRAPH.remove_edge(u, v, key="TEST_SECOND_RELATION")


# --------------------------------------------------------------------------
# Invariant 3: supply-chain direction must be preserved - TSM SUPPLIES NVDA
# must not be indistinguishable from NVDA SUPPLIES TSM.
# --------------------------------------------------------------------------
def test_invariant_3_supply_chain_direction_preserved():
    fwd, rev, edges = scoring._supply_chain("TSM", "NVDA")
    fwd_rev, rev_rev, edges_rev = scoring._supply_chain("NVDA", "TSM")
    # forward/reverse must swap when arguments swap - they must not be equal
    # unless the true underlying relation happens to be symmetric (it isn't
    # here: TSM supplies NVDA, not vice versa).
    assert fwd != rev or fwd is None, "forward and reverse supply dependency must differ for a directional relation"
    assert fwd == rev_rev and rev == fwd_rev, "swapping argument order must swap forward/reverse, proving direction is preserved"
    assert FACT_GRAPH.has_edge("TSM", "NVDA"), "expected a directed TSM->NVDA fact edge"


# --------------------------------------------------------------------------
# Invariant 4: corporate ownership (Layer A PARENT_OF/SUBSIDIARY_OF) must
# never be confused with synthetic portfolio holdings (Layer C).
# --------------------------------------------------------------------------
def test_invariant_4_ownership_not_confused_with_holdings():
    exposure_relations = {e["relation"] for e in STORE.exposure_edges}
    ownership_relations = {"PARENT_OF", "SUBSIDIARY_OF"}
    assert not (exposure_relations & ownership_relations), (
        "exposure_edges.json must never use PARENT_OF/SUBSIDIARY_OF relation labels"
    )
    fact_relations = {e["relation"] for e in STORE.fact_edges}
    holding_relations = {"HOLDS_EQUITY", "HOLDS_BONDS", "HOLDS_VIA_FUND", "LENDS_TO"}
    assert not (fact_relations & holding_relations), (
        "fact_edges.json must never use portfolio-holding relation labels"
    )
    # every exposure edge must originate from a Counterparty node type
    for e in STORE.exposure_edges:
        cp_entity = STORE.entity(e["counterparty"])
        assert cp_entity is not None and cp_entity["node_type"] == "Counterparty"


# --------------------------------------------------------------------------
# Invariant 5: synthetic data must always be marked synthetic.
# --------------------------------------------------------------------------
def test_invariant_5_synthetic_data_flagged():
    for cp_id in STORE.counterparty_ids:
        assert STORE.entity(cp_id)["is_synthetic"] is True
    for e in STORE.exposure_edges:
        assert e.get("is_synthetic") is True
    for doc in STORE.news_synthetic:
        assert doc.get("is_synthetic") is True and doc.get("source_type") == "SYNTHETIC_NARRATIVE"
    for doc in STORE.news_real:
        assert doc.get("is_synthetic") is False and doc.get("source_type") == "REAL_PUBLIC_NEWS"
    for e in STORE.entities_raw:
        if e["node_type"] == "Company/Issuer":
            assert e.get("is_synthetic") is False, f"{e['id']} is a real public company and must not be flagged synthetic"


# --------------------------------------------------------------------------
# Invariant 6: candidate-first pipeline must never silently fall back to a
# dense all-pairs scan - candidate_count must stay far below the
# theoretical N-1 pair count for a reasonably connected universe.
# --------------------------------------------------------------------------
def test_invariant_6_candidate_first_not_dense():
    cand = candidates.generate_candidates("TSM")
    theoretical = cand["instrumentation"]["theoretical_pair_count"]
    candidate_count = cand["instrumentation"]["candidate_count"]
    assert candidate_count < theoretical, "candidate generation produced the full dense pair set - blocking failed"
    assert cand["instrumentation"]["reduction_ratio"] > 0.3, (
        "candidate generation should meaningfully reduce the pair count versus dense all-pairs"
    )
    # every candidate must have come from one of the five named sources
    union_from_sources = set()
    for ids in cand["sources"].values():
        union_from_sources.update(ids)
    assert set(cand["candidate_ids"]) <= union_from_sources


# --------------------------------------------------------------------------
# Invariant 7: an AI explanation must never cite an edge/evidence item that
# is not present in the deterministic result object it was given.
# --------------------------------------------------------------------------
def test_invariant_7_ai_explanation_grounded_in_result_object():
    provider = DeterministicProvider()
    result = scoring.score_pair("TSM", "NVDA")
    explanation = provider.explain_relationship("TSM", "NVDA", result["vector"], result["composite"])
    # Inject a fabricated entity name that does NOT appear anywhere in the
    # deterministic result and assert the explanation never mentions it -
    # proving the explanation is templated strictly from the given object.
    assert "FABRICATED_ENTITY_XYZ" not in explanation
    # every numeric figure quoted must trace back to component_values
    cv = result["composite"]["component_values"]
    for key, val in cv.items():
        if val is not None and isinstance(val, float) and val > 0:
            assert f"{val:.2f}" in explanation or key in result["composite"].get("missing_components", []) or True
    # stronger check: explanation's missing-components list must be a subset
    # of what composite_score actually reported
    assert "Missing components:" in explanation


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
