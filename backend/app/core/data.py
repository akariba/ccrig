"""Loads all bundled data (real + synthetic, clearly flagged) once at
startup and exposes simple lookup structures used by every pipeline module.
"""
import json
import csv
from pathlib import Path
from datetime import datetime
from .config import DATA_DIR, RAW_PRICES_DIR


def _load_json(name):
    with open(DATA_DIR / name) as f:
        return json.load(f)


class DataStore:
    def __init__(self):
        self.entities_raw = _load_json("entities.json")["entities"]
        self.fact_edges = _load_json("fact_edges.json")["fact_edges"]
        self.keywords = _load_json("keywords.json")["keywords"]
        self.entity_keyword_weights = _load_json("entity_keyword_weights.json")
        self.counterparties = _load_json("counterparties.json")["counterparties"]
        self.exposure_edges = _load_json("exposure_edges.json")["exposure_edges"]
        self.news_real = _load_json("news_real.json")["documents"]
        self.news_synthetic = _load_json("news_synthetic.json")["documents"]
        self.news_all = self.news_real + self.news_synthetic
        try:
            self.gleif = _load_json("gleif_sample.json")
        except FileNotFoundError:
            self.gleif = {}

        # Synthetic CCR (Counterparty Credit Risk) decision data - Daily
        # Priority Queue / Breaches & Actions. Fully separate from Layer C
        # portfolio-holdings exposure_edges.json; never confidential/real.
        try:
            self.ccr_counterparties = _load_json("ccr_counterparties.json")["counterparties"]
        except FileNotFoundError:
            self.ccr_counterparties = []
        try:
            self.ccr_events = _load_json("ccr_events.json")["events"]
        except FileNotFoundError:
            self.ccr_events = []
        try:
            self.ccr_model_impacts = _load_json("ccr_model_impacts.json")["runs"]
        except FileNotFoundError:
            self.ccr_model_impacts = []

        self.entities_by_id = {e["id"]: e for e in self.entities_raw}
        self.issuer_ids = [e["id"] for e in self.entities_raw if e["node_type"] == "Company/Issuer"]
        self.counterparty_ids = [e["id"] for e in self.entities_raw if e["node_type"] == "Counterparty"]
        self.browsable_ids = self.issuer_ids + self.counterparty_ids  # excludes helper Country/Sector nodes

        self.keywords_by_id = {k["id"]: k for k in self.keywords}
        # synonym -> canonical keyword id (lowercased)
        self.synonym_index = {}
        for k in self.keywords:
            for syn in k["synonyms"]:
                self.synonym_index[syn.lower()] = k["id"]
            self.synonym_index[k["label"].lower()] = k["id"]

        # GLEIF lookup keyed by our entity id via a small name map built at
        # build_dataset time is not persisted; rebuild a best-effort map here
        # by matching legal_name loosely to entity name.
        self.gleif_by_entity = {}
        gleif_names = {k: v for k, v in self.gleif.items() if v and "error" not in v}
        for eid, e in self.entities_by_id.items():
            name = e.get("name", "")
            for gname, rec in gleif_names.items():
                if _fuzzy_match(name, gname):
                    self.gleif_by_entity[eid] = rec
                    break

        self.prices = self._load_prices()

        # Real GLEIF Level-2 ownership (PARENT_OF/SUBSIDIARY_OF), never
        # fabricated: backend/data/gleif_level2_cache.json is fetched by
        # scripts/fetch_gleif_level2.py from the real GLEIF API and cached
        # so this never depends on network access at startup. Only edges
        # where BOTH ends match a tracked entity (by LEI) are added - as of
        # this build every tracked entity is a top-of-house public company
        # with zero GLEIF-reported parent, so this is correctly a no-op
        # today (see core/ownership.py and tests/test_ownership.py).
        from . import ownership as ownership_mod
        gleif_ownership_edges = ownership_mod.build_ownership_fact_edges(self.gleif_by_entity)
        self.fact_edges = self.fact_edges + gleif_ownership_edges

        # Ownership (Layer A PARENT_OF/SUBSIDIARY_OF) coverage: exposed as
        # an explicit flag so callers (Model Lab) can surface it as N/A
        # instead of implying it's a live, tunable signal when empty.
        self.has_ownership_data = any(
            e["relation"] in ("PARENT_OF", "SUBSIDIARY_OF") for e in self.fact_edges)

    def _load_prices(self):
        prices = {}
        for csv_path in Path(RAW_PRICES_DIR).glob("*.csv"):
            ticker = csv_path.name.split("_price_history")[0]
            rows = []
            with open(csv_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        rows.append((datetime.strptime(row["date"], "%Y-%m-%d").date(), float(row["close"])))
                    except Exception:
                        continue
            rows.sort(key=lambda r: r[0])
            prices[ticker] = rows
        return prices

    def entity(self, entity_id):
        return self.entities_by_id.get(entity_id)

    def is_browsable(self, entity_id):
        return entity_id in self.entities_by_id and self.entities_by_id[entity_id]["node_type"] in (
            "Company/Issuer", "Counterparty")


def _fuzzy_match(a, b):
    a = a.lower().replace(",", "").replace(".", "").strip()
    b = b.lower().replace(",", "").replace(".", "").strip()
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    if not a_tokens or not b_tokens:
        return False
    overlap = len(a_tokens & b_tokens)
    return overlap >= max(1, min(len(a_tokens), len(b_tokens)) - 1) and overlap >= 2


# Module-level singleton, loaded once at process start.
STORE = DataStore()
