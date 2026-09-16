"""Counterparty -> Issuer distance and inferred correlation ("Distance Map").

This is a VIEW over the existing scoring engine (core/scoring.py) and
candidate generation (core/candidates.py) - it does not introduce a new
model or touch either of those modules. For every issuer reachable from a
counterparty (via Layer A fact edges, or via the bounded Layer B candidate
set - never a dense N x N scan, per BUILD_MANDATE section 9) it computes:

    d   = graph distance in [0, 1]  (lower = closer)
    rho = 1 - d                     (higher = more correlated)

and classifies the pair into one of four channels:
    OWNERSHIP   - direct Layer A PARENT_OF/SUBSIDIARY_OF edge
    SUPPLY      - direct or 2-hop Layer A supply-chain edge
    HISTORICAL  - Layer B derived similarity dominated by market/sector/news
    HIDDEN      - Layer B derived similarity with no such dominant signal

rho is always a distance-based proxy, never an observed market correlation
or a trade-position metric - every result is tagged is_synthetic=True.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from . import candidates as candidates_mod
from . import scoring
from .config import DEFAULT_WEIGHTS
from .data import STORE
from .graph_store import exposure_of_counterparty, fact_neighbors

HOP_DECAY = 0.65
HIGH_RHO_THRESHOLD = 0.75
CONCENTRATION_ALERT_COUNT = 4


class CorrelationChannel(str, Enum):
    OWNERSHIP = "ownership"
    SUPPLY = "supply"
    HISTORICAL = "historical"
    HIDDEN = "hidden"


@dataclass
class PathHop:
    from_id: str
    from_label: str
    to_id: str
    to_label: str
    relation: str | None
    direction: str | None  # "FORWARD" | "REVERSE" | None


@dataclass
class IssuerDistance:
    issuer_id: str
    issuer_name: str
    issuer_sector: str
    issuer_ticker: str | None

    distance: float
    rho: float

    channel: CorrelationChannel
    channel_evidence: str

    direct_relation: str | None
    direct_criticality: float | None
    typed_path: list[PathHop]
    score_components: dict[str, float] = field(default_factory=dict)

    is_direct: bool = False
    hop_count: int = 1
    is_synthetic: bool = True


@dataclass
class CounterpartyDistanceResult:
    counterparty_id: str
    counterparty_name: str
    counterparty_sector: str
    exposure_context: list[dict]  # Layer C holdings - separate units, never combined with rho

    issuers: list[IssuerDistance]

    high_rho_count: int
    concentration_alert: bool
    channel_counts: dict[str, int]
    dominant_channel: str | None

    methodology_note: str = (
        "rho = 1 - d. Distance is computed from Layer A supply-chain/ownership fact edges "
        "and, where no direct edge exists, from the same bounded Layer B candidate set and "
        "weighted composite score used everywhere else in CCRIG (core/scoring.py) - never a "
        "dense pairwise scan. This is an inferred proxy correlation, not an observed market "
        "correlation or a trade-position metric. Synthetic POC illustration."
    )


def _direct_hop(cp_id: str, cp_name: str, target_id: str, target_name: str, edge: dict) -> PathHop:
    forward = edge["source"] == cp_id
    return PathHop(
        from_id=cp_id, from_label=cp_name,
        to_id=target_id, to_label=target_name,
        relation=edge["relation"],
        direction="FORWARD" if forward else "REVERSE",
    )


def _derived_hop(a_id: str, a_name: str, b_id: str, b_name: str) -> PathHop:
    return PathHop(from_id=a_id, from_label=a_name, to_id=b_id, to_label=b_name, relation=None, direction=None)


def compute_counterparty_distances(
    counterparty_id: str,
    max_hops: int = 2,
    min_rho: float = 0.0,
) -> CounterpartyDistanceResult | None:
    cp_id = counterparty_id.upper()
    cp = STORE.entity(cp_id)
    if not cp or cp["node_type"] != "Counterparty":
        return None
    cp_name = cp["name"]

    results: dict[str, IssuerDistance] = {}

    # ── Step 1: direct Layer A edges from this counterparty ────────────────
    for target_id, edges in fact_neighbors(cp_id).items():
        if target_id not in STORE.issuer_ids:
            continue
        iss = STORE.entity(target_id)
        for edge in edges:
            rel = edge["relation"]
            crit = edge.get("criticality")
            crit = crit if crit is not None else 0.5

            if rel in scoring.OWNERSHIP_RELATIONS:
                channel = CorrelationChannel.OWNERSHIP
                d = round(1.0 - crit, 3)
                evidence = f"Direct ownership fact edge: {rel} (criticality {crit:.2f})"
            elif rel in scoring.SUPPLY_RELATIONS:
                channel = CorrelationChannel.SUPPLY
                d = round(1.0 - (crit * 0.85), 3)
                evidence = f"Direct supply-chain fact edge: {rel} (criticality {crit:.2f})"
            else:
                continue  # other fact relation types don't define a distance channel here

            rho = round(1.0 - d, 3)
            existing = results.get(target_id)
            if existing is not None and existing.distance <= d:
                continue
            results[target_id] = IssuerDistance(
                issuer_id=target_id, issuer_name=iss["name"], issuer_sector=iss.get("sector", ""),
                issuer_ticker=iss.get("ticker"),
                distance=d, rho=rho, channel=channel, channel_evidence=evidence,
                direct_relation=rel, direct_criticality=round(crit, 3),
                typed_path=[_direct_hop(cp_id, cp_name, target_id, iss["name"], edge)],
                is_direct=True, hop_count=1,
            )

    # ── Step 2: 2-hop supply-chain propagation ──────────────────────────────
    if max_hops >= 2:
        direct_supply_ids = [
            eid for eid, r in results.items()
            if r.channel == CorrelationChannel.SUPPLY and r.hop_count == 1
        ]
        for mid_id in direct_supply_ids:
            parent = results[mid_id]
            mid_name = parent.issuer_name
            for target_id, edges in fact_neighbors(mid_id).items():
                if target_id == cp_id or target_id in results or target_id not in STORE.issuer_ids:
                    continue
                for edge in edges:
                    if edge["relation"] not in scoring.SUPPLY_RELATIONS:
                        continue
                    crit = edge.get("criticality")
                    crit = crit if crit is not None else 0.4
                    d = round(min(parent.distance + (1.0 - crit) * HOP_DECAY, 0.99), 3)
                    rho = round(1.0 - d, 3)
                    iss = STORE.entity(target_id)
                    results[target_id] = IssuerDistance(
                        issuer_id=target_id, issuer_name=iss["name"], issuer_sector=iss.get("sector", ""),
                        issuer_ticker=iss.get("ticker"),
                        distance=d, rho=rho, channel=CorrelationChannel.SUPPLY,
                        channel_evidence=f"2-hop supply chain via {mid_name}",
                        direct_relation=None, direct_criticality=None,
                        typed_path=[
                            _derived_hop(cp_id, cp_name, mid_id, mid_name),
                            _direct_hop(mid_id, mid_name, target_id, iss["name"], edge),
                        ],
                        is_direct=False, hop_count=2,
                    )
                    break  # strongest single edge per (mid, target) pair is enough

    # ── Step 3: Layer B scoring over the bounded candidate set ──────────────
    # Never a dense N x N scan (BUILD_MANDATE section 9) - only the same
    # bounded candidate union every other relatedness view in CCRIG uses.
    cand = candidates_mod.generate_candidates(cp_id)
    candidate_issuer_ids = [eid for eid in (cand["candidate_ids"] if cand else []) if eid in STORE.issuer_ids]

    for iss_id in candidate_issuer_ids:
        pair = scoring.score_pair(cp_id, iss_id, DEFAULT_WEIGHTS)
        composite = pair["composite"]["score"]
        if composite is None:
            continue
        d_b = round(1.0 - composite, 3)
        rho_b = round(composite, 3)
        components = {k: v for k, v in pair["composite"]["component_values"].items() if v is not None}

        existing = results.get(iss_id)
        if existing is not None:
            existing.score_components = components
            if d_b < existing.distance:
                existing.distance, existing.rho = d_b, rho_b
            continue

        if rho_b < min_rho:
            continue

        market_sig = max(components.get("market_positive", 0.0), components.get("market_negative", 0.0))
        sector_sig = components.get("sector", 0.0)
        news_sig = components.get("news", 0.0)
        if market_sig >= 0.5 or (sector_sig >= 0.7 and news_sig >= 0.5):
            channel = CorrelationChannel.HISTORICAL
            evidence = f"Derived similarity: sector={sector_sig:.2f}, market={market_sig:.2f}, news={news_sig:.2f}"
        else:
            channel = CorrelationChannel.HIDDEN
            evidence = (
                f"Shared factor exposure, no direct edge: sector={sector_sig:.2f}, "
                f"semantic={components.get('semantic', 0.0):.2f}, news={news_sig:.2f}"
            )

        iss = STORE.entity(iss_id)
        results[iss_id] = IssuerDistance(
            issuer_id=iss_id, issuer_name=iss["name"], issuer_sector=iss.get("sector", ""),
            issuer_ticker=iss.get("ticker"),
            distance=d_b, rho=rho_b, channel=channel, channel_evidence=evidence,
            direct_relation=None, direct_criticality=None,
            typed_path=[_derived_hop(cp_id, cp_name, iss_id, iss["name"])],
            score_components=components, is_direct=False, hop_count=1,
        )

    # ── Step 4: filter, sort, summarise ─────────────────────────────────────
    ranked = sorted((r for r in results.values() if r.rho >= min_rho), key=lambda r: -r.rho)

    high_rho = [r for r in ranked if r.rho >= HIGH_RHO_THRESHOLD]
    channel_counts: dict[str, int] = {}
    for r in ranked[:5]:
        channel_counts[r.channel.value] = channel_counts.get(r.channel.value, 0) + 1
    dominant = max(channel_counts, key=channel_counts.get) if channel_counts else None

    return CounterpartyDistanceResult(
        counterparty_id=cp_id, counterparty_name=cp_name, counterparty_sector=cp.get("sector", ""),
        exposure_context=exposure_of_counterparty(cp_id),
        issuers=ranked,
        high_rho_count=len(high_rho),
        concentration_alert=len(high_rho) >= CONCENTRATION_ALERT_COUNT,
        channel_counts=channel_counts,
        dominant_channel=dominant,
    )
