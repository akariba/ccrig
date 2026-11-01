"""Holdings, reference entities and CCR exposures: three populations with three meanings, never mixed, never converted, never defaulted.
All rows here are TEST FIXTURES (flagged synthetic); no exposure value is real."""
import json

import pytest

from app.core.config import DATA_DIR
from app.studio import contracts, impact, report, resolve, review
from app.studio.store import StudioStore
from tests.relationship_helpers import AS_OF, ingest_rows
from tests.studio_helpers import tree_hash


@pytest.fixture
def ws(tmp_path):
    before = tree_hash(DATA_DIR)
    yield StudioStore(tmp_path / "ws")
    assert tree_hash(DATA_DIR) == before


def codes(store, job, severity=None):
    return {f["code"] for f in store.findings(job["job_id"]) if severity in (None, f["severity"])}


def ref(cp="CP_FUND_009", issuer="NVDA", product="TRS", kind="TRADE_REFERENCE_ENTITY", **kw):
    return {"counterparty_id": cp, "reference_entity_id": issuer, "product": product, "link_kind": kind, "as_of_date": "2026-08-01", "source_ref": "test-fixture", "is_synthetic": True, **kw}


def exp(cp="CP_HF_001", ns="NS-RATES-01", measure="PFE", value=815.0, **kw):
    row = {"counterparty_id": cp, "netting_set_id": ns, "as_of_date": "2026-08-01", "measure": measure, "value": value, "currency": "USD", "unit": "MILLIONS",
           "source_system": "test-fixture", "source_ref": "unit-test", "is_synthetic": True}
    row.update(kw)
    return row


def test_the_product_codes_match_the_platforms_product_taxonomy():
    assert list(json.loads((DATA_DIR / "product_taxonomy.json").read_text())["products"]) == list(contracts.PRODUCT_CODES)


# ------------------------------------------------------------------ the two counterparty populations stay apart
def test_ccr_counterparties_and_portfolio_counterparties_are_resolved_in_their_own_universe_only():
    ix = resolve.canonical_index()
    assert ix.resolve("CP_FUND_009", "ccr_counterparty").status == resolve.RESOLVED
    assert ix.resolve("CP_ALPHA", "ccr_counterparty").rule == "WRONG_UNIVERSE"                       # a portfolio counterparty is not a CCR counterparty
    assert ix.resolve("NVDA", "ccr_counterparty").rule == "WRONG_UNIVERSE"
    assert ix.resolve("CP_KESTREL", "ccr_counterparty").rule == "WRONG_UNIVERSE"                     # same name as CP_FUND_009's legal entity, still not the same record
    assert ix.resolve("CP_NOPE_9", "ccr_counterparty").rule == "NO_MATCH"
    assert ix.resolve("CP_FUND_009", "portfolio_counterparty").rule == "WRONG_UNIVERSE"


def test_direct_holdings_trade_references_and_inferred_dependencies_are_three_separate_datasets(ws):
    holdings = ingest_rows(ws, [{"counterparty": "CP_ALPHA", "issuer": "NVDA", "relation": "HOLDS_EQUITY", "exposure_pct": 0.1, "is_synthetic": True}], "exposure_edges", source_id="holdings-x", key="exposure_edges")
    refs = ingest_rows(ws, [ref(), ref(kind="INFERRED_DEPENDENCY", basis="Counterparty is a fund whose mandate concentrates in AI hardware (inference from its description, not a trade)")], "reference_entities", source_id="refs-x")
    assert not holdings["blocking"] and not refs["blocking"]
    review.approve(ws, holdings["job_id"], reviewer="r", reason="holdings", acknowledge_changes=True)
    review.approve(ws, refs["job_id"], reviewer="r", reason="trade reference and a labelled inference")
    assert {(c["dataset"], c["rows"]) for c in ws.list_current()} == {("exposure_edges", 1), ("reference_entities", 2)}
    rows = review.export(ws, "reference_entities")["canonical_shape"]["rows"]
    assert {r["link_kind"] for r in rows} == {"TRADE_REFERENCE_ENTITY", "INFERRED_DEPENDENCY"} and len(rows) == 2


def test_reference_entity_rules(ws):
    cases = {
        "UNRESOLVED_ENTITY": ref(cp="CP_ALPHA"),                       # a portfolio counterparty used as a CCR counterparty
        "INVALID_ENUM": ref(product="CRYPTO_SWAP"),
        "INFERRED_WITHOUT_BASIS": ref(kind="INFERRED_DEPENDENCY"),
        "FUTURE_DATE": ref(as_of_date="2027-01-01"),
        "MISSING_REQUIRED_VALUE": ref(source_ref=""),
    }
    for want, row in cases.items():
        job = ingest_rows(ws, [row], "reference_entities", source_id=f"c-{want.lower()}")
        assert job["blocking"] and want in codes(ws, job, "ERROR"), want
    wrong = next(f for f in ws.findings(ingest_rows(ws, [ref(cp="CP_ALPHA")], "reference_entities", source_id="c-unresolved_entity")["job_id"]) if f["code"] == "UNRESOLVED_ENTITY")
    assert wrong["rule"] == "WRONG_UNIVERSE" and "never merged" in wrong["message"]
    differs = ingest_rows(ws, [ref(issuer="AMD")], "reference_entities", source_id="differs")
    assert not differs["blocking"] and "DIFFERS_FROM_CCR_MASTER" in codes(ws, differs, "WARN")          # the master says CP_FUND_009's TRS references NVDA


def test_approved_reference_entities_appear_in_the_linked_counterparty_report_with_their_kind(ws):
    from app.studio import overlay
    from tests.relationship_helpers import ORACLE_QUOTE, oracle_source, rel_row

    review.approve(ws, ingest_rows(ws, [ref(cp="CP_FUND_ECR", issuer="ORCL", product="TRS", as_of_date="2026-09-01")], "reference_entities", source_id="refs-orcl")["job_id"], reviewer="r", reason="a TRS on Oracle")
    job = ingest_rows(ws, [rel_row(oracle_source(ws), "NVDA", "ORCL", "SUPPLIES", [ORACLE_QUOTE])])
    review.approve(ws, job["job_id"], reviewer="r", reason="ok", acknowledge_assertions=True)
    cur = ws.current("reference_entities")
    eff = impact.adoption_effect(overlay.load(ws)[0], ws.read_release(cur["release_id"])["rows"])
    orcl = eff["linked_counterparties"]["ccr_reference_entities"]["ORCL"]
    assert orcl == [{"ccr_counterparty": "CP_FUND_ECR", "product": "TRS", "kind": "approved trade_reference_entity"}]
    assert not any("No CCR record references ORCL" in g for g in eff["gaps"])
    assert any("No portfolio counterparty in the holdings data holds ORCL" in g for g in eff["gaps"]), "a trade reference is not a holding, and the holdings gap remains"
    assert any("No measured CCR exposure" in g for g in eff["gaps"]) and any("Wrong-way risk is not assessed" in g for g in eff["gaps"])


# ------------------------------------------------------------------ CCR exposures: typed, never converted, never defaulted
def test_typed_ccr_exposures_with_limit_utilization_and_lineage_are_staged_as_supplied(ws):
    rows = [exp(limit_id="LIM-HF001-PFE", limit_type="PFE_LIMIT", limit_value=1000.0), exp(measure="RC", value=210.0), exp(cp="CP_BANK_002", ns="NS-RATES-02", measure="NSE", value=700.0, limit_type="STRESS_LIMIT", limit_value=1000.0)]
    job = ingest_rows(ws, rows, "ccr_exposures", source_id="ccr-ok")
    assert job["status"] == "PENDING_REVIEW" and not job["blocking"], codes(ws, job)
    out = {(r["counterparty_id"], r["measure"]): r for r in ws.load_staging(job["job_id"])["proposed_rows"]}
    assert out[("CP_HF_001", "PFE")]["utilization"] == 0.815 and out[("CP_BANK_002", "NSE")]["utilization"] == 0.7
    assert out[("CP_HF_001", "RC")]["utilization"] is None and out[("CP_HF_001", "RC")]["limit_type"] is None
    assert out[("CP_HF_001", "PFE")]["value"] == 815.0 and out[("CP_HF_001", "PFE")]["unit"] == "MILLIONS" and out[("CP_HF_001", "PFE")]["source_system"] == "test-fixture"
    assert not any("wrong_way" in json.dumps(r).lower() for r in out.values()), "no wrong-way-risk field or interpretation is added"
    review.approve(ws, job["job_id"], reviewer="r", reason="fixtures")
    assert contracts.CONTRACTS["ccr_exposures"].notes.startswith("Values are taken exactly as supplied")


@pytest.mark.parametrize("rows,expect,category", [
    ([exp(), exp(cp="CP_BANK_002", ns="NS-RATES-02", value=620.0, unit="BILLIONS")], "INCONSISTENT_UNITS", "inconsistent_units"),
    ([exp(), exp(cp="CP_BANK_002", ns="NS-RATES-02", value=620.0, currency="EUR")], "INCONSISTENT_UNITS", "inconsistent_units"),
    ([exp(measure="RC", limit_type="PFE_LIMIT", limit_value=1000.0)], "LIMIT_MEASURE_MISMATCH", "inconsistent_units"),
    ([exp(limit_type="SETTLEMENT_LIMIT", limit_value=100.0)], "LIMIT_MEASURE_MISMATCH", "inconsistent_units"),
    ([exp(limit_type="PFE_LIMIT")], "LIMIT_VALUE_MISSING", "inconsistent_units"),
    ([exp(limit_value=500.0)], "LIMIT_TYPE_MISSING", "inconsistent_units"),
    ([exp(limit_type="PFE_LIMIT", limit_value=1000.0, utilization=0.5)], "UTILIZATION_MISMATCH", "inconsistent_units"),
    ([exp(utilization=0.5)], "UTILIZATION_WITHOUT_LIMIT", "inconsistent_units"),
    ([exp(cp="CP_NOPE_9")], "UNRESOLVED_ENTITY", "orphan_exposures"),
    ([exp(cp="CP_ALPHA")], "UNRESOLVED_ENTITY", "broken_joins"),
    ([exp(ns="NS-RATES-02")], "NETTING_SET_CONFLICT", "broken_joins"),
    ([exp(), exp(cp="CP_BANK_002", ns="NS-RATES-01", value=620.0)], "NETTING_SET_CONFLICT", "broken_joins"),
    ([exp(value=-5.0)], "OUT_OF_RANGE", "other"),
    ([exp(value=None)], "MISSING_REQUIRED_VALUE", "missing_references"),
    ([exp(currency="usd")], "PATTERN_MISMATCH", "other"),
    ([exp(unit="PERCENT")], "INVALID_ENUM", "other"),
    ([exp(as_of_date="2027-02-01")], "FUTURE_DATE", "other"),
    ([exp(source_system="")], "MISSING_REQUIRED_VALUE", "missing_references"),
    ([exp(), exp(value=900.0)], "DUPLICATE_CONFLICT", "duplicate_entities"),
])
def test_invalid_ccr_exposure_data_is_blocked_and_categorised(ws, rows, expect, category):
    job = ingest_rows(ws, rows, "ccr_exposures", source_id="ccr-bad")
    assert job["blocking"] and expect in codes(ws, job, "ERROR"), (expect, codes(ws, job))
    assert category in report.quality_report(ws, job["job_id"])["categories"] or category == "other"


def test_a_supplied_utilization_that_agrees_is_accepted_and_a_zero_limit_leaves_it_empty(ws):
    good = ingest_rows(ws, [exp(limit_type="PFE_LIMIT", limit_value=1000.0, utilization=0.815)], "ccr_exposures", source_id="util-good")
    assert not good["blocking"]
    zero = ingest_rows(ws, [exp(limit_type="PFE_LIMIT", limit_value=0.0)], "ccr_exposures", source_id="util-zero")
    assert not zero["blocking"] and "ZERO_LIMIT" in codes(ws, zero, "WARN") and ws.load_staging(zero["job_id"])["proposed_rows"][0]["utilization"] is None


def test_an_exposure_on_a_netting_set_the_master_does_not_list_is_an_orphan_warning(ws):
    job = ingest_rows(ws, [exp(ns="NS-RATES-99")], "ccr_exposures", source_id="orphan-ns")
    assert not job["blocking"] and "ORPHAN_NETTING_SET" in codes(ws, job, "WARN")
    rep = report.quality_report(ws, job["job_id"])
    assert rep["categories"]["orphan_exposures"]["warnings"] == 1 and "Warnings need a reviewer" in rep["verdict"]


def test_ccr_exposures_do_not_touch_the_canonical_ccr_dataset_or_the_priority_engine(ws):
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    before = [c.get(u).text for u in ("/api/priority-queue", "/api/breaches", "/api/counterparties")]
    assert all(len(t) > 100 for t in before)
    job = ingest_rows(ws, [exp(limit_type="PFE_LIMIT", limit_value=1000.0)], "ccr_exposures", source_id="ccr-queue")
    review.approve(ws, job["job_id"], reviewer="r", reason="fixtures")
    assert [c.get(u).text for u in ("/api/priority-queue", "/api/breaches", "/api/counterparties")] == before
