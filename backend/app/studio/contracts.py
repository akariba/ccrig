"""Target contracts: what a source must look like to be staged for each supported CCRIG dataset.

The shapes mirror the canonical files under backend/data exactly (read from them, not invented). Pure data: no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Field:
    name: str
    type: str = "str"                    # str | float | int | bool | date | enum | object | url | list
    required: bool = False
    enum: tuple = ()
    min: Optional[float] = None
    max: Optional[float] = None
    pattern: Optional[str] = None
    ref: Optional[str] = None            # entity | issuer | portfolio_counterparty : must resolve to a canonical id
    fields: tuple = ()                   # sub-fields for type == "object"
    item: str = "str"                    # item type for type == "list" (str | url)
    min_items: int = 0
    nullable: bool = True


@dataclass(frozen=True)
class Contract:
    name: str
    description: str
    key: tuple                           # field names that identify a record
    fields: tuple
    canonical_file: Optional[str] = None
    canonical_list_key: Optional[str] = None
    scoped: bool = False                 # one dataset per scope value (e.g. prices per ticker)
    scope_ref: Optional[str] = None      # the scope value must resolve like a ref of this kind
    promotable: bool = True              # False = profile and validate only
    checks: tuple = ()                   # names of cross-record checks implemented in validate.py
    notes: str = ""

    def field_names(self) -> tuple:
        return tuple(f.name for f in self.fields)


NODE_TYPES = ("Company/Issuer", "Counterparty", "Country", "Sector", "Country/Region")
FACT_RELATIONS = ("SUPPLIES", "LICENSES_TO", "PARENT_OF", "SUBSIDIARY_OF", "BELONGS_TO_SECTOR", "OPERATES_IN")
DOCUMENTED = ("WELL_DOCUMENTED_PUBLIC", "REPORTED_NEWS")
EXPOSURE_RELATIONS = ("HOLDS_EQUITY", "HOLDS_BONDS", "LENDS_TO", "HOLDS_VIA_FUND")
EVENT_CATEGORIES = ("CORPORATE_ANNOUNCEMENT", "EARNINGS_RELEASE", "PARTNERSHIP_ANNOUNCEMENT", "PRODUCT_ANNOUNCEMENT", "REGULATORY_ACTION")
SOURCE_TIERS = ("PRIMARY_ISSUER", "PRIMARY_REGULATOR", "PRIMARY_RELATED_PARTY")
LIMIT_TYPES = ("PFE_LIMIT", "SETTLEMENT_LIMIT", "STRESS_LIMIT")
CCR_TYPES = ("Hedge Fund", "Sovereign", "Bank", "Bank Treasury", "Asset Manager", "Family Office", "SPV", "Sovereign Wealth Fund")

CONTRACTS: dict[str, Contract] = {c.name: c for c in (
    Contract(
        "entities", "Entity master (issuers, counterparties, countries, sectors)", ("id",),
        (Field("id", required=True, pattern=r"^[A-Za-z0-9_.\-]{1,40}$"), Field("name", required=True),
         Field("node_type", "enum", required=True, enum=NODE_TYPES), Field("sector"), Field("industry"), Field("country"), Field("region"),
         Field("ticker"), Field("has_market_data", "bool"), Field("is_synthetic", "bool", required=True, nullable=False)),
        "entities.json", "entities", notes="New entities are proposals; none is created as a side effect of any other dataset.",
    ),
    Contract(
        "fact_edges", "Layer A factual relationships between entities (directed)", ("source", "relation", "target"),
        (Field("source", required=True, ref="entity"), Field("target", required=True, ref="entity"),
         Field("relation", "enum", required=True, enum=FACT_RELATIONS), Field("criticality", "float", required=True, min=0.0, max=1.0, nullable=False),
         Field("note"), Field("evidence_status", "enum", required=True, enum=DOCUMENTED + ("UNVERIFIED",)), Field("evidence_url", "url"),
         Field("is_synthetic", "bool")),
        "fact_edges.json", "fact_edges", checks=("no_self_loop", "documented_needs_link", "synthetic_not_documented"),
        notes="A relationship labelled documented or reported must carry an https evidence link. Criticality is a curated judgement, not an exposure.",
    ),
    Contract(
        "exposure_edges", "Layer C portfolio holdings: portfolio counterparty -> issuer", ("counterparty", "relation", "issuer"),
        (Field("counterparty", required=True, ref="portfolio_counterparty"), Field("issuer", required=True, ref="issuer"),
         Field("relation", "enum", required=True, enum=EXPOSURE_RELATIONS), Field("exposure_pct", "float", required=True, min=0.0, max=1.0, nullable=False),
         Field("is_synthetic", "bool", required=True, nullable=False)),
        "exposure_edges.json", "exposure_edges", checks=("holdings_total",),
        notes="The CCR exposure dataset is a different universe and is never resolved here.",
    ),
    Contract(
        "ccr_counterparties", "CCR exposure, limit and breach snapshots (separate universe from portfolio holdings)", ("id",),
        (Field("id", required=True, pattern=r"^CP_[A-Z0-9_]+$"), Field("name", required=True), Field("legal_entity", required=True),
         Field("counterparty_type", "enum", required=True, enum=CCR_TYPES), Field("rating"), Field("watchlist", "bool"),
         Field("exposure", "object", fields=(Field("rc_current", "float"), Field("rc_previous", "float"), Field("pfe_current", "float"),
                                              Field("pfe_previous", "float"), Field("nse_current", "float"), Field("nse_previous", "float"),
                                              Field("settlement_exposure", "float"))),
         Field("limit", "object", fields=(Field("limit_id"), Field("limit_type", "enum", enum=LIMIT_TYPES), Field("limit_value", "float", min=0.0),
                                          Field("currency"), Field("as_of_date", "date"), Field("source"))),
         Field("reference_entity_id", ref="issuer"), Field("is_synthetic", "bool", required=True, nullable=False), Field("source_type")),
        "ccr_counterparties.json", "counterparties", checks=("limit_consistency",),
        notes="Real CCR data is CONFIDENTIAL and must only be processed on an operator machine.",
    ),
    Contract(
        "prices", "Daily closing prices for one entity (date, close)", ("date",),
        (Field("date", "date", required=True, nullable=False), Field("close", "float", required=True, min=0.0, nullable=False)),
        None, None, scoped=True, scope_ref="issuer", checks=("price_series",),
        notes="Scope is the entity id (its ticker file in data/raw_prices is the canonical copy).",
    ),
    Contract(
        "discovered_events", "Events found by Event Discovery in approved sources: machine-verified against the retrieved text, awaiting or after human review",
        ("id",),
        (Field("id", required=True, pattern=r"^[a-z0-9][a-z0-9\-]{5,100}$"), Field("entity_id", required=True, ref="issuer"), Field("kind", "enum", required=True, enum=("REAL_EVENT",)),
         Field("title", required=True), Field("category", "enum", required=True, enum=EVENT_CATEGORIES),
         Field("published_date", "date", required=True, nullable=False), Field("event_date", "date", required=True, nullable=False), Field("event_date_basis", required=True),
         Field("location", "object", required=True, fields=(Field("gazetteer_key"), Field("basis"), Field("basis_text"), Field("unmapped_reason"))),
         Field("source_url", "url", required=True), Field("source_publisher", required=True), Field("source_tier", "enum", required=True, enum=SOURCE_TIERS),
         Field("approved_source_id", required=True), Field("source_title"), Field("source_published_date", "date", required=True), Field("retrieved_at", required=True),
         Field("source_sha256", required=True, pattern=r"^[0-9a-f]{64}$"), Field("text_method", "enum", required=True, enum=("html_text", "api_json")),
         Field("evidence_quotes", "list", required=True, min_items=1),
         Field("verification", "object", required=True, fields=(Field("status", "enum", enum=("VERIFIED_BY_RETRIEVAL",)), Field("method"), Field("checked_at"),
                                                                Field("quotes_total", "int", min=0), Field("quotes_found", "int", min=0), Field("date_confirmed", "bool"),
                                                                Field("date_basis"))),
         Field("discovery", "object", required=True, fields=(Field("run_id"), Field("provider_id"), Field("category_method"), Field("also_reported_by", "list", item="url")))),
        None, None, scoped=True, scope_ref="issuer", checks=("discovered_event_evidence",),
        notes="Machine-verified evidence is not truth and not impact: it shows the source says it. Review status comes from the Studio decision on the job.",
    ),
    Contract(
        "profile_only", "Any CSV/JSON table: profile and validate structure, never promoted", (),
        (), None, None, promotable=False, notes="For files that match no supported contract yet.",
    ),
)}
