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

METHODOLOGY (v2). The first version of the evaluation had four weaknesses,
all verified in the data and all reported side by side with the corrected
numbers (the original procedure is kept verbatim as `legacy`):
  1. The entities NAMED in the event text were scored 1.0 and counted as
     predictions. They are inputs, not predictions: they are now excluded
     from the ranking and the labels (reported separately as `seed_entities`).
  2. Every entity must be measured over the same window. SKHY's price history
     starts after T0, so its "forward move" silently started four days later
     than everyone else's. Entities without a close at T0 and a full forward
     window are excluded, with the reason (`market.window_return`).
  3. The label was the raw absolute return, which mostly measures the market
     (and energy/defence names) rather than the event. It is now the absolute
     ABNORMAL return: the entity's return minus the equal-weighted mean of the
     other eligible non-seed entities over the same window.
  4. Eight "positives" out of 14 priced issuers made precision@5 close to
     meaningless. The positive set is now the top third of the evaluated
     universe, and every metric is shown beside what a random ranking would
     achieve and the exact probability of doing at least this well by chance.
Still true, and still stated in the warnings: one event, a synthetic
narrative, a handful of priced issuers - no statistical significance.
The secondary correlation signal in the model score uses |correlation| on
purpose: the label is a MAGNITUDE of movement, so the direction of co-movement
is irrelevant to it (this is a backtest signal, not a relationship feature).
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



CORRECTED_KS = (3, 5)
LEGACY_KS = (5, 8)


def _hypergeom_tail(population, positives, draws, hits):
    """P(X >= hits) when drawing `draws` of `population` items containing `positives` positives."""
    total = math.comb(population, draws)
    return sum(math.comb(positives, h) * math.comb(population - positives, draws - h)
               for h in range(hits, min(positives, draws) + 1)) / total


def _evaluate_ranking(ranked_ids, label_values, n_positive, ks):
    """Retrieval metrics for a FULL ranking of the evaluated universe against the
    top-`n_positive` entities by label value (ties: entity id)."""
    universe = len(ranked_ids)
    by_label = sorted(ranked_ids, key=lambda e: (-label_values[e], e))
    positives = set(by_label[:n_positive])
    out = {"universe_size": universe, "n_positive": n_positive, "positives": by_label[:n_positive]}
    for k in ks:
        if k > universe:
            continue
        top = ranked_ids[:k]
        hits = len(set(top) & positives)
        out[f"precision_at_{k}"] = round(hits / k, 4)
        out[f"recall_at_{k}"] = round(hits / n_positive, 4)
        out[f"ndcg_at_{k}"] = _ndcg_at_k(ranked_ids, positives, k)
        out[f"random_precision_at_{k}"] = round(n_positive / universe, 4)
        out[f"hits_at_{k}"] = hits
        out[f"p_value_at_{k}"] = round(_hypergeom_tail(universe, n_positive, k, hits), 4)
    return out


def _model_scores(direct_entities, themes, t0):
    """The model score. UNCHANGED from v1: typed-path traversal from the entities
    named in the event, plus an as-of-T0 co-movement signal (pre-T0 data only)."""
    mode1_scores, _typed_paths = mode1_bounded_traversal(direct_entities, themes, max_hops=2)
    model_scores = {eid: 1.0 for eid in direct_entities}
    for eid, d in mode1_scores.items():
        model_scores[eid] = max(model_scores.get(eid, 0), d["score"])
    for other in STORE.issuer_ids:
        if not STORE.entity(other).get("has_market_data") or other in model_scores:
            continue
        best = 0.0
        for direct in direct_entities:
            if not STORE.entity(direct).get("has_market_data"):
                continue
            corr = market.signed_correlation_asof(direct, other, t0)
            if corr:
                best = max(best, abs(corr["asof_corr"]))   # magnitude on purpose: see module docstring
        if best > 0.15:
            model_scores[other] = max(model_scores.get(other, 0), best * 0.8)
    return model_scores


def _legacy_evaluation(model_scores, t0, horizon, top_k):
    """The ORIGINAL (v1) procedure, verbatim, kept so the 'before' numbers stay
    reproducible. Do not use it to judge the model - see the module docstring."""
    ranked_model = sorted(model_scores.items(), key=lambda x: -x[1])
    ranked_model_ids = [eid for eid, _ in ranked_model]

    moves = []
    for eid in STORE.issuer_ids:
        fm = market.forward_move(eid, t0, horizon_days=horizon)
        if fm:
            moves.append(fm)
    moves.sort(key=lambda m: -m["abs_return"])
    observed_top = moves[:top_k]
    positive_set = {m["entity_id"] for m in observed_top}

    market_universe = [eid for eid in ranked_model_ids if STORE.entity(eid) and STORE.entity(eid).get("has_market_data")]
    metrics = {}
    for k in LEGACY_KS:
        top = market_universe[:k]
        hits = len(set(top) & positive_set)
        precision = hits / k if k else 0
        recall = hits / len(positive_set) if positive_set else 0
        metrics[f"precision_at_{k}"] = round(precision, 4)
        metrics[f"recall_at_{k}"] = round(recall, 4)
        metrics[f"ndcg_at_{k}"] = _ndcg_at_k(market_universe, positive_set, k)
    return {
        "metrics": metrics,
        "model_ranking_top_k": [{"entity_id": eid, "model_score": round(s, 4)} for eid, s in ranked_model[:top_k]],
        "observed_subsequent_movers_top_k": observed_top,
        "priced_universe": market_universe,
    }


def _strict_windows(t0, horizon):
    """{entity: window} for priced issuers, plus {entity: reason} for those that cannot be measured."""
    ok, excluded = {}, {}
    for eid in STORE.issuer_ids:
        if not STORE.entity(eid).get("has_market_data"):
            continue
        w = market.window_return(eid, t0, horizon_days=horizon)
        if w["status"] == "OK":
            ok[eid] = w
        else:
            excluded[eid] = w
    return ok, excluded


def _abnormal_returns(windows, members):
    """Return minus the equal-weighted mean of the OTHER members over the same window."""
    out = {}
    for eid in members:
        others = [windows[o]["return"] for o in members if o != eid]
        out[eid] = windows[eid]["return"] - (sum(others) / len(others) if others else 0.0)
    return out


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
    seeds = set(direct_entities)

    # --- MODEL SCORE (look-ahead-safe; unchanged from v1) ---
    model_scores = _model_scores(direct_entities, themes, t0)

    # --- BEFORE: the original procedure, verbatim ---
    legacy = _legacy_evaluation(model_scores, t0, horizon, top_k)

    # --- AFTER: corrected evaluation (labels use post-T0 prices only, evaluation-only) ---
    windows, excluded_windows = _strict_windows(t0, horizon)
    eligible = [e for e in windows if e not in seeds]
    n_positive = max(2, round(len(eligible) / 3))
    abnormal = _abnormal_returns(windows, eligible)
    ranked_ids = sorted(eligible, key=lambda e: (-model_scores.get(e, 0.0), e))
    abs_abnormal = {e: abs(v) for e, v in abnormal.items()}
    corrected = _evaluate_ranking(ranked_ids, abs_abnormal, n_positive, CORRECTED_KS)

    # --- ATTRIBUTION: apply the corrections one at a time ---
    priced_non_seed = [e for e in legacy["priced_universe"] if e not in seeds]      # step 1 universe (v1 windows)
    legacy_abs = {}
    for e in STORE.issuer_ids:
        fm = market.forward_move(e, t0, horizon_days=horizon)
        if fm:
            legacy_abs[e] = fm["abs_return"]
    step_universe = [e for e in sorted(priced_non_seed, key=lambda e: (-model_scores.get(e, 0.0), e)) if e in legacy_abs]
    steps = [{"step": 0, "change": "As originally published (v1)", "universe_size": len(legacy["priced_universe"]),
              "n_positive": top_k, **{k: v for k, v in legacy["metrics"].items() if k.endswith("_at_5")}}]
    s1 = _evaluate_ranking(step_universe, legacy_abs, max(2, round(len(step_universe) / 3)), (5,))
    steps.append({"step": 1, "change": "Exclude entities named in the event text; positives = top third of the universe",
                  **{k: v for k, v in s1.items() if k != "positives"}})
    strict_universe = sorted(eligible, key=lambda e: (-model_scores.get(e, 0.0), e))
    raw_strict = {e: abs(windows[e]["return"]) for e in eligible}
    s2 = _evaluate_ranking(strict_universe, raw_strict, n_positive, (5,))
    steps.append({"step": 2, "change": "+ Require a close at T0 and a full forward window for every entity (drops SKHY)",
                  **{k: v for k, v in s2.items() if k != "positives"}})
    s3 = _evaluate_ranking(ranked_ids, abs_abnormal, n_positive, (5,))
    steps.append({"step": 3, "change": "+ Label = absolute abnormal return (market-adjusted)",
                  **{k: v for k, v in s3.items() if k != "positives"}})

    observed = sorted(eligible, key=lambda e: (-abs_abnormal[e], e))
    return {
        "scenario": scenario,
        "methodology_version": 2,
        "t0": scenario["t0"],
        "data_cutoff": scenario["t0"],
        "event_narrative_at_t0": narrative,
        "news_source": {"id": news_doc["id"], "is_synthetic": news_doc.get("is_synthetic"), "source": news_doc.get("source")} if news_doc else None,
        "detected_entities": direct_entities,
        "seed_entities": {
            "entities": sorted(seeds),
            "note": "Named in the event text: they are the INPUT to the model, not predictions, so they are not "
                    "ranked or scored here (v1 scored them 1.0 and counted them).",
        },
        "detected_themes": themes,
        "model_ranking_top_k": [{"entity_id": e, "model_score": round(model_scores.get(e, 0.0), 4)}
                                for e in ranked_ids[:top_k]],
        "observed_subsequent_movers_top_k": [
            {"entity_id": e, "from_date": windows[e]["from_date"], "to_date": windows[e]["to_date"],
             "return": round(windows[e]["return"], 5), "abnormal_return": round(abnormal[e], 5),
             "abs_abnormal_return": round(abs_abnormal[e], 5), "is_label_positive": e in corrected["positives"]}
            for e in observed[:top_k]],
        "evaluation": {
            "universe": ranked_ids,
            "excluded": [{"entity_id": e, "reason": "NAMED_IN_EVENT_TEXT"} for e in sorted(seeds & set(windows))]
                        + [{"entity_id": e, **w} for e, w in sorted(excluded_windows.items())],
            "label": "absolute abnormal return over the T0 -> T0+%d trading-day window (return minus the "
                     "leave-one-out equal-weighted mean of the evaluated entities)" % horizon,
            "n_positive_rule": "top third of the evaluated universe (at least 2)",
        },
        "metrics": {k: v for k, v in corrected.items() if k not in ("positives",)},
        "correction_steps": steps,
        "legacy": {
            "description": "The ORIGINAL v1 procedure, kept verbatim for before/after comparison. Do not use it to "
                           "judge the model: it ranks the entities named in the event text, shifts SKHY's window and "
                           "labels with raw returns.",
            "metrics": legacy["metrics"],
            "model_ranking_top_k": legacy["model_ranking_top_k"],
            "observed_subsequent_movers_top_k": legacy["observed_subsequent_movers_top_k"],
        },
        "warnings": [
            "SCENARIO REPLAY / BACKTEST PROTOTYPE, NOT A HISTORICAL BACKTEST: the event narrative (news doc "
            f"{scenario['news_id']}) is a SYNTHETIC construction; only the subsequent market prices used for "
            "scoring are real. Do not present this as a validated historical-event backtest.",
            f"POC-SCALE WARNING: one event and {len(ranked_ids)} evaluated issuers. Read the random-ranking baseline and "
            "the chance probability next to every metric: at this size most outcomes are not distinguishable from luck.",
            "'Observed subsequent affected entities' is a REALIZED-RETURN PROXY (largest absolute abnormal price move in "
            f"the {horizon} trading days after T0), not verified causal ground truth - many things move markets "
            "simultaneously and this label cannot isolate the earthquake's specific causal effect.",
            "Model score intentionally excludes any post-T0 data (asof-truncated correlation + timeless fact "
            "graph only) to avoid look-ahead bias.",
            "The window starts at the T0 close, so any reaction already priced into T0 itself is not measured.",
        ],
    }
