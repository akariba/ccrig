"""The Studio over HTTP: disabled by default, operator token required, limits enforced, full flow through the API."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import DATA_DIR, cors_settings
from app.main import app as main_app
from app.routers import studio, studio_ops
from tests.studio_helpers import SKHY, edge, edges_csv, tree_hash

BACKEND = Path(__file__).resolve().parents[1]
TOKEN = "s3cret-operator-token"
H = {"X-Studio-Token": TOKEN, "Content-Type": "application/octet-stream"}      # raw file upload
J = {"X-Studio-Token": TOKEN}                                                    # JSON bodies and reads


def build_app() -> TestClient:
    a = FastAPI()
    a.include_router(studio.router)
    a.include_router(studio_ops.router)
    return TestClient(a)


@pytest.fixture
def op(tmp_path, monkeypatch):
    monkeypatch.setenv("CCRIG_ENABLE_STUDIO", "1")
    monkeypatch.setenv("CCRIG_STUDIO_TOKEN", TOKEN)
    monkeypatch.setenv("CCRIG_STUDIO_DIR", str(tmp_path / "ws"))
    studio_ops._store_for.cache_clear()
    before = tree_hash(DATA_DIR)
    yield build_app()
    assert tree_hash(DATA_DIR) == before
    studio_ops._store_for.cache_clear()


Q = "source_id=skhy-prices&filename=SKHY.csv&target=prices&scope=SKHY&operator=api-test"


def test_default_deployment_exposes_only_the_read_only_description():
    paths = set(main_app.openapi()["paths"])
    assert "/api/studio/status" in paths and "/api/studio/contracts" in paths
    assert not any(p.startswith("/api/studio/jobs") or "/rollback" in p for p in paths), "operator routes must not exist unless the Studio is enabled"
    c = TestClient(main_app)
    s = c.get("/api/studio/status").json()
    assert s["enabled"] is False and s["mode"] == "disabled" and s["capabilities"]["ingest_files"] is False and "read-only" in s["capabilities"]["static_site_note"]
    assert c.post("/api/studio/jobs?source_id=ab&filename=a.csv&target=prices", content=b"x").status_code == 404
    names = {x["name"] for x in c.get("/api/studio/contracts").json()["contracts"]}
    assert {"fact_edges", "exposure_edges", "ccr_counterparties", "prices", "entities", "profile_only"} <= names


def test_operator_routes_are_registered_only_when_enabled():
    code = "import json;from app.main import app;print(json.dumps(sorted(p for p in app.openapi()['paths'] if p.startswith('/api/studio'))))"
    off = json.loads(subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, env={k: v for k, v in os.environ.items() if not k.startswith("CCRIG_")}).stdout)
    on = json.loads(subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, env={**os.environ, "CCRIG_ENABLE_STUDIO": "1"}).stdout)
    assert "/api/studio/jobs" not in off and "/api/studio/jobs" in on and "/api/studio/status" in off


def test_disabled_enabled_without_token_and_wrong_token(monkeypatch):
    c = build_app()
    monkeypatch.delenv("CCRIG_ENABLE_STUDIO", raising=False)
    assert c.get("/api/studio/jobs", headers=H).status_code == 404                              # even a registered route answers 404 when disabled
    monkeypatch.setenv("CCRIG_ENABLE_STUDIO", "1")
    monkeypatch.delenv("CCRIG_STUDIO_TOKEN", raising=False)
    r = c.get("/api/studio/jobs", headers=H)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "STUDIO_TOKEN_NOT_CONFIGURED"
    monkeypatch.setenv("CCRIG_STUDIO_TOKEN", TOKEN)
    assert c.get("/api/studio/jobs").status_code == 401
    assert c.get("/api/studio/jobs", headers={"X-Studio-Token": "nope"}).status_code == 401
    assert c.post(f"/api/studio/jobs?{Q}", content=SKHY, headers={"X-Studio-Token": "nope"}).status_code == 401


def test_browsers_on_other_origins_cannot_send_the_operator_token():
    assert "x-studio-token" not in [h.lower() for h in cors_settings()["allow_headers"]]


def test_full_flow_over_http(op):
    r = op.post(f"/api/studio/jobs?{Q}", content=SKHY, headers=H)
    assert r.status_code == 200, r.text
    job = r.json()["job"]
    assert job["status"] == "PENDING_REVIEW" and r.json()["duplicate"] is False
    again = op.post(f"/api/studio/jobs?{Q}", content=SKHY, headers=H).json()
    assert again["duplicate"] is True and again["job"]["job_id"] == job["job_id"]
    detail = op.get(f"/api/studio/jobs/{job['job_id']}", headers=J).json()
    assert detail["job"]["manifest"]["sha256"] == job["sha256"] and any(e["stage"] == "STAGE" and e["kind"] == "COMPLETED" for e in detail["events"])
    assert op.get(f"/api/studio/jobs/{job['job_id']}/staging", headers=J).json()["vs_canonical"]["unchanged"] == 20
    refused = op.post(f"/api/studio/jobs/{job['job_id']}/approve", json={"reviewer": "", "reason": "x"}, headers=J)
    assert refused.status_code == 422
    ok = op.post(f"/api/studio/jobs/{job['job_id']}/approve", json={"reviewer": "alice", "reason": "matches canonical"}, headers=J)
    assert ok.status_code == 200 and ok.json()["version"] == 1
    twice = op.post(f"/api/studio/jobs/{job['job_id']}/approve", json={"reviewer": "alice", "reason": "again"}, headers=J)
    assert twice.status_code == 409 and twice.json()["detail"]["code"] == "NOT_PENDING"
    assert op.get("/api/studio/datasets", headers=J).json()["current"][0]["dataset"] == "prices"
    exp = op.get("/api/studio/datasets/prices/export?scope=SKHY", headers=J).json()
    assert len(exp["canonical_shape"]["rows"]) == 20 and "canonical files" in exp["warning"]
    rb = op.post("/api/studio/datasets/prices/rollback?scope=SKHY", json={"reviewer": "alice", "reason": "test"}, headers=J)
    assert rb.status_code == 200 and rb.json()["current"] is None
    assert op.get("/api/studio/datasets/prices/export?scope=SKHY", headers=J).status_code == 404
    assert op.get("/api/studio/ledger/verify", headers=J).json()["ok"] is True
    assert op.get("/api/studio/jobs/job-99999-x", headers=J).status_code == 404


def test_reject_over_http(op):
    job = op.post("/api/studio/jobs?source_id=edges-src&filename=e.csv&target=fact_edges", content=edges_csv(edge()), headers=H).json()["job"]
    assert op.post(f"/api/studio/jobs/{job['job_id']}/reject", json={"reviewer": "bob", "reason": "no"}, headers=J).json()["status"] == "REJECTED"
    assert op.get(f"/api/studio/jobs/{job['job_id']}", headers=J).json()["decisions"][0]["decision"] == "REJECT"


def test_upload_limits_and_hostile_content_over_http(op, monkeypatch):
    monkeypatch.setenv("CCRIG_STUDIO_MAX_BYTES", "100")
    big = op.post(f"/api/studio/jobs?{Q}", content=b"x" * 500, headers=H)
    assert big.status_code == 413 and big.json()["detail"]["code"] == "OVERSIZE"
    monkeypatch.delenv("CCRIG_STUDIO_MAX_BYTES")
    exe = op.post("/api/studio/jobs?source_id=bad-src&filename=a.csv&target=profile_only", content=b"MZ" + b"\x00" * 100, headers=H)
    assert exe.status_code == 200 and exe.json()["job"]["status"] == "REJECTED_INPUT" and exe.json()["job"]["error_code"] == "FORBIDDEN_CONTENT"
    for q in ("source_id=X&filename=a.csv&target=prices&scope=SKHY", "source_id=ok-src&filename=a.csv&target=nope", "source_id=ok-src&filename=a.csv&target=prices"):
        assert op.post(f"/api/studio/jobs?{q}", content=SKHY, headers=H).status_code == 422
    traversal = op.post("/api/studio/jobs?source_id=ok-src&filename=../../etc/passwd.csv&target=profile_only", content=b"a,b\n1,2\n", headers=H)
    assert traversal.json()["job"]["filename"] == "passwd.csv"


def test_secrets_never_appear_in_responses(op):
    r = op.post(f"/api/studio/jobs?{Q}", content=SKHY, headers=H)
    blob = r.text + op.get("/api/studio/status").text + op.get("/api/studio/jobs", headers=J).text
    assert TOKEN not in blob
