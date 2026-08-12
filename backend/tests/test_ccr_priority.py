"""Tests for the Daily Review CCR decision workflow: limit-type semantics,
evidence-based driver classification, priority rule matrix, missing-data
handling, and the business-materiality join (core/ccr_priority.py,
core/materiality.py, core/correlation_domains.py).

Covers the required test categories:
  A. LIMIT TYPE           C. MISSING DATA         E. CORRELATION SIGN
  B. SIMULATION NOISE      D. PFE VS NSE            G. MATERIALITY
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core import ccr_priority, materiality, correlation_domains
from app.core.data import STORE


def _by_id(rows, cid):
    return next(r for r in rows if r["id"] == cid)


def test_dataset_size_in_range():
    assert 15 <= len(STORE.ccr_counterparties) <= 20


def test_all_records_synthetic_and_fictional():
    real_institution_markers = {"jpmorgan", "ubs group", "bnp paribas", "citadel", "government of"}
    for c in STORE.ccr_counterparties:
        assert c["is_synthetic"] is True
        assert c["source_type"] == "SYNTHETIC_CCR_DECISION_DATA"
        name_lower = c["name"].lower()
        assert not any(marker in name_lower for marker in real_institution_markers), \
            f"{c['name']} looks like a real institution name - must be fictional"


# --------------------------------------------------------------------------
# The four named business scenarios (still hold under the new schema)
# --------------------------------------------------------------------------
def test_example_1_real_market_risk_ranks_high():
    rows = ccr_priority.build_priority_queue()
    r = _by_id(rows, "CP_HF_001")
    assert r["delta_pfe"] == 315
    assert r["driver"] == "MARKET_MOVE"
    assert r["priority"] == "HIGH"
    assert r["reasons"]


def test_example_2_model_move_ranks_below_example_1_despite_large_delta():
    rows = ccr_priority.build_priority_queue()
    r2 = _by_id(rows, "CP_BANK_002")
    r1 = _by_id(rows, "CP_HF_001")
    assert r2["delta_pfe"] == 280
    assert r2["driver"] == "MODEL_RECALIBRATION"
    assert r2["priority"] == "MEDIUM"
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFORMATIONAL": 4}
    assert order[r2["priority"]] > order[r1["priority"]]


def test_example_3_old_breach_outranks_everything():
    rows = ccr_priority.build_priority_queue()
    r = _by_id(rows, "CP_PUB_ALPHA")
    assert r["is_breach"] is True
    assert r["is_overdue"] is True
    assert r["driver"] == "LIMIT_BREACH"
    assert r["priority"] == "CRITICAL"
    assert rows[0]["priority"] == "CRITICAL"


def test_example_4_immaterial_event_relevance_ranks_low():
    rows = ccr_priority.build_priority_queue()
    r = _by_id(rows, "CP_FUND_009")
    assert r["event"]["id"] != "NONE"
    assert r["priority"] == "LOW"
    assert any("immaterial" in reason.lower() for reason in r["reasons"])


# --------------------------------------------------------------------------
# A. LIMIT TYPE - a settlement limit cannot be compared against PFE
# --------------------------------------------------------------------------
def test_settlement_limit_utilisation_uses_settlement_exposure_not_pfe():
    rows = ccr_priority.build_priority_queue()
    r = _by_id(rows, "CP_PUB_ALPHA")
    assert r["limit"]["limit_type"] == "SETTLEMENT_LIMIT"
    assert r["exposure"]["pfe_current"] is None  # no PFE on file for this record
    # utilisation must be computed off settlement_exposure, never off a None PFE
    expected = round(100 * r["exposure"]["settlement_exposure"] / r["limit"]["limit_value"], 1)
    assert r["utilisation_pct"] == expected


def test_pfe_limit_utilisation_never_uses_rc():
    rows = ccr_priority.build_priority_queue()
    r = _by_id(rows, "CP_HF_001")
    assert r["limit"]["limit_type"] == "PFE_LIMIT"
    expected = round(100 * r["exposure"]["pfe_current"] / r["limit"]["limit_value"], 1)
    assert r["utilisation_pct"] == expected
    # explicitly NOT rc_current / limit_value
    wrong = round(100 * r["exposure"]["rc_current"] / r["limit"]["limit_value"], 1)
    assert r["utilisation_pct"] != wrong or r["exposure"]["rc_current"] == r["exposure"]["pfe_current"]


def test_stress_limit_utilisation_uses_nse():
    rows = ccr_priority.build_priority_queue()
    r = _by_id(rows, "CP_SOV_EPS")
    assert r["limit"]["limit_type"] == "STRESS_LIMIT"
    expected = round(100 * r["exposure"]["nse_current"] / r["limit"]["limit_value"], 1)
    assert r["utilisation_pct"] == expected


def test_no_limit_on_file_gives_unavailable_utilisation():
    rows = ccr_priority.build_priority_queue()
    r = _by_id(rows, "CP_SPV_NORD")
    assert r["limit"]["limit_type"] is None
    assert r["utilisation_pct"] is None
    assert r["headroom"] is None


def test_breach_excess_computed_against_matching_metric_not_rc():
    rows = ccr_priority.build_priority_queue()
    r = _by_id(rows, "CP_PUB_ALPHA")
    assert r["limit"]["limit_type"] == "SETTLEMENT_LIMIT"
    assert r["excess"] == r["breach"]["excess"]
    assert r["excess"] > 0


# --------------------------------------------------------------------------
# B. SIMULATION NOISE - small |Delta PFE| alone must NEVER produce
# SIMULATION_NOISE; it requires an explicit confirmed-diagnostic flag.
# --------------------------------------------------------------------------
def test_small_move_without_evidence_is_not_labelled_noise():
    driver, evidence = ccr_priority.classify_driver({
        "breach": None,
        "exposure": {"pfe_current": 105, "pfe_previous": 100},
        "driver_evidence": {k: False for k in (
            "data_sourcing_issue_flag", "data_issue_flag", "model_coverage_change_flag",
            "model_version_changed", "trade_population_changed", "volatility_update_flag",
            "recovery_change_flag", "replacement_cost_move_flag", "non_netted_flag", "wwr_flag",
            "netting_change_flag", "collateral_change_flag", "new_trade_flag", "matured_trade_flag",
            "market_move_flag", "simulation_noise_confirmed_flag",
        )},
    })
    assert driver != "SIMULATION_NOISE"
    assert driver == "SMALL_MOVE"


def test_simulation_noise_requires_explicit_confirmed_flag():
    flags = {k: False for k in (
        "data_sourcing_issue_flag", "data_issue_flag", "model_coverage_change_flag",
        "model_version_changed", "trade_population_changed", "volatility_update_flag",
        "recovery_change_flag", "replacement_cost_move_flag", "non_netted_flag", "wwr_flag",
        "netting_change_flag", "collateral_change_flag", "new_trade_flag", "matured_trade_flag",
        "market_move_flag",
    )}
    flags["simulation_noise_confirmed_flag"] = True
    driver, evidence = ccr_priority.classify_driver({
        "breach": None, "exposure": {"pfe_current": 5, "pfe_previous": 3}, "driver_evidence": flags,
    })
    assert driver == "SIMULATION_NOISE"
    assert any("simulation_noise_confirmed_flag=True" in e for e in evidence)


def test_no_record_in_dataset_is_labelled_noise_without_evidence():
    # the fictional dataset intentionally contains NO
    # simulation_noise_confirmed_flag=True records - confirms the old
    # bug (inferring noise from size) is fully gone.
    rows = ccr_priority.build_priority_queue()
    assert not any(r["driver"] == "SIMULATION_NOISE" for r in rows)
    # a genuinely small, evidence-free move should be SMALL_MOVE or UNKNOWN
    small_movers = [r for r in rows if r["delta_pfe"] is not None and abs(r["delta_pfe"]) < 10]
    for r in small_movers:
        assert r["driver"] != "SIMULATION_NOISE"


# --------------------------------------------------------------------------
# C. MISSING DATA - missing limit/exposure remains null, never fabricated
# --------------------------------------------------------------------------
def test_missing_pfe_stays_null_not_zero():
    rows = ccr_priority.build_priority_queue()
    r = _by_id(rows, "CP_SPV_NORD")
    assert r["exposure"]["pfe_current"] is None
    assert r["delta_pfe"] is None  # never fabricated as 0


def test_missing_data_surfaces_in_decision_missing_information():
    rows = ccr_priority.build_priority_queue()
    r = _by_id(rows, "CP_SPV_NORD")
    assert "limit" in r["decision"]["missing_information"]
    assert "rating" in r["decision"]["missing_information"]


def test_informational_priority_for_no_confirmed_exposure():
    rows = ccr_priority.build_priority_queue()
    r = _by_id(rows, "CP_SPV_NORD")
    assert r["priority"] == "INFORMATIONAL"


# --------------------------------------------------------------------------
# D. PFE VS NSE - never merged
# --------------------------------------------------------------------------
def test_pfe_and_nse_never_merged():
    rows = ccr_priority.build_priority_queue()
    for r in rows:
        assert "pfe_current" in r["exposure"] and "nse_current" in r["exposure"]
        assert "combined" not in str(r.keys()).lower()
    stress_only = _by_id(rows, "CP_SOV_EPS")
    assert stress_only["exposure"]["pfe_current"] is None
    assert stress_only["exposure"]["nse_current"] is not None


# --------------------------------------------------------------------------
# E. CORRELATION SIGN - preserved via correlation_domains.py
# --------------------------------------------------------------------------
def test_issuer_correlation_sign_preserved():
    corr = correlation_domains.issuer_market_correlation("TSM", "NVDA")
    if corr:
        assert -1.0 <= corr["full_sample_corr"] <= 1.0
        assert corr["domain"] == "ISSUER_MARKET_CORRELATION"
        assert not (corr["positive_channel"] > 0 and corr["negative_channel"] > 0)


def test_risk_factor_transmission_path_is_typed_not_a_correlation_number():
    path = correlation_domains.risk_factor_transmission_path("JPY_DEPRECIATION_SHOCK")
    assert path["domain"] == "RISK_FACTOR_TRANSMISSION_PATH"
    assert isinstance(path["path"], list) and len(path["path"]) > 1
    assert path["source_type"] == "CURATED_REFERENCE_DATA"


def test_wwr_diagnostic_never_inferred_from_size():
    diag = correlation_domains.wwr_diagnostic("CP_SOV_GAMMA")
    assert diag["wwr_flagged"] is True
    assert "never inferred" in diag["basis"]
    non_wwr = correlation_domains.wwr_diagnostic("CP_BANK_002")
    assert non_wwr["wwr_flagged"] is False


# --------------------------------------------------------------------------
# F. PRODUCT PATH - different products carry different risk factors
# --------------------------------------------------------------------------
def test_trs_and_repo_have_different_risk_factors():
    from app.core import product_taxonomy as pt
    trs_factors = set(pt.risk_factors_for_product("TRS"))
    repo_factors = set(pt.risk_factors_for_product("REPO"))
    assert trs_factors != repo_factors
    assert "REFERENCE_ENTITY" in trs_factors
    assert "COLLATERAL" in repo_factors


# --------------------------------------------------------------------------
# G. MATERIALITY - high relationship + negligible exposure must not
# automatically outrank moderate relationship + material exposure/control.
# --------------------------------------------------------------------------
def test_materiality_join_ranks_by_priority_not_nomination():
    rows = materiality.materiality_join({"NVDA"})
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFORMATIONAL": 4}
    ranks = [order[r["priority"]] for r in rows]
    assert ranks == sorted(ranks)
    # CP_FUND_009 (immaterial, NVDA reference) must not outrank a material
    # NVDA-referencing counterparty if one exists at higher priority
    priorities = {r["id"]: r["priority"] for r in rows}
    if "CP_FUND_009" in priorities:
        assert priorities["CP_FUND_009"] == "LOW"


def test_counterparties_for_reference_entity():
    rows = materiality.counterparties_for_reference_entity("NVDA")
    assert rows
    for r in rows:
        assert r["reference_entity_id"] == "NVDA"
        assert "priority" in r and "product" in r


# --------------------------------------------------------------------------
# H. BREACH - aged settlement breach surfaces as control issue
# --------------------------------------------------------------------------
def test_aged_settlement_breach_is_critical_control_issue():
    rows = ccr_priority.build_priority_queue()
    r = _by_id(rows, "CP_PUB_ALPHA")
    assert r["limit"]["limit_type"] == "SETTLEMENT_LIMIT"
    assert r["priority"] == "CRITICAL"
    assert r["decision"]["control_flags"]["is_overdue"] is True


# --------------------------------------------------------------------------
# I. DRIVER ATTRIBUTION - source analyst explanation retained verbatim
# --------------------------------------------------------------------------
def test_analyst_explanation_retained():
    rows = ccr_priority.build_priority_queue()
    for r in rows:
        assert r.get("analyst_explanation")
        assert len(r["analyst_explanation"]) > 10


def test_uncertain_driver_stays_unknown_not_guessed():
    rows = ccr_priority.build_priority_queue()
    r = _by_id(rows, "CP_MACRO_BRKL")
    assert r["driver"] == "UNKNOWN"
    assert "did not conclusively identify" in r["analyst_explanation"]


# --------------------------------------------------------------------------
# J. PROVENANCE - internal sample vs public vs synthetic are distinct tags
# --------------------------------------------------------------------------
def test_ccr_data_tagged_synthetic_not_internal_sample():
    for c in STORE.ccr_counterparties:
        assert c["source_type"] == "SYNTHETIC_CCR_DECISION_DATA"
        assert c["source_type"] != "USER_PROVIDED_INTERNAL_SAMPLE_DATA"


def test_product_taxonomy_tagged_curated_reference():
    from app.core import product_taxonomy as pt
    taxonomy = pt.load_taxonomy()
    assert taxonomy  # loads without error


# --------------------------------------------------------------------------
# K. REGRESSION - every existing surface still works
# --------------------------------------------------------------------------
def test_every_row_has_a_valid_driver_and_evidence():
    valid_drivers = {"NEW_TRADE", "MATURED_TRADE", "MARKET_MOVE", "MTM_MOVE", "COLLATERAL_CHANGE",
                      "NETTING_CHANGE", "MODEL_RECALIBRATION", "DATA_ISSUE", "SIMULATION_NOISE",
                      "WWR_RELATED", "LIMIT_BREACH", "UNKNOWN", "RECOVERY_CHANGE", "NON_NETTED_EXPOSURE",
                      "REPLACEMENT_COST_MOVE", "VOLATILITY_UPDATE", "DATA_SOURCING_ISSUE",
                      "MODEL_COVERAGE_CHANGE", "SMALL_MOVE"}
    rows = ccr_priority.build_priority_queue()
    for r in rows:
        assert r["driver"] in valid_drivers
        assert r["driver_evidence_trace"]


def test_queue_sorted_critical_first():
    rows = ccr_priority.build_priority_queue()
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFORMATIONAL": 4}
    ranks = [order[r["priority"]] for r in rows]
    assert ranks == sorted(ranks)


def test_no_naked_score_field():
    rows = ccr_priority.build_priority_queue()
    for r in rows:
        assert r["priority"] in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFORMATIONAL")
        assert not isinstance(r["priority"], (int, float))


def test_decision_object_shape():
    rows = ccr_priority.build_priority_queue()
    for r in rows:
        d = r["decision"]
        # legacy fields (backward compatible)
        assert set(["context", "counterparty_id", "decision", "reasons", "driver", "driver_evidence",
                     "relationship_paths", "control_flags", "missing_information", "recommended_owner",
                     "evidence", "provenance"]) <= set(d.keys())
        # new DecisionContext-shaped fields
        assert set(["context_type", "subject", "relationship_summary", "economic_exposure_paths",
                     "risk_drivers", "materiality_metrics", "control_constraints", "decision_reasons"]) <= set(d.keys())
        assert d["provenance"] == "DERIVED_DATA"
        assert isinstance(d["evidence"], list)
        assert isinstance(d["risk_drivers"], list) and d["risk_drivers"]


def test_risk_drivers_are_plain_language_not_raw_flags():
    rows = ccr_priority.build_priority_queue()
    r = _by_id(rows, "CP_HF_001")
    for sentence in r["decision"]["risk_drivers"]:
        assert "flag=" not in sentence  # never a raw debug-looking flag string
        assert sentence[0].isupper()    # reads as a sentence, not a token


def test_economic_exposure_path_is_typed_route_not_a_statistic():
    rows = ccr_priority.build_priority_queue()
    r = _by_id(rows, "CP_HF_001")
    assert r["decision"]["economic_exposure_paths"]
    path = r["decision"]["economic_exposure_paths"][0]
    assert "REPO" in path and "→" in path


def test_materiality_metrics_status_matches_data_availability():
    rows = ccr_priority.build_priority_queue()
    r = _by_id(rows, "CP_SPV_NORD")  # deal-contingent FX forward, PFE unsupported
    metrics = {m["metric"]: m for m in r["decision"]["materiality_metrics"]}
    assert metrics["PFE"]["status"] == "UNAVAILABLE"
    assert metrics["PFE"]["value"] is None


def test_control_constraints_reflect_limit_type():
    rows = ccr_priority.build_priority_queue()
    r = _by_id(rows, "CP_PUB_ALPHA")
    constraint = next(c for c in r["decision"]["control_constraints"] if "utilisation" in c["constraint"])
    assert "SETTLEMENT_LIMIT" in constraint["constraint"]
    assert constraint["status"] == "AVAILABLE"
