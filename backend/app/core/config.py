"""Runtime configuration. All AI settings are optional; the app must run
fully offline without them (BUILD_MANDATE section 4 & 27)."""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "data"
RAW_PRICES_DIR = DATA_DIR / "raw_prices"

# --- AI provider (optional, OpenAI-compatible) ---
AI_BASE_URL = os.environ.get("AI_BASE_URL", "").strip()
AI_API_KEY = os.environ.get("AI_API_KEY", "").strip()
AI_MODEL = os.environ.get("AI_MODEL", "").strip()
AI_ENABLED = bool(AI_BASE_URL and AI_API_KEY and AI_MODEL)

# --- Document ingestion (POC) ---
# POST /api/themes/ingest appends to the process-wide in-memory news corpus
# that every Theme Radar / discovery view reads. Anyone who can reach the API
# could otherwise grow that shared state, so it is OFF unless explicitly
# enabled (CCRIG_ENABLE_INGEST=1). Ingested text is always labelled
# synthetic / unverified; INGEST_MAX_DOCS bounds how many may be added.
INGEST_ENABLED = os.environ.get("CCRIG_ENABLE_INGEST", "").strip().lower() in {"1", "true", "yes", "on"}
INGEST_MAX_DOCS = 200

# --- Candidate generation / scoring defaults ---
DEFAULT_TOP_K = 12
MAX_TOP_K = 50
CANDIDATE_SEMANTIC_NN = 15          # per-entity nearest neighbours kept from TF-IDF/business-description space
CANDIDATE_THEME_NN = 15             # per-entity neighbours kept from shared-theme space
CANDIDATE_MARKET_NN = 10            # per-entity neighbours kept from market-correlation space
CANDIDATE_CATEGORY_BLOCK_MAX = 40   # max peers pulled from same sector/country block before dedupe

# Default relationship-vector weights (General relatedness preset).
# These are heuristic starting weights - NOT calibrated - editable live in
# the Model Lab. Sum need not be exactly 1.0 for every pair because missing
# components are re-normalised over available components (see scoring.py).
DEFAULT_WEIGHTS = {
    "sector": 0.15,
    "geography": 0.08,
    "supply_chain": 0.25,
    "ownership": 0.10,
    "semantic": 0.12,
    "news": 0.15,
    "market_positive": 0.10,
    "market_negative": 0.05,
}

WEIGHT_PRESETS = {
    "general": {
        "label": "General relatedness",
        "weights": DEFAULT_WEIGHTS,
    },
    "supply_chain_shock": {
        "label": "Supply-chain / geographic shock",
        "weights": {
            "sector": 0.10, "geography": 0.15, "supply_chain": 0.40, "ownership": 0.10,
            "semantic": 0.05, "news": 0.10, "market_positive": 0.05, "market_negative": 0.05,
        },
    },
    "market_funding_shock": {
        "label": "Market / funding shock",
        "weights": {
            "sector": 0.10, "geography": 0.05, "supply_chain": 0.05, "ownership": 0.10,
            "semantic": 0.05, "news": 0.15, "market_positive": 0.30, "market_negative": 0.20,
        },
    },
    "thematic_tech_shock": {
        "label": "Thematic / technology shock",
        "weights": {
            "sector": 0.15, "geography": 0.05, "supply_chain": 0.20, "ownership": 0.05,
            "semantic": 0.20, "news": 0.25, "market_positive": 0.07, "market_negative": 0.03,
        },
    },
}

ROLLING_WINDOW_DAYS = 30
STRESS_WINDOW_DAYS = 10

# POC_HEURISTIC: minimum |signed correlation| for the Connected Risk Graph
# to surface a MARKET_CORRELATED_WITH statistical edge for an entity (see
# core/graph_query.py get_statistical_relationships). Sign is always
# preserved above this magnitude - a strong inverse relationship (very
# negative rho) qualifies exactly like a strong positive one. Not a
# validated production threshold; purely a POC candidate-surfacing cutoff.
STATISTICAL_EDGE_MIN_ABS_CORRELATION = 0.3

# POC_HEURISTIC: bounds on risk-cluster member expansion (core/risk_clusters.py).
# A broad equity exposure can nominate a dozen+ structurally/statistically
# adjacent names - these caps keep the DEFAULT view to what's actually
# analyst-relevant; the full candidate set is still computed and available
# via structural_relationships/statistical_relationships, just not all
# presented as equally important FIRST_ORDER members.
CLUSTER_MAX_FIRST_ORDER_STRUCTURAL = 3
CLUSTER_MAX_FIRST_ORDER_STATISTICAL = 2
CLUSTER_MAX_CONTEXTUAL_MEMBERS = 10
# Minimum share of the first-order neighborhood that must share the
# reference entity's sector before the cluster label uses that sector name
# (e.g. "Semiconductors") - below this, a sector label would overstate a
# consensus that isn't actually there.
CLUSTER_SECTOR_LABEL_MIN_SHARE = 0.5

# --- CCR Daily Review priority-engine thresholds ---
# EXPLICITLY POC_HEURISTIC: these are illustrative POC cut-offs for this
# demo dataset, NOT a real institution's risk appetite. Centralised here
# (never scattered as inline magic numbers in core/ccr_priority.py) and
# always surfaced to the API/UI as heuristic, not authoritative.
CCR_PRIORITY_THRESHOLDS = {
    "label": "POC_HEURISTIC",
    "small_move_abs_pfe": 10,          # $mm - below this, a move is labelled "small" but NEVER asserted as noise
    "immaterial_abs_pfe": 50,          # $mm - below this AND low utilisation, ranks LOW regardless of event relevance
    "immaterial_utilisation_pct": 10,  # %
    "material_delta_abs": 150,         # $mm - Delta PFE/NSE magnitude considered "material" for HIGH
    "high_utilisation_pct": 85,        # % - utilisation at/above this is "close to limit"
}
