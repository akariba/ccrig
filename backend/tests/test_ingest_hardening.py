"""POST /api/themes/ingest writes to process-wide state that every viewer
shares (the news corpus behind Theme Radar). It must be off by default,
unable to forge provenance, unable to poison the corpus, and bounded.

Every endpoint case runs through FastAPI AND the in-browser dispatcher.
"""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core import config  # noqa: E402
from app.core import themes as theme_mod  # noqa: E402
from app.core.data import STORE  # noqa: E402
from validation import snapshot  # noqa: E402

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
via_fastapi = snapshot.fastapi_request()
via_dispatch = snapshot.dispatch_request()
BOTH = pytest.mark.parametrize("request_fn", [via_fastapi, via_dispatch], ids=["fastapi", "dispatcher"])

GOOD = {"id": "t_ingest_1", "date": "2026-08-01", "title": "Undersea cable incident",
        "snippet": "A test document about an undersea cable incident near Maersk routes."}


@pytest.fixture(autouse=True)
def restore_corpus():
    """Ingestion mutates shared state; always roll it back."""
    before = len(STORE.news_all)
    yield
    del STORE.news_all[before:]
    theme_mod.invalidate_discovery_cache()


@pytest.fixture
def ingest_on(monkeypatch):
    monkeypatch.setattr(config, "INGEST_ENABLED", True)


def post(request_fn, body):
    return request_fn("POST", "/api/themes/ingest", body)


# ------------------------------------------------------------ off by default
@BOTH
def test_ingest_is_disabled_by_default(request_fn):
    assert config.INGEST_ENABLED is False
    before = len(STORE.news_all)
    status, body = post(request_fn, GOOD)
    assert status == 403 and "CCRIG_ENABLE_INGEST" in body["detail"]
    assert len(STORE.news_all) == before


@pytest.mark.parametrize("value,expected", [
    (None, False), ("", False), ("0", False), ("false", False), ("no", False), ("maybe", False),
    ("1", True), ("true", True), ("TRUE", True), (" yes ", True), ("on", True),
])
def test_enable_flag_parsing(value, expected):
    env = {k: v for k, v in os.environ.items() if k != "CCRIG_ENABLE_INGEST"}
    if value is not None:
        env["CCRIG_ENABLE_INGEST"] = value
    out = subprocess.run([sys.executable, "-c", "import app.core.config as c; print(c.INGEST_ENABLED)"],
                         cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60)
    assert out.stdout.strip() == str(expected), out.stderr


# ------------------------------------------------------------- when enabled
@BOTH
def test_valid_document_is_stored_as_unverified_synthetic(request_fn, ingest_on):
    before = len(STORE.news_all)
    status, body = post(request_fn, {**GOOD, "entities": ["maersk"], "keywords": ["taiwan"]})
    assert status == 200
    stored = body["ingested"]
    assert stored["is_synthetic"] is True and stored["source_type"] == "SYNTHETIC_NARRATIVE"
    assert stored["source"] == "INGESTED (unverified)"
    assert stored["entities"] == ["MAERSK"] and stored["keywords"] == ["TAIWAN"]   # normalised
    assert len(STORE.news_all) == before + 1 and body["news_corpus_size"] == before + 1


@BOTH
def test_provenance_cannot_be_forged(request_fn, ingest_on):
    status, body = post(request_fn, {**GOOD, "source": "Reuters", "url": "https://example.org/a"})
    assert status == 200
    stored = body["ingested"]
    assert stored["is_synthetic"] is True                       # always synthetic
    assert stored["source"] == "INGESTED (unverified)"          # never the claimed outlet
    assert stored["claimed_source"] == "Reuters"                # kept, but visibly a claim

    status, body = post(request_fn, {**GOOD, "id": "t_ingest_2", "is_synthetic": False})
    assert status == 422 and any("synthetic" in e["msg"] for e in body["detail"])


@BOTH
@pytest.mark.parametrize("patch", [
    {"url": "javascript:alert(1)"}, {"url": "ftp://example.org/x"}, {"url": "https://"},
    {"date": "2026-13-45"}, {"date": "tomorrow"},
    {"id": ""}, {"id": "has space"}, {"id": "x" * 65},
    {"title": ""}, {"title": "   "}, {"title": "t" * 301},
    {"snippet": ""}, {"snippet": "s" * 5001},
    {"keywords": [[1]]}, {"keywords": [{"a": 1}]}, {"keywords": [1, 2]}, {"keywords": ["k"] * 51},
    {"entities": [["TSM"]]}, {"entities": ["NOT_AN_ENTITY"]}, {"entities": "TSM"},
    {"source": "s" * 101},
])
def test_malformed_documents_rejected(request_fn, ingest_on, patch):
    before = len(STORE.news_all)
    status, body = post(request_fn, {**GOOD, **patch})
    assert status == 422, (patch, status, body)
    assert len(STORE.news_all) == before


@BOTH
def test_missing_required_fields_rejected(request_fn, ingest_on):
    for field in ("id", "date", "title", "snippet"):
        body = {k: v for k, v in GOOD.items() if k != field}
        assert post(request_fn, body)[0] == 422


@BOTH
def test_duplicate_ids_rejected(request_fn, ingest_on):
    assert post(request_fn, GOOD)[0] == 200
    status, body = post(request_fn, GOOD)
    assert status == 409 and "already exists" in body["detail"]
    existing = STORE.news_all[0]["id"]                           # ids of the shipped corpus are protected too
    assert post(request_fn, {**GOOD, "id": existing})[0] == 409


@BOTH
def test_capacity_is_bounded(request_fn, ingest_on, monkeypatch):
    monkeypatch.setattr(config, "INGEST_MAX_DOCS", 2)
    assert post(request_fn, {**GOOD, "id": "cap_1"})[0] == 200
    assert post(request_fn, {**GOOD, "id": "cap_2"})[0] == 200
    status, body = post(request_fn, {**GOOD, "id": "cap_3"})
    assert status == 409 and "at most 2" in body["detail"]


@BOTH
def test_rejected_payloads_cannot_poison_theme_radar(request_fn, ingest_on):
    """Regression: a document with non-string keywords used to be stored and
    then made /api/themes return 500 for every later caller."""
    poison = {**GOOD, "id": "poison", "keywords": [[1]], "entities": [{"x": 1}]}
    assert post(request_fn, poison)[0] == 422
    status, body = request_fn("GET", "/api/themes", None)
    assert status == 200 and body["count"] > 0


# ------------------------------------------------- service layer (direct callers)
def test_service_layer_enforces_the_same_rules_without_http():
    stored = theme_mod.ingest_news_document({**GOOD, "is_synthetic": False, "source": "Bloomberg"})
    assert stored["is_synthetic"] is True and stored["source"] == "INGESTED (unverified)"
    with pytest.raises(theme_mod.DuplicateDocument):
        theme_mod.ingest_news_document(GOOD)
    with pytest.raises(theme_mod.DocumentRejected):
        theme_mod.ingest_news_document({**GOOD, "id": "k", "keywords": [[1]]})
    with pytest.raises(theme_mod.DocumentRejected):
        theme_mod.ingest_news_document({**GOOD, "id": "u", "url": "javascript:alert(1)"})
    with pytest.raises(ValueError):                              # pre-existing contract
        theme_mod.ingest_news_document({"id": "bad_doc"})


def test_documents_without_optional_fields_still_work_for_discovery():
    """The documented use (see test_theme_discovery): bare id/date/title/snippet."""
    for i in range(3):
        theme_mod.ingest_news_document({**GOOD, "id": f"bare_{i}"})
    assert theme_mod.discover_themes() is not None
    assert STORE.news_all[-1]["entities"] == [] and STORE.news_all[-1]["keywords"] == []
