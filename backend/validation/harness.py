"""Falsifiable checks on the relationship ranking (read-only).

Two questions, both answerable from data already in the repo:

1. Leave-edge-out retrieval. The 34 documented supply/licence edges between
   issuers are used as ground truth. The supply_chain and ownership
   components are MASKED (weight 0) so an edge is never used to predict
   itself; we then ask how highly the true counterpart ranks among all other
   issuers, and compare the composite against simple single-feature
   baselines.

2. Inversion count. With edges INCLUDED, how many issuers that have no
   documented supply relationship nevertheless outrank a documented
   supplier/customer?

The "current" variant is the application's own `scoring.composite_score`.
The "reference" variants (zero-fill, shrinkage) exist only to give context
to the numbers; the application does not use them.

Caveats that apply to every number here (also recorded in the report):
  * 21 queries / 68 directed positives: wide confidence intervals.
  * `news` is built from keyword weights curated by the dataset author, as
    are the edges, so it may carry curation leakage.
  * Ties (e.g. binary sector similarity) are broken by seeded random
    shuffles, averaged over N_TIE_SHUFFLES, so results are deterministic.
"""
from __future__ import annotations

import itertools
from functools import lru_cache

import numpy as np

from app.core import scoring
from app.core.config import DEFAULT_WEIGHTS
from app.core.data import STORE

SEED = 7
N_TIE_SHUFFLES = 30
N_BOOTSTRAP = 300
MASKED_COMPONENTS = ("supply_chain", "ownership")
HIGH_CRITICALITY = 0.8

CAVEATS = [
    "Small sample (21 queries, 68 directed positives): read the bootstrap intervals, not the point estimates.",
    "The news feature is built from keyword weights curated by the same author as the documented edges; "
    "its strong baseline performance may reflect curation leakage rather than independent signal.",
    "Ties are broken by seeded random shuffles averaged over several trials (deterministic, not exact ranks).",
    "Reference variants (zero-fill, shrinkage) are analysis aids only; the application does not use them.",
]


@lru_cache(maxsize=1)
def _pairs():
    """{(a, b): {"vec": feature_vector, "comp": component_values}} for every
    ordered issuer pair, computed with the application's own scoring code."""
    out = {}
    for a, b in itertools.combinations(STORE.issuer_ids, 2):
        vec = scoring.feature_vector(a, b)
        comp = scoring.composite_score(vec, DEFAULT_WEIGHTS, round_output=False)["component_values"]
        out[(a, b)] = out[(b, a)] = {"vec": vec, "comp": comp}
    return out


def _masked_weights():
    return {k: (0.0 if k in MASKED_COMPONENTS else w) for k, w in DEFAULT_WEIGHTS.items()}


def _priors(components):
    """Population mean of each component over the pairs where it is observed
    (used only by the shrinkage reference variant)."""
    pairs = _pairs()
    priors = {}
    for k in components:
        vals = [p["comp"][k] for (a, b), p in pairs.items() if a < b and p["comp"][k] is not None]
        priors[k] = float(np.mean(vals)) if vals else 0.0
    return priors


# --------------------------------------------------------------- score variants
def _variants(masked: bool):
    """name -> score(pair_record). `masked` hides supply/ownership evidence."""
    w_all = _masked_weights() if masked else dict(DEFAULT_WEIGHTS)
    used = [k for k in DEFAULT_WEIGHTS if not (masked and k in MASKED_COMPONENTS)]
    priors = _priors(used)
    w_sum = sum(DEFAULT_WEIGHTS[k] for k in used)

    def current(p):
        return scoring.composite_score(p["vec"], w_all, round_output=False)["score"] or 0.0

    def zero_fill(p):
        return sum(DEFAULT_WEIGHTS[k] * (p["comp"][k] or 0.0) for k in used) / w_sum

    def shrink(p):
        return sum(
            DEFAULT_WEIGHTS[k] * (p["comp"][k] if p["comp"][k] is not None else priors[k]) for k in used
        ) / w_sum

    return {
        "current_composite": current,
        "reference_zero_fill": zero_fill,
        "reference_shrinkage": shrink,
    }


BASELINES = {
    "baseline_sector_only": lambda p: p["comp"]["sector"] or 0.0,
    "baseline_semantic_only": lambda p: p["comp"]["semantic"] or 0.0,
    "baseline_news_only": lambda p: p["comp"]["news"] or 0.0,
    "baseline_sector_plus_semantic": lambda p: 0.5 * (p["comp"]["sector"] or 0.0) + 0.5 * (p["comp"]["semantic"] or 0.0),
    "baseline_random": lambda p: 0.0,  # all ties -> pure seeded shuffle
}


# ------------------------------------------------------------------ evaluation
def _positives():
    """Directed documented supply/licence neighbours for each issuer (from the
    unmasked supply_chain component, i.e. the curated fact edges)."""
    pairs = _pairs()
    pos = {a: set() for a in STORE.issuer_ids}
    for (a, b), p in pairs.items():
        if p["comp"]["supply_chain"] is not None:
            pos[a].add(b)
    return pos


def _average_precision(order, positives):
    hits, ap = 0, 0.0
    for rank, b in enumerate(order, 1):
        if b in positives:
            hits += 1
            ap += hits / rank
    return ap / len(positives)


def _evaluate(score_fn, universe):
    pairs, pos = _pairs(), _positives()
    queries = [a for a in universe if pos[a] & set(universe)]
    rng = np.random.default_rng(SEED)
    per_query_ap, per_query_h5, per_query_h10 = [], [], []
    for a in queries:
        cands = [b for b in universe if b != a]
        positives = pos[a] & set(cands)
        scores = np.array([score_fn(pairs[(a, b)]) for b in cands])
        aps, h5, h10 = [], [], []
        for _ in range(N_TIE_SHUFFLES):
            perm = rng.permutation(len(cands))
            order_idx = sorted(perm, key=lambda i: -scores[i])  # stable: ties follow the shuffle
            order = [cands[i] for i in order_idx]
            aps.append(_average_precision(order, positives))
            h5.append(1.0 if any(b in positives for b in order[:5]) else 0.0)
            h10.append(1.0 if any(b in positives for b in order[:10]) else 0.0)
        per_query_ap.append(float(np.mean(aps)))
        per_query_h5.append(float(np.mean(h5)))
        per_query_h10.append(float(np.mean(h10)))

    ap = np.array(per_query_ap)
    boot_rng = np.random.default_rng(SEED + 1)
    boots = [float(np.mean(ap[boot_rng.integers(0, len(ap), len(ap))])) for _ in range(N_BOOTSTRAP)]
    return {
        "n_queries": len(queries),
        "map": round(float(ap.mean()), 4),
        "map_ci95": [round(float(np.percentile(boots, 2.5)), 4), round(float(np.percentile(boots, 97.5)), 4)],
        "hit_at_5": round(float(np.mean(per_query_h5)), 4),
        "hit_at_10": round(float(np.mean(per_query_h10)), 4),
    }


def leave_edge_out():
    all_issuers = list(STORE.issuer_ids)
    priced = [e for e in all_issuers if STORE.entity(e).get("has_market_data")]
    result = {}
    for label, universe in (("all_issuers", all_issuers), ("priced_issuers_only", priced)):
        variants = {**_variants(masked=True), **BASELINES}
        result[label] = {name: _evaluate(fn, universe) for name, fn in variants.items()}
    return result


# ------------------------------------------------------------------ inversions
def _inversions(score_fn, min_criticality=0.0):
    pairs = _pairs()
    issuers = STORE.issuer_ids
    outrankers = []
    for (a, b), p in pairs.items():
        crit = p["comp"]["supply_chain"]
        if crit is None or crit < min_criticality:
            continue
        s = score_fn(p)
        no_edge = [z for z in issuers if z not in (a, b) and pairs[(a, z)]["comp"]["supply_chain"] is None]
        outrankers.append(sum(1 for z in no_edge if score_fn(pairs[(a, z)]) > s))
    return {
        "directed_pairs": len(outrankers),
        "share_with_at_least_one_outranker": round(sum(1 for n in outrankers if n) / len(outrankers), 4),
        "mean_outrankers": round(float(np.mean(outrankers)), 3),
        "max_outrankers": int(max(outrankers)),
    }


def inversion_report():
    """Edges INCLUDED in the score. Lower is better."""
    variants = _variants(masked=False)
    return {
        name: {
            "all_edges": _inversions(fn),
            f"criticality_ge_{HIGH_CRITICALITY}": _inversions(fn, HIGH_CRITICALITY),
        }
        for name, fn in variants.items()
    }


def hard_cases():
    """Specific rankings a domain reader would expect to hold. Recorded as
    observed facts; a later scoring change is judged against them."""
    pairs = _pairs()
    fn = _variants(masked=False)["current_composite"]
    ranking = sorted((z for z in STORE.issuer_ids if z != "TSM"), key=lambda z: -fn(pairs[("TSM", z)]))
    return {
        "tsm_ranking_current_top8": ranking[:8],
        "tsm_rank_of_nvda_documented_customer_crit_0.95": ranking.index("NVDA") + 1,
        "tsm_rank_of_ssnlf_no_documented_supply_edge": ranking.index("SSNLF") + 1,
        "expectation": "documented customer (NVDA) ranks above a peer with no documented edge (SSNLF)",
        "expectation_met": ranking.index("NVDA") < ranking.index("SSNLF"),
    }


def availability():
    pairs = _pairs()
    n = len(pairs) // 2
    return {
        "issuer_pairs": n,
        "pairs_with_component": {
            k: sum(1 for (a, b), p in pairs.items() if a < b and p["comp"][k] is not None)
            for k in DEFAULT_WEIGHTS
        },
    }


def run_validation():
    pos = _positives()
    return {
        "caveats": CAVEATS,
        "default_weights": dict(DEFAULT_WEIGHTS),
        "availability": availability(),
        "ground_truth": {
            "queries_with_documented_edge": sum(1 for a in STORE.issuer_ids if pos[a]),
            "directed_positives": sum(len(v) for v in pos.values()),
        },
        "leave_edge_out": leave_edge_out(),
        "inversions": inversion_report(),
        "hard_cases": hard_cases(),
    }
