"""Daily Review: deterministic driver classification + priority ranking over
the synthetic CCR exposure/breach dataset (backend/data/ccr_counterparties.json).

Two explicit, separately-testable stages, per the product principle
"GRAPH NOMINATES. EXPOSURE RANKS.":

  1. classify_driver(record)  - WHY did the exposure move? Reads ONLY the
     record's evidence flags - never an AI guess, never inferred from the
     size of the move alone. In particular: a small |Delta PFE| is NEVER
     sufficient evidence of "simulation noise" on its own - that label
     requires an explicit simulation_noise_confirmed_flag (see
     CRITICAL FIX comment below).

  2. compute_priority(record, driver) - HOW urgent is this? A documented
     RULE MATRIX (never a naked 0-1 ML score) that can rank operational/
     governance risk (an old unresolved breach) above a larger exposure
     mover, and can rank a model-driven move or an immaterial-exposure
     event nomination BELOW a genuine market-driven risk mover.

LIMIT SEMANTICS (critical fix): every limit carries an explicit limit_type
(PFE_LIMIT / SETTLEMENT_LIMIT / STRESS_LIMIT / None). Utilisation is ONLY
ever computed against the metric that matches that type:
    PFE_LIMIT        -> utilisation = PFE_current / limit_value
    SETTLEMENT_LIMIT  -> utilisation = settlement_exposure / limit_value
    STRESS_LIMIT      -> utilisation = NSE_current / limit_value
    None (no limit on file) -> utilisation = None ("Unavailable"), NEVER
    silently computed off whatever numbers happen to be present.
"""
from .config import CCR_PRIORITY_THRESHOLDS
from .ccr_provider import get_ccr_provider

# All numeric thresholds below are explicitly POC_HEURISTIC (not real risk
# appetite) - centralised in config.py, never scattered as inline magic
# numbers, and always displayed as heuristic rather than authoritative in
# the API/UI (see routers/priority.py).
T = CCR_PRIORITY_THRESHOLDS

# Drivers that represent genuine market/credit risk signal (vs. model,
# data, or operational noise) - only these can drive a HIGH priority on
# exposure-move grounds alone.
REAL_RISK_DRIVERS = {"MARKET_MOVE", "MTM_MOVE", "WWR_RELATED", "NEW_TRADE", "NON_NETTED_EXPOSURE"}
ROUTED_NOT_ESCALATED_DRIVERS = {"MODEL_RECALIBRATION", "DATA_ISSUE", "NETTING_CHANGE", "COLLATERAL_CHANGE",
                                 "RECOVERY_CHANGE", "VOLATILITY_UPDATE", "MODEL_COVERAGE_CHANGE",
                                 "DATA_SOURCING_ISSUE", "REPLACEMENT_COST_MOVE"}


def _load_events():
    from .config import DATA_DIR
    import json
    path = DATA_DIR / "ccr_events.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return {e["id"]: e for e in json.load(f)["events"]}


_EVENTS_BY_ID = _load_events()


def _delta(current, previous):
    if current is None or previous is None:
        return None
    return current - previous


def enrich(record):
    """Adds every DERIVED field (never re-seeded raw): deltas, utilisation
    (limit-type-matched), headroom, excess, is_overdue. Missing inputs
    propagate as None ("Unavailable"), never a fabricated 0."""
    exp = record["exposure"]
    delta_pfe = _delta(exp.get("pfe_current"), exp.get("pfe_previous"))
    delta_nse = _delta(exp.get("nse_current"), exp.get("nse_previous"))

    limit = record["limit"]
    limit_type = limit.get("limit_type")
    limit_value = limit.get("limit_value")

    metric_for_limit = {
        "PFE_LIMIT": exp.get("pfe_current"),
        "SETTLEMENT_LIMIT": exp.get("settlement_exposure"),
        "STRESS_LIMIT": exp.get("nse_current"),
    }.get(limit_type)

    if limit_type and limit_value and metric_for_limit is not None:
        utilisation_pct = round(100 * metric_for_limit / limit_value, 1)
        headroom = round(limit_value - metric_for_limit, 1)
    else:
        utilisation_pct = None
        headroom = None

    breach = record.get("breach")
    is_breach = bool(breach and breach.get("is_breach"))
    is_overdue = bool(is_breach and breach.get("age_days") is not None and breach.get("age_days") > breach.get("sla_days", 0))
    excess = breach.get("excess") if (is_breach and breach) else None

    event = _EVENTS_BY_ID.get(record.get("linked_event_id"), _EVENTS_BY_ID.get("NONE"))

    return {
        **record,
        "delta_pfe": delta_pfe,
        "delta_nse": delta_nse,
        "utilisation_pct": utilisation_pct,
        "headroom": headroom,
        "is_breach": is_breach,
        "is_overdue": is_overdue,
        "excess": excess,
        "event": event,
    }


def classify_driver(record):
    """Deterministic cascade over evidence flags ONLY - first matching rule
    wins. Returns (driver, evidence) where evidence is a short list of the
    exact flags/values that justified the classification (never invented).

    CRITICAL FIX vs. the prior version of this module: there is NO rule of
    the form `abs(delta_pfe) < threshold -> SIMULATION_NOISE`. A small move
    is not evidence of simulation noise - that label requires an explicit
    simulation_noise_confirmed_flag (e.g. a documented Monte Carlo
    diagnostic). Absent any evidence flag at all, an unexplained move is
    UNKNOWN or SMALL_MOVE (by size, labelled honestly as just "small",
    never asserted to be noise)."""
    flags = record.get("driver_evidence", {})
    breach = record.get("breach")

    if breach and breach.get("is_breach"):
        return "LIMIT_BREACH", [f"breach.is_breach=True", f"age_days={breach.get('age_days')}",
                                 f"sla_days={breach.get('sla_days')}", f"root_cause={breach.get('root_cause')}"]
    if flags.get("data_sourcing_issue_flag"):
        return "DATA_SOURCING_ISSUE", ["data_sourcing_issue_flag=True"]
    if flags.get("data_issue_flag"):
        return "DATA_ISSUE", ["data_issue_flag=True"]
    if flags.get("model_coverage_change_flag"):
        return "MODEL_COVERAGE_CHANGE", ["model_coverage_change_flag=True"]
    if flags.get("model_version_changed") and not flags.get("trade_population_changed"):
        return "MODEL_RECALIBRATION", ["model_version_changed=True", "trade_population_changed=False"]
    if flags.get("volatility_update_flag"):
        return "VOLATILITY_UPDATE", ["volatility_update_flag=True"]
    if flags.get("recovery_change_flag"):
        return "RECOVERY_CHANGE", ["recovery_change_flag=True"]
    if flags.get("replacement_cost_move_flag"):
        return "REPLACEMENT_COST_MOVE", ["replacement_cost_move_flag=True"]
    if flags.get("non_netted_flag"):
        return "NON_NETTED_EXPOSURE", ["non_netted_flag=True (trade booked outside standard netting set)"]
    if flags.get("wwr_flag"):
        return "WWR_RELATED", ["wwr_flag=True"]
    if flags.get("netting_change_flag"):
        return "NETTING_CHANGE", ["netting_change_flag=True"]
    if flags.get("collateral_change_flag"):
        return "COLLATERAL_CHANGE", ["collateral_change_flag=True"]
    if flags.get("new_trade_flag"):
        return "NEW_TRADE", ["new_trade_flag=True"]
    if flags.get("matured_trade_flag"):
        return "MATURED_TRADE", ["matured_trade_flag=True"]
    if flags.get("market_move_flag"):
        return "MARKET_MOVE", ["market_move_flag=True", f"risk_factor_path={record.get('risk_factor_path')}"]
    if flags.get("simulation_noise_confirmed_flag"):
        return "SIMULATION_NOISE", ["simulation_noise_confirmed_flag=True (explicit diagnostic, not inferred from size)"]

    delta_pfe = _delta(record["exposure"].get("pfe_current"), record["exposure"].get("pfe_previous"))
    if all(v is None for v in flags.values()):
        return "UNKNOWN", ["no evidence flags available for this record"]
    if delta_pfe is not None and abs(delta_pfe) < T["small_move_abs_pfe"]:
        # Small in size, but NEVER asserted to be noise without evidence.
        return "SMALL_MOVE", [f"delta_pfe={delta_pfe} (small by POC_HEURISTIC size threshold only - not asserted as noise)"]
    return "UNKNOWN", ["no evidence flag matched"]


def compute_priority(enriched_record, driver):
    """Documented RULE MATRIX -> one of CRITICAL/HIGH/MEDIUM/LOW/INFORMATIONAL
    plus an explicit `reasons` list. Never a naked 0-1 score. All numeric
    thresholds are POC_HEURISTIC (config.py), not real risk appetite."""
    r = enriched_record
    reasons = []

    # CRITICAL: confirmed material breach significantly overdue, OR
    # confirmed WWR + material exposure, OR authoritative stressed
    # utilisation over limit.
    if r["is_overdue"]:
        reasons.append(f"Overdue {r['limit'].get('limit_type') or 'unknown-type'} breach: "
                        f"{r['breach']['age_days']} business days vs. {r['breach']['sla_days']}-day SLA "
                        f"(root cause: {r['breach'].get('root_cause') or 'unknown'})")
        if not r.get("coverage_owner"):
            reasons.append("No coverage owner assigned")
        return "CRITICAL", reasons
    if driver == "WWR_RELATED" and (r["utilisation_pct"] or 0) >= T["high_utilisation_pct"]:
        reasons.append(f"Confirmed WWR driver with utilisation {r['utilisation_pct']}% "
                        f">= {T['high_utilisation_pct']}% (POC_HEURISTIC)")
        return "CRITICAL", reasons
    if r["utilisation_pct"] is not None and r["utilisation_pct"] >= 100:
        reasons.append(f"Utilisation {r['utilisation_pct']}% at/over limit ({r['limit'].get('limit_type')})")
        return "CRITICAL", reasons

    # INFORMATIONAL: discovery-only signal, no exposure confirmation at all
    # (e.g. PFE/limit genuinely unavailable) - never silently promoted.
    if r["utilisation_pct"] is None and r["exposure"].get("pfe_current") is None and r["exposure"].get("nse_current") is None:
        reasons.append("No confirmed exposure metric available for this record (discovery-only signal)")
        return "INFORMATIONAL", reasons

    # LOW: relationship/event link exists but exposure is clearly
    # immaterial - "graph nominates, exposure ranks."
    pfe_current = r["exposure"].get("pfe_current") or 0
    immaterial = (pfe_current < T["immaterial_abs_pfe"]
                  and (r["utilisation_pct"] is None or r["utilisation_pct"] < T["immaterial_utilisation_pct"]))
    if immaterial:
        reasons.append(f"PFE ${pfe_current}mm and utilisation {r['utilisation_pct']}% are both immaterial "
                        f"(POC_HEURISTIC thresholds)")
        if r["event"]["id"] != "NONE":
            reasons.append(f"Event relevance ({r['event']['label']}) noted but does not override immateriality")
        return "LOW", reasons

    # HIGH: genuine new risk + high utilisation, OR significant stress move
    # + relevant event, OR unresolved material exposure with weak headroom.
    material_move = (r["delta_pfe"] is not None and abs(r["delta_pfe"]) >= T["material_delta_abs"]) or \
                     (r["delta_nse"] is not None and abs(r["delta_nse"]) >= T["material_delta_abs"])
    weak_headroom = r["utilisation_pct"] is not None and r["utilisation_pct"] >= T["high_utilisation_pct"]
    if driver in REAL_RISK_DRIVERS and (material_move or weak_headroom):
        reasons.append(f"Driver {driver} is a genuine risk signal with a material move "
                        f"(ΔPFE={r['delta_pfe']}, ΔNSE={r['delta_nse']}) or high utilisation ({r['utilisation_pct']}%)")
        if r["event"]["id"] != "NONE":
            reasons.append(f"Linked live event: {r['event']['label']}")
        return "HIGH", reasons

    # MEDIUM: material model/data-driven issue requiring routing, or
    # material exposure move without control pressure.
    if driver in ROUTED_NOT_ESCALATED_DRIVERS:
        reasons.append(f"Driver is {driver} - routed for review, not escalated as a market/credit risk signal")
        if material_move:
            reasons.append(f"Move is material in size (ΔPFE={r['delta_pfe']}, ΔNSE={r['delta_nse']}) but the "
                            f"driver explains it as non-risk")
        return "MEDIUM", reasons
    if material_move:
        reasons.append(f"Material exposure move (ΔPFE={r['delta_pfe']}, ΔNSE={r['delta_nse']}) without a "
                        f"confirmed control-pressure signal")
        return "MEDIUM", reasons

    # Everything else: real but non-material, or driver unresolved.
    reasons.append(f"Driver is {driver}; move is below HIGH/MEDIUM materiality thresholds")
    return "MEDIUM", reasons


# Plain-English translation of each raw evidence flag, for analyst-facing
# copy. Raw flag strings (e.g. "non_netted_flag=True") stay available under
# driver_evidence_trace / "Technical Evidence" for auditability, but the
# primary screen must never show a debug-looking flag name.
FLAG_TRANSLATIONS = {
    "trade_population_changed": "The underlying trade population changed.",
    "model_version_changed": "The PFE model was recalibrated.",
    "market_move_flag": "Exposure moved because the underlying market/risk factor moved.",
    "collateral_change_flag": "Collateral terms changed.",
    "netting_change_flag": "Netting terms changed.",
    "data_issue_flag": "A data quality issue was identified.",
    "new_trade_flag": "New trades were booked.",
    "matured_trade_flag": "Trades matured or were unwound.",
    "wwr_flag": "Specific wrong-way-risk treatment applies.",
    "recovery_change_flag": "The recovery-rate assumption changed.",
    "non_netted_flag": "This trade sits outside the standard netting set.",
    "replacement_cost_move_flag": "Replacement cost moved sharply on a single valuation date.",
    "volatility_update_flag": "The volatility surface/input was updated.",
    "data_sourcing_issue_flag": "A data sourcing issue was identified.",
    "model_coverage_change_flag": "Model coverage for this book changed.",
    "simulation_noise_confirmed_flag": "A confirmed simulation-noise diagnostic applies.",
}


def _risk_drivers_plain_language(enriched_record):
    flags = enriched_record.get("driver_evidence", {}) or {}
    sentences = [FLAG_TRANSLATIONS[k] for k, v in flags.items() if v is True and k in FLAG_TRANSLATIONS]
    return sentences or ["No evidence flag on file for this record."]


def _economic_exposure_paths(enriched_record):
    """A typed, human-readable economic route: counterparty -> product ->
    underlying/collateral - the mechanism a relationship can produce
    exposure through, not just a statistical association."""
    hop = [enriched_record.get("product")] if enriched_record.get("product") else []
    if enriched_record.get("reference_entity_id"):
        hop.append(enriched_record["reference_entity_id"])
    elif enriched_record.get("collateral") and enriched_record["collateral"].get("type"):
        hop.append(enriched_record["collateral"]["type"])
    if not hop:
        return []
    return [f"{enriched_record['id']} → " + " → ".join(hop)]


def _materiality_metrics(enriched_record):
    exp = enriched_record["exposure"]
    out = []
    for key, label in [("rc_current", "RC"), ("pfe_current", "PFE"),
                        ("nse_current", "NSE / Stress"), ("settlement_exposure", "Settlement Exposure")]:
        val = exp.get(key)
        out.append({"metric": label, "value": val, "status": "AVAILABLE" if val is not None else "UNAVAILABLE"})
    return out


def _control_constraints(enriched_record):
    out = []
    limit_type = enriched_record["limit"].get("limit_type")
    if limit_type:
        out.append({"constraint": f"{limit_type} utilisation", "value": enriched_record["utilisation_pct"],
                     "status": "AVAILABLE" if enriched_record["utilisation_pct"] is not None else "UNAVAILABLE"})
    else:
        out.append({"constraint": "Limit", "value": None, "status": "NOT_PROVIDED"})
    if enriched_record["is_breach"]:
        b = enriched_record["breach"]
        out.append({"constraint": "Breach", "value": f"{b['age_days']}d vs {b['sla_days']}d SLA",
                     "status": "AVAILABLE"})
    if enriched_record.get("driver_evidence", {}).get("wwr_flag"):
        out.append({"constraint": "Wrong-way risk", "value": "Flagged", "status": "AVAILABLE"})
    if enriched_record.get("watchlist"):
        out.append({"constraint": "Watchlist", "value": "Flagged", "status": "AVAILABLE"})
    return out


def build_decision(enriched_record, driver, driver_evidence, priority, reasons):
    """The common structured output object (Decision Recommendation) -
    every downstream consumer (Daily Review, Counterparty 360, Event
    Studio materiality join) reads THIS, not ad-hoc fields.

    Field names follow the DecisionContext shape (context_type, subject,
    relationship_summary, economic_exposure_paths, risk_drivers,
    materiality_metrics, control_constraints, decision, decision_reasons,
    missing_information, recommended_owner, evidence, provenance). Older
    field names (context, counterparty_id, reasons, control_flags,
    driver_evidence) are kept alongside for backward compatibility with
    existing consumers - this is additive, not a breaking rename."""
    missing = []
    if enriched_record["limit"].get("limit_type") is None:
        missing.append("limit")
    if enriched_record["exposure"].get("pfe_current") is None and enriched_record["exposure"].get("nse_current") is None \
            and enriched_record["exposure"].get("settlement_exposure") is None:
        missing.append("exposure_metric")
    if enriched_record.get("rating") is None:
        missing.append("rating")
    if not enriched_record.get("coverage_owner"):
        missing.append("coverage_owner")

    control_flags = {
        "is_breach": enriched_record["is_breach"],
        "is_overdue": enriched_record["is_overdue"],
        "wwr": bool(enriched_record.get("driver_evidence", {}).get("wwr_flag")),
        "watchlist": bool(enriched_record.get("watchlist")),
    }

    return {
        # new DecisionContext-shaped fields
        "context_type": "POST_TRADE",
        "subject": enriched_record["id"],
        "relationship_summary": enriched_record.get("risk_factor_path", []),
        "economic_exposure_paths": _economic_exposure_paths(enriched_record),
        "risk_drivers": _risk_drivers_plain_language(enriched_record),
        "materiality_metrics": _materiality_metrics(enriched_record),
        "control_constraints": _control_constraints(enriched_record),
        "decision_reasons": reasons,
        "evidence": [enriched_record.get("analyst_explanation")] if enriched_record.get("analyst_explanation") else [],
        # kept for backward compatibility with existing consumers
        "context": "POST_TRADE",
        "counterparty_id": enriched_record["id"],
        "decision": enriched_record["suggested_action"],
        "priority": priority,
        "reasons": reasons,
        "driver": driver,
        "driver_evidence": driver_evidence,
        "relationship_paths": enriched_record.get("risk_factor_path", []),
        "control_flags": control_flags,
        "missing_information": missing,
        "recommended_owner": enriched_record.get("coverage_owner"),
        "provenance": "DERIVED_DATA",
    }


def build_priority_queue():
    """Full pipeline: load synthetic CCR records -> enrich -> classify
    driver -> compute priority -> attach decision object -> sort
    CRITICAL > HIGH > MEDIUM > LOW > INFORMATIONAL (ties by |Delta PFE| desc)."""
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFORMATIONAL": 4}
    provider = get_ccr_provider()
    rows = []
    for raw in provider.get_full_records():
        enriched = enrich(raw)
        driver, evidence = classify_driver(raw)
        priority, reasons = compute_priority(enriched, driver)
        decision = build_decision(enriched, driver, evidence, priority, reasons)
        rows.append({
            **enriched,
            "driver": driver,
            "driver_evidence_trace": evidence,
            "priority": priority,
            "reasons": reasons,
            "decision": decision,
        })
    rows.sort(key=lambda r: (order[r["priority"]], -(abs(r["delta_pfe"]) if r["delta_pfe"] is not None else 0)))
    return rows
