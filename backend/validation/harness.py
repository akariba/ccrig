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
    "'Hard negatives' are issuers with NO DOCUMENTED edge to the query. The edge list is curated and incomplete, so "
    "undocumented is not proven unrelated.",
    "The composite measures SIMILARITY (sector, geography, text, themes); the documented edges are supply/licence "
    "DEPENDENCIES. With the edges masked, ranking dependencies by similarity is a hard task by construction - a low "
    "score here says the composite is not a dependency detector, not that the similarity it computes is wrong.",
    "The 34 expert anchors are easy (a supplier vs an oil major): single features score 94-100% on them, so they "
    "cannot tell weight sets apart, and the existing train/holdout split shares entities.",
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


# ============================================================ extended validation
# Everything below is derived from data already in the repo (documented edges,
# the 34 pairwise expert anchors). Nothing is invented. "No documented edge"
# means UNDOCUMENTED, not proven unrelated - the edge list is curated and
# incomplete - and every section says so.
MIN_ANCHORS_TO_FIT = 8


def _expected_rank(scores, target):
    """1 + (#strictly better) + (#ties)/2: the rank under a random tie-break."""
    s = scores[target]
    better = sum(1 for v in scores.values() if v > s)
    ties = sum(1 for v in scores.values() if v == s) - 1
    return 1 + better + ties / 2


def _all_variants():
    return {**_variants(masked=True), **BASELINES}


def _directed_edges():
    pairs, issuers = _pairs(), STORE.issuer_ids
    return [(a, b) for a in issuers for b in issuers if a != b and pairs[(a, b)]["comp"]["supply_chain"] is not None]


def hard_cases_extended():
    """Difficult positives and negatives, all derived from the documented edges
    (supply_chain/ownership masked so an edge never predicts itself).

    * hard positives: documented edges between issuers of DIFFERENT sectors -
      a ranker leaning on "same sector" cannot find them by construction;
    * hard negatives: issuers in the SAME sector AND country as the query with
      no documented edge to it - look-alikes. For every (query, partner,
      look-alike) triple, how often does the model score the documented partner
      above the look-alike? (ties count 0.5)
    """
    pairs, issuers = _pairs(), STORE.issuer_ids
    edges = _directed_edges()
    sector = lambda e: STORE.entity(e)["sector"]            # noqa: E731
    country = lambda e: STORE.entity(e)["country"]          # noqa: E731
    cross = [(a, b) for a, b in edges if sector(a) != sector(b)]
    same = [(a, b) for a, b in edges if sector(a) == sector(b)]
    documented = {a: {b for x, b in edges if x == a} for a in issuers}
    triples = [(a, b, z) for a, b in edges for z in issuers
               if z not in (a, b) and z not in documented[a] and sector(z) == sector(a) and country(z) == country(a)]

    out = {"definitions": {
        "hard_positives": "documented supply/licence edges between issuers of different sectors",
        "easy_positives": "documented edges between issuers of the same sector",
        "hard_negatives": "same sector AND same country as the query, no documented edge ('undocumented', not proven unrelated)",
    }, "counts": {"directed_edges": len(edges), "hard_positive_edges": len(cross), "easy_positive_edges": len(same),
                  "hard_negative_triples": len(triples)}, "variants": {}}
    for name, fn in _all_variants().items():
        rec = {}
        for label, subset in (("hard_positives", cross), ("easy_positives", same)):
            ranks = []
            for a, b in subset:
                scores = {z: fn(pairs[(a, z)]) for z in issuers if z != a}
                ranks.append(_expected_rank(scores, b))
            if ranks:
                rec[label] = {"median_rank": round(float(np.median(ranks)), 2),
                              "mean_reciprocal_rank": round(float(np.mean([1 / r for r in ranks])), 4),
                              "share_in_top10": round(float(np.mean([r <= 10 for r in ranks])), 4)}
        if triples:
            wins = [1.0 if fn(pairs[(a, b)]) > fn(pairs[(a, z)]) else 0.5 if fn(pairs[(a, b)]) == fn(pairs[(a, z)]) else 0.0
                    for a, b, z in triples]
            rec["partner_above_lookalike"] = round(float(np.mean(wins)), 4)
        out["variants"][name] = rec
    return out


def _anchor_entities(anchor):
    return {anchor["anchor_entity"], anchor["preferred_entity"], anchor["less_related_entity"]}


def _anchor_scores(fn, anchor):
    pairs = _pairs()
    a, b, z = anchor["anchor_entity"], anchor["preferred_entity"], anchor["less_related_entity"]
    return fn(pairs[(a, b)]), fn(pairs[(a, z)])


def _pairwise_accuracy(fn, anchors):
    if not anchors:
        return None
    wins = []
    for anchor in anchors:
        s_pref, s_less = _anchor_scores(fn, anchor)
        wins.append(1.0 if s_pref > s_less else 0.5 if s_pref == s_less else 0.0)
    return round(float(np.mean(wins)), 4)


def entity_folds():
    """Deterministic 2-fold entity split: issuers sorted by id, alternating A/B."""
    return {e: ("A" if i % 2 == 0 else "B") for i, e in enumerate(sorted(STORE.issuer_ids))}


def anchor_evaluation():
    """Pairwise accuracy of every scorer on the 34 expert anchors, and how
    independent the existing train/holdout split really is."""
    from app.core import calibration

    anchors = calibration.load_anchors()
    train = [a for a in anchors if a["split"] == "train"]
    hold = [a for a in anchors if a["split"] == "holdout"]
    train_entities = set().union(*(_anchor_entities(a) for a in train))
    folds = entity_folds()
    in_fold = {f: [a for a in anchors if all(folds[e] == f for e in _anchor_entities(a))] for f in ("A", "B")}
    return {
        "n_anchors": len(anchors),
        "existing_split_independence": {
            "n_train": len(train), "n_holdout": len(hold),
            "holdout_anchors_sharing_an_entity_with_train": sum(1 for a in hold if _anchor_entities(a) & train_entities),
            "holdout_anchors_sharing_the_query_entity_with_train": sum(1 for a in hold if a["anchor_entity"] in train_entities),
            "verdict": "NOT entity-disjoint: the holdout cannot show that anything generalises to unseen entities",
        },
        "entity_disjoint_capacity": {
            "anchors_fully_inside_fold_A": len(in_fold["A"]), "anchors_fully_inside_fold_B": len(in_fold["B"]),
            "anchors_crossing_folds_unusable": len(anchors) - len(in_fold["A"]) - len(in_fold["B"]),
            "min_anchors_to_fit": MIN_ANCHORS_TO_FIT,
        },
        "pairwise_accuracy": {name: {"all_34": _pairwise_accuracy(fn, anchors),
                                     "existing_train": _pairwise_accuracy(fn, train),
                                     "existing_holdout": _pairwise_accuracy(fn, hold)}
                              for name, fn in _all_variants().items()},
        "note": "Anchors are weak-supervision judgments, many easy (supplier vs an oil major). Accuracy near the "
                "single-feature baselines means the anchors cannot tell weight sets apart.",
    }


def fit_weights_on(anchors):
    """The calibration objective (app.core.calibration), applied to `anchors`
    only. Analysis aid: production weights are never touched."""
    from scipy.optimize import minimize

    from app.core import calibration

    keys = calibration.COMPONENT_KEYS
    start = np.array([DEFAULT_WEIGHTS.get(k, 0.0) for k in keys], dtype=float)
    result = minimize(calibration._objective, start,
                      args=(anchors, start, calibration.DEFAULT_GAMMA, calibration.DEFAULT_LAMBDA),
                      method="SLSQP", bounds=[(0.0, 1.0)] * len(keys),
                      constraints=[{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}],
                      options={"maxiter": 200, "ftol": 1e-9})
    vec = np.clip(result.x if result.success else start, 0.0, 1.0)
    vec = vec / vec.sum()
    return {k: float(v) for k, v in zip(keys, vec)}, bool(result.success)


def _fold_universe(fold):
    folds = entity_folds()
    return [e for e in STORE.issuer_ids if folds[e] == fold]


def entity_disjoint_holdout():
    """2-fold, entity-disjoint evaluation of leave-edge-out retrieval.

    For each fold F the universe is F's issuers ONLY: queries, candidates and
    documented positives all lie inside F, and nothing is fitted on F. Scorers
    with no fitted parameters (the default composite, the single-feature
    baselines) are therefore trivially disjoint; `fitted_on_other_fold()` covers
    the one scorer that has parameters.
    """
    variants = {**_variants(masked=True), **BASELINES}
    return {
        "folds": {f: _fold_universe(f) for f in ("A", "B")},
        "design": "universe = one fold's issuers; queries, candidates and documented positives all inside it",
        "per_fold": {f: {name: _evaluate(fn, _fold_universe(f)) for name, fn in variants.items()} for f in ("A", "B")},
    }


def fitted_on_other_fold():
    """INFORMATIONAL (not part of the gated baseline: SLSQP's last digits depend
    on the scipy build). For each fold F: fit the calibration objective on the
    expert anchors lying ENTIRELY inside the other fold, then run retrieval on
    F. Fitted only if at least MIN_ANCHORS_TO_FIT anchors exist."""
    from app.core import calibration

    folds = entity_folds()
    anchors = calibration.load_anchors()
    out = {}
    for fold in ("A", "B"):
        other = "B" if fold == "A" else "A"
        train_anchors = [a for a in anchors if all(folds[e] == other for e in _anchor_entities(a))]
        info = {"fitted_on_fold": other, "tested_on_fold": fold, "n_anchors_used": len(train_anchors),
                "train_entities": sorted(set().union(*(_anchor_entities(a) for a in train_anchors))) if train_anchors else []}
        if len(train_anchors) < MIN_ANCHORS_TO_FIT:
            info["status"] = "INSUFFICIENT_ANCHORS"
        else:
            weights, converged = fit_weights_on(train_anchors)
            masked = {k: (0.0 if k in MASKED_COMPONENTS else w) for k, w in weights.items()}
            fitted_fn = lambda p, m=masked: scoring.composite_score(p["vec"], m, round_output=False)["score"] or 0.0  # noqa: E731
            universe = _fold_universe(fold)
            info.update({
                "status": "fitted" if converged else "optimizer_did_not_converge_using_starting_weights",
                "weights": {k: round(v, 4) for k, v in weights.items()},
                "retrieval": _evaluate(fitted_fn, universe),
                "default_weights_retrieval": _evaluate(_variants(masked=True)["current_composite"], universe),
            })
        out[fold] = info
    return out


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
        "hard_cases_extended": hard_cases_extended(),
        "anchors": anchor_evaluation(),
        "entity_disjoint_holdout": entity_disjoint_holdout(),
    }
