"""Entity resolution and geographic mapping for event evidence.

Precision matters more than recall here: a wrong link would draw a false
relationship on the map. Each trap below is a mistake a naive matcher makes.
"""
import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core import event_entities as ee  # noqa: E402
from app.core import event_geo as geo  # noqa: E402
from app.core import event_register as reg  # noqa: E402
from app.core.data import STORE  # noqa: E402


def ids(text):
    return {m["entity_id"] for m in ee.resolve_text(text)}


EVENTS = {e["id"]: e for e in reg.load_register()["events"]}


# ------------------------------------------------------------- traps and rules
@pytest.mark.parametrize("text,expected", [
    # different companies that share a word
    ("Samsung Electro-Mechanics is joining NVIDIA’s substrate supply chain.", {"NVDA"}),
    ("Samsung Electronics supplies HBM to NVIDIA.", {"NVDA", "SSNLF"}),
    ("Samsung announced a new plant.", set()),                                  # 'Samsung' alone is a group, not an entity
    ("Unimicron expands in Taiwan.", set()),                                    # 'Unimicron' does not contain 'Micron'
    ("Micron Technology reported results.", {"MU"}),
    ("SK Group and SK Telecom announced plans.", set()),                        # affiliates, not the dataset's SK hynix
    ("SK hynix is a memory supplier.", {"SKHY"}),
    # a product brand is not the company that happens to share its ticker
    ("NVIDIA RTX Spark is a new superchip.", {"NVDA"}),
    ("The GeForce RTX 50 series launched.", set()),
    ("RTX Corporation reported results.", {"RTX"}),
    # common words are not companies
    ("They arm the rebels and consult the oracle.", set()),
    ("Arm Holdings plc licenses core designs.", {"ARM"}),
    ("A meta-analysis of the data.", set()),
    ("Meta and Google are customers.", {"META", "GOOGL"}),
    ("The Oracle Cloud Infrastructure region opened.", {"ORCL"}),
    # brands resolve to their parent
    ("racks at CoreWeave, Google Cloud, Microsoft Azure and Nebius", {"GOOGL", "MSFT"}),
    ("Amazon Web Services (AWS) adopts it.", {"AMZN"}),
    # tickers and acronyms
    ("NVIDIA (NASDAQ: NVDA) today reported revenue.", {"NVDA"}),
    ("TSMC and Taiwan Semiconductor Manufacturing are the same company.", {"TSM"}),
    ("tsmc in lower case is not a proper noun here", set()),
    ("IBM and AMD announced a collaboration.", {"IBM", "AMD"}),
    ("AMD Instinct accelerators ship soon.", set()),                            # documented conservatism: product-name shape
    # synthetic counterparties are never resolved from real events
    ("Alpha Quant Capital LP and Cascade Regional Bank Treasury.", set()),
])
def test_entity_resolution_traps(text, expected):
    assert ids(text) == expected


def test_every_resolution_names_its_rule_and_its_matched_text():
    for m in ee.resolve_text("NVIDIA (NASDAQ: NVDA) and Google Cloud and Microsoft"):
        assert m["rule"] in ("NAME_MATCH", "BRAND_ALIAS", "TICKER_TOKEN")
        assert m["matched_text"] and m["start"] < m["end"]
    rules = {m["matched_text"]: m["rule"] for m in ee.resolve_text("Google Cloud, Microsoft and NVDA")}
    assert rules == {"Google Cloud": "BRAND_ALIAS", "Microsoft": "NAME_MATCH", "NVDA": "TICKER_TOKEN"}


def test_longest_name_wins_and_spans_are_not_double_counted():
    mentions = ee.resolve_text("Applied Materials and Samsung Electronics")
    assert [m["entity_id"] for m in mentions] == ["AMAT", "SSNLF"]
    assert len(ee.resolve_text("Amazon Web Services")) == 1                     # not also 'Amazon'


def test_candidates_are_real_issuers_only():
    for m in ee._matchers():
        assert STORE.entity(m[0])["node_type"] == "Company/Issuer"


# ------------------------------------------------------------- the real evidence
EXPECTED = {
    "nvda-20261021-supply-chain-capacity": {"NVDA"},
    "nvda-20261014-semicon-west-ai-fabs": {"NVDA", "AMAT"},
    "nvda-20261008-us-science-commitment": {"NVDA"},
    "nvda-20260826-q2-fy2027-results": {"NVDA", "GOOGL", "MSFT", "ORCL", "SKHY"},
    "nvda-20260725-sk-group-partnership": {"NVDA", "SKHY"},
    "nvda-20260601-gtc-taipei-rtx-spark": {"NVDA", "MSFT"},
    "nvda-20260115-bis-h200-china-license-policy": {"NVDA"},
    "nvda-20260105-ces-rubin-platform": {"NVDA", "MSFT", "AMZN", "GOOGL", "META", "ORCL"},
}


@pytest.mark.parametrize("event_id", sorted(EXPECTED))
def test_resolution_of_each_registered_event(event_id):
    resolved = {r["entity_id"] for r in ee.resolve_event(EVENTS[event_id])}
    assert resolved == EXPECTED[event_id]


def test_supply_chain_event_does_not_confuse_samsung_electro_mechanics_with_samsung_electronics():
    resolved = {r["entity_id"] for r in ee.resolve_event(EVENTS["nvda-20261021-supply-chain-capacity"])}
    assert "SSNLF" not in resolved
    assert "Samsung Electro-Mechanics" in " ".join(q["quote"] for q in EVENTS["nvda-20261021-supply-chain-capacity"]["evidence"])


def test_rtx_spark_is_not_rtx_corporation():
    resolved = {r["entity_id"] for r in ee.resolve_event(EVENTS["nvda-20260601-gtc-taipei-rtx-spark"])}
    assert "RTX" not in resolved


def test_every_mention_is_traceable_to_a_cited_passage():
    for event in EVENTS.values():
        allowed = {p["ref"]: p["text"] for p in ee.passages(event)}
        for rec in ee.resolve_event(event):
            assert rec["mentions"]
            for m in rec["mentions"]:
                assert m["quote"] == allowed[m["ref"]] and m["matched_text"].lower() in m["quote"].lower()


def test_only_cited_passages_are_read():
    event = copy.deepcopy(EVENTS["nvda-20261008-us-science-commitment"])
    event["location"]["basis"] = "Microsoft Oracle Meta"                          # not a cited passage: must be ignored
    assert {r["entity_id"] for r in ee.resolve_event(event)} == {"NVDA"}


def test_resolution_is_deterministic():
    event = EVENTS["nvda-20260105-ces-rubin-platform"]
    assert ee.resolve_event(event) == ee.resolve_event(event)


# -------------------------------------------------------------------- search
@pytest.mark.parametrize("q,expected", [("NVIDIA", ["NVDA"]), ("nvda", ["NVDA"]), ("Nvidia Corporation", ["NVDA"]),
                                        ("  nvidia ", ["NVDA"]), ("asdfghjkl", []), ("", []), ("   ", [])])
def test_query_resolution(q, expected):
    assert [m["entity_id"] for m in ee.resolve_query(q)] == expected


# ---------------------------------------------------------------- geography
def test_every_registered_event_is_mapped_with_its_basis_and_precision():
    for event in EVENTS.values():
        loc = geo.event_location(event)
        assert loc["mapped"] and -90 <= loc["lat"] <= 90 and -180 <= loc["lon"] <= 180
        assert loc["precision"] in ("approximate city point", "country centroid") and loc["basis"]
    assert geo.event_location(EVENTS["nvda-20261021-supply-chain-capacity"])["label"] == "Berlin, Germany"
    bis = geo.event_location(EVENTS["nvda-20260115-bis-h200-china-license-policy"])
    assert bis["precision"] == "country centroid" and "country-level" in bis["basis"]


def test_an_unplaceable_event_is_reported_not_plotted():
    event = copy.deepcopy(EVENTS["nvda-20261008-us-science-commitment"])
    event["location"]["gazetteer_key"] = "atlantis"
    loc = geo.event_location(event)
    assert loc["mapped"] is False and "not in the gazetteer" in loc["reason"] and "lat" not in loc


def test_regions_mentioned_come_from_the_cited_passages():
    regions = geo.regions_mentioned(EVENTS["nvda-20261021-supply-chain-capacity"])
    assert [r["label"] for r in regions] == ["South Korea", "Taiwan", "Japan", "United States", "Singapore"]
    for r in regions:
        assert r["matched_text"] in r["quote"] and r["precision"] == "country centroid"
    assert [r["label"] for r in geo.regions_mentioned(EVENTS["nvda-20260115-bis-h200-china-license-policy"])][:2] == ["China", "Macau"]
    assert geo.regions_mentioned(EVENTS["nvda-20261014-semicon-west-ai-fabs"]) == []        # names none: invents none


def _event_with(quote):
    return {"evidence": [{"source_id": "s1", "quote": quote}]}


@pytest.mark.parametrize("quote,expected", [
    ("capacity in South Korea and Korea", ["South Korea"]),                     # longest name first, no double count
    ("a plant in Korea", ["South Korea"]),
    ("the U.S. and the United States", ["United States"]),
    ("china and taiwan in lower case", []),                                     # case-sensitive
    ("Taiwanese suppliers", []),                                                # word boundary
    ("Chinatown", []),
    ("sites in Singapore and Japan", ["Singapore", "Japan"]),
])
def test_region_detection_rules(quote, expected):
    assert [r["label"] for r in geo.regions_mentioned(_event_with(quote))] == expected


def test_entity_positions_use_headquarters_country_and_say_so():
    pos = geo.entity_position("TSM")
    assert pos["label"] == "Taiwan" and pos["precision"] == "country centroid" and "headquarters country" in pos["basis"]
    assert geo.entity_position("SKHY")["label"] == "South Korea"
    assert geo.entity_position("NOPE") is None
    for eid in STORE.issuer_ids:
        assert geo.entity_position(eid) is not None, f"{eid}'s country is missing from the gazetteer"
