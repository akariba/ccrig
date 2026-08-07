"""Basic pipeline sanity checks (beyond the 7 required invariants)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.data import STORE
from app.core import market, themes as theme_mod, event_parser, backtest, paths as path_mod


def test_market_signed_correlation_not_absoluted():
    corr = market.signed_correlation("XOM", "AAPL")
    if corr:
        assert -1.0 <= corr["full_sample_corr"] <= 1.0
        assert corr["positive_channel"] >= 0 and corr["negative_channel"] >= 0
        # exactly one channel should be non-zero (sign is preserved, not abs'd away)
        assert not (corr["positive_channel"] > 0 and corr["negative_channel"] > 0)


def test_theme_stats_nondestructive():
    stats = theme_mod.theme_stats()
    assert len(stats) == len(STORE.keywords)
    assert all("mention_count" in t for t in stats)


def test_event_parser_all_six_sample_scenarios_run():
    scenarios = ["IBM", "Taiwan", "AI bubble",
                 "A major earthquake in Taiwan disrupts semiconductor fabrication facilities.",
                 "Russia-Ukraine escalation raises energy and defense risks.",
                 "Regional bank funding stress after a major bank failure."]
    for s in scenarios:
        result = event_parser.parse_event(s)
        assert "event_type" in result
        assert isinstance(result["mode1_bounded_traversal"]["results"], list)
        assert isinstance(result["mode2_personalized_pagerank"]["results"], list)


def test_backtest_runs_and_returns_metrics():
    result = backtest.run_backtest("taiwan_earthquake_2026")
    assert "metrics" in result
    assert result["metrics"]["precision_at_5"] >= 0
    assert len(result["warnings"]) >= 2


def test_typed_path_between_tsm_and_nvda_is_directional_and_sourced():
    p = path_mod.fact_path_between("TSM", "NVDA")
    assert p is not None
    assert p["hops"][0]["relation"] == "SUPPLIES"
    assert p["hops"][0]["evidence_url"]
