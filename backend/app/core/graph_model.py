"""Canonical Connected Risk Graph domain types (Phase 2B).

One typed node/edge model, backend-serialized, shared by every consumer
(Relationship Workbench, Counterparty risk clusters, Event transmission).
Pages must query this rather than each independently re-deriving graph
semantics from raw JSON - that duplication is exactly what produced the
Phase 1/2 direction bug (a consumer silently reinventing edge semantics
instead of reading a canonical field).
"""
from dataclasses import dataclass, field
from typing import Any, Literal

GraphNodeType = Literal[
    "ISSUER", "ENTITY", "COUNTERPARTY", "LEGAL_ENTITY", "EVENT", "RISK_FACTOR",
    "COUNTRY", "SECTOR", "THEME", "PRODUCT", "TRADE", "EXPOSURE_POSITION",
    "UNDERLYING", "REFERENCE_ENTITY", "COLLATERAL", "NETTING_SET", "CSA",
    "LIMIT", "CONTROL_EXCEPTION", "OWNER",
]

EdgeDomain = Literal["STRUCTURAL", "STATISTICAL", "TRANSMISSION", "EXPOSURE", "CONTROL", "REFERENCE"]

Provenance = Literal[
    "REAL_PUBLIC_DATA", "SYNTHETIC_BUSINESS_SCENARIO_DATA", "CURATED_REFERENCE_DATA",
    "DERIVED_DATA", "AI_ASSISTED_EXTRACTION",
]


@dataclass(frozen=True)
class GraphNode:
    id: str  # stable, namespaced e.g. "COUNTERPARTY:CP_HF_001" - never a display label
    type: GraphNodeType
    label: str
    short_label: str | None = None
    provenance: Provenance | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    id: str
    domain: EdgeDomain
    type: str  # canonical type e.g. "SUPPLIES", "MARKET_CORRELATED_WITH", "TRS"
    source_node_id: str
    target_node_id: str
    directed: bool
    provenance: Provenance
    signed_value: float | None = None
    strength: float | None = None
    evidence: dict[str, Any] | None = None
    as_of_date: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def entity_node_id(entity_id: str) -> str:
    return f"ENTITY:{entity_id}"


def counterparty_node_id(cp_id: str) -> str:
    return f"COUNTERPARTY:{cp_id}"


def product_node_id(code: str) -> str:
    return f"PRODUCT:{code}"


def risk_factor_node_id(code: str) -> str:
    return f"RISK_FACTOR:{code}"


def event_node_id(event_id: str) -> str:
    return f"EVENT:{event_id}"


def collateral_node_id(description: str) -> str:
    return f"COLLATERAL:{description}"


def netting_set_node_id(netting_set: str) -> str:
    return f"NETTING_SET:{netting_set}"


def limit_node_id(cp_id: str, limit_id: str) -> str:
    return f"LIMIT:{cp_id}:{limit_id}"


def control_exception_node_id(cp_id: str, limit_id: str) -> str:
    return f"CONTROL_EXCEPTION:{cp_id}:{limit_id}"


def owner_node_id(owner_name: str) -> str:
    return f"OWNER:{owner_name}"


def sector_node_id(sector: str) -> str:
    return f"SECTOR:{sector}"


def country_node_id(country: str) -> str:
    return f"COUNTRY:{country}"
