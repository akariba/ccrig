"""Event discovery, typed transmission paths, missing evidence and the API.

The rules this protects (from the product brief): nothing invented; fewer than five events when
fewer qualify, with the reason; graph proximity, similarity and correlation are never equated;
relationship evidence is kept apart from impact; impact is never estimated until validated.
"""
import copy
import json
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core import event_discovery as disc  # noqa: E402
from app.core import event_graph as graph  # noqa: E402
from app.core import event_register as reg  # noqa: E402
from app.core.data import STORE  # noqa: E402
from validation import snapshot  # noqa: E402

via_fastapi = snapshot.fastapi_request()
via_dispatch = snapshot.dispatch_request()
BOTH = pytest.mark.parametrize("request_fn", [via_fastapi, via_dispatch], ids=["fastapi", "dispatcher"])
REGISTER_IDS = {e["id"] for e in reg.load_register()["events"]}


@pytest.fixture(scope="module")
def nvda():
    return disc.discover("NVDA")


def by_id(result):
    return {e["id"]: e for e in result["events"]}


# ------------------------------------------------------------------ discovery
def test_returns_the_five_most_recent_verified_events_newest_first(nvda):
    assert len(nvda["events"]) == 5
    dates = [e["published_date"] for e in nvda["events"]]
    assert dates == sorted(dates, reverse=True) == ["2026-10-21", "2026-10-14", "2026-10-08", "2026-08-26", "2026-07-25"]
    assert nvda["query"]["as_of"] == "2026-11-01" and nvda["as_of_basis"] == "the register's build date"


def test_nothing_is_invented_every_event_is_a_register_record(nvda):
    assert {e["id"] for e in nvda["events"]} <= REGISTER_IDS
    assert {e["id"] for e in nvda["events"]} | {r["id"] for r in nvda["not_returned"]} == REGISTER_IDS      # every record is accounted for


def test_each_event_carries_source_dates_location_and_evidence(nvda):
    for e in nvda["events"]:
        assert e["sources"] and e["sources"][0]["url"].startswith("https://") and e["sources"][0]["publisher"]
        assert e["published_date"] and e["event_date"] and e["event_date_basis"]
        assert e["location"]["mapped"] and e["location"]["basis"] and e["location"]["precision"]
        assert e["evidence"] and all(q["quote"] and q["url"] for q in e["evidence"])
        assert e["verification"]["status"] == reg.VERIFIED
        assert e["limitations"] and e["impact"]["status"] == "NOT_ESTIMATED"


def test_events_not_returned_say_why(nvda):
    reasons = {r["id"]: r["reason"] for r in nvda["not_returned"]}
    assert set(reasons) == {"nvda-20260601-gtc-taipei-rtx-spark", "nvda-20260115-bis-h200-china-license-policy", "nvda-20260105-ces-rubin-platform"}
    assert "ranks below the limit of 5" in reasons["nvda-20260601-gtc-taipei-rtx-spark"]
    assert "290 days" in reasons["nvda-20260115-bis-h200-china-license-policy"] and "180 days" in reasons["nvda-20260115-bis-h200-china-license-policy"]


def test_fewer_than_five_are_returned_and_the_shortfall_is_explained():
    r = disc.discover("NVDA", recency_days=30)
    assert [e["published_date"] for e in r["events"]] == ["2026-10-21", "2026-10-14", "2026-10-08"]
    assert "fewer than the 5 requested" in r["explanation"] and "No events were added to fill the count" in r["explanation"]


def test_limit_is_respected_and_capped_at_five():
    assert len(disc.discover("NVDA", limit=2)["events"]) == 2
    assert len(disc.discover("NVDA", limit=99)["events"]) == 5
    assert len(disc.discover("NVDA", limit=0)["events"]) == 1                       # clamped to at least one


def test_widening_the_window_still_never_exceeds_five():
    r = disc.discover("NVDA", recency_days=730)
    assert len(r["events"]) == 5 and sum("ranks below the limit" in x["reason"] for x in r["not_returned"]) == 3


def test_as_of_moves_the_window():
    r = disc.discover("NVDA", as_of=date(2026, 6, 30))
    assert [e["published_date"] for e in r["events"]] == ["2026-06-01", "2026-01-15", "2026-01-05"] and r["as_of_basis"] == "supplied by the caller"
    assert disc.discover("NVDA", as_of=date(2025, 1, 1))["events"] == []              # before the register: none, not invented
    future = {x["id"]: x["reason"] for x in disc.discover("NVDA", as_of=date(2026, 7, 1))["not_returned"]}
    assert "published after the as-of date" in future["nvda-20261021-supply-chain-capacity"]


def test_an_entity_the_register_does_not_cover_gets_no_events_and_an_honest_explanation():
    r = disc.discover("TSM")
    assert r["events"] == [] and "No event in the approved-source register names" in r["explanation"] and "none are invented" in r["explanation"]
    assert r["graph"]["nodes"][0]["entity_id"] == "TSM" and r["graph"]["edges"] == []


def test_ranking_is_deterministic():
    assert json.dumps(disc.discover("NVDA"), sort_keys=True) == json.dumps(disc.discover("NVDA"), sort_keys=True)


# ------------------------------------------------- policy gates inside discovery
def with_register(monkeypatch, mutate):
    register = copy.deepcopy(reg.load_register())
    mutate(register)
    monkeypatch.setattr(reg, "load_register", lambda: register)


def test_an_unapproved_source_never_reaches_the_map(monkeypatch):
    with_register(monkeypatch, lambda r: r["events"][0]["sources"][0].update(url="https://www.reuters.com/x"))
    r = disc.discover("NVDA")
    assert "nvda-20261021-supply-chain-capacity" not in by_id(r)
    reason = next(x["reason"] for x in r["not_returned"] if x["id"] == "nvda-20261021-supply-chain-capacity")
    assert reason.startswith("inadmissible") and "approved" in reason


@pytest.mark.parametrize("mutate", [
    lambda r: r["events"][0]["verification"].update(status="FAILED"),
    lambda r: r["events"][0].update(hypothetical=True),
    lambda r: r["events"][0].update(kind="SCENARIO"),
    lambda r: r["events"][0]["verification"].update(quotes_found=0),
])
def test_unverified_or_hypothetical_records_are_excluded(monkeypatch, mutate):
    with_register(monkeypatch, mutate)
    r = disc.discover("NVDA")
    assert "nvda-20261021-supply-chain-capacity" not in by_id(r)
    assert len(r["events"]) == 5                                                  # the next-newest takes its place; nothing fabricated
    assert all(e["id"] in REGISTER_IDS for e in r["events"])


def test_an_event_that_does_not_name_the_entity_is_excluded(monkeypatch):
    def strip(register):
        ev = register["events"][2]                                                 # US science commitment
        ev["title"] = "A commitment to US science"
        ev["evidence"] = [{"source_id": "s1", "quote": "The company today announced commitments valued at $1 billion for research."}]
    with_register(monkeypatch, strip)
    reason = next(x["reason"] for x in disc.discover("NVDA")["not_returned"] if x["id"] == "nvda-20261008-us-science-commitment")
    assert "not named in the cited evidence" in reason


# ------------------------------------------------------------------ typed paths
def test_the_target_itself_is_a_direct_mention_with_quoted_evidence(nvda):
    e = by_id(nvda)["nvda-20261008-us-science-commitment"]
    [path] = e["paths"]
    assert path["relationship_type"] == "DIRECT_MENTION" and [s["type"] for s in path["steps"]] == ["MENTIONS"]
    assert path["steps"][0]["evidence"]["matched_text"] and path["steps"][0]["evidence"]["quote"]


def test_documented_direct_paths_keep_relation_direction_and_evidence_status(nvda):
    e = by_id(nvda)["nvda-20260725-sk-group-partnership"]
    skhy = next(p for p in e["paths"] if p["entity_id"] == "SKHY")
    hop = skhy["steps"][1]
    assert skhy["relationship_type"] == "DOCUMENTED_DIRECT" and hop["relation"] == "SUPPLIES"
    assert (hop["from"], hop["to"]) == ("SKHY", "NVDA") and hop["traversal"] == "WITH_STORED_DIRECTION"
    assert hop["stored_edge"] == {"source": "SKHY", "target": "NVDA"} and hop["evidence_status"] == "REPORTED_NEWS"
    assert hop["criticality"] == 0.78 and "not a measured exposure" in hop["criticality_meaning"]


def test_direction_is_never_flipped_when_traversed_against_the_stored_edge(nvda):
    e = by_id(nvda)["nvda-20260826-q2-fy2027-results"]
    msft = next(p for p in e["paths"] if p["entity_id"] == "MSFT")
    hop = msft["steps"][1]
    assert hop["stored_edge"] == {"source": "NVDA", "target": "MSFT"}             # NVIDIA supplies Microsoft
    assert (hop["from"], hop["to"]) == ("MSFT", "NVDA") and hop["traversal"] == "AGAINST_STORED_DIRECTION"


def test_indirect_paths_are_the_shortest_documented_ones(nvda):
    e = by_id(nvda)["nvda-20261014-semicon-west-ai-fabs"]
    indirect = [p for p in e["paths"] if p["entity_id"] == "AMAT"]
    assert indirect and all(p["relationship_type"] == "DOCUMENTED_INDIRECT" and len(p["steps"]) == 3 for p in indirect)
    assert {p["steps"][1]["to"] for p in indirect} == {"TSM", "SKHY", "MU"} and all(p["steps"][2]["to"] == "NVDA" for p in indirect)
    assert len(indirect) <= graph.MAX_PATHS_PER_ENTITY


def test_a_named_entity_with_no_documented_path_is_shown_as_such_not_linked(nvda):
    e = by_id(nvda)["nvda-20260826-q2-fy2027-results"]
    oracle = next(x for x in e["entities"] if x["entity_id"] == "ORCL")
    assert oracle["relationship_to_target"] == "NO_DOCUMENTED_PATH" and "absence in the data" in oracle["explanation"]
    assert not [p for p in e["paths"] if p["entity_id"] == "ORCL"]                    # no path is drawn
    assert any("Oracle" in lim and "no documented relationship" in lim for lim in e["limitations"])


def test_documented_paths_function_edge_cases():
    assert graph.documented_paths("NVDA", "NVDA") == []
    assert graph.documented_paths("ORCL", "NVDA") == []
    assert graph.documented_paths("NOPE", "NVDA") == [] and graph.documented_paths("TSM", "NOPE") == []
    assert all(len(p) == 1 for p in graph.documented_paths("TSM", "NVDA"))
    assert graph.classify("NVDA", "NVDA", []) == "SELF" and graph.classify("X", "NVDA", []) == "NO_DOCUMENTED_PATH"


def test_only_typed_documented_relations_and_mentions_appear_never_similarity_or_correlation(nvda):
    for e in nvda["events"]:
        for p in e["paths"]:
            assert p["steps"][0]["type"] == "MENTIONS"
            for step in p["steps"][1:]:
                assert step["type"] == "DOCUMENTED_RELATION" and step["relation"] in graph.DOCUMENTED_RELATIONS
    text = json.dumps(nvda).lower()
    for banned in ("similarity", "correlation", "composite_score", "ppr_score", "relatedness"):
        assert banned not in text.replace("no similarity", ""), banned


def test_impact_is_never_estimated_and_is_kept_apart_from_relationship_evidence(nvda):
    for e in nvda["events"]:
        assert e["impact"] == {**graph.IMPACT_NOT_ESTIMATED} and e["impact"]["estimate"] is None
        assert e["verified_exposure"]["status"] == "NOT_AVAILABLE"
        assert "exposure_pct" not in json.dumps(e)                                  # the synthetic exposure data is not used
    flat = json.dumps(nvda)
    for banned in ('"probability"', '"impact_score"', '"impact_weight"', '"expected_loss"', '"exposure_amount"'):
        assert banned not in flat


def test_the_graph_has_typed_nodes_and_edges_traceable_to_events(nvda):
    g = nvda["graph"]
    node_ids = {n["id"] for n in g["nodes"]}
    assert {n["type"] for n in g["nodes"]} == {"EVENT", "ENTITY", "REGION"}
    assert {e["type"] for e in g["edges"]} == {"MENTIONS", "MENTIONS_REGION", "DOCUMENTED_RELATION"}
    for edge in g["edges"]:
        assert edge["source"] in node_ids and edge["target"] in node_ids and edge["event_ids"]
        assert set(edge["event_ids"]) <= {e["id"] for e in nvda["events"]}
        if edge["type"] == "DOCUMENTED_RELATION":
            assert edge["relation"] in graph.DOCUMENTED_RELATIONS and edge["evidence_status"]
        else:
            assert edge["evidence"]["quote"]
    assert sum(1 for n in g["nodes"] if n["type"] == "EVENT") == 5


def test_an_unmapped_event_is_not_plotted(monkeypatch):
    with_register(monkeypatch, lambda r: r["events"][0]["location"].update(gazetteer_key="atlantis"))
    r = disc.discover("NVDA")
    # the record fails the gazetteer check, so it is excluded rather than drawn at a guessed point
    assert "nvda-20261021-supply-chain-capacity" not in by_id(r)
    assert "gazetteer" in next(x["reason"] for x in r["not_returned"] if x["id"] == "nvda-20261021-supply-chain-capacity")


def test_an_entity_without_a_known_position_is_returned_but_not_plotted(monkeypatch):
    monkeypatch.setattr("app.core.event_geo.entity_position", lambda eid: None)
    r = disc.discover("NVDA")
    nodes = [n for n in r["graph"]["nodes"] if n["type"] == "ENTITY"]
    assert nodes and all(n["position"] is None for n in nodes)


def test_limitations_are_specific_and_honest(nvda):
    e = by_id(nvda)["nvda-20261021-supply-chain-capacity"]
    text = " ".join(e["limitations"])
    assert "not independently verified" in text and "forward-looking" in text and "Regions are countries named" in text
    q2 = " ".join(by_id(nvda)["nvda-20260826-q2-fy2027-results"]["limitations"])
    assert "curated judgement" in q2 and "not a measured exposure" in q2          # an event with documented links says what criticality is
    assert "not necessarily the relationship the event describes" in q2
    assert all("is not named" not in lim for lim in e["limitations"])
    assert len(nvda["limitations"]) >= 3 and any("does not search the live web" in lim for lim in nvda["limitations"])


# ------------------------------------------------------------------------ API
@BOTH
def test_search_resolves_the_company_and_reports_coverage(request_fn):
    status, body = request_fn("GET", "/api/impact-map/search?q=NVIDIA", None)
    assert status == 200 and [m["entity_id"] for m in body["matches"]] == ["NVDA"]
    assert body["matches"][0]["event_coverage"] is True and body["matches"][0]["events_in_register"] == 8
    status, body = request_fn("GET", "/api/impact-map/search?q=zzzzqq", None)
    assert status == 200 and body["matches"] == [] and "Nothing is guessed" in body["message"]
    status, body = request_fn("GET", "/api/impact-map/search?q=TSMC", None)
    assert [m["entity_id"] for m in body["matches"]] == ["TSM"] and body["matches"][0]["event_coverage"] is False


@BOTH
def test_events_endpoint_returns_the_full_picture(request_fn):
    status, body = request_fn("GET", "/api/impact-map/NVDA/events", None)
    assert status == 200 and len(body["events"]) == 5 and body["graph"]["nodes"] and body["limitations"]
    assert request_fn("GET", "/api/impact-map/nvda/events", None)[0] == 200
    status, body = request_fn("GET", "/api/impact-map/NVDA/events?recency_days=30", None)
    assert status == 200 and len(body["events"]) == 3 and "fewer than" in body["explanation"]
    status, body = request_fn("GET", "/api/impact-map/TSM/events", None)
    assert status == 200 and body["events"] == []


@BOTH
@pytest.mark.parametrize("path,expected", [
    ("/api/impact-map/NOPE/events", 404), ("/api/impact-map/CP_ALPHA/events", 404),                 # counterparties are not issuers
    ("/api/impact-map/NVDA/events?limit=0", 422), ("/api/impact-map/NVDA/events?limit=6", 422),
    ("/api/impact-map/NVDA/events?recency_days=0", 422), ("/api/impact-map/NVDA/events?recency_days=731", 422),
    ("/api/impact-map/NVDA/events?as_of=tomorrow", 422), ("/api/impact-map/NVDA/events?as_of=2026-02-30", 422),
    ("/api/impact-map/NVDA/events?as_of=2026-1-1", 422), ("/api/impact-map/search?q=", 422), ("/api/impact-map/search", 422),
])
def test_api_rejects_what_it_should(request_fn, path, expected):
    assert request_fn("GET", path, None)[0] == expected


def test_both_transports_return_identical_bodies():
    for path in ("/api/impact-map/NVDA/events", "/api/impact-map/search?q=NVIDIA", "/api/impact-map/NVDA/events?limit=2&recency_days=400",
                 "/api/impact-map/TSM/events", "/api/impact-map/register"):
        a, b = via_fastapi("GET", path, None), via_dispatch("GET", path, None)
        assert a[0] == b[0] == 200 and snapshot.diff(a[1], b[1]) == [], path


def test_the_register_endpoint_reports_policy_and_its_own_admissibility():
    status, body = via_fastapi("GET", "/api/impact-map/register", None)
    assert status == 200 and body["inadmissible"] == {} and body["events_total"] == 8
    assert {s["id"] for s in body["approved_sources"]} >= {"nvidia_newsroom", "us_federal_register"}


def test_the_synthetic_counterparty_data_is_not_touched_by_the_map(nvda):
    assert not any(STORE.entity(n["entity_id"])["node_type"] == "Counterparty" for n in nvda["graph"]["nodes"] if n["type"] == "ENTITY")


# ------------------------------------------------------------------ baseline
def test_impact_map_responses_match_their_recorded_baseline_on_both_transports():
    from validation import impact_snapshot as base
    expected = json.loads(base.IMPACT_FILE.read_text())
    for label, request_fn in (("fastapi", via_fastapi), ("dispatcher", via_dispatch)):
        diffs = snapshot.diff(expected, snapshot.normalise(base.capture(request_fn)))
        assert not diffs, f"{label}: " + "; ".join(f"{p}: {e!r} -> {a!r}" for p, e, a in diffs[:5])


def test_the_existing_analytics_baseline_is_untouched_by_the_map():
    """The map adds endpoints; it must not move a single pinned score, rank or priority."""
    actual = snapshot.normalise(snapshot.capture(via_fastapi))
    assert snapshot.diff(snapshot.load_snapshot(), actual) == []
