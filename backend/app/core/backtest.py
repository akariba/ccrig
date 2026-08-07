"""Scenario Replay / Backtest Prototype (BUILD_MANDATE section 18).

Worked example: the Taiwan earthquake narrative (news doc n11, 2026-07-06)
disrupting TSMC fabrication. The EVENT NARRATIVE ITSELF IS SYNTHETIC (n11 is
drawn from news_synthetic.json, not news_real.json); only the subsequent
market prices used to score the outcome are real. This is therefore a
scenario replay / backtest PROTOTYPE illustrating the methodology on a
synthetic-narrative + real-price case, NOT a validated historical-event
backtest and NOT a validated trading or risk model. A true historical-event
backtest (real narrative + real prices) can be added later; see
docs/LIMITATIONS.md.

Look-ahead prevention BY DESIGN:
  - Theme/entity detection uses only the event narrative text itself.
  - The model score uses ONLY: (a) the static factual supply-chain graph
    (timeless, no dates), and (b) market correlation computed with
    `signed_correlation_asof(..., asof_date=T0)`, which truncates every
    price series at T0 before computing anything.
  - "Observed subsequent affected entities" are computed strictly from
    price moves AFTER T0 (`market.forward_move`) and are only ever used as
    the evaluation label, never fed back into the model score.

The SVB-collapse and 2011-Japan-earthquake alternates mentioned in the
mandate are not implemented as second worked examples in this POC pass
(no bundled 2011/2023 price or news data) - see docs/LIMITATIONS.md.
"""
import math
from datetime import date
from .data import STORE
from . import market
from .event_parser import detect_entities, detect_themes, mode1_bounded_traversal

SCENARIOS = {
    "taiwan_earthquake_2026": {
        "id": "taiwan_earthquake_2026",
        "label": "Taiwan earthquake disrupts semiconductor fabrication (Scenario Replay / Backtest Prototype)",
        "methodology": "SCENARIO_REPLAY_PROTOTYPE",
        "narrative_type": "SYNTHETIC",
        "price_data_type": "REAL",
        "methodology_note": "Synthetic event narrative + real subsequent market data. Not a validated "
                             "historical-event backtest.",
        "news_id": "n11",
        "t0": "2026-07-06",
        "horizon_trading_days": 5,
        "top_k": 8,
        "status": "IMPLEMENTED",
    },
    "svb_collapse": {
        "id": "svb_collapse", "label": "Regional bank funding stress after a major bank failure (SVB-style)",
        "status": "NOT_IMPLEMENTED_NO_BUNDLED_DATA",
    },
    "japan_2011_earthquake": {
        "id": "japan_2011_earthquake", "label": "2011 Japan earthquake supply-chain shock",
        "status": "NOT_IMPLEMENTED_NO_BUNDLED_DATA",
    },
}


def list_scenarios():
    return list(SCENARIOS.values())


def _dcg(rels):
    return sum(r / math.log2(i + 2) for i, r in enumerate(rels))


def _ndcg_at_k(ranked_ids, positive_set, k):
    top = ranked_ids[:k]
    rels = [1.0 if eid in positive_set else 0.0 for eid in top]
    ideal = sorted(rels, reverse=True)
    dcg = _dcg(rels)
    idcg = _dcg(ideal)
    return round(dcg / idcg, 4) if idcg > 0 else 0.0


def run_backtest(scenario_id="taiwan_earthquake_2026"):
    scenario = SCENARIOS.get(scenario_id)
    if not scenario or scenario.get("status") != "IMPLEMENTED":
        return {"error": f"scenario '{scenario_id}' is not implemented in this POC", "available": list_scenarios()}

    news_doc = next((d for d in STORE.news_all if d["id"] == scenario["news_id"]), None)
    t0 = date.fromisoformat(scenario["t0"])
    horizon = scenario["horizon_trading_days"]
    top_k = scenario["top_k"]

    narrative = news_doc["text"] if news_doc else ""
    direct_entities = detect_entities(narrative)
    themes = detect_themes(narrative)

    # --- MODEL SCORE (look-ahead-safe) ---
    mode1_scores, typed_paths = mode1_bounded_traversal(direct_entities, themes, max_hops=2)
    model_scores = {eid: 1.0 for eid in direct_entities}
    for eid, d in mode1_scores.items():
        model_scores[eid] = max(model_scores.get(eid, 0), d["score"])

    # asof market-shock candidates: correlate every market-data entity to
    # the direct entities using ONLY pre-T0 data, add as a secondary signal.
    for other in STORE.issuer_ids:
        if not STORE.entity(other).get("has_market_data") or other in model_scores:
            continue
        best = 0.0
        for direct in direct_entities:
            if not STORE.entity(direct).get("has_market_data"):
                continue
            corr = market.signed_correlation_asof(direct, other, t0)
            if corr:
                best = max(best, abs(corr["asof_corr"]))
        if best > 0.15:
            model_scores[other] = max(model_scores.get(other, 0), best * 0.8)

    ranked_model = sorted(model_scores.items(), key=lambda x: -x[1])
    ranked_model_ids = [eid for eid, _ in ranked_model]

    # --- OBSERVED OUTCOME LABELS (post-T0 only, evaluation-only) ---
    moves = []
    for eid in STORE.issuer_ids:
        fm = market.forward_move(eid, t0, horizon_days=horizon)
        if fm:
            moves.append(fm)
    moves.sort(key=lambda m: -m["abs_return"])
    observed_top = moves[:top_k]
    positive_set = {m["entity_id"] for m in observed_top}

    # --- METRICS (restricted to entities that HAVE market data, since the
    # observed-label universe only exists for those - comparing a mixed
    # universe would silently penalise entities we have no label for) ---
    market_universe = [eid for eid in ranked_model_ids if STORE.entity(eid) and STORE.entity(eid).get("has_market_data")]
    metrics = {}
    for k in (5, 8):
        top = market_universe[:k]
        hits = len(set(top) & positive_set)
        precision = hits / k if k else 0
        recall = hits / len(positive_set) if positive_set else 0
        metrics[f"precision_at_{k}"] = round(precision, 4)
        metrics[f"recall_at_{k}"] = round(recall, 4)
        metrics[f"ndcg_at_{k}"] = _ndcg_at_k(market_universe, positive_set, k)

    return {
        "scenario": scenario,
        "t0": scenario["t0"],
        "data_cutoff": scenario["t0"],
        "event_narrative_at_t0": narrative,
        "news_source": {"id": news_doc["id"], "is_synthetic": news_doc.get("is_synthetic"), "source": news_doc.get("source")} if news_doc else None,
        "detected_entities": direct_entities,
        "detected_themes": themes,
        "model_ranking_top_k": [{"entity_id": eid, "model_score": round(s, 4)} for eid, s in ranked_model[:top_k]],
        "observed_subsequent_movers_top_k": observed_top,
        "metrics": metrics,
        "warnings": [
            "SCENARIO REPLAY / BACKTEST PROTOTYPE, NOT A HISTORICAL BACKTEST: the event narrative (news doc "
            f"{scenario['news_id']}) is a SYNTHETIC construction; only the subsequent market prices used for "
            "scoring are real. Do not present this as a validated historical-event backtest.",
            "POC-SCALE WARNING: this is a single illustrative worked example, not a validated backtest. "
            "Sample size (one event) is far too small for statistical significance.",
            "'Observed subsequent affected entities' is a REALIZED-RETURN PROXY (largest absolute price move in "
            f"the {horizon} trading days after T0), not verified causal ground truth - many things move markets "
            "simultaneously and this label cannot isolate the earthquake's specific causal effect.",
            "Model score intentionally excludes any post-T0 data (asof-truncated correlation + timeless fact "
            "graph only) to avoid look-ahead bias.",
        ],
    }
