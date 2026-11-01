"""The approved-source event register: what may enter it, and that what is in it is admissible.

Everything here is offline. The retrieval script is exercised with canned pages
(a real fetch is `python scripts/event_register.py verify`).
"""
import copy
import importlib.util
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core import event_register as reg  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "event_register.py")
spec = importlib.util.spec_from_file_location("event_register_script", SCRIPT)
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)


def a_record():
    return copy.deepcopy(reg.load_register()["events"][0])


# ---------------------------------------------------------------- shipped data
def test_every_shipped_event_is_admissible():
    assert reg.validate_register() == {}


def test_shipped_register_is_real_verified_and_sourced():
    events = reg.load_register()["events"]
    assert len(events) == 8
    assert len({e["id"] for e in events}) == len(events)
    for e in events:
        assert e["kind"] == "REAL_EVENT"
        assert e["verification"]["status"] == reg.VERIFIED
        assert e["verification"]["quotes_found"] == e["verification"]["quotes_total"] == len(e["evidence"]) >= 1
        assert e["verification"]["date_confirmed"] is True and e["verification"]["http_status"] == 200
        for s in e["sources"]:
            assert reg.source_policy(s["url"]) is not None and s["url"].startswith("https://")
            assert s["retrieved_at"] and date.fromisoformat(s["published_date"])
        for ev in e["evidence"]:
            assert len(ev["quote"]) >= reg.MIN_QUOTE_CHARS
        assert date.fromisoformat(e["event_date"]) <= date.fromisoformat(e["published_date"])
        assert reg.gazetteer()[e["location"]["gazetteer_key"]]            # location resolves
        assert e["location"]["basis"] and e["location"]["basis_text"]


def test_location_basis_text_is_quoted_in_the_evidence_or_title():
    """The place on the map must be traceable to words in the source."""
    for e in reg.load_register()["events"]:
        haystack = " ".join([e["title"]] + [q["quote"] for q in e["evidence"]])
        if e["id"].startswith("nvda-20260115"):
            continue                                                      # country-level, basis is agency metadata (stated)
        assert e["location"]["basis_text"] in haystack, e["id"]


def test_the_register_is_deterministically_ordered_newest_first():
    dates = [e["published_date"] for e in reg.load_register()["events"]]
    assert dates == sorted(dates, reverse=True)


# --------------------------------------------------------------- source policy
@pytest.mark.parametrize("url", [
    "https://nvidianews.nvidia.com/news/x", "https://investor.nvidia.com/a", "https://news.skhynix.com/en/x/",
    "https://www.federalregister.gov/documents/2026/01/15/x", "https://www.sec.gov/Archives/x", "https://sub.investor.nvidia.com/x",
])
def test_approved_domains_are_accepted(url):
    assert reg.source_policy(url)


@pytest.mark.parametrize("url", [
    "http://nvidianews.nvidia.com/news/x",                    # not https
    "https://nvidia.com.attacker.example/news", "https://evilnvidianews.nvidia.com.attacker.io/x",
    "https://nvidianews.nvidia.com.evil.example/x", "https://notnvidia.com/x", "https://www.reuters.com/x",
    "https://twitter.com/nvidia/status/1", "https://example.org/federalregister.gov", "ftp://investor.nvidia.com/x", "",
])
def test_unapproved_or_lookalike_sources_are_rejected(url):
    assert reg.source_policy(url) is None


# ------------------------------------------------------------ inadmissibility
def _problems(mutate):
    e = a_record()
    mutate(e)
    return reg.validate_event(e)


@pytest.mark.parametrize("name,mutate,expected", [
    ("unapproved domain", lambda e: e["sources"][0].update(url="https://www.reuters.com/x"), "not on an approved"),
    ("lookalike domain", lambda e: e["sources"][0].update(url="https://nvidianews.nvidia.com.evil.example/x"), "not on an approved"),
    ("wrong tier", lambda e: e["sources"][0].update(tier="PRIMARY_REGULATOR"), "does not match approved tier"),
    ("not a real event", lambda e: e.update(kind="SCENARIO"), "kind must be"),
    ("hypothetical", lambda e: e.update(hypothetical=True), "not a real event"),
    ("scenario flag", lambda e: e.update(scenario=True), "not a real event"),
    ("synthetic flag", lambda e: e.update(synthetic=True), "not a real event"),
    ("no evidence", lambda e: e.update(evidence=[]), "missing field 'evidence'"),
    ("short quote", lambda e: e["evidence"][0].update(quote="too short"), "too short"),
    ("unknown source id", lambda e: e["evidence"][0].update(source_id="s9"), "unknown source"),
    ("unknown place", lambda e: e["location"].update(gazetteer_key="atlantis"), "not in the gazetteer"),
    ("no location basis", lambda e: e["location"].update(basis=""), "no stated basis"),
    ("not verified", lambda e: e["verification"].update(status="FAILED"), "verification status"),
    ("quote not found", lambda e: e["verification"].update(quotes_found=e["verification"]["quotes_total"] - 1), "verbatim"),
    ("date unconfirmed", lambda e: e["verification"].update(date_confirmed=False), "not confirmed"),
    ("event after publication", lambda e: e.update(event_date="2099-01-01"), "after published_date"),
    ("bad date", lambda e: e.update(published_date="soon"), "ISO"),
    ("no verification", lambda e: e.pop("verification"), "missing field 'verification'"),
])
def test_inadmissible_records_are_rejected(name, mutate, expected):
    problems = _problems(mutate)
    assert any(expected in p for p in problems), (name, problems)


def test_duplicate_ids_are_rejected():
    register = copy.deepcopy(reg.load_register())
    register["events"].append(copy.deepcopy(register["events"][0]))
    assert "duplicate id" in reg.validate_register(register)[register["events"][0]["id"]]


# ------------------------------------------------------------------ text helpers
def test_text_helpers():
    assert reg.normalize_text("A &amp;  B\n\tC") == "A & B C"
    assert reg.html_to_text("<p>One</p><script>x()</script><style>.a{}</style><b>Two&nbsp;three</b>") == "One Two three"
    assert reg.sentence_containing("First one. Samsung Electro-Mechanics is joining us. Last.", "joining") == "Samsung Electro-Mechanics is joining us."
    assert reg.sentence_containing("Nothing here.", "absent") is None
    assert reg.long_date_forms("2026-10-08") == ["October 8, 2026", "October 08, 2026"]


# ------------------------------------------------- the retrieval script (offline)
PAGE = ("<html><body><h1>Big Announcement Title</h1><p>October 08, 2026</p>"
        "<p>SANTA CLARA, Calif., Oct. 08, 2026 (GLOBE NEWSWIRE) -- Acme today announced plans for a thing that matters. "
        "It will happen in Taiwan.</p></body></html>")


def a_spec(**over):
    s = dict(id="t1", title="Big Announcement Title", url="https://investor.nvidia.com/x", published="2026-10-08", category="CORPORATE_ANNOUNCEMENT",
             anchors=["Acme today announced plans"], location_key="santa-clara-us", location_anchor="SANTA CLARA, Calif., Oct. 08, 2026",
             publisher="NVIDIA Investor Relations", kind="html", api_url=None, location_basis=None, event_date_basis="press release date")
    s.update(over)
    return s


def with_page(monkeypatch, html=PAGE, status=200):
    monkeypatch.setattr(script, "fetch", lambda url: (status, html))


def test_script_verifies_a_good_page_and_records_verbatim_quotes(monkeypatch):
    with_page(monkeypatch)
    result = script.check(a_spec())
    assert result["problems"] == [] and result["verification"]["status"] == reg.VERIFIED
    quote = result["quotes"][0]
    assert quote in reg.html_to_text(PAGE) and "Acme today announced plans" in quote
    rec = script.record(a_spec(), result)
    assert reg.validate_event(rec) == []                                  # the record the script writes is admissible


@pytest.mark.parametrize("override,expected", [
    (dict(published="2026-10-09"), "publication date not confirmed"),
    (dict(title="A Different Title"), "title not found"),
    (dict(anchors=["this sentence is not on the page"]), "anchor not found"),
    (dict(location_anchor="LAS VEGAS, Jan. 05, 2026"), "location basis"),
])
def test_script_refuses_anything_it_cannot_verify(monkeypatch, override, expected):
    with_page(monkeypatch)
    result = script.check(a_spec(**override))
    assert result["verification"]["status"] == "FAILED"
    assert any(expected in p for p in result["problems"]), result["problems"]


def test_script_rechecks_stored_quotes_and_detects_drift(monkeypatch):
    with_page(monkeypatch)
    stored = script.check(a_spec())["quotes"]
    assert script.check(a_spec(), quotes=stored)["problems"] == []
    with_page(monkeypatch, html=PAGE.replace("plans for a thing", "plans for something else"))
    drifted = script.check(a_spec(), quotes=stored)
    assert any("not found verbatim" in p for p in drifted["problems"])


def test_build_writes_only_what_verified_and_reports_the_rest(monkeypatch, tmp_path):
    good, bad = a_spec(), a_spec(id="t2", title="Missing Title")
    monkeypatch.setattr(script, "SPECS", [good, bad])
    with_page(monkeypatch)
    out = tmp_path / "register.json"
    assert script.build(out) == 1                                          # non-zero: something was rejected
    import json
    written = json.loads(out.read_text())
    assert [e["id"] for e in written["events"]] == ["t1"]
    assert written["register"]["specs_rejected"][0]["id"] == "t2"


def test_build_survives_a_failed_fetch_without_guessing(monkeypatch, tmp_path):
    monkeypatch.setattr(script, "SPECS", [a_spec()])
    def boom(url): raise OSError("network down")
    monkeypatch.setattr(script, "fetch", boom)
    assert script.build(tmp_path / "r.json") == 1
    import json
    assert json.loads((tmp_path / "r.json").read_text())["events"] == []
