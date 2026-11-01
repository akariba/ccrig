"""Event discovery building blocks: hardened retrieval, providers, extraction, verification, deduplication and the guarded AI layer."""
import json
from datetime import date, timedelta

import pytest

from app.core import event_register as reg
from app.discovery import agent, dedupe, entity, extract, net, providers, verify
from app.discovery.providers import RetrievedDocument, canonical_bytes, to_text
from app.studio.resolve import EntityIndex
from tests.discovery_helpers import AS_OF, FIX, MANIFEST, transport


# ------------------------------------------------------------------ retrieval hardening
@pytest.mark.parametrize("url,code", [
    ("http://nvidianews.nvidia.com/x", "NOT_HTTPS"), ("ftp://nvidianews.nvidia.com/x", "NOT_HTTPS"), ("file:///etc/passwd", "NOT_HTTPS"),
    ("https://user:pw@nvidianews.nvidia.com/x", "CREDENTIALS_IN_URL"), ("https://nvidianews.nvidia.com@evil.example/x", "CREDENTIALS_IN_URL"),
    ("https://nvidianews.nvidia.com:8443/x", "BAD_PORT"), ("https://127.0.0.1/x", "IP_LITERAL"), ("https://[::1]/x", "IP_LITERAL"),
    ("https://evil.example/x", "HOST_NOT_APPROVED"), ("https://nvidianews.nvidia.com.evil.example/x", "HOST_NOT_APPROVED"), ("https:///x", "NO_HOST"),
])
def test_urls_are_refused_unless_https_approved_and_plain(url, code):
    with pytest.raises(net.FetchRefused) as e:
        net.check_url(url, providers.host_ok)
    assert e.value.code == code


def test_approved_hosts_and_their_subdomains_pass():
    assert net.check_url("https://nvidianews.nvidia.com/news/x", providers.host_ok) == "nvidianews.nvidia.com"
    assert net.check_url("https://www.federalregister.gov/api/v1/documents.json", providers.host_ok) == "www.federalregister.gov"


@pytest.mark.parametrize("addr", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1", "fe80::1", "0.0.0.0", "100.64.0.1"])
def test_private_and_special_addresses_are_refused(addr):
    with pytest.raises(net.FetchRefused) as e:
        net.check_addresses(["93.184.216.34", addr])                       # one bad address among good ones is enough
    assert e.value.code == "PRIVATE_ADDRESS"
    assert net.check_addresses(["93.184.216.34"]) == ["93.184.216.34"]


def test_network_is_off_unless_the_operator_turns_it_on(monkeypatch):
    monkeypatch.delenv("CCRIG_DISCOVERY_NETWORK", raising=False)
    with pytest.raises(net.FetchRefused) as e:
        net.HttpTransport(providers.host_ok).get("https://nvidianews.nvidia.com/releases.xml")
    assert e.value.code == "NETWORK_DISABLED"


def test_fixture_transport_enforces_the_same_url_policy_and_has_no_hidden_network():
    t = net.FixtureTransport({"https://nvidianews.nvidia.com/a": (200, "text/html", b"x")}, providers.host_ok)
    assert t.get("https://nvidianews.nvidia.com/a").status == 200
    with pytest.raises(net.FetchRefused) as e:
        t.get("https://nvidianews.nvidia.com/never-recorded")
    assert e.value.code == "NOT_RECORDED"
    with pytest.raises(net.FetchRefused):
        t.get("https://evil.example/a")


def test_provider_configuration_is_checked_against_the_approved_sources(monkeypatch):
    assert [p.id for p in providers.load_providers()] == ["nvidia_newsroom_feed", "federal_register"]
    bad = json.loads(json.dumps({"providers": [{"id": "x", "kind": "rss", "label": "x", "approved_source_id": "nvidia_newsroom", "url": "https://evil.example/feed", "entities": "*"}]}))
    monkeypatch.setattr(providers.json, "loads", lambda s, *a, **k: bad if "providers" in s else json.JSONDecoder().decode(s))
    with pytest.raises(providers.ProviderConfigError):
        providers.load_config()


def test_feeds_that_declare_a_dtd_or_entities_are_refused():
    for body in (b'<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title></item></channel></rss>',
                 b'<!doctype html><html></html>', b'<rss><channel><!ENTITY x "y"></channel></rss>'):
        with pytest.raises(net.FetchRefused) as e:
            providers.parse_feed(body)
        assert e.value.code == "UNSAFE_XML"
    with pytest.raises(net.FetchRefused) as e:
        providers.parse_feed(b"<rss><channel><item>")
    assert e.value.code == "MALFORMED_FEED"


def test_feed_items_become_dated_references_and_unapproved_hosts_are_listed_not_fetched():
    q = entity.build_query("NVDA")
    t = transport()
    refs, excluded, notes = providers.FeedProvider(providers.load_config()[0]).search(q, t, window_start=date(2026, 5, 5), as_of=AS_OF)
    assert [r.published_date for r in refs] == ["2026-10-28", "2026-10-27", "2026-10-27", "2026-10-21"]
    assert all("nvidianews.nvidia.com" in r.url for r in refs) and "pubDate" in refs[0].date_basis
    assert len(excluded) == 3 and all("blogs.nvidia.com" in x["reason"] and "not on the approved source list" in x["reason"] for x in excluded)
    assert not any("blogs.nvidia.com" in u for u in t.requested), "an unapproved host must never be requested"


# ------------------------------------------------------------------ entity resolution for the query
def test_the_query_is_resolved_to_one_canonical_company_or_explained():
    cases = {"NVIDIA": ("RESOLVED", "NVDA"), "nvda": ("RESOLVED", "NVDA"), "Nvidia Corporation": ("RESOLVED", "NVDA"), "TSMC": ("RESOLVED", "TSM"), "Google": ("RESOLVED", "GOOGL"),
             "Samsung": ("UNRESOLVED", None), "NotACompany": ("UNRESOLVED", None), "": ("UNRESOLVED", None)}
    for text, (status, eid) in cases.items():
        r = entity.resolve_entity(text)
        assert (r.status, r.entity_id) == (status, eid), text
    assert entity.resolve_entity("Samsung").rule == "DENIED_ALIAS" and "more than one distinct company" in entity.resolve_entity("Samsung").reason


def test_an_ambiguous_name_returns_every_candidate_and_chooses_none():
    ix = EntityIndex([{"id": "AC1", "name": "Acme Holdings", "ticker": "ACM", "node_type": "Company/Issuer"},
                      {"id": "AC2", "name": "ACME Holdings", "ticker": "ACME", "node_type": "Company/Issuer"}], set(), {})
    r = entity.resolve_entity("Acme Holdings", ix)
    assert r.status == "AMBIGUOUS" and r.candidates == ["AC1", "AC2"] and r.entity_id is None


def test_search_terms_come_from_the_canonical_name_and_approved_aliases_only():
    q = entity.build_query("GOOGL")
    assert q.terms == ["Alphabet", "Google Cloud", "Google"] and q.identifiers["entity_id"] == "GOOGL" and "GOOGL" not in q.terms
    assert entity.build_query("TSM").terms == ["Taiwan Semiconductor Manufacturing", "TSMC"]
    assert entity.core_name("JPMorgan Chase & Co.") == "JPMorgan Chase" and entity.core_name("Arm Holdings plc") == "Arm Holdings"


# ------------------------------------------------------------------ verification
def test_dates_are_recognised_in_every_common_printed_form():
    for printed in ("October 8, 2026", "October 08, 2026", "Oct. 8, 2026", "Oct. 08, 2026", "Oct 8, 2026", "8 October 2026", "2026-10-08"):
        assert verify.date_in_text("2026-10-08", f"x {printed} y"), printed
    assert not verify.date_in_text("2026-10-08", "October 9, 2026") and not verify.date_in_text("2026-10-08", "Oct. 18, 2026")
    assert verify.parse_printed_date("Oct. 26, 2026") == "2026-10-26" and verify.parse_printed_date("Feb. 30, 2026") is None and verify.parse_printed_date("soon") is None


def test_verification_checks_quotes_title_date_and_dateline_against_the_text():
    text = "Big News Inc. Big News Inc. Oct. 8, 2026 BERLIN -- Acme today announced something quite substantial about chips."
    ok = verify.verify_candidate(text=text, method="html_text", published_date="2026-10-08", title="Big News Inc.", quotes=["Acme today announced something quite substantial about chips."], basis_text="BERLIN --")
    assert ok["problems"] == [] and ok["verification"]["status"] == "VERIFIED_BY_RETRIEVAL" and ok["verification"]["quotes_found"] == 1
    bad = verify.verify_candidate(text=text, method="html_text", published_date="2026-10-09", title="Other title", quotes=["Acme announced nothing at all in this passage."], basis_text="PARIS --")
    assert len(bad["problems"]) == 4 and bad["verification"]["status"] == "FAILED"
    short = verify.verify_candidate(text=text, method="html_text", published_date="2026-10-08", title="Big News Inc.", quotes=["Acme"], basis_text=None)
    assert any("too short" in p for p in short["problems"])


# ------------------------------------------------------------------ extraction from real recorded pages
def _doc(page_file: str, title: str, published: str):
    raw = (FIX / page_file).read_bytes()
    return RetrievedDocument("nvidia_newsroom_feed", "nvidia_newsroom", "PRIMARY_ISSUER", "NVIDIA Newsroom", f"https://nvidianews.nvidia.com/news/{page_file}", f"https://nvidianews.nvidia.com/news/{page_file}",
                             title, published, "feed pubDate", raw, "text/html", to_text(raw, "html_text"), "html_text", "2026-11-01T10:00:00Z", 200)


def _page_for(fragment):
    return next(f for f in MANIFEST["pages"].values() if fragment in f)


def test_a_real_release_becomes_a_verified_candidate_with_the_places_the_source_prints():
    doc = _doc(_page_for("supply-chain"), "NVIDIA and Supply Chain Partners Expand Capacity to Accelerate AI Infrastructure Buildout", "2026-10-21")
    cand, rej = extract.extract(doc, entity.build_query("NVDA"), reg.gazetteer())
    assert rej is None and cand.verification["status"] == "VERIFIED_BY_RETRIEVAL" and cand.verification["quotes_found"] == len(cand.evidence_quotes) >= 1
    assert cand.location["gazetteer_key"] == "berlin-de" and "GTC Berlin" in cand.location["basis_text"]
    assert cand.category == "PARTNERSHIP_ANNOUNCEMENT" and cand.category_method.startswith("keyword rules")
    assert all(q in doc.text and len(q) >= 25 for q in cand.evidence_quotes)
    assert cand.id.startswith("nvda-20261021-") and cand.entity_in_title


def test_no_dateline_means_no_location_never_a_guessed_headquarters():
    doc = _doc(_page_for("oracle"), "NVIDIA and Oracle Expand NVIDIA Vera Rubin to Multi-Gigawatt Scale and Bring NVIDIA Vera CPU to Oracle Cloud Infrastructure", "2026-10-27")
    cand, rej = extract.extract(doc, entity.build_query("NVDA"), reg.gazetteer())
    assert rej is None and cand.location["gazetteer_key"] is None and "no dateline place" in cand.location["unmapped_reason"]
    assert "Santa Clara" not in json.dumps(cand.location) and cand.event_date_basis.startswith("press release date")


def test_a_one_day_difference_between_feed_and_page_is_used_openly_but_larger_gaps_are_refused():
    title = "NVIDIA and Meta to Expand Collaboration on Muse and Muse Family of Models Amid Robust Growth"
    near, rej = extract.extract(_doc(_page_for("meta"), title, "2026-10-27"), entity.build_query("NVDA"), reg.gazetteer())
    assert rej is None and near.published_date == "2026-10-26" and "the feed listed 2026-10-27" in near.event_date_basis
    far, rej = extract.extract(_doc(_page_for("meta"), title, "2026-10-12"), entity.build_query("NVDA"), reg.gazetteer())
    assert far is None and rej.stage == "VERIFY" and "not confirmed" in rej.reason


def test_scenarios_background_and_unrelated_documents_are_not_events():
    gz, q = reg.gazetteer(), entity.build_query("NVDA")
    mk = lambda title, text, method="html_text": RetrievedDocument("p", "nvidia_newsroom", "PRIMARY_ISSUER", "x", "https://nvidianews.nvidia.com/a", "https://nvidianews.nvidia.com/a", title, "2026-10-20", "d",  # noqa: E731
                                                                  text.encode(), "text/html", text, method, "2026-11-01T10:00:00Z", 200)
    scen = extract.extract(mk("Scenario: what if NVIDIA loses its foundry", "Scenario: what if NVIDIA loses its foundry Oct. 20, 2026 NVIDIA could face a disruption in this hypothetical scenario of chip supply."), q, gz)
    assert scen[0] is None and "scenario" in scen[1].reason
    back = extract.extract(mk("An overview of NVIDIA and its suppliers", "An overview of NVIDIA and its suppliers Oct. 20, 2026 NVIDIA works with many partners across the world."), q, gz)
    assert back[0] is None and "background" in back[1].reason
    other = extract.extract(mk("Acme Corp opens a lab", "Acme Corp opens a lab Oct. 20, 2026 Acme Corp today announced a new research laboratory in a European city."), q, gz)
    assert other[0] is None and other[1].stage == "RELEVANCE" and "not named" in other[1].reason


# ------------------------------------------------------------------ federal register: real recorded shape
def test_federal_register_documents_must_name_the_company_and_get_an_issuer_country_location():
    pv = {p.id: p for p in providers.load_providers()}
    fr = pv["federal_register"]
    t = transport("NVDA", date(2026, 2, 1), feed=False)
    refs, excluded, notes = fr.search(entity.build_query("NVDA"), t, window_start=date(2026, 2, 1) - timedelta(days=180), as_of=date(2026, 2, 1))
    assert refs and all(r.url.startswith("https://www.federalregister.gov/") and r.record for r in refs)
    named = [r for r in refs if "nvidia" in (r.title + " " + r.summary).lower()]
    assert named, "the recorded real response contains a document naming NVIDIA"
    doc = fr.retrieve(named[0], t)
    cand, rej = extract.extract(doc, entity.build_query("NVDA"), reg.gazetteer())
    assert rej is None and cand.category == "REGULATORY_ACTION" and cand.location["gazetteer_key"] == "country-us" and "country-level" in cand.location["basis"]
    assert doc.text_method == "api_json" and to_text(doc.raw, "api_json") == doc.text and cand.verification["date_basis"].startswith("Federal Register API")


# ------------------------------------------------------------------ deduplication
def _cand(title, url, tier, published="2026-10-21", quotes=("NVIDIA today announced plans with partners to expand capacity.",)):
    doc = RetrievedDocument("p", "nvidia_newsroom", tier, "x", url, url, title, published, "d", b"", "text/html", " ".join(quotes), "html_text", "2026-11-01T10:00:00Z", 200)
    return extract.Candidate(extract.event_id("NVDA", published, title, url), "NVDA", title, "CORPORATE_ANNOUNCEMENT", "m", published, published, "b", {}, list(quotes), {}, doc)


def test_reports_of_the_same_event_collapse_into_the_best_source():
    a = _cand("NVIDIA and Partners Expand Capacity", "https://nvidianews.nvidia.com/news/a?utm_source=x", "PRIMARY_ISSUER")
    b = _cand("NVIDIA and Partners Expand Capacity", "https://nvidianews.nvidia.com/news/a/", "PRIMARY_ISSUER")               # same URL, tracking query, trailing slash
    c = _cand("Partners Expand Capacity With NVIDIA", "https://news.skhynix.com/x", "PRIMARY_RELATED_PARTY", published="2026-10-22", quotes=("Different words entirely in this passage here.",))
    d = _cand("NVIDIA Announces Quarterly Results", "https://nvidianews.nvidia.com/news/q", "PRIMARY_ISSUER", published="2026-10-28", quotes=("NVIDIA reported revenue for the quarter that ended.",))
    primaries, dup = dedupe.dedupe([c, a, b, d])
    assert {p.id for p in primaries} == {a.id, d.id} or len(primaries) == 2
    head = next(p for p in primaries if "Capacity" in p.title)
    assert head.doc.tier == "PRIMARY_ISSUER" and set(head.also_reported_by) == {x.doc.url for x in (a, b, c) if x is not head}
    assert len(dup) == 2 and all(x["stage"] == "DEDUPE" and "another report of the same event" in x["reason"] for x in dup)
    assert [p.id for p in dedupe.dedupe([d, b, a, c])[0]] == [p.id for p in primaries]                 # independent of input order


def test_different_events_on_the_same_day_are_not_merged():
    a = _cand("NVIDIA and Oracle Expand Vera Rubin", "https://nvidianews.nvidia.com/news/o", "PRIMARY_ISSUER", published="2026-10-27", quotes=("NVIDIA and Oracle today announced plans to expand clusters.",))
    b = _cand("NVIDIA and Meta Expand Collaboration on Muse", "https://nvidianews.nvidia.com/news/m", "PRIMARY_ISSUER", published="2026-10-27", quotes=("NVIDIA and Meta today announced they will partner to expand work.",))
    assert len(dedupe.dedupe([a, b])[0]) == 2


# ------------------------------------------------------------------ the AI layer can suggest, never decide
TEXT = ("Acme Corp Oct. 20, 2026 NVIDIA and Oracle today announced plans to expand cloud capacity with new systems. "
        "Oracle will buy accelerated computing systems from NVIDIA to power its regions around the world. NVIDIA also works with Zorblax Dynamics on new deployments worldwide.")


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply

    def complete_json(self, system, user):
        assert "untrusted" in system and "TEXT>>>" in user
        return self.reply


def test_the_guard_drops_everything_the_model_invented_and_keeps_only_verified_suggestions():
    q = entity.build_query("NVDA")
    reply = {"category": "ALIEN_INVASION", "quotes": ["NVIDIA and Oracle today announced plans to expand cloud capacity with new systems.", "NVIDIA acquired Zorblax Dynamics for $5 billion in cash."],
             "relationships": [
                 {"a": "NVIDIA", "b": "Oracle", "relation": "SUPPLIES", "quote": "Oracle will buy accelerated computing systems from NVIDIA to power its regions around the world."},
                 {"a": "NVIDIA", "b": "Zorblax Dynamics", "relation": "SUPPLIES", "quote": "NVIDIA also works with Zorblax Dynamics on new deployments worldwide."},
                 {"a": "NVIDIA", "b": "Oracle", "relation": "OWNS", "quote": "Oracle will buy accelerated computing systems from NVIDIA to power its regions around the world."},
                 {"a": "NVIDIA", "b": "Oracle", "relation": "SUPPLIES", "quote": "NVIDIA supplies Oracle with everything it needs."}, "garbage", None]}
    out = agent.guard(reply, text=TEXT, query=q)
    assert out["category"] is None and out["quotes"] == ["NVIDIA and Oracle today announced plans to expand cloud capacity with new systems."]
    assert len(out["relationships"]) == 1
    rel = out["relationships"][0]
    assert (rel["a_entity"], rel["b_entity"], rel["relation"]) == ("NVDA", "ORCL", "SUPPLIES") and rel["status"] == "AI_PROPOSED_UNREVIEWED" and "not an edge" in rel["note"]
    reasons = " | ".join(d["reason"] for d in out["dropped"])
    for expect in ("not one of the allowed categories", "not found verbatim", "not one of the allowed types", "does not resolve to exactly one distinct canonical entity"):
        assert expect in reasons, expect
    assert agent.guard("not json", text=TEXT, query=q)["dropped"][0]["reason"].startswith("the model did not return")


def test_model_supplied_identifiers_are_ignored_and_an_unreachable_model_changes_nothing():
    q = entity.build_query("NVDA")
    out = agent.guard({"relationships": [{"a": "NVIDIA", "b": "Oracle", "relation": "SUPPLIES", "a_id": "JPM", "b_id": "AMD",
                                          "quote": "Oracle will buy accelerated computing systems from NVIDIA to power its regions around the world."}]}, text=TEXT, query=q)
    assert (out["relationships"][0]["a_entity"], out["relationships"][0]["b_entity"]) == ("NVDA", "ORCL")
    none = agent.refine(FakeLLM(None), text=TEXT, candidate=_cand("t", "https://nvidianews.nvidia.com/x", "PRIMARY_ISSUER"), query=q)
    assert none["used"] is False and none["relationships"] == [] and "unreachable" in none["dropped"][0]["reason"]
    assert agent.refine(None, text=TEXT, candidate=None, query=q)["used"] is False
