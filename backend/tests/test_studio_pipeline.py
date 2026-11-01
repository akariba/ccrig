"""Studio ingestion pipeline: success path, malformed inputs, duplicates, validation, staging, persistence."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import DATA_DIR
from app.studio import acquire, config, pipeline, review
from app.studio.store import IntegrityError, StudioStore
from tests.studio_helpers import AS_OF, SKHY, codes, csv_bytes, edge, edges_csv, run, tree_hash

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def store(tmp_path):
    return StudioStore(tmp_path / "ws")


@pytest.fixture(autouse=True)
def canonical_untouched():
    before = tree_hash(DATA_DIR)
    yield
    assert tree_hash(DATA_DIR) == before, "a Studio operation modified canonical data"


# ------------------------------------------------------------------ the genuine dataset: real SKHY prices
def test_real_price_file_goes_through_every_stage(store):
    job = run(store, SKHY, target="prices", scope="skhy", filename="SKHY.csv")["job"]
    assert job["status"] == "PENDING_REVIEW" and not job["blocking"] and job["scope"] == "SKHY"
    assert job["manifest"]["sha256"] == job["sha256"] and job["manifest"]["bytes"] == len(SKHY) and job["manifest"]["scope_input"] == "skhy"
    prof = job["profile"]
    assert prof["rows"] == 20 and prof["duplicate_rows"] == 0
    close = next(c for c in prof["column_profiles"] if c["name"] == "close")
    assert close["inferred_type"] == "float" and close["null_pct"] == 0.0 and close["min"] < close["max"]
    assert prof["freshness"][0]["latest"] == "2026-08-06" and prof["freshness"][0]["age_days"] == (AS_OF - __import__("datetime").date(2026, 8, 6)).days
    stg = store.load_staging(job["job_id"])
    assert stg["vs_canonical"] == {"available": True, "base_rows": 20, "new": 0, "changed": 0, "unchanged": 20, "changed_samples": []}   # real data == canonical copy
    stages = [(e["stage"], e["kind"]) for e in store.events(job["job_id"])]
    for s in ("ACQUIRE", "PARSE", "PROFILE", "VALIDATE", "RESOLVE", "CHECK", "STAGE"):
        assert (s, "STARTED") in stages and (s, "COMPLETED") in stages
    done = {e["stage"]: e for e in store.events(job["job_id"]) if e["kind"] == "COMPLETED"}
    assert done["PARSE"]["counts"] == {"columns": 2, "rows": 20} and isinstance(done["PARSE"]["elapsed_ms"], int)
    assert store.read_raw(job["sha256"]) == SKHY and store.verify_chain()["ok"]


def test_approve_publishes_a_release_and_rollback_restores_the_previous_state(store):
    j1 = run(store, SKHY, target="prices", scope="SKHY")["job"]
    r1 = review.approve(store, j1["job_id"], reviewer="alice", reason="matches the canonical copy")
    assert r1["version"] == 1 and store.current("prices", "SKHY")["version"] == 1
    extra = SKHY + b"2026-08-07,150.5\n2026-08-10,151.0\n"
    j2 = run(store, extra, target="prices", scope="SKHY", source_id="skhy-update")["job"]
    stg = store.load_staging(j2["job_id"])
    assert stg["vs_previous_release"]["new"] == 2 and stg["vs_previous_release"]["unchanged"] == 20 and stg["vs_canonical"]["new"] == 2
    r2 = review.approve(store, j2["job_id"], reviewer="alice", reason="two new closes")
    assert r2["version"] == 2 and r2["rows"] == 22
    assert [r["status"] for r in store.releases("prices", "SKHY")] == ["SUPERSEDED", "ACTIVE"]
    back = review.rollback(store, "prices", "SKHY", reviewer="alice", reason="bad update")
    assert back["current"]["version"] == 1
    assert [r["status"] for r in store.releases("prices", "SKHY")] == ["ACTIVE", "ROLLED_BACK"]
    assert len(review.export(store, "prices", "SKHY")["canonical_shape"]["rows"]) == 20
    gone = review.rollback(store, "prices", "SKHY", reviewer="alice", reason="and the first one too")
    assert gone["current"] is None
    with pytest.raises(review.ReviewError) as e:
        review.export(store, "prices", "SKHY")
    assert e.value.code == "NO_APPROVED_STATE"
    restored = review.restore(store, "prices", "SKHY", r2["release_id"], reviewer="alice", reason="undo")
    assert restored["current"]["version"] == 2 and len(review.export(store, "prices", "SKHY")["canonical_shape"]["rows"]) == 22
    # a new approval after a rollback gets a new version number, history is never rewritten
    j3 = run(store, SKHY + b"2026-08-07,150.5\n2026-08-10,151.0\n2026-08-11,152.0\n", target="prices", scope="SKHY", source_id="skhy-update-3")["job"]
    assert review.approve(store, j3["job_id"], reviewer="alice", reason="more")["version"] == 3


def test_everything_survives_a_restart(tmp_path):
    root = tmp_path / "ws"
    s1 = StudioStore(root)
    job = run(s1, SKHY, target="prices", scope="SKHY")["job"]
    review.approve(s1, job["job_id"], reviewer="alice", reason="ok")
    del s1
    s2 = StudioStore(root)                                           # a fresh object over the same files: nothing was held in memory
    again = s2.get_job(job["job_id"])
    assert again["status"] == "APPROVED" and again["manifest"]["sha256"] == job["sha256"]
    assert s2.current("prices", "SKHY")["version"] == 1 and len(s2.events(job["job_id"])) >= 15
    assert len(review.export(s2, "prices", "SKHY")["canonical_shape"]["rows"]) == 20 and s2.verify_chain()["ok"]
    assert run(s2, SKHY, target="prices", scope="SKHY")["duplicate"] is True                 # idempotency also survives


def test_a_separate_process_sees_the_same_state(tmp_path):
    ws = tmp_path / "ws"
    f = tmp_path / "SKHY.csv"
    f.write_bytes(SKHY)
    cli = [sys.executable, "-m", "app.studio", "--dir", str(ws)]
    out = subprocess.run([*cli, "ingest", str(f), "--source-id", "skhy-prices", "--target", "prices", "--scope", "SKHY"], cwd=BACKEND, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    job_id = json.loads(out.stdout)["job_id"]
    ok = subprocess.run([*cli, "approve", job_id, "--reviewer", "bob", "--reason", "cli"], cwd=BACKEND, capture_output=True, text=True)
    assert ok.returncode == 0 and json.loads(ok.stdout)["version"] == 1
    listed = json.loads(subprocess.run([*cli, "datasets"], cwd=BACKEND, capture_output=True, text=True).stdout)
    assert listed[0]["dataset"] == "prices" and listed[0]["approved_by"] == "bob"
    refused = subprocess.run([*cli, "approve", job_id, "--reviewer", "bob", "--reason", "again"], cwd=BACKEND, capture_output=True, text=True)
    assert refused.returncode == 2 and json.loads(refused.stderr)["error"] == "NOT_PENDING"


# ------------------------------------------------------------------ duplicates and idempotency
def test_identical_resubmission_is_idempotent_unless_a_new_version_is_requested(store):
    data = edges_csv(edge())
    first = run(store, data)
    again = run(store, data)
    assert again["duplicate"] and again["job"]["job_id"] == first["job"]["job_id"] and len(store.list_jobs()) == 1
    assert any(e["kind"] == "RESUBMITTED" for e in store.events(first["job"]["job_id"]))
    other_source = run(store, data, source_id="another-source")
    assert not other_source["duplicate"] and other_source["job"]["job_id"] != first["job"]["job_id"]
    forced = run(store, data, force_new=True)
    assert not forced["duplicate"] and forced["job"]["supersedes"] == first["job"]["job_id"]
    assert len(store.list_jobs()) == 3


def test_approving_the_same_content_twice_publishes_nothing_new(store):
    a = run(store, edges_csv(edge()))["job"]
    review.approve(store, a["job_id"], reviewer="r", reason="x", acknowledge_changes=False)
    b = run(store, edges_csv(edge()), source_id="mirror")["job"]
    with pytest.raises(review.ReviewError) as e:
        review.approve(store, b["job_id"], reviewer="r", reason="x")
    assert e.value.code == "ALREADY_CURRENT" and len(store.releases("fact_edges")) == 1


# ------------------------------------------------------------------ malformed and hostile inputs
BAD = [
    ("empty", b"", "a.csv", "EMPTY_INPUT"),
    ("windows exe", b"MZ\x90\x00" + b"x" * 50, "a.csv", "FORBIDDEN_CONTENT"),
    ("elf", b"\x7fELF\x02\x01" + b"x" * 50, "a.csv", "FORBIDDEN_CONTENT"),
    ("zip", b"PK\x03\x04" + b"x" * 50, "a.csv", "FORBIDDEN_CONTENT"),
    ("gzip", b"\x1f\x8b\x08" + b"x" * 50, "a.json", "FORBIDDEN_CONTENT"),
    ("script", b"#!/bin/sh\nrm -rf /\n", "a.csv", "FORBIDDEN_CONTENT"),
    ("html", b"<!DOCTYPE html><script>alert(1)</script>", "a.csv", "FORBIDDEN_CONTENT"),
    ("pdf", b"%PDF-1.4 " + b"x" * 50, "a.csv", "FORBIDDEN_CONTENT"),
    ("bad extension", b"a,b\n1,2\n", "a.xlsx", "UNSUPPORTED_EXTENSION"),
    ("no extension", b"a,b\n1,2\n", "payload", "UNSUPPORTED_EXTENSION"),
    ("json named csv", b'{"a":1}', "a.csv", "CONTENT_MISMATCH"),
    ("csv named json", b"a,b\n1,2\n", "a.json", "CONTENT_MISMATCH"),
    ("nul bytes", b"a,b\n1,\x002\n", "a.csv", "BINARY_CONTENT"),
    ("bad utf8", b"a,b\n\xff\xfe,2\n", "a.csv", "BAD_ENCODING"),
    ("fake parquet", b"not parquet at all", "a.parquet", "CONTENT_MISMATCH"),
    ("malformed json", b'{"a": [1, 2,', "a.json", "MALFORMED_JSON"),
    ("NaN in json", b'[{"a": NaN}]', "a.json", "MALFORMED_JSON"),
    ("json scalar", b"[1, 2, 3]", "a.json", "UNSUPPORTED_JSON_SHAPE"),
    ("two lists", b'{"a":[{"x":1}],"b":[{"y":2}]}', "a.json", "UNSUPPORTED_JSON_SHAPE"),
    ("too deep", b'[{"a":' + b'{"b":' * 12 + b"1" + b"}" * 12 + b"}]", "a.json", "TOO_DEEP"),
]


@pytest.mark.parametrize("name,data,filename,code", BAD, ids=[b[0] for b in BAD])
def test_hostile_or_malformed_input_is_rejected_with_a_stable_code_and_never_stored(store, name, data, filename, code):
    job = run(store, data, filename=filename, target="profile_only")["job"]
    assert job["status"] == "REJECTED_INPUT" and job["error_code"] == code and job["blocking"]
    assert any(e["kind"] == "FAILED" for e in store.events(job["job_id"]))
    if code in ("FORBIDDEN_CONTENT", "CONTENT_MISMATCH", "UNSUPPORTED_EXTENSION", "BINARY_CONTENT"):
        assert not [p for p in (store.root / "raw").rglob("*") if p.is_file()], "rejected content must not be written to the raw store"


def test_configurable_limits(store):
    small = acquire.Limits(max_bytes=50, max_rows=3, max_columns=2, max_depth=8, max_cell_chars=10, max_findings=500)
    assert run(store, b"a,b\n" + b"1,2\n" * 30, filename="a.csv", target="profile_only", limits=small)["job"]["error_code"] == "OVERSIZE"
    assert run(store, b"a,b\n1,2\n3,4\n5,6\n7,8\n", filename="b.csv", target="profile_only", limits=small)["job"]["error_code"] == "TOO_MANY_ROWS"
    assert run(store, b"a,b,c\n1,2,3\n", filename="c.csv", target="profile_only", limits=small)["job"]["error_code"] == "TOO_MANY_COLUMNS"
    assert run(store, b"a,b\n" + b"x" * 40 + b",1\n", filename="d.csv", target="profile_only", limits=small)["job"]["error_code"] == "CELL_TOO_LONG"


def test_environment_overrides_limits(monkeypatch):
    monkeypatch.setenv("CCRIG_STUDIO_MAX_BYTES", "1234")
    monkeypatch.setenv("CCRIG_STUDIO_MAX_ROWS", "not-a-number")
    lim = config.limits()
    assert lim.max_bytes == 1234 and lim.max_rows == config.Limits().max_rows


def test_parquet_is_explicitly_unsupported_without_pyarrow(store, monkeypatch):
    monkeypatch.setattr(acquire, "parquet_supported", lambda: False)
    job = run(store, b"PAR1" + b"x" * 40 + b"PAR1", filename="a.parquet", target="profile_only")["job"]
    assert job["status"] == "REJECTED_INPUT" and job["error_code"] == "PARQUET_UNSUPPORTED"


@pytest.mark.skipif(not acquire.parquet_supported(), reason="pyarrow not installed")
def test_parquet_round_trip(store, tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.table({"date": ["2026-08-01", "2026-08-02"], "close": [10.0, 11.0]})
    path = tmp_path / "p.parquet"
    pq.write_table(table, path)
    job = run(store, path.read_bytes(), filename="p.parquet", target="prices", scope="NVDA")["job"]
    assert job["status"] == "PENDING_REVIEW" and job["profile"]["rows"] == 2


def test_malformed_csv_structure_is_reported_not_repaired(store):
    ragged = run(store, b"source,target,relation,criticality,evidence_status\nQCOM,AAPL,SUPPLIES\nQCOM,AMD,SUPPLIES,0.5,UNVERIFIED,extra\n", target="fact_edges")["job"]
    assert ragged["blocking"] and "RAGGED_ROW" in codes(store, ragged["job_id"], "ERROR")
    dup_header = run(store, b"source,target,target,relation\nA,B,C,D\n", filename="h.csv", target="profile_only")["job"]
    assert "DUPLICATE_HEADER" in codes(store, dup_header["job_id"])
    dup_key = run(store, b'[{"a": 1, "a": 2}]', filename="k.json", target="profile_only")["job"]
    assert "DUPLICATE_JSON_KEY" in codes(store, dup_key["job_id"])


def test_unexpected_errors_are_recorded_and_promote_nothing(store, monkeypatch):
    monkeypatch.setattr(pipeline, "build_staging", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    job = run(store, edges_csv(edge()))["job"]
    assert job["status"] == "FAILED" and job["error_code"] == "UNEXPECTED_ERROR" and "boom" in job["error_message"]
    failed = [e for e in store.events(job["job_id"]) if e["kind"] == "FAILED" and e["stage"] == "STAGE"][0]
    assert failed["error"]["type"] == "RuntimeError" and isinstance(failed["elapsed_ms"], int)
    with pytest.raises(review.ReviewError) as e:
        review.approve(store, job["job_id"], reviewer="r", reason="x")
    assert e.value.code == "NOT_PENDING" and store.current("fact_edges") is None


@pytest.mark.parametrize("kw", [dict(source_id="X"), dict(source_id="a b"), dict(target="nope"), dict(target="prices"), dict(target="fact_edges", scope="NVDA"), dict(classification="SECRET")])
def test_bad_parameters_are_refused_before_anything_is_stored(store, kw):
    args = dict(source_id="ok-source", target="fact_edges", scope="", classification="PUBLIC")
    args.update(kw)
    with pytest.raises(pipeline.BadRequest):
        pipeline.ingest(store, b"a,b\n1,2\n", filename="a.csv", **args)
    assert store.list_jobs() == []


# ------------------------------------------------------------------ profiling
def test_profile_reports_types_nulls_duplicates_coverage_freshness_and_samples(store):
    data = csv_bytes(["id", "ticker", "score", "seen", "label"], [["TSM", "TSM", "1", "2026-10-01", "a"], ["NVDA", "NVDA", "2.5", "2026-10-30", ""], ["NVDA", "NVDA", "2.5", "2026-10-30", ""],
                                                                    ["ZZZ9", "ZZZ9", "x", "2026-10-31", "c"], ["TSM", "TSM", "3", "", "d"]])
    job = run(store, data, filename="mixed.csv", target="profile_only")["job"]
    p = job["profile"]
    cols = {c["name"]: c for c in p["column_profiles"]}
    assert p["rows"] == 5 and p["duplicate_rows"] == 1 and p["duplicate_rate_pct"] == 20.0
    assert cols["label"]["null_count"] == 2 and cols["label"]["null_pct"] == 40.0
    assert cols["score"]["mixed_types"] == {"int": 2, "float": 2, "str": 1}                                     # a text value among numbers is flagged
    assert any(i["code"] == "MIXED_TYPES" and i["column"] == "score" for i in p["schema_inconsistencies"])
    assert cols["id"]["identifier_coverage"] == {"distinct": 3, "exact_canonical": 2, "pct": 66.67}
    assert cols["seen"]["inferred_type"] == "date" and cols["seen"]["max"] == "2026-10-31" and cols["seen"]["age_days"] == 1
    assert len(p["sample_rows"]) == 5 and p["sample_rows"][0]["row"] == 1


def test_profile_only_targets_are_never_promotable(store):
    job = run(store, csv_bytes(["a"], [["1"]]), filename="a.csv", target="profile_only")["job"]
    assert job["status"] == "PROFILED_ONLY"
    with pytest.raises(review.ReviewError) as e:
        review.approve(store, job["job_id"], reviewer="r", reason="x")
    assert e.value.code == "NOT_PENDING"


# ------------------------------------------------------------------ validation
def test_fact_edge_validation_rules(store):
    cases = {
        "INVALID_ENUM": edge(relation="LIKES"), "OUT_OF_RANGE": edge(crit="1.7"), "WRONG_TYPE": edge(crit="high"),
        "DOCUMENTED_WITHOUT_LINK": edge(url=""), "INVALID_URL": edge(url="http://insecure.example/x"), "SELF_LOOP": edge(source="TSM", target="TSM"),
        "SYNTHETIC_CLAIMS_DOCUMENTED": edge(synth="true"), "MISSING_REQUIRED_VALUE": edge(crit=""),
    }
    for code, row in cases.items():
        job = run(store, edges_csv(row), source_id=f"case-{code.lower()}")["job"]
        assert job["blocking"] and code in codes(store, job["job_id"], "ERROR"), code
    ok = run(store, edges_csv(edge(status="UNVERIFIED", url="")), source_id="honest-unverified")["job"]
    assert not ok["blocking"], "an unverified relationship is allowed when it is labelled unverified"


def test_missing_required_column_and_unknown_columns(store):
    job = run(store, csv_bytes(["source", "target", "relation"], [["QCOM", "AAPL", "SUPPLIES"]]))["job"]
    assert job["blocking"] and "MISSING_REQUIRED_COLUMN" in codes(store, job["job_id"], "ERROR")
    extra = run(store, csv_bytes(EDGE := ["source", "target", "relation", "criticality", "evidence_status", "colour"], [["QCOM", "AAPL", "SUPPLIES", "0.4", "UNVERIFIED", "red"]]), source_id="x-extra")["job"]
    assert not extra["blocking"] and "UNKNOWN_COLUMN" in codes(store, extra["job_id"], "WARN")
    assert "colour" not in store.load_staging(extra["job_id"])["proposed_rows"][0]


def test_duplicates_identical_are_collapsed_and_conflicting_ones_block(store):
    same = run(store, edges_csv(edge(), edge()), source_id="dup-same")["job"]
    assert not same["blocking"] and "DUPLICATE_IDENTICAL" in codes(store, same["job_id"], "WARN") and len(store.load_staging(same["job_id"])["proposed_rows"]) == 1
    clash = run(store, edges_csv(edge(crit="0.4"), edge(crit="0.9")), source_id="dup-clash")["job"]
    assert clash["blocking"] and "DUPLICATE_CONFLICT" in codes(store, clash["job_id"], "ERROR")


def test_price_series_checks(store):
    rows = [["2026-10-01", "100"], ["2026-10-02", "100.5"], ["2026-10-20", "101"], ["2026-10-21", "160"], ["2026-12-30", "5"], ["2026-10-22", "-1"], ["2026-10-23", "0"]]
    job = run(store, csv_bytes(["date", "close"], rows), target="prices", scope="NVDA", filename="p.csv")["job"]
    c = codes(store, job["job_id"])
    assert {"DATE_GAP", "OUTLIER_RETURN", "FUTURE_DATE", "OUT_OF_RANGE", "NON_POSITIVE_PRICE", "NOT_SORTED"} <= set(c)
    assert job["blocking"]
    bad_scope = run(store, SKHY, target="prices", scope="NOPE", filename="p2.csv")["job"]
    assert bad_scope["blocking"] and "SCOPE_UNRESOLVED" in codes(store, bad_scope["job_id"])


def test_holdings_cannot_exceed_100_percent_and_the_ccr_universe_is_not_merged(store):
    cols = ["counterparty", "issuer", "relation", "exposure_pct", "is_synthetic"]
    over = run(store, csv_bytes(cols, [["CP_ALPHA", "NVDA", "HOLDS_EQUITY", "0.7", "true"], ["CP_ALPHA", "AMD", "HOLDS_EQUITY", "0.5", "true"]]), target="exposure_edges")["job"]
    assert "HOLDINGS_EXCEED_100" in codes(store, over["job_id"], "ERROR")
    wrong = run(store, csv_bytes(cols, [["CP_HF_001", "NVDA", "HOLDS_EQUITY", "0.1", "true"]]), target="exposure_edges", source_id="ccr-ids")["job"]
    f = [x for x in store.findings(wrong["job_id"]) if x["code"] == "UNRESOLVED_ENTITY"][0]
    assert wrong["blocking"] and f["rule"] == "WRONG_UNIVERSE" and "never merged" in f["message"]
    ok = run(store, csv_bytes(cols, [["CP_ALPHA", "NVDA", "HOLDS_EQUITY", "0.1", "true"]]), target="exposure_edges", source_id="portfolio-ok")["job"]
    assert not ok["blocking"]
    assert "is_synthetic" in store.load_staging(ok["job_id"])["proposed_rows"][0]


def test_ccr_nested_records_and_limit_consistency(store):
    good = {"id": "CP_TEST_1", "name": "Test Fund", "legal_entity": "Test Fund Ltd", "counterparty_type": "Hedge Fund", "exposure": {"rc_current": 1.0, "pfe_current": 2.5},
            "limit": {"limit_type": "PFE_LIMIT", "limit_value": 10.0}, "is_synthetic": True}
    ok = run(store, json.dumps({"counterparties": [good]}).encode(), target="ccr_counterparties", filename="ccr.json")["job"]
    assert ok["status"] == "PENDING_REVIEW" and not ok["blocking"]
    no_value = dict(good, id="CP_TEST_2", limit={"limit_type": "PFE_LIMIT", "limit_value": None})
    no_type = dict(good, id="CP_TEST_3", limit={"limit_type": None, "limit_value": 5.0})
    job = run(store, json.dumps([no_value, no_type]).encode(), target="ccr_counterparties", filename="ccr2.json")["job"]
    assert {"LIMIT_VALUE_MISSING", "LIMIT_TYPE_MISSING"} <= set(codes(store, job["job_id"], "ERROR"))
    bad_type = dict(good, id="CP_TEST_4", exposure={"rc_current": "lots"})
    assert "WRONG_TYPE" in codes(store, run(store, json.dumps([bad_type]).encode(), target="ccr_counterparties", filename="ccr3.json", source_id="ccr-3")["job"]["job_id"], "ERROR")
    csv_job = run(store, csv_bytes(["id", "name", "legal_entity", "counterparty_type", "exposure", "is_synthetic"], [["CP_X", "n", "l", "Bank", "{}", "true"]]), target="ccr_counterparties", filename="c.csv", source_id="ccr-csv")["job"]
    assert "OBJECT_NEEDS_JSON" in codes(store, csv_job["job_id"], "ERROR")


# ------------------------------------------------------------------ integrity and determinism
def test_tampering_is_detected(store):
    job = run(store, SKHY, target="prices", scope="SKHY")["job"]
    review.approve(store, job["job_id"], reviewer="a", reason="ok")
    assert store.verify_chain()["ok"]
    import sqlite3
    with sqlite3.connect(store.db_path) as c:
        c.execute("UPDATE events SET message='edited' WHERE seq=3")
    assert store.verify_chain()["ok"] is False and store.verify_chain()["first_bad_seq"] == 3
    raw = store.root / "raw" / job["sha256"][:2] / job["sha256"]
    raw.write_bytes(raw.read_bytes() + b"x")
    with pytest.raises(IntegrityError):
        store.read_raw(job["sha256"])
    rel = Path(store.current("prices", "SKHY")["path"])
    doc = json.loads(rel.read_text())
    doc["rows"][0]["close"] = 1.0
    rel.write_text(json.dumps(doc))
    with pytest.raises(IntegrityError):
        review.export(store, "prices", "SKHY")


def test_staging_is_deterministic_across_hash_seeds(tmp_path):
    f = tmp_path / "e.csv"
    f.write_bytes(edges_csv(edge(), edge("ARM", "AMD"), edge("ARM", "QCOM", url="")))
    outs = set()
    for seed in ("1", "424242"):
        r = subprocess.run([sys.executable, "-m", "app.studio", "--dir", str(tmp_path / f"w{seed}"), "ingest", str(f), "--source-id", "seed-test", "--target", "fact_edges"],
                           cwd=BACKEND, capture_output=True, text=True, env={**__import__("os").environ, "PYTHONHASHSEED": seed})
        job_id = json.loads(r.stdout)["job_id"]
        st = StudioStore(tmp_path / f"w{seed}")
        stg = st.load_staging(job_id)
        outs.add(json.dumps({k: stg[k] for k in ("proposed_hash", "merged_hash", "proposed_rows", "excluded_rows", "mappings")}, sort_keys=True) + json.dumps(st.findings(job_id), sort_keys=True))
    assert len(outs) == 1


def test_workspace_cannot_live_inside_published_folders(monkeypatch):
    monkeypatch.setenv("CCRIG_STUDIO_DIR", str(DATA_DIR / "studio"))
    with pytest.raises(config.UnsafeWorkspace):
        config.studio_dir()
    monkeypatch.setenv("CCRIG_STUDIO_DIR", str(BACKEND.parent / "frontend" / "public" / "x"))
    with pytest.raises(config.UnsafeWorkspace):
        config.studio_dir()
    monkeypatch.setenv("CCRIG_STUDIO_DIR", "/tmp/some-private-studio")
    assert str(config.studio_dir()).endswith("some-private-studio")
