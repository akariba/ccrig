"""Entity resolution outcomes, staging conflicts, approval gates, rejection, rollback atomicity."""
import json

import pytest

from app.core.config import DATA_DIR
from app.studio import pipeline, resolve, review
from app.studio.resolve import AMBIGUOUS, MAPPED, RESOLVED, UNRESOLVED, EntityIndex, canonical_index
from app.studio.store import StudioStore
from tests.studio_helpers import codes, csv_bytes, edge, edges_csv, run, tree_hash


@pytest.fixture
def store(tmp_path):
    return StudioStore(tmp_path / "ws")


@pytest.fixture(autouse=True)
def canonical_untouched():
    before = tree_hash(DATA_DIR)
    yield
    assert tree_hash(DATA_DIR) == before


# ------------------------------------------------------------------ resolution
def test_exact_identifiers_come_first_and_no_fuzzy_match_is_ever_applied():
    ix = canonical_index()
    assert ix.resolve("TSM").status == RESOLVED and ix.resolve("TSM").rule == "EXACT_ID"
    n = ix.resolve("  nvda ")
    assert (n.status, n.entity_id, n.rule) == (RESOLVED, "NVDA", "NORMALIZED_ID")
    arm, hsbc = ix.resolve("Arm Holdings plc"), ix.resolve("HSBC Holdings plc")
    assert (arm.status, arm.entity_id, arm.rule) == (MAPPED, "ARM", "NAME_EXACT") and hsbc.entity_id == "HSBC"        # the token-overlap defect cannot recur here
    shared = ix.resolve("Holdings plc")
    assert shared.status == UNRESOLVED and shared.rule == "NO_MATCH"
    for near in ("TSMC", "Nvidia Corp", "Alphabet", "Taiwan Semiconductor"):
        assert ix.resolve(near).status == UNRESOLVED, near
    alias = ix.resolve("Google Cloud")
    assert (alias.status, alias.entity_id, alias.rule) == (MAPPED, "GOOGL", "ALIAS")
    assert ix.resolve("Samsung").rule == "DENIED_ALIAS" and ix.resolve("Samsung").status == UNRESOLVED
    assert ix.resolve("").rule == "EMPTY"


def test_ambiguous_outcomes_list_every_candidate_and_choose_none():
    ix = EntityIndex([{"id": "A1", "name": "Acme Corp", "ticker": "ACM", "node_type": "Company/Issuer"}, {"id": "A2", "name": "ACME corp.", "ticker": "ACM", "node_type": "Company/Issuer"},
                      {"id": "B1", "name": "Beta", "ticker": "BET", "node_type": "Company/Issuer"}, {"id": "b1", "name": "Beta Two", "ticker": "BT2", "node_type": "Company/Issuer"}], set(), {})
    by_name, by_ticker, by_norm = ix.resolve("Acme Corp"), ix.resolve("acm"), ix.resolve("B1")
    assert by_name.status == AMBIGUOUS and by_name.candidates == ["A1", "A2"] and by_name.entity_id is None
    assert by_ticker.status == AMBIGUOUS and by_ticker.candidates == ["A1", "A2"]
    assert by_norm.status == RESOLVED and by_norm.rule == "EXACT_ID"                      # an exact id still wins over a normalised clash
    assert (ix.resolve("beta").status, ix.resolve("beta").entity_id, ix.resolve("beta").rule) == (MAPPED, "B1", "NAME_EXACT")
    assert ix.resolve("BET").status == MAPPED and ix.resolve("BET").entity_id == "B1"


def test_wrong_kind_and_wrong_universe_are_refused():
    ix = canonical_index()
    assert ix.resolve("SECTOR_ENERGY", "issuer").rule == "WRONG_KIND"
    assert ix.resolve("NVDA", "portfolio_counterparty").rule == "WRONG_KIND"
    assert ix.resolve("CP_ALPHA", "portfolio_counterparty").status == RESOLVED
    assert ix.resolve("CP_HF_001", "portfolio_counterparty").rule == "WRONG_UNIVERSE"


def test_unresolved_and_ambiguous_references_block_approval_and_the_row_is_not_proposed(store):
    job = run(store, edges_csv(edge("MU", "AMD"), edge("NOT-A-COMPANY", "AMD"), edge("Samsung", "AMD")), source_id="unresolved")["job"]
    assert job["blocking"] and {"UNRESOLVED_ENTITY"} <= set(codes(store, job["job_id"], "ERROR"))
    stg = store.load_staging(job["job_id"])
    assert [r["source"] for r in stg["proposed_rows"]] == ["MU"] and len(stg["excluded_rows"]) == 2
    reasons = {f["rule"] for f in store.findings(job["job_id"]) if f["code"] == "UNRESOLVED_ENTITY"}
    assert reasons == {"NO_MATCH", "DENIED_ALIAS"}
    with pytest.raises(review.ReviewError) as e:
        review.approve(store, job["job_id"], reviewer="r", reason="x", acknowledge_mappings=True, acknowledge_changes=True)
    assert e.value.code == "BLOCKED_BY_FINDINGS" and store.releases("fact_edges") == []


def test_mapped_names_are_recorded_and_need_explicit_acknowledgement(store):
    job = run(store, edges_csv(edge("Google Cloud", "AMD"), edge("ARM", "tsm", status="UNVERIFIED", url="")), source_id="mapped")["job"]
    assert not job["blocking"]
    maps = {(m["value"], m["entity_id"], m["rule"], m["requires_acknowledgement"]) for m in store.load_staging(job["job_id"])["mappings"]}
    assert maps == {("Google Cloud", "GOOGL", "ALIAS", True), ("tsm", "TSM", "NORMALIZED_ID", False)}
    assert "ENTITY_MAPPED" in codes(store, job["job_id"], "WARN")
    with pytest.raises(review.ReviewError) as e:
        review.approve(store, job["job_id"], reviewer="r", reason="x")
    assert e.value.code == "MAPPINGS_NOT_ACKNOWLEDGED"
    done = review.approve(store, job["job_id"], reviewer="r", reason="alias checked", acknowledge_mappings=True)
    rows = review.export(store, "fact_edges")["canonical_shape"]["fact_edges"]
    assert done["rows"] == 2 and {r["source"] for r in rows} == {"GOOGL", "ARM"}                  # stored under canonical ids, never the typed alias


# ------------------------------------------------------------------ conflicts and approval gates
def test_changes_against_canonical_data_are_conflicts_that_need_acknowledgement(store):
    job = run(store, edges_csv(edge("TSM", "NVDA", crit="0.5", note="x", status="REPORTED_NEWS", url="https://example.org/a"), edge("MU", "AMD")), source_id="conflict")["job"]
    vs = store.load_staging(job["job_id"])["vs_canonical"]
    assert vs["new"] == 1 and vs["changed"] == 1 and vs["changed_samples"][0]["key"] == "TSM|SUPPLIES|NVDA"
    assert vs["changed_samples"][0]["fields"]["criticality"] == {"was": 0.95, "proposed": 0.5}
    with pytest.raises(review.ReviewError) as e:
        review.approve(store, job["job_id"], reviewer="r", reason="x")
    assert e.value.code == "CHANGES_NOT_ACKNOWLEDGED"
    assert review.approve(store, job["job_id"], reviewer="r", reason="analyst re-rated this supplier", acknowledge_changes=True)["version"] == 1
    canonical = json.loads((DATA_DIR / "fact_edges.json").read_text())["fact_edges"]
    assert next(e for e in canonical if e["source"] == "TSM" and e["target"] == "NVDA")["criticality"] == 0.95      # the canonical row keeps its value


def test_changes_between_approved_releases_also_need_acknowledgement(store):
    review.approve(store, run(store, edges_csv(edge("MU", "AMD", crit="0.3")), source_id="s1")["job"]["job_id"], reviewer="r", reason="first")
    second = run(store, edges_csv(edge("MU", "AMD", crit="0.6")), source_id="s2")["job"]
    assert store.load_staging(second["job_id"])["vs_previous_release"]["changed"] == 1
    with pytest.raises(review.ReviewError) as e:
        review.approve(store, second["job_id"], reviewer="r", reason="x")
    assert e.value.code == "CHANGES_NOT_ACKNOWLEDGED"
    review.approve(store, second["job_id"], reviewer="r", reason="re-rated", acknowledge_changes=True)
    assert review.export(store, "fact_edges")["canonical_shape"]["fact_edges"][0]["criticality"] == 0.6


def test_rejected_jobs_cannot_be_approved_and_the_decision_is_recorded(store):
    job = run(store, edges_csv(edge()))["job"]
    review.reject(store, job["job_id"], reviewer="carol", reason="evidence link is a marketing page")
    assert store.get_job(job["job_id"])["status"] == "REJECTED"
    d = store.decisions(job["job_id"])
    assert d[0]["decision"] == "REJECT" and d[0]["reviewer"] == "carol" and "marketing" in d[0]["reason"]
    for fn in (review.approve, review.reject):
        with pytest.raises(review.ReviewError) as e:
            fn(store, job["job_id"], reviewer="carol", reason="again")
        assert e.value.code == "NOT_PENDING"
    assert store.releases("fact_edges") == [] and store.current("fact_edges") is None
    again = run(store, edges_csv(edge()))
    assert again["duplicate"] and again["job"]["status"] == "REJECTED"           # the rejection stands until someone explicitly resubmits
    fresh = run(store, edges_csv(edge()), force_new=True)["job"]
    assert fresh["status"] == "PENDING_REVIEW"


def test_reviewer_and_reason_are_mandatory(store):
    job = run(store, edges_csv(edge()))["job"]
    for who, why in (("", "x"), ("r", ""), ("   ", "x"), ("r", "  "), ("x" * 81, "x")):
        with pytest.raises(review.ReviewError) as e:
            review.approve(store, job["job_id"], reviewer=who, reason=why)
        assert e.value.code in ("REVIEWER_REQUIRED", "REASON_REQUIRED")
    assert store.get_job(job["job_id"])["status"] == "PENDING_REVIEW"


def test_stale_staging_cannot_be_approved_after_the_approved_state_moved(store):
    a = run(store, edges_csv(edge("MU", "AMD")), source_id="src-a")["job"]
    b = run(store, edges_csv(edge("ARM", "AMD")), source_id="src-b")["job"]
    review.approve(store, a["job_id"], reviewer="r", reason="first")
    with pytest.raises(review.ReviewError) as e:
        review.approve(store, b["job_id"], reviewer="r", reason="second")
    assert e.value.code == "STALE_BASE"
    again = run(store, edges_csv(edge("ARM", "AMD")), source_id="src-b", force_new=True)["job"]
    assert review.approve(store, again["job_id"], reviewer="r", reason="restaged")["rows"] == 2


def test_a_failed_commit_leaves_the_previous_approved_state_intact(store, monkeypatch):
    first = run(store, edges_csv(edge("MU", "AMD")), source_id="src-a")["job"]
    review.approve(store, first["job_id"], reviewer="r", reason="ok")
    second = run(store, edges_csv(edge("ARM", "AMD")), source_id="src-b")["job"]
    def boom(**kw):
        raise RuntimeError("disk full")
    monkeypatch.setattr(store, "commit_release", boom)
    with pytest.raises(RuntimeError):
        review.approve(store, second["job_id"], reviewer="r", reason="x")
    monkeypatch.undo()
    assert store.current("fact_edges")["version"] == 1 and store.get_job(second["job_id"])["status"] == "PENDING_REVIEW"
    assert len(review.export(store, "fact_edges")["canonical_shape"]["fact_edges"]) == 1
    assert review.approve(store, second["job_id"], reviewer="r", reason="retry")["version"] == 2


def test_rollback_and_restore_are_guarded(store):
    with pytest.raises(review.ReviewError) as e:
        review.rollback(store, "fact_edges", reviewer="r", reason="x")
    assert e.value.code == "NOTHING_TO_ROLL_BACK"
    with pytest.raises(review.ReviewError) as e:
        review.rollback(store, "profile_only", reviewer="r", reason="x")
    assert e.value.code == "UNKNOWN_DATASET"
    r1 = review.approve(store, run(store, edges_csv(edge("MU", "AMD")), source_id="src-a")["job"]["job_id"], reviewer="r", reason="1")
    with pytest.raises(review.ReviewError) as e:
        review.restore(store, "fact_edges", "", 999, reviewer="r", reason="x")
    assert e.value.code == "NOT_FOUND"
    assert review.rollback(store, "fact_edges", reviewer="r", reason="undo")["current"] is None
    assert [x["status"] for x in store.releases("fact_edges")] == ["ROLLED_BACK"]
    assert review.restore(store, "fact_edges", "", r1["release_id"], reviewer="r", reason="redo")["current"]["version"] == 1
    kinds = [e["kind"] for e in store.events() if e["stage"] == "REVIEW"]
    assert "ROLLED_BACK" in kinds and "RESTORED" in kinds and store.verify_chain()["ok"]


def test_datasets_are_independent_per_scope(store):
    for scope in ("NVDA", "AMD"):
        job = run(store, csv_bytes(["date", "close"], [["2026-10-01", "100"], ["2026-10-02", "101"]]), target="prices", scope=scope, source_id=f"px-{scope.lower()}", filename=f"{scope}.csv")["job"]
        review.approve(store, job["job_id"], reviewer="r", reason="ok")
    assert {(c["dataset"], c["scope"]) for c in store.list_current()} == {("prices", "NVDA"), ("prices", "AMD")}
    review.rollback(store, "prices", "NVDA", reviewer="r", reason="x")
    assert store.current("prices", "NVDA") is None and store.current("prices", "AMD")["version"] == 1
