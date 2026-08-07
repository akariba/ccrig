"""Quick manual smoke test of the core pipeline modules (run directly with
python, not pytest - see backend/tests/ for the real invariant test suite)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.data import STORE
from app.core import candidates, scoring, themes, event_parser, backtest, provenance, scalability, paths

print("== DataStore ==")
print("browsable entities:", len(STORE.browsable_ids), "issuers:", len(STORE.issuer_ids), "cps:", len(STORE.counterparty_ids))

print("\n== Candidate generation (TSM) ==")
cand = candidates.generate_candidates("TSM")
print(cand["instrumentation"])
print("sources:", {k: len(v) for k, v in cand["sources"].items()})

print("\n== Scoring TSM vs NVDA ==")
r = scoring.score_pair("TSM", "NVDA")
print(r["composite"])

print("\n== Rank candidates for TSM ==")
ranked = scoring.rank_candidates("TSM", cand["candidate_ids"], top_k=5)
print("scored:", ranked["scored_pair_count"], "retained:", ranked["retained_count"])
for res in ranked["results"]:
    print(" ", res["b"], res["composite"]["score"])

print("\n== Theme stats (top 5) ==")
for t in themes.theme_stats()[:5]:
    print(" ", t["theme_id"], t["mention_count"], t["portfolio_relevance"])

print("\n== Event parse: Taiwan earthquake scenario ==")
ev = event_parser.parse_event("A major earthquake in Taiwan disrupts semiconductor fabrication facilities.")
print("event_type:", ev["event_type"])
print("direct:", [d["entity_id"] for d in ev["direct_relevance"]])
print("mode1 top:", [(r["entity_id"], r["score"]) for r in ev["mode1_bounded_traversal"]["results"][:5]])
print("mode2 top:", [(r["entity_id"], r["ppr_score"]) for r in ev["mode2_personalized_pagerank"]["results"][:5]])
print("counterparties:", [c["counterparty"] for c in ev["relevant_counterparties"][:5]])

print("\n== Backtest ==")
bt = backtest.run_backtest("taiwan_earthquake_2026")
print("metrics:", bt["metrics"])
print("model top:", bt["model_ranking_top_k"][:5])
print("observed top:", [(m["entity_id"], m["abs_return"]) for m in bt["observed_subsequent_movers_top_k"][:5]])

print("\n== Provenance ==")
print(provenance.registry()["totals"])

print("\n== Scalability (projections only, quick) ==")
for row in scalability.projected_counts():
    print(" ", row)

print("\n== Fact path TSM -> NVDA ==")
print(paths.fact_path_between("TSM", "NVDA"))

print("\nOK - sanity check completed without exceptions.")
