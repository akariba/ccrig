"""CCR (Counterparty Credit Risk) decision-data builder — v2.

Assembles the SYNTHETIC daily-review dataset used by the DISCOVER -> UNDERSTAND
-> MEASURE -> STRESS -> CONTROL -> DECIDE workflow. Every counterparty here is
FICTIONAL. Records mirror realistic CCR scenario SHAPES (a repo-driven PFE
jump, a recovery-rate-driven stress move, a non-netted triparty collateral
increase, a settlement breach, an equity-delta swing from index futures,
etc.) but no real institution, government, or confidential position is
represented anywhere in this file.

Each record carries an explicit `limit` object with a `limit_type`
(PFE_LIMIT / SETTLEMENT_LIMIT / STRESS_LIMIT / None) - utilisation is ONLY
ever computed against the metric that matches that type (core/ccr_priority.py
enforces this; never RC-vs-arbitrary-limit, never PFE-vs-a-settlement-limit).

Missing fields are `null`, never fabricated - many records intentionally
leave rating/sensitivities/limit unset to mirror real analyst workflows
where not every field is available at read time.

Run:
    python backend/scripts/build_ccr_dataset.py

Outputs (backend/data/):
    ccr_counterparties.json  - synthetic CCR exposure/breach/sensitivity snapshots
    ccr_events.json          - synthetic macro/market event catalog
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")

# ---------------------------------------------------------------------------
# Synthetic macro/market events referenced by ccr_counterparties[].linked_event_id
# ---------------------------------------------------------------------------
CCR_EVENTS = [
    dict(id="JPY_DEPRECIATION_SHOCK", label="JPY depreciation / rates shock",
         description="Synthetic scenario: sharp JPY depreciation/intervention drives Japanese rates higher, "
                      "pressuring UST yields via prospective Treasury selling, transmitting into repo/basis "
                      "financing markets used by leveraged funds.",
         risk_factor_path=["JPY", "JAPAN_RATES", "UST_YIELD", "REPO_MARKET", "TREASURY_BASIS"],
         is_synthetic=True),
    dict(id="CREDIT_SPREAD_WIDENING", label="Credit spread widening",
         description="Synthetic scenario: broad IG/HY credit spread widening affecting CDS and bond-financing books.",
         risk_factor_path=["CREDIT_SPREAD", "BOND_FINANCING", "REPO_MARKET"],
         is_synthetic=True),
    dict(id="EQUITY_VOL_SPIKE", label="Equity volatility spike",
         description="Synthetic scenario: broad equity vol spike affecting TRS/options-heavy and index-future books.",
         risk_factor_path=["EQUITY_VOL", "EQUITY_INDEX", "MARGIN_CALLS"],
         is_synthetic=True),
    dict(id="NONE", label="No linked event",
         description="No live event nominated this counterparty.", risk_factor_path=[], is_synthetic=True),
]

# ---------------------------------------------------------------------------
# Synthetic CCR counterparties. Every counterparty/legal-entity name below is
# FICTIONAL. driver_evidence flags are the ONLY inputs the deterministic
# driver classifier may use - never an AI guess, never inferred from the
# size of a move alone.
# ---------------------------------------------------------------------------
CCR_COUNTERPARTIES = [
    # 1. Real market-driven risk (JPY shock transmission) -> HIGH
    dict(id="CP_HF_001", name="Meridian Alpha Rates Fund", legal_entity="Meridian Alpha Rates Fund (Cayman) Ltd",
         counterparty_type="Hedge Fund", rating=None, watchlist=False, reference_entity_id=None,
         product="REPO", netting_set="NS-RATES-01", collateral={"type": "UST / Cash VM", "csa": True, "haircut": 0.02},
         notional=None, direction=None, unmatched_trades=False,
         exposure=dict(rc_previous=180, rc_current=210, pfe_previous=500, pfe_current=815,
                        nse_previous=520, nse_current=700, settlement_exposure=None),
         sensitivities=dict(equity_delta_previous=None, equity_delta_current=None, fx_delta=None, dv01=-42.0, cs01=None),
         limit=dict(limit_id="LIM-HF001-PFE", limit_type="PFE_LIMIT", limit_value=1000, currency="USD",
                     as_of_date="2026-08-01", source="POC_HEURISTIC"),
         breach=None,
         driver_evidence=dict(trade_population_changed=True, model_version_changed=False, market_move_flag=True,
                               collateral_change_flag=False, netting_change_flag=False, data_issue_flag=False,
                               new_trade_flag=False, matured_trade_flag=False, wwr_flag=False,
                               recovery_change_flag=False, non_netted_flag=False, replacement_cost_move_flag=False,
                               volatility_update_flag=False, data_sourcing_issue_flag=False,
                               model_coverage_change_flag=False, simulation_noise_confirmed_flag=False),
         analyst_explanation="Repo/IRS book revalued materially on UST yield moves following the JPY shock; "
                              "trade population changed intraweek but the primary driver is the market move itself.",
         risk_factor_path=["JPY", "JAPAN_RATES", "UST_YIELD", "REPO_MARKET"],
         linked_event_id="JPY_DEPRECIATION_SHOCK", coverage_owner="J. Ferris", suggested_action="INVESTIGATE"),

    # 2. Model recalibration, large Delta PFE but ranks below #1 -> MEDIUM
    dict(id="CP_BANK_002", name="Cascade Regional Bank Treasury", legal_entity="Cascade Regional Bank Treasury NA",
         counterparty_type="Bank Treasury", rating=None, watchlist=False, reference_entity_id=None,
         product="IRS", netting_set="NS-RATES-02", collateral={"type": "Cash VM", "csa": True, "haircut": 0.0},
         notional=None, direction=None, unmatched_trades=False,
         exposure=dict(rc_previous=120, rc_current=140, pfe_previous=340, pfe_current=620,
                        nse_previous=310, nse_current=340, settlement_exposure=None),
         sensitivities=dict(equity_delta_previous=None, equity_delta_current=None, fx_delta=None, dv01=-18.5, cs01=None),
         limit=dict(limit_id="LIM-BANK002-PFE", limit_type="PFE_LIMIT", limit_value=1200, currency="USD",
                     as_of_date="2026-08-01", source="POC_HEURISTIC"),
         breach=None,
         driver_evidence=dict(trade_population_changed=False, model_version_changed=True, market_move_flag=False,
                               collateral_change_flag=False, netting_change_flag=False, data_issue_flag=False,
                               new_trade_flag=False, matured_trade_flag=False, wwr_flag=False,
                               recovery_change_flag=False, non_netted_flag=False, replacement_cost_move_flag=False,
                               volatility_update_flag=False, data_sourcing_issue_flag=False,
                               model_coverage_change_flag=False, simulation_noise_confirmed_flag=False),
         analyst_explanation="PFE model was recalibrated overnight (volatility surface refresh); trade population "
                              "is unchanged from the prior run, so the move is entirely model-driven.",
         risk_factor_path=[],
         linked_event_id="NONE", coverage_owner="M. Oduya", suggested_action="ROUTE_TO_MODEL_TEAM"),

    # 3. Old settlement breach, governance risk outranks PFE size -> CRITICAL
    #    (mirrors: overdue settlement-limit breach, root cause pending)
    dict(id="CP_PUB_ALPHA", name="Sovereign Debt Office — Nation Alpha", legal_entity="Nation Alpha Treasury Settlement Desk",
         counterparty_type="Sovereign", rating=None, watchlist=True, reference_entity_id=None,
         product="BOND", netting_set="NS-SETTLE-01", collateral=None,
         notional=None, direction=None, unmatched_trades=None,
         exposure=dict(rc_previous=None, rc_current=None, pfe_previous=None, pfe_current=None,
                        nse_previous=None, nse_current=None, settlement_exposure=181),
         sensitivities=dict(equity_delta_previous=None, equity_delta_current=None, fx_delta=None, dv01=None, cs01=None),
         limit=dict(limit_id="LIM-PUBALPHA-SETTLE", limit_type="SETTLEMENT_LIMIT", limit_value=140, currency="USD",
                     as_of_date="2026-08-01", source="POC_HEURISTIC"),
         breach=dict(is_breach=True, age_days=141, sla_days=20, excess=41, root_cause="UNKNOWN_PENDING_INVESTIGATION"),
         driver_evidence=dict(trade_population_changed=False, model_version_changed=False, market_move_flag=False,
                               collateral_change_flag=False, netting_change_flag=False, data_issue_flag=False,
                               new_trade_flag=False, matured_trade_flag=False, wwr_flag=False,
                               recovery_change_flag=False, non_netted_flag=False, replacement_cost_move_flag=False,
                               volatility_update_flag=False, data_sourcing_issue_flag=False,
                               model_coverage_change_flag=False, simulation_noise_confirmed_flag=False),
         analyst_explanation="Settlement-limit breach, 141 business days overdue against a 20-day SLA. Root cause "
                              "was still under investigation as of the last coverage review; no owner assigned.",
         risk_factor_path=[],
         linked_event_id="NONE", coverage_owner=None, suggested_action="ASSIGN_OWNER_AND_ESCALATE"),

    # 4. High event relevance, immaterial exposure -> LOW ("graph nominates, exposure ranks")
    dict(id="CP_FUND_009", name="Kestrel Family Office", legal_entity="Kestrel Family Office LLC",
         counterparty_type="Family Office", rating=None, watchlist=False, reference_entity_id="NVDA",
         product="TRS", netting_set="NS-EQ-11", collateral={"type": "Cash VM", "csa": True, "haircut": 0.0},
         notional=15, direction="RECEIVE_EQUITY", unmatched_trades=False,
         exposure=dict(rc_previous=2, rc_current=2, pfe_previous=8, pfe_current=9,
                        nse_previous=6, nse_current=7, settlement_exposure=None),
         sensitivities=dict(equity_delta_previous=6, equity_delta_current=7, fx_delta=None, dv01=None, cs01=None),
         limit=dict(limit_id="LIM-FUND009-PFE", limit_type="PFE_LIMIT", limit_value=300, currency="USD",
                     as_of_date="2026-08-01", source="POC_HEURISTIC"),
         breach=None,
         driver_evidence=dict(trade_population_changed=False, model_version_changed=False, market_move_flag=True,
                               collateral_change_flag=False, netting_change_flag=False, data_issue_flag=False,
                               new_trade_flag=False, matured_trade_flag=False, wwr_flag=False,
                               recovery_change_flag=False, non_netted_flag=False, replacement_cost_move_flag=False,
                               volatility_update_flag=False, data_sourcing_issue_flag=False,
                               model_coverage_change_flag=False, simulation_noise_confirmed_flag=False),
         analyst_explanation="Small single-name TRS on a nominated issuer; the equity-vol event is relevant to the "
                              "reference name but this counterparty's exposure to it is immaterial.",
         risk_factor_path=["EQUITY_VOL"],
         linked_event_id="EQUITY_VOL_SPIKE", coverage_owner="R. Delacroix", suggested_action="MONITOR"),

    # 5. New equity-coupon trades + specific WWR, unmatched trades (mirrors a real-desk PFE-jump shape)
    dict(id="CP_FUND_ECR", name="Meridian Structured Equity Fund", legal_entity="Meridian Structured Equity Fund LP",
         counterparty_type="Hedge Fund", rating=None, watchlist=False, reference_entity_id=None,
         product="TRS", netting_set="NS-EQ-CPN-01", collateral={"type": "Cash VM", "csa": True, "haircut": 0.0},
         notional=192, direction="PAY_EQUITY_RECEIVE_FUNDING", unmatched_trades=True,
         exposure=dict(rc_previous=140, rc_current=175, pfe_previous=410, pfe_current=630,
                        nse_previous=None, nse_current=None, settlement_exposure=None),
         sensitivities=dict(equity_delta_previous=None, equity_delta_current=None, fx_delta=None, dv01=None, cs01=None),
         limit=dict(limit_id="LIM-FUNDECR-PFE", limit_type="PFE_LIMIT", limit_value=900, currency="USD",
                     as_of_date="2026-08-01", source="POC_HEURISTIC"),
         breach=None,
         driver_evidence=dict(trade_population_changed=True, model_version_changed=False, market_move_flag=False,
                               collateral_change_flag=False, netting_change_flag=False, data_issue_flag=False,
                               new_trade_flag=True, matured_trade_flag=False, wwr_flag=True,
                               recovery_change_flag=False, non_netted_flag=False, replacement_cost_move_flag=False,
                               volatility_update_flag=False, data_sourcing_issue_flag=False,
                               model_coverage_change_flag=False, simulation_noise_confirmed_flag=False),
         analyst_explanation="Newly booked equity-coupon TRS trades under specific wrong-way-risk treatment; "
                              "a subset of trades are still unmatched with the counterparty's own records.",
         risk_factor_path=["EQUITY"],
         linked_event_id="NONE", coverage_owner="J. Ferris", suggested_action="INVESTIGATE"),

    # 6. Deal-contingent FX forward, PFE unsupported -> demonstrates missing-data handling
    dict(id="CP_SPV_NORD", name="Nordkap Holdings SPV", legal_entity="Nordkap Holdings Special Purpose Vehicle",
         counterparty_type="SPV", rating=None, watchlist=False, reference_entity_id=None,
         product="FX_FORWARD", netting_set="NS-FX-DC-01", collateral=None,
         notional=600, direction="RECEIVE_EUR_PAY_USD", unmatched_trades=False,
         exposure=dict(rc_previous=None, rc_current=None, pfe_previous=None, pfe_current=None,
                        nse_previous=None, nse_current=None, settlement_exposure=None),
         sensitivities=dict(equity_delta_previous=None, equity_delta_current=None, fx_delta=600, dv01=None, cs01=None),
         limit=dict(limit_id=None, limit_type=None, limit_value=None, currency="USD",
                     as_of_date=None, source=None),
         breach=None,
         driver_evidence=dict(trade_population_changed=None, model_version_changed=None, market_move_flag=None,
                               collateral_change_flag=None, netting_change_flag=None, data_issue_flag=None,
                               new_trade_flag=None, matured_trade_flag=None, wwr_flag=None,
                               recovery_change_flag=None, non_netted_flag=None, replacement_cost_move_flag=None,
                               volatility_update_flag=None, data_sourcing_issue_flag=None,
                               model_coverage_change_flag=None, simulation_noise_confirmed_flag=None),
         analyst_explanation="Deal-contingent FX forward, Citi-equivalent leg receives EUR / pays USD. PFE is not "
                              "supported for this deal-contingent structure at this valuation date - left null, "
                              "not estimated.",
         risk_factor_path=["FX"],
         linked_event_id="NONE", coverage_owner="M. Oduya", suggested_action="MONITOR"),

    # 7. New triparty repo trades, add-on/payable securities (repo/collateral shape)
    dict(id="CP_FUND_SAKR", name="Sakura Triparty Funding Ltd", legal_entity="Sakura Triparty Funding Ltd",
         counterparty_type="Asset Manager", rating=None, watchlist=False, reference_entity_id=None,
         product="REPO", netting_set="NS-REPO-TRI-01", collateral={"type": "JGB-equivalent Govt Bond", "csa": True, "haircut": 0.03},
         notional=None, direction=None, unmatched_trades=False,
         exposure=dict(rc_previous=60, rc_current=95, pfe_previous=220, pfe_current=330,
                        nse_previous=None, nse_current=None, settlement_exposure=None),
         sensitivities=dict(equity_delta_previous=None, equity_delta_current=None, fx_delta=None, dv01=-8.0, cs01=None),
         limit=dict(limit_id="LIM-SAKR-PFE", limit_type="PFE_LIMIT", limit_value=500, currency="USD",
                     as_of_date="2026-08-01", source="POC_HEURISTIC"),
         breach=None,
         driver_evidence=dict(trade_population_changed=True, model_version_changed=False, market_move_flag=False,
                               collateral_change_flag=False, netting_change_flag=False, data_issue_flag=False,
                               new_trade_flag=True, matured_trade_flag=False, wwr_flag=False,
                               recovery_change_flag=False, non_netted_flag=False, replacement_cost_move_flag=False,
                               volatility_update_flag=False, data_sourcing_issue_flag=False,
                               model_coverage_change_flag=False, simulation_noise_confirmed_flag=False),
         analyst_explanation="Add-on/payable-securities driven PFE increase from newly booked triparty repo trades.",
         risk_factor_path=["INTEREST_RATE"],
         linked_event_id="NONE", coverage_owner="J. Ferris", suggested_action="MONITOR"),

    # 8. Replacement-cost-driven move that later returned to zero (FI cash shape)
    dict(id="CP_AM_HALC", name="Halcyon Fixed Income AM", legal_entity="Halcyon Fixed Income Asset Management LLC",
         counterparty_type="Asset Manager", rating=None, watchlist=False, reference_entity_id=None,
         product="BOND", netting_set="NS-FI-CASH-02", collateral=None,
         notional=6, direction=None, unmatched_trades=False,
         exposure=dict(rc_previous=1, rc_current=226, pfe_previous=2, pfe_current=225,
                        nse_previous=None, nse_current=None, settlement_exposure=None),
         sensitivities=dict(equity_delta_previous=None, equity_delta_current=None, fx_delta=None, dv01=None, cs01=None),
         limit=dict(limit_id="LIM-HALC-PFE", limit_type="PFE_LIMIT", limit_value=400, currency="USD",
                     as_of_date="2026-08-01", source="POC_HEURISTIC"),
         breach=None,
         driver_evidence=dict(trade_population_changed=False, model_version_changed=False, market_move_flag=False,
                               collateral_change_flag=False, netting_change_flag=False, data_issue_flag=False,
                               new_trade_flag=False, matured_trade_flag=False, wwr_flag=False,
                               recovery_change_flag=False, non_netted_flag=False, replacement_cost_move_flag=True,
                               volatility_update_flag=False, data_sourcing_issue_flag=False,
                               model_coverage_change_flag=False, simulation_noise_confirmed_flag=False),
         analyst_explanation="Small-notional FI cash trade whose replacement cost spiked on a single valuation date "
                              "(RC ~226 vs. ~6 notional) then returned to zero on the next calculation date - "
                              "consistent with a transient RC/settlement-timing artifact, not a real exposure trend.",
         risk_factor_path=["INTEREST_RATE"],
         linked_event_id="NONE", coverage_owner="M. Oduya", suggested_action="MONITOR"),

    # 9. Sovereign bond PFE move, cause genuinely inconclusive -> UNKNOWN (not guessed)
    dict(id="CP_MACRO_BRKL", name="Brookline Macro Partners", legal_entity="Brookline Macro Partners LP",
         counterparty_type="Hedge Fund", rating=None, watchlist=False, reference_entity_id=None,
         product="BOND", netting_set="NS-FI-CASH-03", collateral=None,
         notional=None, direction=None, unmatched_trades=None,
         exposure=dict(rc_previous=70, rc_current=90, pfe_previous=140, pfe_current=248,
                        nse_previous=None, nse_current=None, settlement_exposure=None),
         sensitivities=dict(equity_delta_previous=None, equity_delta_current=None, fx_delta=None, dv01=None, cs01=None),
         limit=dict(limit_id="LIM-BRKL-PFE", limit_type="PFE_LIMIT", limit_value=600, currency="USD",
                     as_of_date="2026-08-01", source="POC_HEURISTIC"),
         breach=None,
         driver_evidence=dict(trade_population_changed=None, model_version_changed=None, market_move_flag=None,
                               collateral_change_flag=None, netting_change_flag=None, data_issue_flag=None,
                               new_trade_flag=None, matured_trade_flag=None, wwr_flag=None,
                               recovery_change_flag=None, non_netted_flag=None, replacement_cost_move_flag=None,
                               volatility_update_flag=None, data_sourcing_issue_flag=None,
                               model_coverage_change_flag=None, simulation_noise_confirmed_flag=None),
         analyst_explanation="Sovereign-bond FI cash book PFE increase; the coverage note at review time did not "
                              "conclusively identify a single driver. Left as UNKNOWN rather than guessed.",
         risk_factor_path=["INTEREST_RATE"],
         linked_event_id="NONE", coverage_owner="R. Delacroix", suggested_action="INVESTIGATE"),

    # 10. Non-netted triparty repo collateral increase (sovereign repo shape)
    dict(id="CP_SOV_BETA", name="Sovereign Debt Office — Nation Beta", legal_entity="Nation Beta Debt Management Office",
         counterparty_type="Sovereign", rating=None, watchlist=False, reference_entity_id=None,
         product="REPO", netting_set=None, collateral={"type": "Govt Bill / Bond (non-netted)", "csa": False, "haircut": 0.01},
         notional=None, direction=None, unmatched_trades=False,
         exposure=dict(rc_previous=400, rc_current=700, pfe_previous=650, pfe_current=1550,
                        nse_previous=None, nse_current=None, settlement_exposure=None),
         sensitivities=dict(equity_delta_previous=None, equity_delta_current=None, fx_delta=None, dv01=-60.0, cs01=None),
         limit=dict(limit_id="LIM-SOVBETA-PFE", limit_type="PFE_LIMIT", limit_value=2000, currency="USD",
                     as_of_date="2026-08-01", source="POC_HEURISTIC"),
         breach=None,
         driver_evidence=dict(trade_population_changed=True, model_version_changed=False, market_move_flag=False,
                               collateral_change_flag=False, netting_change_flag=False, data_issue_flag=False,
                               new_trade_flag=False, matured_trade_flag=False, wwr_flag=False,
                               recovery_change_flag=False, non_netted_flag=True, replacement_cost_move_flag=False,
                               volatility_update_flag=False, data_sourcing_issue_flag=False,
                               model_coverage_change_flag=False, simulation_noise_confirmed_flag=False),
         analyst_explanation="Triparty repo collateral booked outside the standard netting set (non-netted trade "
                              "structure) drives the PFE increase - this is a trade-structure/netting-eligibility "
                              "issue, not a netting-terms CHANGE, so it is classified separately from NETTING_CHANGE.",
         risk_factor_path=["INTEREST_RATE", "COLLATERAL"],
         linked_event_id="NONE", coverage_owner="J. Ferris", suggested_action="REVIEW_NETTING"),

    # 11. Specific WWR add-on, securities lending (sovereign sec-lending shape)
    dict(id="CP_SOV_GAMMA", name="Sovereign Debt Office — Nation Gamma", legal_entity="Nation Gamma Debt Management Office",
         counterparty_type="Sovereign", rating=None, watchlist=False, reference_entity_id=None,
         product="SEC_LENDING", netting_set="NS-SECLEND-01", collateral={"type": "Govt Bond", "csa": True, "haircut": 0.02},
         notional=None, direction=None, unmatched_trades=False,
         exposure=dict(rc_previous=250, rc_current=400, pfe_previous=520, pfe_current=1220,
                        nse_previous=None, nse_current=None, settlement_exposure=None),
         sensitivities=dict(equity_delta_previous=None, equity_delta_current=None, fx_delta=None, dv01=None, cs01=None),
         limit=dict(limit_id="LIM-SOVGAMMA-PFE", limit_type="PFE_LIMIT", limit_value=1600, currency="USD",
                     as_of_date="2026-08-01", source="POC_HEURISTIC"),
         breach=None,
         driver_evidence=dict(trade_population_changed=False, model_version_changed=False, market_move_flag=False,
                               collateral_change_flag=False, netting_change_flag=False, data_issue_flag=False,
                               new_trade_flag=False, matured_trade_flag=False, wwr_flag=True,
                               recovery_change_flag=False, non_netted_flag=False, replacement_cost_move_flag=False,
                               volatility_update_flag=False, data_sourcing_issue_flag=False,
                               model_coverage_change_flag=False, simulation_noise_confirmed_flag=False),
         analyst_explanation="Specific wrong-way-risk add-on applied to the securities-lending book against "
                              "government-bond collateral.",
         risk_factor_path=["INTEREST_RATE", "COLLATERAL"],
         linked_event_id="NONE", coverage_owner="M. Oduya", suggested_action="REVIEW_WWR"),

    # 12. New specific-WWR reverse-repo trades (sovereign reverse-repo shape)
    dict(id="CP_SOV_DELTA", name="Sovereign Debt Office — Nation Delta", legal_entity="Nation Delta Debt Management Office",
         counterparty_type="Sovereign", rating=None, watchlist=False, reference_entity_id=None,
         product="REVERSE_REPO", netting_set="NS-REVREPO-01", collateral={"type": "Govt Bond", "csa": True, "haircut": 0.02},
         notional=None, direction=None, unmatched_trades=False,
         exposure=dict(rc_previous=180, rc_current=310, pfe_previous=340, pfe_current=767,
                        nse_previous=None, nse_current=None, settlement_exposure=None),
         sensitivities=dict(equity_delta_previous=None, equity_delta_current=None, fx_delta=None, dv01=-22.0, cs01=None),
         limit=dict(limit_id="LIM-SOVDELTA-PFE", limit_type="PFE_LIMIT", limit_value=1100, currency="USD",
                     as_of_date="2026-08-01", source="POC_HEURISTIC"),
         breach=None,
         driver_evidence=dict(trade_population_changed=True, model_version_changed=False, market_move_flag=False,
                               collateral_change_flag=False, netting_change_flag=False, data_issue_flag=False,
                               new_trade_flag=True, matured_trade_flag=False, wwr_flag=True,
                               recovery_change_flag=False, non_netted_flag=False, replacement_cost_move_flag=False,
                               volatility_update_flag=False, data_sourcing_issue_flag=False,
                               model_coverage_change_flag=False, simulation_noise_confirmed_flag=False),
         analyst_explanation="Newly booked specific wrong-way-risk reverse-repo trades against government-bond collateral.",
         risk_factor_path=["INTEREST_RATE", "COLLATERAL"],
         linked_event_id="NONE", coverage_owner="R. Delacroix", suggested_action="INVESTIGATE"),

    # 13. MTM move on futures, small negative -> genuine market move, not noise
    dict(id="CP_FUT_KEST", name="Kestrel Quant Futures Fund", legal_entity="Kestrel Quant Futures Fund Ltd",
         counterparty_type="Hedge Fund", rating=None, watchlist=False, reference_entity_id=None,
         product="EQUITY_FUTURE", netting_set="NS-EQFUT-01", collateral={"type": "Cash VM", "csa": True, "haircut": 0.0},
         notional=None, direction=None, unmatched_trades=False,
         exposure=dict(rc_previous=95, rc_current=60, pfe_previous=210, pfe_current=120,
                        nse_previous=None, nse_current=None, settlement_exposure=None),
         sensitivities=dict(equity_delta_previous=None, equity_delta_current=None, fx_delta=None, dv01=None, cs01=None),
         limit=dict(limit_id="LIM-KEST-PFE", limit_type="PFE_LIMIT", limit_value=500, currency="USD",
                     as_of_date="2026-08-01", source="POC_HEURISTIC"),
         breach=None,
         driver_evidence=dict(trade_population_changed=False, model_version_changed=False, market_move_flag=True,
                               collateral_change_flag=False, netting_change_flag=False, data_issue_flag=False,
                               new_trade_flag=False, matured_trade_flag=False, wwr_flag=False,
                               recovery_change_flag=False, non_netted_flag=False, replacement_cost_move_flag=False,
                               volatility_update_flag=False, data_sourcing_issue_flag=False,
                               model_coverage_change_flag=False, simulation_noise_confirmed_flag=False),
         analyst_explanation="PFE decrease driven by mark-to-market movement on the futures book, unwinding some "
                              "of the prior week's exposure.",
         risk_factor_path=["EQUITY"],
         linked_event_id="NONE", coverage_owner="J. Ferris", suggested_action="MONITOR"),

    # 14. Stress/SI move on margin portfolio swaps (sovereign wealth reserve shape) -> STRESS_LIMIT type
    dict(id="CP_SOV_EPS", name="Sovereign Wealth Reserve — Nation Epsilon", legal_entity="Nation Epsilon Reserve Management Authority",
         counterparty_type="Sovereign Wealth Fund", rating=None, watchlist=False, reference_entity_id=None,
         product="IRS", netting_set="NS-MARGIN-PORT-01", collateral={"type": "Cash VM", "csa": True, "haircut": 0.0},
         notional=None, direction=None, unmatched_trades=False,
         exposure=dict(rc_previous=None, rc_current=None, pfe_previous=None, pfe_current=None,
                        nse_previous=2400, nse_current=3700, settlement_exposure=None),
         sensitivities=dict(equity_delta_previous=None, equity_delta_current=None, fx_delta=None, dv01=-140.0, cs01=None),
         limit=dict(limit_id="LIM-SOVEPS-STRESS", limit_type="STRESS_LIMIT", limit_value=5000, currency="USD",
                     as_of_date="2026-08-01", source="POC_HEURISTIC"),
         breach=None,
         driver_evidence=dict(trade_population_changed=False, model_version_changed=False, market_move_flag=True,
                               collateral_change_flag=False, netting_change_flag=False, data_issue_flag=False,
                               new_trade_flag=False, matured_trade_flag=False, wwr_flag=False,
                               recovery_change_flag=False, non_netted_flag=False, replacement_cost_move_flag=False,
                               volatility_update_flag=False, data_sourcing_issue_flag=False,
                               model_coverage_change_flag=False, simulation_noise_confirmed_flag=False),
         analyst_explanation="Stress exposure increase from MTM movement on the margin-portfolio-swaps book.",
         risk_factor_path=["INTEREST_RATE"],
         linked_event_id="NONE", coverage_owner="M. Oduya", suggested_action="MONITOR"),

    # 15. Large negative stress move, FX swaps/spot, max scenario changed
    dict(id="CP_BANK_MERID", name="Meridian Global Bank Treasury", legal_entity="Meridian Global Bank Treasury plc",
         counterparty_type="Bank Treasury", rating=None, watchlist=False, reference_entity_id=None,
         product="FX_SWAP", netting_set="NS-FXSWAP-01", collateral={"type": "Cash VM", "csa": True, "haircut": 0.0},
         notional=None, direction=None, unmatched_trades=False,
         exposure=dict(rc_previous=None, rc_current=None, pfe_previous=None, pfe_current=None,
                        nse_previous=4100, nse_current=2600, settlement_exposure=None),
         sensitivities=dict(equity_delta_previous=None, equity_delta_current=None, fx_delta=-2600, dv01=None, cs01=None),
         limit=dict(limit_id="LIM-MERID-STRESS", limit_type="STRESS_LIMIT", limit_value=6000, currency="USD",
                     as_of_date="2026-08-01", source="POC_HEURISTIC"),
         breach=None,
         driver_evidence=dict(trade_population_changed=False, model_version_changed=False, market_move_flag=True,
                               collateral_change_flag=False, netting_change_flag=False, data_issue_flag=False,
                               new_trade_flag=False, matured_trade_flag=False, wwr_flag=False,
                               recovery_change_flag=False, non_netted_flag=False, replacement_cost_move_flag=False,
                               volatility_update_flag=False, data_sourcing_issue_flag=False,
                               model_coverage_change_flag=False, simulation_noise_confirmed_flag=False),
         analyst_explanation="Stress exposure decrease from GBP/USD FX swap and spot activity; the worst-case "
                              "scenario driving the stress number also changed between runs.",
         risk_factor_path=["FX"],
         linked_event_id="NONE", coverage_owner="R. Delacroix", suggested_action="MONITOR"),

    # 16. Recovery-rate assumption change drives a stress-exposure decrease
    dict(id="CP_BANK_ALP", name="Alpine Universal Bank AG", legal_entity="Alpine Universal Bank AG",
         counterparty_type="Bank", rating=None, watchlist=False, reference_entity_id=None,
         product="CDS", netting_set="NS-CDS-ALP-01", collateral={"type": "Cash VM", "csa": True, "haircut": 0.0},
         notional=None, direction=None, unmatched_trades=False,
         exposure=dict(rc_previous=None, rc_current=None, pfe_previous=None, pfe_current=None,
                        nse_previous=1900, nse_current=1420, settlement_exposure=None),
         sensitivities=dict(equity_delta_previous=None, equity_delta_current=None, fx_delta=None, dv01=None, cs01=-9.5),
         limit=dict(limit_id="LIM-ALP-STRESS", limit_type="STRESS_LIMIT", limit_value=2500, currency="USD",
                     as_of_date="2026-08-01", source="POC_HEURISTIC"),
         breach=None,
         driver_evidence=dict(trade_population_changed=False, model_version_changed=False, market_move_flag=False,
                               collateral_change_flag=False, netting_change_flag=False, data_issue_flag=False,
                               new_trade_flag=False, matured_trade_flag=False, wwr_flag=False,
                               recovery_change_flag=True, non_netted_flag=False, replacement_cost_move_flag=False,
                               volatility_update_flag=False, data_sourcing_issue_flag=False,
                               model_coverage_change_flag=False, simulation_noise_confirmed_flag=False),
         analyst_explanation="Recovery-rate assumption for this counterparty was updated from ~81% to ~96%, "
                              "reducing modeled loss-given-default and therefore the stress exposure number.",
         risk_factor_path=["CREDIT_SPREAD"],
         linked_event_id="NONE", coverage_owner="J. Ferris", suggested_action="ROUTE_TO_MODEL_TEAM"),

    # 17. Maturing FI cash trades reduce stress exposure (bank shape)
    dict(id="CP_BANK_LOMB", name="Lombardy Factoring Bank SpA", legal_entity="Lombardy Factoring Bank SpA",
         counterparty_type="Bank", rating=None, watchlist=False, reference_entity_id=None,
         product="BOND", netting_set="NS-FI-CASH-04", collateral=None,
         notional=None, direction=None, unmatched_trades=False,
         exposure=dict(rc_previous=None, rc_current=None, pfe_previous=None, pfe_current=None,
                        nse_previous=610, nse_current=448, settlement_exposure=None),
         sensitivities=dict(equity_delta_previous=None, equity_delta_current=None, fx_delta=None, dv01=None, cs01=None),
         limit=dict(limit_id="LIM-LOMB-STRESS", limit_type="STRESS_LIMIT", limit_value=900, currency="USD",
                     as_of_date="2026-08-01", source="POC_HEURISTIC"),
         breach=None,
         driver_evidence=dict(trade_population_changed=True, model_version_changed=False, market_move_flag=False,
                               collateral_change_flag=False, netting_change_flag=False, data_issue_flag=False,
                               new_trade_flag=False, matured_trade_flag=True, wwr_flag=False,
                               recovery_change_flag=False, non_netted_flag=False, replacement_cost_move_flag=False,
                               volatility_update_flag=False, data_sourcing_issue_flag=False,
                               model_coverage_change_flag=False, simulation_noise_confirmed_flag=False),
         analyst_explanation="Stress exposure decrease from maturing FI cash trades referencing government bonds.",
         risk_factor_path=["INTEREST_RATE"],
         linked_event_id="NONE", coverage_owner="M. Oduya", suggested_action="MONITOR"),

    # 18. Equity delta swing from cash equity trades (bank equity-financing desk shape)
    dict(id="CP_BANK_CONT", name="Continental Universal Bank SA", legal_entity="Continental Universal Bank SA",
         counterparty_type="Bank", rating=None, watchlist=False, reference_entity_id="LMT",
         product="EQUITY_CASH", netting_set="NS-EQCASH-01", collateral={"type": "Cash VM", "csa": True, "haircut": 0.0},
         notional=None, direction=None, unmatched_trades=False,
         exposure=dict(rc_previous=None, rc_current=None, pfe_previous=None, pfe_current=None,
                        nse_previous=None, nse_current=None, settlement_exposure=None),
         sensitivities=dict(equity_delta_previous=3340, equity_delta_current=5130, fx_delta=None, dv01=None, cs01=None),
         limit=dict(limit_id=None, limit_type=None, limit_value=None, currency="USD", as_of_date=None, source=None),
         breach=None,
         driver_evidence=dict(trade_population_changed=True, model_version_changed=False, market_move_flag=False,
                               collateral_change_flag=False, netting_change_flag=False, data_issue_flag=False,
                               new_trade_flag=True, matured_trade_flag=False, wwr_flag=False,
                               recovery_change_flag=False, non_netted_flag=False, replacement_cost_move_flag=False,
                               volatility_update_flag=False, data_sourcing_issue_flag=False,
                               model_coverage_change_flag=False, simulation_noise_confirmed_flag=False),
         analyst_explanation="Equity delta increased materially on newly booked cash-equity trades, concentrated "
                              "in a small number of industrial/aerospace single names.",
         risk_factor_path=["EQUITY"],
         linked_event_id="NONE", coverage_owner="R. Delacroix", suggested_action="MONITOR"),

    # 19. Large equity delta swing from index futures, no PFE/limit data available yet
    dict(id="CP_HF_VANT", name="Vantage Multi-Strategy Partners", legal_entity="Vantage Multi-Strategy Partners LP",
         counterparty_type="Hedge Fund", rating=None, watchlist=False, reference_entity_id=None,
         product="EQUITY_FUTURE", netting_set="NS-EQFUT-02", collateral={"type": "Cash VM", "csa": True, "haircut": 0.0},
         notional=None, direction=None, unmatched_trades=False,
         exposure=dict(rc_previous=None, rc_current=None, pfe_previous=None, pfe_current=None,
                        nse_previous=None, nse_current=None, settlement_exposure=None),
         sensitivities=dict(equity_delta_previous=-3000, equity_delta_current=8500, fx_delta=None, dv01=None, cs01=None),
         limit=dict(limit_id=None, limit_type=None, limit_value=None, currency="USD", as_of_date=None, source=None),
         breach=None,
         driver_evidence=dict(trade_population_changed=True, model_version_changed=False, market_move_flag=True,
                               collateral_change_flag=False, netting_change_flag=False, data_issue_flag=False,
                               new_trade_flag=False, matured_trade_flag=False, wwr_flag=False,
                               recovery_change_flag=False, non_netted_flag=False, replacement_cost_move_flag=False,
                               volatility_update_flag=False, data_sourcing_issue_flag=False,
                               model_coverage_change_flag=False, simulation_noise_confirmed_flag=False),
         analyst_explanation="Equity delta swung from net short to net long on equity index futures, primarily "
                              "driven by S&P 500-equivalent index exposure. PFE/limit not yet available for this book.",
         risk_factor_path=["EQUITY", "SP500_INDEX"],
         linked_event_id="NONE", coverage_owner="J. Ferris", suggested_action="MONITOR"),
]


# ---------------------------------------------------------------------------
# Synthetic portfolio-level model/simulation run summary (mirrors the SHAPE
# of a real model-release impact report - facility counts, categorised
# causes - at illustrative POC scale, not tied to any real institution's
# actual portfolio size).
# ---------------------------------------------------------------------------
CCR_MODEL_IMPACTS = [
    dict(
        id="MODEL_RUN_2026_08_01",
        run_date="2026-08-01",
        total_impact_usd_mm=4200,
        facilities_total=1850,
        facilities_over_1mm_impact=310,
        material_changes=48,
        increases=31,
        decreases=17,
        new_limit_breaches=3,
        approaching_limit=4,
        categories_observed=[
            "MODEL_RECALIBRATION", "VOLATILITY_UPDATE", "DATA_SOURCING_ISSUE",
            "MODEL_COVERAGE_CHANGE",
        ],
        is_synthetic=True, source_type="SYNTHETIC_CCR_DECISION_DATA",
    ),
]


def main():
    for c in CCR_COUNTERPARTIES:
        c["is_synthetic"] = True
        c["source_type"] = "SYNTHETIC_CCR_DECISION_DATA"

    with open(os.path.join(DATA_DIR, "ccr_events.json"), "w") as f:
        json.dump({"events": CCR_EVENTS}, f, indent=2)
    with open(os.path.join(DATA_DIR, "ccr_counterparties.json"), "w") as f:
        json.dump({"counterparties": CCR_COUNTERPARTIES}, f, indent=2)
    with open(os.path.join(DATA_DIR, "ccr_model_impacts.json"), "w") as f:
        json.dump({"runs": CCR_MODEL_IMPACTS}, f, indent=2)

    print(f"Wrote {len(CCR_COUNTERPARTIES)} synthetic CCR counterparties, {len(CCR_EVENTS)} events, "
          f"{len(CCR_MODEL_IMPACTS)} model-impact runs.")


if __name__ == "__main__":
    main()
