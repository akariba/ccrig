"""Tests for real GLEIF Level-2 corporate ownership (core/ownership.py)."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core import ownership as own
from app.core.data import STORE
from app.core import scoring


# --------------------------------------------------------------------------
# Main dataset: honest zero-result, never fabricated
# --------------------------------------------------------------------------
def test_main_dataset_has_no_fabricated_ownership():
    # Every one of the 40 LEI-bearing entities in this dataset is a
    # top-of-house public company; live GLEIF data (cached in
    # gleif_level2_cache.json) confirms zero of them report a parent. This
    # must remain False - it must NEVER be flipped by inventing an edge.
    assert STORE.has_ownership_data is False
    ownership_relations = {e["relation"] for e in STORE.fact_edges} & {"PARENT_OF", "SUBSIDIARY_OF"}
    assert not ownership_relations


def test_gleif_level2_cache_exists_and_is_real():
    cache = own.load_gleif_level2_cache()
    assert len(cache) >= 20
    for rec in cache.values():
        if "error" in rec:
            continue
        assert rec["source"] == "GLEIF"
        assert rec["source_type"] == "REAL_PUBLIC_DATA"


def test_build_ownership_fact_edges_is_noop_on_live_cache():
    # Calling the real pipeline against the real cache + real gleif_by_entity
    # mapping must reproduce STORE's own (empty) result deterministically.
    edges = own.build_ownership_fact_edges(STORE.gleif_by_entity)
    assert edges == []


def test_ownership_status_is_na_in_composite_score():
    comp = scoring.composite_score(scoring.feature_vector("TSM", "NVDA"))
    assert comp["ownership_status"] == "N/A (no ownership data in dataset)"
    assert "ownership" in comp["missing_components"]


# --------------------------------------------------------------------------
# Pipeline correctness proof: a SEPARATE real GLEIF parent/child pair
# (gleif_level2_demo.json), never merged into the main dataset.
# --------------------------------------------------------------------------
def _load_demo():
    from app.core.config import DATA_DIR
    with open(DATA_DIR / "gleif_level2_demo.json") as f:
        return json.load(f)


def test_demo_fixture_is_real_gleif_data():
    demo = _load_demo()
    assert demo["source"] == "GLEIF"
    assert demo["source_type"] == "REAL_PUBLIC_DATA"
    assert demo["relationship"]["relationship_type"] == "IS_DIRECTLY_CONSOLIDATED_BY"
    assert demo["parent"]["lei"] and demo["child"]["lei"]
    assert demo["parent"]["lei"] != demo["child"]["lei"]


def test_ownership_pipeline_works_on_real_external_pair():
    demo = _load_demo()
    gleif_by_entity = {
        "DEMO_PARENT": {"lei": demo["parent"]["lei"], "legal_name": demo["parent"]["legal_name"]},
        "DEMO_CHILD": {"lei": demo["child"]["lei"], "legal_name": demo["child"]["legal_name"]},
    }
    cache = {
        "DEMO_CHILD": {
            "lei": demo["child"]["lei"],
            "direct_parent": {"parent_lei": demo["parent"]["lei"], "child_lei": demo["child"]["lei"],
                               "relationship_type": demo["relationship"]["relationship_type"]},
            "ultimate_parent": None,
        }
    }
    edges = own.build_ownership_fact_edges(gleif_by_entity, gleif_cache=cache)
    assert len(edges) == 1
    edge = edges[0]
    assert edge["source"] == "DEMO_CHILD"
    assert edge["target"] == "DEMO_PARENT"
    assert edge["relation"] == "SUBSIDIARY_OF"
    assert edge["criticality"] == own.DIRECT_CRITICALITY
    assert edge["evidence_status"] == "REAL_PUBLIC_DATA"
    assert edge["gleif_relationship_type"] == "IS_DIRECTLY_CONSOLIDATED_BY"


def test_edges_only_created_when_both_ends_tracked():
    demo = _load_demo()
    # only the CHILD is "tracked" - parent LEI is unknown to us, so no edge
    # should be created (never link to an entity we don't actually have).
    gleif_by_entity = {"DEMO_CHILD": {"lei": demo["child"]["lei"], "legal_name": demo["child"]["legal_name"]}}
    cache = {
        "DEMO_CHILD": {
            "lei": demo["child"]["lei"],
            "direct_parent": {"parent_lei": demo["parent"]["lei"], "child_lei": demo["child"]["lei"],
                               "relationship_type": demo["relationship"]["relationship_type"]},
            "ultimate_parent": None,
        }
    }
    edges = own.build_ownership_fact_edges(gleif_by_entity, gleif_cache=cache)
    assert edges == []


def test_ultimate_only_gets_weaker_criticality_than_direct():
    demo = _load_demo()
    gleif_by_entity = {
        "DEMO_PARENT": {"lei": demo["parent"]["lei"], "legal_name": demo["parent"]["legal_name"]},
        "DEMO_CHILD": {"lei": demo["child"]["lei"], "legal_name": demo["child"]["legal_name"]},
    }
    cache = {
        "DEMO_CHILD": {
            "lei": demo["child"]["lei"],
            "direct_parent": None,
            "ultimate_parent": {"parent_lei": demo["parent"]["lei"], "child_lei": demo["child"]["lei"],
                                 "relationship_type": "IS_ULTIMATELY_CONSOLIDATED_BY"},
        }
    }
    edges = own.build_ownership_fact_edges(gleif_by_entity, gleif_cache=cache)
    assert len(edges) == 1
    assert edges[0]["criticality"] == own.ULTIMATE_ONLY_CRITICALITY
    assert edges[0]["criticality"] < own.DIRECT_CRITICALITY


def test_ownership_summary_reports_no_data_honestly():
    summary = own.ownership_summary_for_entity("TSM", STORE.entities_raw, STORE.gleif_by_entity)
    assert summary["has_any_ownership_data"] is False
    assert summary["direct_parent"] is None
    assert summary["note"] is not None
