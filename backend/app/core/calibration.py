"""Experimental Anchor Calibration.

A constrained pairwise-ranking calibration of the composite-score weights
against a small, EXPLICITLY weak-supervision anchor set
(backend/data/calibration_anchors.json). This is a POC demonstration that
the heuristic weights CAN be nudged by relative-ranking evidence - it is
NOT a validated model fit. The L2 regularisation toward the current
heuristic starting weights exists specifically because the anchor set is
small and unstable/extreme coefficients from a handful of anchors would be
misleading.

Uses the EXISTING scoring.score_pair()/composite_score() - no scoring logic
is duplicated here, and the existing missing-component renormalisation
(e.g. for ownership, which has zero data in this dataset) applies exactly
as it does everywhere else in the platform.
"""
import json
import numpy as np
from scipy.optimize import minimize
from .config import DATA_DIR, DEFAULT_WEIGHTS
from . import scoring, market

COMPONENT_KEYS = ["sector", "geography", "supply_chain", "ownership", "semantic",
                   "news", "market_positive", "market_negative"]

DEFAULT_GAMMA = 8.0   # logistic loss steepness
DEFAULT_LAMBDA = 2.0  # L2 regularisation strength toward starting weights


def load_anchors():
    with open(DATA_DIR / "calibration_anchors.json") as f:
        return json.load(f)["anchors"]


def _weights_from_vector(w_vec):
    return {k: float(v) for k, v in zip(COMPONENT_KEYS, w_vec)}


def _pair_score(a, b, w_vec):
    """Delegates entirely to the existing composite_score/feature_vector
    pipeline; a missing composite score (no computable components at all
    for this pair) is treated as 0 for calibration purposes only."""
    weights = _weights_from_vector(w_vec)
    vec = scoring.feature_vector(a, b)
    comp = scoring.composite_score(vec, weights, round_output=False)
    s = comp["score"]
    return s if s is not None else 0.0


def _margin(anchor, w_vec):
    pos = _pair_score(anchor["anchor_entity"], anchor["preferred_entity"], w_vec)
    neg = _pair_score(anchor["anchor_entity"], anchor["less_related_entity"], w_vec)
    return pos - neg


def _pairwise_loss(anchors, w_vec, gamma):
    if not anchors:
        return 0.0
    margins = np.array([_margin(a, w_vec) for a in anchors])
    return float(np.sum(np.logaddexp(0, -gamma * margins)))


def _objective(w_vec, train_anchors, w_start_vec, gamma, lam):
    loss = _pairwise_loss(train_anchors, w_vec, gamma)
    reg = lam * float(np.sum((w_vec - w_start_vec) ** 2))
    return loss + reg


def _metrics(anchors, w_vec, gamma):
    if not anchors:
        return {"count": 0, "satisfied": 0, "satisfied_pct": None, "mean_margin": None, "pairwise_loss": None}
    margins = [_margin(a, w_vec) for a in anchors]
    satisfied = sum(1 for m in margins if m > 0)
    return {
        "count": len(anchors),
        "satisfied": satisfied,
        "satisfied_pct": round(100 * satisfied / len(anchors), 1),
        "mean_margin": round(float(np.mean(margins)), 4),
        "pairwise_loss": round(_pairwise_loss(anchors, w_vec, gamma), 4),
    }


def run_calibration(starting_weights=None, gamma=DEFAULT_GAMMA, lam=DEFAULT_LAMBDA):
    """SLSQP-constrained pairwise-ranking calibration on TRAIN anchors only;
    HOLDOUT anchors are evaluated afterward and never enter the objective or
    the optimizer in any way. Deterministic: fixed anchors, fixed starting
    point, no randomness in the optimizer call."""
    w_start = starting_weights or DEFAULT_WEIGHTS
    w_start_vec = np.array([w_start.get(k, 0.0) for k in COMPONENT_KEYS], dtype=float)

    anchors = load_anchors()
    train_anchors = [a for a in anchors if a["split"] == "train"]
    holdout_anchors = [a for a in anchors if a["split"] == "holdout"]

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
    bounds = [(0.0, 1.0) for _ in COMPONENT_KEYS]

    result = minimize(
        _objective, w_start_vec, args=(train_anchors, w_start_vec, gamma, lam),
        method="SLSQP", bounds=bounds, constraints=constraints,
        options={"maxiter": 200, "ftol": 1e-9},
    )
    converged = bool(result.success)
    w_calibrated_vec = result.x if converged else w_start_vec
    # guard against tiny SLSQP floating-point drift off the simplex
    w_calibrated_vec = np.clip(w_calibrated_vec, 0.0, 1.0)
    w_calibrated_vec = w_calibrated_vec / w_calibrated_vec.sum()

    w_calibrated = {k: round(float(v), 4) for k, v in zip(COMPONENT_KEYS, w_calibrated_vec)}
    w_starting = {k: round(float(v), 4) for k, v in zip(COMPONENT_KEYS, w_start_vec)}

    return {
        "status": "ok" if converged else "optimizer_did_not_converge_using_starting_weights",
        "label": "Experimental Anchor Calibration",
        "disclaimer": "POC weak-supervision experiment; coefficients are not statistically validated.",
        "starting_weights": w_starting,
        "calibrated_weights": w_calibrated,
        "train": _metrics(train_anchors, w_calibrated_vec, gamma),
        "holdout": _metrics(holdout_anchors, w_calibrated_vec, gamma),
        "train_at_starting_weights": _metrics(train_anchors, w_start_vec, gamma),
        "holdout_at_starting_weights": _metrics(holdout_anchors, w_start_vec, gamma),
        "n_anchors_total": len(anchors),
        "n_train": len(train_anchors),
        "n_holdout": len(holdout_anchors),
        "gamma": gamma,
        "lambda": lam,
    }


def list_anchors():
    anchors = load_anchors()
    return {
        "n_total": len(anchors),
        "n_train": sum(1 for a in anchors if a["split"] == "train"),
        "n_holdout": sum(1 for a in anchors if a["split"] == "holdout"),
        "source_type": "POC_EXPERT_ANCHOR",
        "disclaimer": "Weak-supervision relative-ranking constraints, hand-picked for this POC. Not ground truth.",
        "anchors": anchors,
    }


def market_agreement_diagnostic(weights=None, top_k=5):
    """DIAGNOSTIC ONLY (BUILD_MANDATE-consistent: market correlation is a
    feature, never the optimisation target). For each issuer with real
    market data, take its top-K composite-ranked candidates that ALSO have
    market data, and compare their mean |signed correlation| against the
    baseline mean |correlation| across all market-data issuer pairs. This
    is evidence about whether the composite ranking tends to surface
    entities that also co-move historically - it does not feed back into
    calibration."""
    from . import candidates as candidates_mod
    w = weights or DEFAULT_WEIGHTS
    from .data import STORE

    market_ids = [eid for eid in STORE.issuer_ids if STORE.entity(eid).get("has_market_data")]

    # baseline: mean |corr| across all observable market-data pairs
    baseline_corrs = []
    for i, a in enumerate(market_ids):
        for b in market_ids[i + 1:]:
            corr = market.signed_correlation(a, b)
            if corr:
                baseline_corrs.append(abs(corr["full_sample_corr"]))

    top_k_corrs = []
    n_pairs_evaluated = 0
    for eid in market_ids:
        cand = candidates_mod.generate_candidates(eid)
        if not cand:
            continue
        ranked = scoring.rank_candidates(eid, cand["candidate_ids"], w, top_k=top_k)
        for r in ranked["results"]:
            other = r["b"]
            if other not in market_ids:
                continue
            corr = market.signed_correlation(eid, other)
            if corr:
                top_k_corrs.append(abs(corr["full_sample_corr"]))
                n_pairs_evaluated += 1

    return {
        "description": "Diagnostic evidence only: does the composite ranking tend to surface entities that also "
                        "co-move historically? Market correlation is a scoring FEATURE, never a calibration target.",
        "mean_top_k_abs_correlation": round(float(np.mean(top_k_corrs)), 4) if top_k_corrs else None,
        "baseline_mean_abs_correlation": round(float(np.mean(baseline_corrs)), 4) if baseline_corrs else None,
        "n_top_k_pairs_evaluated": n_pairs_evaluated,
        "n_baseline_pairs": len(baseline_corrs),
        "n_market_data_issuers": len(market_ids),
    }
