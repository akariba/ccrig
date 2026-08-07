"""
CCRIG dataset builder.

Assembles the curated POC dataset from hand-maintained, source-labelled
dictionaries below. This script is the single source of truth for entity
master data, factual (Layer A) relations, keyword/theme definitions, and
synthetic (clearly labelled) counterparties + exposures (Layer C).

Run:
    python backend/scripts/build_dataset.py

Outputs (backend/data/):
    entities.json          - entity master (issuers + counterparties)
    fact_edges.json         - Layer A: FACT RELATIONS (directional, sourced)
    keywords.json           - theme/keyword taxonomy + synonyms
    entity_keyword_weights.json - curated entity<->keyword relevance (seed;
                              also augmented at runtime from news co-mentions)
    counterparties.json     - SYNTHETIC counterparty master
    exposure_edges.json     - Layer C: SYNTHETIC exposure edges (directional)
    news_real.json          - REAL public news headlines w/ URL + snippet
    news_synthetic.json     - SYNTHETIC narrative corpus (labelled)
    gleif_sample.json       - already fetched from the public GLEIF API (kept)

All "real" facts here (sector, country, well-documented supplier
relationships) reflect analyst/public knowledge current as of this build and
are NOT pulled from a single verifiable filing per edge in this POC unless a
URL is attached. Where a specific 2026 news URL exists it is attached as
`evidence_url`. See DATA_DICTIONARY.md for full provenance rules.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")

PRICE_DIR = os.path.join(DATA_DIR, "raw_prices")
TICKERS_WITH_PRICES = set()
for fn in os.listdir(PRICE_DIR):
    if fn.endswith(".csv"):
        TICKERS_WITH_PRICES.add(fn.split("_price_history")[0])

# ---------------------------------------------------------------------------
# 1. ENTITY MASTER (issuers). Sector/country/industry = public knowledge,
#    curated by the build author. has_market_data reflects the bundled real
#    price CSVs only (no fabricated prices for others).
# ---------------------------------------------------------------------------
ISSUERS = [
    # id, name, sector, industry, country, region, ticker
    ("TSM", "Taiwan Semiconductor Manufacturing Co (TSMC)", "Semiconductors", "Foundry / Contract Manufacturing", "Taiwan", "APAC", "TSM"),
    ("NVDA", "NVIDIA Corporation", "Semiconductors", "Fabless Design (GPU / AI Accelerators)", "United States", "North America", "NVDA"),
    ("AMD", "Advanced Micro Devices, Inc.", "Semiconductors", "Fabless Design (CPU / GPU)", "United States", "North America", "AMD"),
    ("INTC", "Intel Corporation", "Semiconductors", "Integrated Device Manufacturer", "United States", "North America", "INTC"),
    ("SKHY", "SK Hynix Inc.", "Semiconductors", "Memory (DRAM / HBM / NAND)", "South Korea", "APAC", "SKHY"),
    ("SSNLF", "Samsung Electronics Co., Ltd.", "Semiconductors", "Memory / Foundry / Devices", "South Korea", "APAC", None),
    ("ASML", "ASML Holding N.V.", "Semiconductors", "Semiconductor Equipment (EUV Lithography)", "Netherlands", "Europe", None),
    ("AMAT", "Applied Materials, Inc.", "Semiconductors", "Semiconductor Equipment (Wafer Fab Tools)", "United States", "North America", None),
    ("AVGO", "Broadcom Inc.", "Semiconductors", "Fabless Design / Networking / Custom AI ASIC", "United States", "North America", None),
    ("MU", "Micron Technology, Inc.", "Semiconductors", "Memory (DRAM / NAND / HBM)", "United States", "North America", None),
    ("QCOM", "QUALCOMM Incorporated", "Semiconductors", "Fabless Design (Mobile SoC / Modem)", "United States", "North America", None),
    ("ARM", "Arm Holdings plc", "Semiconductors", "Semiconductor IP Licensing", "United Kingdom", "Europe", None),

    ("IBM", "International Business Machines Corporation", "Technology", "Enterprise IT / Hybrid Cloud / AI", "United States", "North America", "IBM"),
    ("MSFT", "Microsoft Corporation", "Technology", "Software / Cloud Infrastructure", "United States", "North America", "MSFT"),
    ("AAPL", "Apple Inc.", "Technology", "Consumer Electronics", "United States", "North America", "AAPL"),
    ("GOOGL", "Alphabet Inc.", "Technology", "Internet / Cloud / AI (Hyperscaler)", "United States", "North America", None),
    ("AMZN", "Amazon.com, Inc.", "Technology", "Internet / Cloud Infrastructure (Hyperscaler)", "United States", "North America", None),
    ("META", "Meta Platforms, Inc.", "Technology", "Internet / Social / AI (Hyperscaler)", "United States", "North America", None),
    ("ORCL", "Oracle Corporation", "Technology", "Enterprise Software / Cloud Infrastructure", "United States", "North America", None),

    ("JPM", "JPMorgan Chase & Co.", "Financials", "Global Bank / Universal Bank", "United States", "North America", "JPM"),
    ("C", "Citigroup Inc.", "Financials", "Global Bank / Universal Bank", "United States", "North America", "C"),
    ("DBK", "Deutsche Bank AG", "Financials", "Global Bank / Universal Bank", "Germany", "Europe", None),
    ("BAC", "Bank of America Corporation", "Financials", "Global Bank / Universal Bank", "United States", "North America", None),
    ("GS", "The Goldman Sachs Group, Inc.", "Financials", "Investment Bank / Broker-Dealer", "United States", "North America", None),
    ("MS", "Morgan Stanley", "Financials", "Investment Bank / Broker-Dealer", "United States", "North America", None),
    ("WFC", "Wells Fargo & Company", "Financials", "Global Bank / Universal Bank", "United States", "North America", None),
    ("UBS", "UBS Group AG", "Financials", "Global Bank / Wealth Management", "Switzerland", "Europe", None),
    ("HSBC", "HSBC Holdings plc", "Financials", "Global Bank / Universal Bank", "United Kingdom", "Europe", None),
    ("AIG", "American International Group, Inc.", "Financials", "Insurance (Multiline)", "United States", "North America", None),

    ("BA", "The Boeing Company", "Industrials", "Aerospace & Defense (Commercial)", "United States", "North America", "BA"),
    ("LMT", "Lockheed Martin Corporation", "Industrials", "Aerospace & Defense (Defense Prime)", "United States", "North America", "LMT"),
    ("RTX", "RTX Corporation (Raytheon Technologies)", "Industrials", "Aerospace & Defense Systems", "United States", "North America", None),
    ("NOC", "Northrop Grumman Corporation", "Industrials", "Aerospace & Defense (Defense Prime)", "United States", "North America", None),
    ("GD", "General Dynamics Corporation", "Industrials", "Aerospace & Defense / Marine", "United States", "North America", None),
    ("MAERSK", "A.P. Moller - Maersk A/S", "Industrials", "Container Shipping & Logistics", "Denmark", "Europe", None),
    ("CAT", "Caterpillar Inc.", "Industrials", "Heavy Machinery / Industrial Equipment", "United States", "North America", None),

    ("XOM", "ExxonMobil Corporation", "Energy", "Integrated Oil & Gas", "United States", "North America", "XOM"),
    ("SHEL", "Shell plc", "Energy", "Integrated Oil & Gas", "United Kingdom", "Europe", "SHEL"),
    ("CVX", "Chevron Corporation", "Energy", "Integrated Oil & Gas", "United States", "North America", None),
    ("BP", "BP p.l.c.", "Energy", "Integrated Oil & Gas", "United Kingdom", "Europe", None),
    ("TTE", "TotalEnergies SE", "Energy", "Integrated Oil & Gas", "France", "Europe", None),

    ("FCX", "Freeport-McMoRan Inc.", "Materials", "Copper Mining", "United States", "North America", None),
    ("RIO", "Rio Tinto plc", "Materials", "Diversified Mining", "United Kingdom", "Europe", None),
]

# ---------------------------------------------------------------------------
# 2. SYNTHETIC COUNTERPARTIES (Layer C anchor nodes) - clearly synthetic
# ---------------------------------------------------------------------------
COUNTERPARTIES = [
    ("CP_ALPHA", "Alpha Quant Capital LP", "Hedge Fund - Tech/AI Long-Short", "United States", "North America"),
    ("CP_PACIFIC", "Pacific Tech Partners", "Asset Manager - Asia Tech/Supply Chain", "Hong Kong", "APAC"),
    ("CP_MERIDIAN", "Meridian Global Macro LP", "Hedge Fund - Global Macro (Energy/Defense)", "United States", "North America"),
    ("CP_NORTHBRIDGE", "Northbridge Insurance Group", "Insurer - Fixed Income Book", "United Kingdom", "Europe"),
    ("CP_SUMMIT", "Summit State Pension Fund", "Pension Fund - Diversified Public Equity", "United States", "North America"),
    ("CP_HELIX", "Helix Multi-Strategy Partners", "Hedge Fund - Quant Multi-Strategy", "United States", "North America"),
    ("CP_CASCADE", "Cascade Regional Bank Treasury", "Bank Treasury / ALM Book", "United States", "North America"),
    ("CP_IRONGATE", "Irongate Private Credit Fund", "Private Credit - Industrials/Defense Lending", "United States", "North America"),
    ("CP_LATTICE", "Lattice Sovereign Growth Fund", "Sovereign Wealth Fund - Tech Allocation", "Singapore", "APAC"),
    ("CP_VANTAGE", "Vantage European Equity Partners", "Asset Manager - Broad European Equities", "Germany", "Europe"),
    ("CP_HARBOR", "Harbor Commodities Trading SA", "Commodity Trading Firm - Energy/Shipping", "Switzerland", "Europe"),
    ("CP_KESTREL", "Kestrel Family Office", "Family Office - Concentrated Tech Bets", "United States", "North America"),
    ("CP_ORION", "Orion Re Group", "Reinsurer - Catastrophe & Credit Book", "Bermuda", "North America"),
    ("CP_DELTA", "Delta Prime Brokerage Client Book", "Broker-Dealer Client - Prime Brokerage", "United States", "North America"),
    ("CP_ANCHOR", "Anchor Money Market Fund", "Money Market Fund - Short-Term Bank Funding", "United States", "North America"),
    ("CP_TRIREME", "Trireme Shipping Finance", "Shipping/Logistics Financier", "Greece", "Europe"),
    ("CP_EQUINOX", "Equinox Global Multi-Asset Fund", "Hedge Fund - Diversified Multi-Asset", "United Kingdom", "Europe"),
    ("CP_GRANITE", "Granite Resources Capital", "Fund - Mining/Commodities Focus", "Australia", "APAC"),
]

# ---------------------------------------------------------------------------
# 3. FACT RELATIONS (Layer A) - directional, curated, source-labelled
#    evidence_status: WELL_DOCUMENTED_PUBLIC (industry-standard knowledge,
#      no single article cited) | REPORTED_NEWS (has evidence_url) |
#      SYNTHETIC (POC-only, not asserted as real)
# ---------------------------------------------------------------------------
FACT_EDGES = [
    # --- Foundry / supply chain: logic & advanced packaging ---
    dict(source="TSM", target="NVDA", relation="SUPPLIES", criticality=0.95,
         note="Primary advanced-node foundry (CoWoS packaging) for NVIDIA AI GPUs.",
         evidence_status="REPORTED_NEWS", evidence_url="https://www.bloomberg.com/news/articles/2026-06-04/tsmc-ceo-warns-chip-supply-won-t-meet-ai-fueled-demand-for-years"),
    dict(source="TSM", target="AMD", relation="SUPPLIES", criticality=0.88,
         note="Primary foundry for AMD CPU/GPU dies.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="TSM", target="AAPL", relation="SUPPLIES", criticality=0.80,
         note="Primary foundry for Apple silicon (A-series / M-series).", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="TSM", target="INTC", relation="SUPPLIES", criticality=0.20,
         note="Partial outsourced leading-edge capacity for select Intel products.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="TSM", target="QCOM", relation="SUPPLIES", criticality=0.70,
         note="Foundry for Qualcomm mobile SoCs.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="TSM", target="AVGO", relation="SUPPLIES", criticality=0.55,
         note="Foundry for Broadcom custom AI ASICs and networking chips.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="TSM", target="ARM", relation="SUPPLIES", criticality=0.15,
         note="Fabricates chips designed around Arm-licensed cores (indirect).", evidence_status="WELL_DOCUMENTED_PUBLIC"),

    # --- Equipment suppliers into foundries ---
    dict(source="ASML", target="TSM", relation="SUPPLIES", criticality=0.85,
         note="EUV lithography systems critical to TSMC advanced nodes.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="ASML", target="SSNLF", relation="SUPPLIES", criticality=0.75,
         note="EUV lithography systems for Samsung Foundry/memory.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="ASML", target="INTC", relation="SUPPLIES", criticality=0.65,
         note="EUV lithography systems for Intel Foundry.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="AMAT", target="TSM", relation="SUPPLIES", criticality=0.55,
         note="Wafer fab equipment (deposition/etch) supplier.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="AMAT", target="SSNLF", relation="SUPPLIES", criticality=0.50,
         note="Wafer fab equipment supplier.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="AMAT", target="SKHY", relation="SUPPLIES", criticality=0.50,
         note="Wafer fab equipment supplier for memory production.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="AMAT", target="MU", relation="SUPPLIES", criticality=0.55,
         note="Wafer fab equipment supplier for memory production.", evidence_status="WELL_DOCUMENTED_PUBLIC"),

    # --- Memory / HBM ---
    dict(source="SKHY", target="NVDA", relation="SUPPLIES", criticality=0.78,
         note="Key HBM supplier for NVIDIA AI accelerators.", evidence_status="REPORTED_NEWS",
         evidence_url="https://finance.yahoo.com/news/ai-capital-expenditure-shows-no-093005586.html"),
    dict(source="SKHY", target="AMD", relation="SUPPLIES", criticality=0.42, note="HBM/memory supplier.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="MU", target="NVDA", relation="SUPPLIES", criticality=0.45, note="HBM/DRAM supplier for AI accelerators.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="MU", target="AAPL", relation="SUPPLIES", criticality=0.30, note="DRAM/NAND memory supplier.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="SSNLF", target="AAPL", relation="SUPPLIES", criticality=0.45, note="Display panel and memory component supplier.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="SSNLF", target="NVDA", relation="SUPPLIES", criticality=0.30, note="Secondary/emerging HBM supplier.", evidence_status="WELL_DOCUMENTED_PUBLIC"),

    # --- Fabless -> hyperscaler customers ---
    dict(source="NVDA", target="MSFT", relation="SUPPLIES", criticality=0.55, note="GPU supply for Azure AI infrastructure.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="NVDA", target="GOOGL", relation="SUPPLIES", criticality=0.50, note="GPU supply for Google Cloud AI infrastructure.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="NVDA", target="AMZN", relation="SUPPLIES", criticality=0.50, note="GPU supply for AWS AI infrastructure.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="NVDA", target="META", relation="SUPPLIES", criticality=0.50, note="GPU supply for Meta AI data centres.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="AMD", target="MSFT", relation="SUPPLIES", criticality=0.25, note="Secondary GPU/CPU procurement.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="AVGO", target="GOOGL", relation="SUPPLIES", criticality=0.55, note="Co-designed custom AI ASIC (TPU) partnership.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="QCOM", target="AAPL", relation="SUPPLIES", criticality=0.35, note="Modem chip supplier (historically primary).", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="AVGO", target="AAPL", relation="SUPPLIES", criticality=0.30, note="RF/connectivity component supplier.", evidence_status="WELL_DOCUMENTED_PUBLIC"),

    # --- IP licensing (distinct fact type; not a physical supply relation) ---
    dict(source="ARM", target="QCOM", relation="LICENSES_TO", criticality=0.70, note="Core architecture license for mobile SoCs.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="ARM", target="AAPL", relation="LICENSES_TO", criticality=0.75, note="Core architecture license for Apple Silicon.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="ARM", target="NVDA", relation="LICENSES_TO", criticality=0.40, note="Architecture license used in Grace CPU/data centre platforms.", evidence_status="WELL_DOCUMENTED_PUBLIC"),

    # --- Defense industrial base ---
    dict(source="LMT", target="RTX", relation="SUPPLIES", criticality=0.30, note="Missile/subsystem component interdependencies across primes.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="BA", target="RTX", relation="SUPPLIES", criticality=0.25, note="Avionics/engine subsystem supplier relationships.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="NOC", target="LMT", relation="SUPPLIES", criticality=0.20, note="Subsystem/sensor supply on shared defense programs.", evidence_status="WELL_DOCUMENTED_PUBLIC"),

    # --- Geography / operates-in facts (for geographic event propagation) ---
    dict(source="TSM", target="TAIWAN", relation="OPERATES_IN", criticality=1.0, note="Headquartered and fabricates primarily in Taiwan.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="SKHY", target="SOUTH_KOREA", relation="OPERATES_IN", criticality=1.0, note="Headquartered and fabricates primarily in South Korea.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="SSNLF", target="SOUTH_KOREA", relation="OPERATES_IN", criticality=1.0, note="Headquartered in South Korea.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="DBK", target="GERMANY", relation="OPERATES_IN", criticality=1.0, note="Headquartered in Germany.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="SHEL", target="EUROPE", relation="OPERATES_IN", criticality=0.8, note="Major European-domiciled energy major.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="BP", target="EUROPE", relation="OPERATES_IN", criticality=0.8, note="Major European-domiciled energy major.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="TTE", target="EUROPE", relation="OPERATES_IN", criticality=0.8, note="Major European-domiciled energy major.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="MAERSK", target="EUROPE", relation="OPERATES_IN", criticality=0.7, note="Headquartered in Denmark; global shipping operations.", evidence_status="WELL_DOCUMENTED_PUBLIC"),
    dict(source="RIO", target="EUROPE", relation="OPERATES_IN", criticality=0.4, note="Dual-listed, UK-domiciled mining major.", evidence_status="WELL_DOCUMENTED_PUBLIC"),

    # --- Sector membership (used for hierarchical blocking) ---
] + [
    dict(source=eid, target=("SECTOR_" + sector.upper().replace(" ", "_")), relation="BELONGS_TO_SECTOR",
         criticality=1.0, note=f"{sector} sector membership.", evidence_status="WELL_DOCUMENTED_PUBLIC")
    for (eid, _, sector, *_rest) in ISSUERS
]

# ---------------------------------------------------------------------------
# 4. KEYWORDS / THEMES taxonomy (seed set; theme radar pipeline augments
#    salience/velocity at runtime from the news corpus)
# ---------------------------------------------------------------------------
KEYWORDS = [
    ("AI", "AI", ["ai", "artificial intelligence", "genai", "generative ai", "gen ai"]),
    ("AI_BUBBLE", "AI bubble", ["ai bubble", "ai valuation bubble", "ai overbuild", "tech bubble", "data center bubble"]),
    ("SEMICONDUCTORS", "semiconductors", ["semiconductor", "semiconductors", "chip", "chips", "chipmaker", "chipmakers"]),
    ("FOUNDRY", "foundry", ["foundry", "fabrication", "fab", "fabs", "advanced node", "advanced packaging", "cowos"]),
    ("GPU", "GPU", ["gpu", "gpus", "graphics processing unit", "ai accelerator", "ai accelerators"]),
    ("MEMORY", "memory chips", ["memory", "dram", "nand", "memory chips"]),
    ("HBM", "HBM", ["hbm", "high bandwidth memory", "hbm4"]),
    ("LITHOGRAPHY", "lithography equipment", ["euv", "lithography", "litho tools", "wafer fab equipment"]),
    ("DATA_CENTERS", "data centres", ["data centre", "data centres", "datacenter", "datacenters", "data center"]),
    ("HYPERSCALERS", "hyperscalers", ["hyperscaler", "hyperscalers", "cloud provider", "cloud providers"]),
    ("CLOUD", "cloud computing", ["cloud", "cloud computing", "azure", "hybrid cloud"]),
    ("CAPEX", "capex", ["capex", "capital expenditure", "infrastructure spend"]),
    ("AI_MONETIZATION", "AI monetisation", ["ai monetisation", "ai monetization", "ai roi", "ai returns"]),
    ("EXPORT_CONTROLS", "export controls", ["export control", "export controls", "export restriction", "export restrictions", "chip ban"]),
    ("SANCTIONS", "sanctions", ["sanction", "sanctions"]),
    ("TAIWAN", "Taiwan", ["taiwan", "taiwanese", "taiwan strait", "hsinchu"]),
    ("CHINA", "China", ["china", "chinese"]),
    ("SOUTH_KOREA", "South Korea", ["south korea", "korea", "korean"]),
    ("GERMANY", "Germany", ["germany", "german"]),
    ("EUROPE", "Europe", ["europe", "european", "eu"]),
    ("GEOPOLITICS", "geopolitics", ["geopolitical", "geopolitics", "geopolitical risk", "geopolitical tension"]),
    ("EARTHQUAKE", "earthquake", ["earthquake", "seismic", "seismic activity", "natural disaster"]),
    ("SUPPLY_DISRUPTION", "supply chain disruption", ["supply disruption", "supply chain disruption", "supply chain risk", "disrupted", "disruption"]),
    ("ENERGY", "energy", ["energy", "energy markets", "energy security"]),
    ("OIL", "oil", ["oil", "crude oil", "petroleum"]),
    ("NATURAL_GAS", "natural gas", ["natural gas", "lng", "gas supply"]),
    ("OPEC", "OPEC", ["opec", "opec+"]),
    ("DEFENSE", "defense", ["defense", "defence", "military", "military spending"]),
    ("AEROSPACE", "aerospace", ["aerospace"]),
    ("NATO", "NATO", ["nato"]),
    ("UKRAINE", "Ukraine", ["ukraine", "ukrainian"]),
    ("RUSSIA", "Russia", ["russia", "russian"]),
    ("BANKING", "banking", ["bank", "banks", "banking"]),
    ("CREDIT_CRISIS", "credit crisis", ["credit crisis", "credit crunch", "banking crisis", "counterparty credit risk"]),
    ("BANK_FUNDING", "bank funding stress", ["funding stress", "deposit run", "bank run", "liquidity stress"]),
    ("INTEREST_RATES", "interest rates", ["interest rate", "interest rates", "rate hike", "rate hikes", "fed funds rate"]),
    ("INFLATION", "inflation", ["inflation"]),
    ("RECESSION", "recession", ["recession"]),
    ("INSURANCE", "insurance", ["insurance", "insurer", "insurers", "reinsurance"]),
    ("TARIFFS", "tariffs", ["tariff", "tariffs", "trade tariff"]),
    ("TRADE_WAR", "trade war", ["trade war", "trade tension", "trade tensions"]),
    ("CHIPS_ACT", "CHIPS Act", ["chips act", "chip subsidies", "chips act subsidies"]),
    ("CYBERSECURITY", "cybersecurity", ["cybersecurity", "cyber attack", "cyberattack", "cyber risk"]),
    ("SHIPPING", "shipping", ["shipping", "logistics", "maritime shipping", "container shipping"]),
    ("MNA", "M&A", ["m&a", "merger", "mergers", "acquisition", "acquisitions"]),
    ("MINING", "mining / metals", ["mining", "copper", "metals", "critical minerals"]),
    ("POWER_GRID", "power grid / electricity", ["power grid", "electricity demand", "grid capacity", "power constraints"]),
]

# Curated seed entity<->keyword weights (0..1). Runtime pipeline augments
# with news co-mention counts; this seed captures durable structural themes.
ENTITY_KEYWORD_WEIGHTS = {
    "TSM": {"SEMICONDUCTORS": 1.0, "FOUNDRY": 1.0, "TAIWAN": 1.0, "AI": 0.6, "GPU": 0.5, "HBM": 0.4,
            "EXPORT_CONTROLS": 0.5, "EARTHQUAKE": 0.4, "GEOPOLITICS": 0.6, "CHIPS_ACT": 0.3,
            "SUPPLY_DISRUPTION": 0.5, "CAPEX": 0.5, "LITHOGRAPHY": 0.4},
    "NVDA": {"AI": 1.0, "GPU": 1.0, "SEMICONDUCTORS": 0.9, "DATA_CENTERS": 0.8, "HYPERSCALERS": 0.7,
             "HBM": 0.6, "AI_BUBBLE": 0.7, "EXPORT_CONTROLS": 0.5, "CHINA": 0.4, "TAIWAN": 0.3, "AI_MONETIZATION": 0.5},
    "AMD": {"SEMICONDUCTORS": 0.9, "GPU": 0.8, "AI": 0.7, "DATA_CENTERS": 0.6, "AI_BUBBLE": 0.5, "TAIWAN": 0.3},
    "INTC": {"SEMICONDUCTORS": 1.0, "FOUNDRY": 0.5, "CHIPS_ACT": 0.6, "AI": 0.3, "DATA_CENTERS": 0.4, "TAIWAN": 0.2, "LITHOGRAPHY": 0.3},
    "SKHY": {"MEMORY": 1.0, "HBM": 1.0, "SEMICONDUCTORS": 0.9, "SOUTH_KOREA": 1.0, "AI": 0.5, "CAPEX": 0.4},
    "SSNLF": {"MEMORY": 0.9, "SEMICONDUCTORS": 0.9, "SOUTH_KOREA": 1.0, "FOUNDRY": 0.5, "AI": 0.3, "HBM": 0.4},
    "ASML": {"LITHOGRAPHY": 1.0, "SEMICONDUCTORS": 0.9, "EXPORT_CONTROLS": 0.6, "CHINA": 0.4, "EUROPE": 0.5, "FOUNDRY": 0.5},
    "AMAT": {"LITHOGRAPHY": 0.8, "SEMICONDUCTORS": 0.9, "CAPEX": 0.5, "EXPORT_CONTROLS": 0.4},
    "AVGO": {"SEMICONDUCTORS": 0.9, "AI": 0.7, "GPU": 0.3, "HYPERSCALERS": 0.6, "DATA_CENTERS": 0.6},
    "MU": {"MEMORY": 1.0, "HBM": 0.7, "SEMICONDUCTORS": 0.9, "AI": 0.4, "CAPEX": 0.4},
    "QCOM": {"SEMICONDUCTORS": 0.8, "TAIWAN": 0.3, "CHINA": 0.4},
    "ARM": {"SEMICONDUCTORS": 0.7, "AI": 0.4, "MNA": 0.2},
    "IBM": {"AI": 0.6, "CLOUD": 0.5, "CYBERSECURITY": 0.4, "SEMICONDUCTORS": 0.2, "AI_MONETIZATION": 0.4},
    "MSFT": {"AI": 1.0, "CLOUD": 1.0, "DATA_CENTERS": 0.9, "HYPERSCALERS": 1.0, "CYBERSECURITY": 0.4,
             "AI_BUBBLE": 0.5, "GPU": 0.4, "CAPEX": 0.6, "AI_MONETIZATION": 0.6, "POWER_GRID": 0.3},
    "AAPL": {"SEMICONDUCTORS": 0.5, "CHINA": 0.5, "TAIWAN": 0.4, "FOUNDRY": 0.3},
    "GOOGL": {"AI": 1.0, "CLOUD": 0.9, "DATA_CENTERS": 0.9, "HYPERSCALERS": 1.0, "AI_BUBBLE": 0.5, "CAPEX": 0.6, "AI_MONETIZATION": 0.5, "POWER_GRID": 0.3},
    "AMZN": {"AI": 0.8, "CLOUD": 1.0, "DATA_CENTERS": 0.9, "HYPERSCALERS": 1.0, "AI_BUBBLE": 0.4, "CAPEX": 0.6, "POWER_GRID": 0.3},
    "META": {"AI": 0.9, "DATA_CENTERS": 0.9, "HYPERSCALERS": 0.9, "AI_BUBBLE": 0.5, "CAPEX": 0.6, "GPU": 0.4, "AI_MONETIZATION": 0.4},
    "ORCL": {"AI": 0.6, "CLOUD": 0.8, "DATA_CENTERS": 0.6, "HYPERSCALERS": 0.5, "CAPEX": 0.4},
    "JPM": {"BANKING": 1.0, "INTEREST_RATES": 0.6, "CREDIT_CRISIS": 0.4, "INFLATION": 0.3},
    "C": {"BANKING": 1.0, "INTEREST_RATES": 0.5, "CREDIT_CRISIS": 0.4, "EUROPE": 0.2},
    "DBK": {"BANKING": 1.0, "GERMANY": 1.0, "EUROPE": 0.8, "CREDIT_CRISIS": 0.4, "INTEREST_RATES": 0.4, "RUSSIA": 0.3},
    "BAC": {"BANKING": 1.0, "INTEREST_RATES": 0.5, "CREDIT_CRISIS": 0.3, "BANK_FUNDING": 0.3},
    "GS": {"BANKING": 0.9, "INTEREST_RATES": 0.4, "MNA": 0.4},
    "MS": {"BANKING": 0.9, "INTEREST_RATES": 0.4, "MNA": 0.4},
    "WFC": {"BANKING": 1.0, "INTEREST_RATES": 0.5, "BANK_FUNDING": 0.3},
    "UBS": {"BANKING": 1.0, "EUROPE": 0.6, "BANK_FUNDING": 0.4, "CREDIT_CRISIS": 0.3},
    "HSBC": {"BANKING": 1.0, "EUROPE": 0.5, "CHINA": 0.4},
    "AIG": {"INSURANCE": 1.0, "BANKING": 0.2, "CREDIT_CRISIS": 0.3},
    "BA": {"AEROSPACE": 1.0, "DEFENSE": 0.6, "SUPPLY_DISRUPTION": 0.4, "TARIFFS": 0.3},
    "LMT": {"DEFENSE": 1.0, "AEROSPACE": 0.8, "UKRAINE": 0.4, "RUSSIA": 0.3, "NATO": 0.6},
    "RTX": {"DEFENSE": 1.0, "AEROSPACE": 0.8, "NATO": 0.6, "UKRAINE": 0.3},
    "NOC": {"DEFENSE": 1.0, "AEROSPACE": 0.6, "NATO": 0.5},
    "GD": {"DEFENSE": 1.0, "AEROSPACE": 0.5, "NATO": 0.4, "SHIPPING": 0.2},
    "MAERSK": {"SHIPPING": 1.0, "EUROPE": 0.5, "SUPPLY_DISRUPTION": 0.4, "TARIFFS": 0.3},
    "CAT": {"SUPPLY_DISRUPTION": 0.3, "TARIFFS": 0.3, "MINING": 0.3},
    "XOM": {"OIL": 1.0, "ENERGY": 1.0, "NATURAL_GAS": 0.5, "OPEC": 0.5, "INFLATION": 0.3},
    "SHEL": {"OIL": 1.0, "ENERGY": 1.0, "NATURAL_GAS": 0.7, "OPEC": 0.4, "EUROPE": 0.5, "RUSSIA": 0.3},
    "CVX": {"OIL": 1.0, "ENERGY": 1.0, "OPEC": 0.4},
    "BP": {"OIL": 1.0, "ENERGY": 1.0, "NATURAL_GAS": 0.5, "EUROPE": 0.6, "RUSSIA": 0.3},
    "TTE": {"OIL": 0.9, "ENERGY": 1.0, "NATURAL_GAS": 0.6, "EUROPE": 0.6, "RUSSIA": 0.3},
    "FCX": {"MINING": 1.0, "AI": 0.2, "DATA_CENTERS": 0.2, "POWER_GRID": 0.3},
    "RIO": {"MINING": 1.0, "CHINA": 0.4, "EUROPE": 0.3},
    "CP_ALPHA": {"AI": 0.6, "AI_BUBBLE": 0.5, "SEMICONDUCTORS": 0.4, "GPU": 0.4},
    "CP_PACIFIC": {"TAIWAN": 0.5, "SEMICONDUCTORS": 0.5, "SOUTH_KOREA": 0.3, "MEMORY": 0.3},
    "CP_MERIDIAN": {"ENERGY": 0.5, "DEFENSE": 0.4, "OIL": 0.3, "AEROSPACE": 0.3},
    "CP_NORTHBRIDGE": {"BANKING": 0.5, "INSURANCE": 1.0, "EUROPE": 0.3, "CREDIT_CRISIS": 0.3},
    "CP_SUMMIT": {"BANKING": 0.3, "AI": 0.3, "ENERGY": 0.2},
    "CP_HELIX": {"AI": 0.5, "SEMICONDUCTORS": 0.5, "AI_BUBBLE": 0.4},
    "CP_CASCADE": {"BANKING": 0.7, "BANK_FUNDING": 0.6, "INTEREST_RATES": 0.5},
    "CP_IRONGATE": {"DEFENSE": 0.5, "AEROSPACE": 0.3},
    "CP_LATTICE": {"AI": 0.5, "SEMICONDUCTORS": 0.4, "TAIWAN": 0.3},
    "CP_VANTAGE": {"EUROPE": 0.6, "BANKING": 0.3},
    "CP_HARBOR": {"ENERGY": 0.6, "SHIPPING": 0.5, "OIL": 0.3},
    "CP_KESTREL": {"AI": 0.6, "AI_BUBBLE": 0.5},
    "CP_ORION": {"INSURANCE": 0.8, "CREDIT_CRISIS": 0.3},
    "CP_DELTA": {"BANKING": 0.4, "AI": 0.3},
    "CP_ANCHOR": {"BANK_FUNDING": 0.8, "BANKING": 0.6, "INTEREST_RATES": 0.4},
    "CP_TRIREME": {"SHIPPING": 0.8, "ENERGY": 0.3},
    "CP_EQUINOX": {"AI": 0.3, "ENERGY": 0.3, "DEFENSE": 0.3},
    "CP_GRANITE": {"MINING": 0.8, "CHINA": 0.3},
}

# ---------------------------------------------------------------------------
# 5. SYNTHETIC EXPOSURE EDGES (Layer C). Counterparty -> Issuer.
#    exposure_pct = % of the (synthetic) portfolio in that issuer's
#    securities. Kept separate namespace from any relatedness weight.
# ---------------------------------------------------------------------------
EXPOSURE_EDGES = [
    dict(counterparty="CP_ALPHA", issuer="NVDA", relation="HOLDS_EQUITY", exposure_pct=0.32),
    dict(counterparty="CP_ALPHA", issuer="AMD", relation="HOLDS_EQUITY", exposure_pct=0.20),
    dict(counterparty="CP_ALPHA", issuer="TSM", relation="HOLDS_EQUITY", exposure_pct=0.18),
    dict(counterparty="CP_ALPHA", issuer="MSFT", relation="HOLDS_EQUITY", exposure_pct=0.15),
    dict(counterparty="CP_ALPHA", issuer="AVGO", relation="HOLDS_EQUITY", exposure_pct=0.15),

    dict(counterparty="CP_PACIFIC", issuer="TSM", relation="HOLDS_EQUITY", exposure_pct=0.30),
    dict(counterparty="CP_PACIFIC", issuer="SKHY", relation="HOLDS_EQUITY", exposure_pct=0.22),
    dict(counterparty="CP_PACIFIC", issuer="SSNLF", relation="HOLDS_EQUITY", exposure_pct=0.22),
    dict(counterparty="CP_PACIFIC", issuer="AAPL", relation="HOLDS_VIA_FUND", exposure_pct=0.13),
    dict(counterparty="CP_PACIFIC", issuer="ASML", relation="HOLDS_EQUITY", exposure_pct=0.13),

    dict(counterparty="CP_MERIDIAN", issuer="XOM", relation="HOLDS_EQUITY", exposure_pct=0.28),
    dict(counterparty="CP_MERIDIAN", issuer="SHEL", relation="HOLDS_EQUITY", exposure_pct=0.22),
    dict(counterparty="CP_MERIDIAN", issuer="LMT", relation="HOLDS_EQUITY", exposure_pct=0.22),
    dict(counterparty="CP_MERIDIAN", issuer="BA", relation="HOLDS_EQUITY", exposure_pct=0.16),
    dict(counterparty="CP_MERIDIAN", issuer="RTX", relation="HOLDS_EQUITY", exposure_pct=0.12),

    dict(counterparty="CP_NORTHBRIDGE", issuer="JPM", relation="HOLDS_BONDS", exposure_pct=0.35),
    dict(counterparty="CP_NORTHBRIDGE", issuer="C", relation="HOLDS_BONDS", exposure_pct=0.28),
    dict(counterparty="CP_NORTHBRIDGE", issuer="DBK", relation="HOLDS_BONDS", exposure_pct=0.24),
    dict(counterparty="CP_NORTHBRIDGE", issuer="AIG", relation="HOLDS_BONDS", exposure_pct=0.13),

    dict(counterparty="CP_SUMMIT", issuer="MSFT", relation="HOLDS_EQUITY", exposure_pct=0.14),
    dict(counterparty="CP_SUMMIT", issuer="AAPL", relation="HOLDS_EQUITY", exposure_pct=0.14),
    dict(counterparty="CP_SUMMIT", issuer="JPM", relation="HOLDS_EQUITY", exposure_pct=0.12),
    dict(counterparty="CP_SUMMIT", issuer="XOM", relation="HOLDS_EQUITY", exposure_pct=0.12),
    dict(counterparty="CP_SUMMIT", issuer="GOOGL", relation="HOLDS_EQUITY", exposure_pct=0.12),
    dict(counterparty="CP_SUMMIT", issuer="LMT", relation="HOLDS_EQUITY", exposure_pct=0.10),
    dict(counterparty="CP_SUMMIT", issuer="BA", relation="HOLDS_EQUITY", exposure_pct=0.10),
    dict(counterparty="CP_SUMMIT", issuer="RIO", relation="HOLDS_EQUITY", exposure_pct=0.10),
    dict(counterparty="CP_SUMMIT", issuer="HSBC", relation="HOLDS_EQUITY", exposure_pct=0.06),

    dict(counterparty="CP_HELIX", issuer="NVDA", relation="HOLDS_EQUITY", exposure_pct=0.25),
    dict(counterparty="CP_HELIX", issuer="AVGO", relation="HOLDS_EQUITY", exposure_pct=0.20),
    dict(counterparty="CP_HELIX", issuer="MU", relation="HOLDS_EQUITY", exposure_pct=0.20),
    dict(counterparty="CP_HELIX", issuer="ASML", relation="HOLDS_EQUITY", exposure_pct=0.20),
    dict(counterparty="CP_HELIX", issuer="ARM", relation="HOLDS_EQUITY", exposure_pct=0.15),

    dict(counterparty="CP_CASCADE", issuer="JPM", relation="HOLDS_BONDS", exposure_pct=0.30),
    dict(counterparty="CP_CASCADE", issuer="BAC", relation="HOLDS_BONDS", exposure_pct=0.25),
    dict(counterparty="CP_CASCADE", issuer="WFC", relation="HOLDS_BONDS", exposure_pct=0.25),
    dict(counterparty="CP_CASCADE", issuer="C", relation="HOLDS_BONDS", exposure_pct=0.20),

    dict(counterparty="CP_IRONGATE", issuer="LMT", relation="LENDS_TO", exposure_pct=0.30),
    dict(counterparty="CP_IRONGATE", issuer="RTX", relation="LENDS_TO", exposure_pct=0.25),
    dict(counterparty="CP_IRONGATE", issuer="GD", relation="LENDS_TO", exposure_pct=0.25),
    dict(counterparty="CP_IRONGATE", issuer="CAT", relation="LENDS_TO", exposure_pct=0.20),

    dict(counterparty="CP_LATTICE", issuer="TSM", relation="HOLDS_EQUITY", exposure_pct=0.24),
    dict(counterparty="CP_LATTICE", issuer="NVDA", relation="HOLDS_EQUITY", exposure_pct=0.22),
    dict(counterparty="CP_LATTICE", issuer="MSFT", relation="HOLDS_EQUITY", exposure_pct=0.18),
    dict(counterparty="CP_LATTICE", issuer="ASML", relation="HOLDS_EQUITY", exposure_pct=0.18),
    dict(counterparty="CP_LATTICE", issuer="GOOGL", relation="HOLDS_EQUITY", exposure_pct=0.18),

    dict(counterparty="CP_VANTAGE", issuer="SHEL", relation="HOLDS_EQUITY", exposure_pct=0.18),
    dict(counterparty="CP_VANTAGE", issuer="DBK", relation="HOLDS_EQUITY", exposure_pct=0.18),
    dict(counterparty="CP_VANTAGE", issuer="ASML", relation="HOLDS_EQUITY", exposure_pct=0.18),
    dict(counterparty="CP_VANTAGE", issuer="TTE", relation="HOLDS_EQUITY", exposure_pct=0.16),
    dict(counterparty="CP_VANTAGE", issuer="RIO", relation="HOLDS_EQUITY", exposure_pct=0.15),
    dict(counterparty="CP_VANTAGE", issuer="UBS", relation="HOLDS_EQUITY", exposure_pct=0.15),

    dict(counterparty="CP_HARBOR", issuer="XOM", relation="HOLDS_EQUITY", exposure_pct=0.25),
    dict(counterparty="CP_HARBOR", issuer="SHEL", relation="HOLDS_EQUITY", exposure_pct=0.25),
    dict(counterparty="CP_HARBOR", issuer="BP", relation="HOLDS_EQUITY", exposure_pct=0.25),
    dict(counterparty="CP_HARBOR", issuer="MAERSK", relation="HOLDS_EQUITY", exposure_pct=0.25),

    dict(counterparty="CP_KESTREL", issuer="NVDA", relation="HOLDS_EQUITY", exposure_pct=0.45),
    dict(counterparty="CP_KESTREL", issuer="AAPL", relation="HOLDS_EQUITY", exposure_pct=0.30),
    dict(counterparty="CP_KESTREL", issuer="MSFT", relation="HOLDS_EQUITY", exposure_pct=0.25),

    dict(counterparty="CP_ORION", issuer="AIG", relation="HOLDS_BONDS", exposure_pct=0.35),
    dict(counterparty="CP_ORION", issuer="HSBC", relation="HOLDS_BONDS", exposure_pct=0.30),
    dict(counterparty="CP_ORION", issuer="UBS", relation="HOLDS_BONDS", exposure_pct=0.35),

    dict(counterparty="CP_DELTA", issuer="GS", relation="HOLDS_VIA_FUND", exposure_pct=0.30),
    dict(counterparty="CP_DELTA", issuer="MS", relation="HOLDS_VIA_FUND", exposure_pct=0.30),
    dict(counterparty="CP_DELTA", issuer="NVDA", relation="HOLDS_EQUITY", exposure_pct=0.40),

    dict(counterparty="CP_ANCHOR", issuer="JPM", relation="HOLDS_BONDS", exposure_pct=0.28),
    dict(counterparty="CP_ANCHOR", issuer="WFC", relation="HOLDS_BONDS", exposure_pct=0.24),
    dict(counterparty="CP_ANCHOR", issuer="BAC", relation="HOLDS_BONDS", exposure_pct=0.24),
    dict(counterparty="CP_ANCHOR", issuer="UBS", relation="HOLDS_BONDS", exposure_pct=0.24),

    dict(counterparty="CP_TRIREME", issuer="MAERSK", relation="LENDS_TO", exposure_pct=0.50),
    dict(counterparty="CP_TRIREME", issuer="SHEL", relation="HOLDS_EQUITY", exposure_pct=0.25),
    dict(counterparty="CP_TRIREME", issuer="XOM", relation="HOLDS_EQUITY", exposure_pct=0.25),

    dict(counterparty="CP_EQUINOX", issuer="LMT", relation="HOLDS_EQUITY", exposure_pct=0.20),
    dict(counterparty="CP_EQUINOX", issuer="XOM", relation="HOLDS_EQUITY", exposure_pct=0.20),
    dict(counterparty="CP_EQUINOX", issuer="NVDA", relation="HOLDS_EQUITY", exposure_pct=0.20),
    dict(counterparty="CP_EQUINOX", issuer="DBK", relation="HOLDS_BONDS", exposure_pct=0.20),
    dict(counterparty="CP_EQUINOX", issuer="RIO", relation="HOLDS_EQUITY", exposure_pct=0.20),

    dict(counterparty="CP_GRANITE", issuer="RIO", relation="HOLDS_EQUITY", exposure_pct=0.45),
    dict(counterparty="CP_GRANITE", issuer="FCX", relation="HOLDS_EQUITY", exposure_pct=0.35),
    dict(counterparty="CP_GRANITE", issuer="CAT", relation="HOLDS_EQUITY", exposure_pct=0.20),
]

# ---------------------------------------------------------------------------
# 6. REAL PUBLIC NEWS EVIDENCE (headline + URL + short derived snippet only;
#    no full article text redistributed)
# ---------------------------------------------------------------------------
NEWS_REAL = [
    dict(id="r1", date="2026-06-04", entities=["TSM", "NVDA", "AMD"], keywords=["AI", "FOUNDRY", "TAIWAN", "SUPPLY_DISRUPTION"],
         title="TSMC CEO Warns Chip Supply Won't Meet AI-Fueled Demand for Years", source="Bloomberg",
         url="https://www.bloomberg.com/news/articles/2026-06-04/tsmc-ceo-warns-chip-supply-won-t-meet-ai-fueled-demand-for-years",
         snippet="TSMC's global chip supply will fall short of AI-fuelled demand for years, CEO C.C. Wei said."),
    dict(id="r2", date="2026-06-04", entities=["TSM"], keywords=["AI", "TAIWAN", "CAPEX"],
         title="TSMC posts record profits on continued AI demand", source="CNBC",
         url="https://www.cnbc.com/2026/04/16/tsmc-q1-profit-58-percent-ai-chip-demand-record.html",
         snippet="TSMC Q1 2026 profit rose sharply on continued AI-driven demand."),
    dict(id="r3", date="2026-07-15", entities=["TSM"], keywords=["AI", "TAIWAN", "CAPEX"],
         title="TSMC to invest another $100 billion in US as Q2 profit surges", source="Reuters",
         url="https://www.reuters.com/world/asia-pacific/tsmcs-second-quarter-profit-seen-hitting-record-ai-boom-2026-07-15/",
         snippet="TSMC Q2 profit surged 77% on AI boom; raised US and capex plans."),
    dict(id="r4", date="2026-03-24", entities=["AVGO", "TSM"], keywords=["SEMICONDUCTORS", "SUPPLY_DISRUPTION", "FOUNDRY"],
         title="Broadcom flags supply constraints, says TSMC capacity a bottleneck", source="Reuters",
         url="https://www.reuters.com/world/asia-pacific/broadcom-flags-supply-constraints-says-tsmc-capacity-bottleneck-2026-03-24/",
         snippet="Broadcom said TSMC production capacity limitations are a supply bottleneck."),
    dict(id="r5", date="2026-05-27", entities=["NVDA", "MSFT", "GOOGL", "AMZN", "META"], keywords=["AI_BUBBLE", "CAPEX", "AI_MONETIZATION"],
         title="Investors stay calm as AI capex boom eclipses dotcom mania", source="Reuters",
         url="https://www.reuters.com/commentary/reuters-open-interest/investors-stay-calm-ai-capex-boom-eclipses-dotcom-mania-2026-05-27/",
         snippet="AI capex projected near $800bn in 2026; Morgan Stanley sees $1.12tn in 2027; PIMCO flags overbuild and debt-financing risk."),
    dict(id="r6", date="2026-06-29", entities=["MSFT", "GOOGL", "AMZN", "META"], keywords=["AI_BUBBLE", "CAPEX", "RECESSION"],
         title="The central bank of central banks sees a $1 trillion AI investment boom risk", source="Fortune / BIS",
         url="https://fortune.com/2026/06/29/bis-central-bank-warning-hyperscaler-data-center-1-trillion-gamble-recession/",
         snippet="BIS warns hyperscaler AI/data-centre spending concentration poses a macro risk."),
    dict(id="r7", date="2025-12-03", entities=["MSFT", "GOOGL", "AMZN", "META"], keywords=["AI_BUBBLE", "CAPEX"],
         title="Bank of America says we're in an AI 'air pocket,' not a bubble", source="Fortune / BofA",
         url="https://fortune.com/2025/12/03/is-ai-a-bubble-bofa-says-air-pocket-in-2026-data-center-debt/",
         snippet="BofA: aggressive hyperscaler capex increasingly debt-financed; risk if monetisation lags."),
    dict(id="r8", date="2026-06-10", entities=["NVDA", "AMD", "MSFT"], keywords=["AI_BUBBLE", "CAPEX"],
         title="Goldman Sachs says the AI boom is bigger than investors think", source="Business Insider / Goldman Sachs",
         url="https://www.businessinsider.com/stock-market-wall-street-tech-selloff-ai-token-goldman-sachs-2026-6",
         snippet="Goldman: 2027 hyperscaler capex consensus too conservative; could reach ~$1.1tn."),
    dict(id="r9", date="2026-02-23", entities=["TSM"], keywords=["TAIWAN", "FOUNDRY", "CAPEX"],
         title="TSMC Speeds up Expansion in Taiwan: up to 10 Fabs Under Construction", source="TrendForce",
         url="https://www.trendforce.com/news/2026/02/23/news-tsmc-speeds-up-expansion-in-taiwan-up-to-10-fabs-reportedly-under-construction-or-starting-in-2026/",
         snippet="TrendForce reports up to 10 TSMC fabs under construction or starting in 2026 in Taiwan."),
    dict(id="r10", date="2026-07-08", entities=["LMT", "BA", "RTX", "NOC"], keywords=["DEFENSE", "NATO"],
         title="Fact Sheet: NATO allies commit to historic defense investment", source="The White House",
         url="https://www.whitehouse.gov/fact-sheets/2026/07/fact-sheet-president-donald-j-trump-secures-historic-defense-investment-from-nato-allies-powering-american-industry/",
         snippet="NATO Ankara Summit: allies announce major defense procurement deals with Lockheed Martin, Boeing, Northrop Grumman, RTX and others."),
    dict(id="r11", date="2026-07-07", entities=["LMT", "BA", "RTX", "NOC"], keywords=["DEFENSE", "NATO"],
         title="NATO touts $50 billion in arms deals as leaders meet in Ankara", source="Reuters",
         url="https://www.reuters.com/business/autos-transportation/defence-companies-sign-deals-nato-industry-forum-2026-07-07/",
         snippet="NATO members and defense contractors sign roughly $50bn in deals at the industry forum."),
    dict(id="r12", date="2026-01-26", entities=["SHEL", "BP", "TTE", "XOM"], keywords=["RUSSIA", "NATURAL_GAS", "ENERGY", "EUROPE"],
         title="EU countries give final approval to Russian gas ban", source="Reuters",
         url="https://www.reuters.com/business/energy/eu-countries-give-final-approval-russian-gas-ban-2026-01-26/",
         snippet="EU formally approves phase-out/ban of Russian gas imports, reshaping European energy supply."),
    dict(id="r13", date="2026-07-27", entities=["SHEL", "BP", "TTE"], keywords=["NATURAL_GAS", "ENERGY", "EUROPE"],
         title="Europe faces a long, cold winter as fuel buffers dwindle", source="Reuters",
         url="https://www.reuters.com/commentary/reuters-open-interest/europe-faces-long-cold-winter-fuel-buffers-dwindle-2026-07-27/",
         snippet="European gas storage buffers are running low heading into winter 2026."),
    dict(id="r14", date="2026-03-11", entities=["SHEL", "BP", "TTE"], keywords=["RUSSIA", "NATURAL_GAS", "GEOPOLITICS"],
         title="Mideast conflict may hasten Europe's gas divorce from Russia", source="Reuters",
         url="https://www.reuters.com/markets/commodities/mideast-conflict-may-hasten-europes-gas-divorce-russia-vladimirov-2026-03-11/",
         snippet="Middle East tensions add pressure to Europe's shift away from Russian gas."),
]

# ---------------------------------------------------------------------------
# 7. SYNTHETIC NEWS CORPUS (labelled). Extends the bundled sample corpus for
#    theme-radar demo density; used for co-mention/TF-IDF/clustering demo.
# ---------------------------------------------------------------------------
NEWS_SYNTHETIC = [
    dict(id="n1", date="2026-06-02", entities=["TSM", "NVDA", "AMD"], text="TSMC reported record advanced-node demand as NVIDIA and AMD compete for allocation of next-generation AI chip capacity in Taiwan."),
    dict(id="n2", date="2026-06-05", entities=["NVDA", "SKHY"], text="SK Hynix said high-bandwidth memory (HBM) supply for NVIDIA's AI accelerators remains sold out through next year amid surging data centre demand."),
    dict(id="n3", date="2026-06-10", entities=["TSM", "AAPL", "INTC"], text="Apple locks in TSMC's newest fabrication node for upcoming chips, while Intel pushes its own foundry roadmap to compete for leading-edge orders."),
    dict(id="n4", date="2026-06-14", entities=["MSFT", "NVDA"], text="Microsoft Azure signs a multi-year GPU supply agreement with NVIDIA to expand AI data centre capacity across hyperscale cloud regions."),
    dict(id="n5", date="2026-06-18", entities=["IBM", "INTC"], text="IBM and Intel both highlight enterprise AI and hybrid cloud roadmaps at industry conference, emphasizing on-premise inference chips."),
    dict(id="n6", date="2026-06-20", entities=["TSM", "SSNLF", "SKHY"], text="Taiwan, South Korea semiconductor manufacturers TSMC, Samsung and SK Hynix face rising capital expenditure for advanced packaging and HBM output."),
    dict(id="n7", date="2026-06-25", entities=["XOM", "SHEL"], text="ExxonMobil and Shell report resilient refining margins as global energy markets stay volatile amid OPEC+ supply decisions."),
    dict(id="n8", date="2026-06-28", entities=["BA", "LMT"], text="Boeing and Lockheed Martin see rising defense budgets across NATO members as governments increase military procurement spending."),
    dict(id="n9", date="2026-07-01", entities=["JPM", "C"], text="JPMorgan and Citigroup post strong trading revenue as market volatility boosts fixed income and equities trading desks."),
    dict(id="n10", date="2026-07-03", entities=["NVDA", "AMD", "MSFT"], text="AI bubble concerns resurface as analysts question whether hyperscaler capital expenditure on GPUs from NVIDIA and AMD can be justified by near-term returns."),
    dict(id="n11", date="2026-07-06", entities=["TSM", "NVDA", "AMD", "AAPL"], text="A magnitude 7.2 earthquake struck near Hsinchu, Taiwan, disrupting semiconductor fabrication at several TSMC plants and raising concerns for NVIDIA, AMD and Apple chip supply."),
    dict(id="n11b", date="2026-07-06", entities=["TSM", "SKHY"], text="Power outages following the Taiwan earthquake also affected nearby memory and packaging facilities linked to SK Hynix supply chains."),
    dict(id="n11c", date="2026-07-07", entities=["TSM", "MSFT", "NVDA"], text="Hyperscalers including Microsoft warn of potential AI chip delivery delays after the Taiwan earthquake disrupted TSMC's advanced packaging lines."),
    dict(id="n11d", date="2026-07-07", entities=["TSM", "AMAT", "ASML"], text="Equipment suppliers ASML and Applied Materials say a portion of tool installations near Hsinchu were paused for inspection after the earthquake."),
    dict(id="n12", date="2026-07-10", entities=["SHEL", "XOM"], text="Russia-Ukraine escalation raises fears over European natural gas supply, lifting Shell and ExxonMobil energy trading desks."),
    dict(id="n12b", date="2026-07-11", entities=["LMT", "BA"], text="Defense stocks Lockheed Martin and Boeing rally as Russia-Ukraine tensions escalate and European governments announce new defense spending packages."),
    dict(id="n12c", date="2026-07-12", entities=["DBK", "JPM"], text="European banks including Deutsche Bank face scrutiny over exposure to Russian counterparties as sanctions tighten amid the Ukraine crisis."),
    dict(id="n12d", date="2026-07-13", entities=["RTX", "NOC", "GD"], text="Raytheon, Northrop Grumman and General Dynamics see order backlogs grow as European NATO members accelerate defense procurement amid the Ukraine crisis."),
    dict(id="n13", date="2026-07-15", entities=["NVDA", "AMD", "MSFT", "TSM"], text="AI bubble correction fears deepen as NVIDIA, AMD and cloud hyperscalers see valuations slide on concerns over data centre overbuild and GPU depreciation."),
    dict(id="n13b", date="2026-07-16", entities=["SKHY", "SSNLF"], text="Memory makers SK Hynix and Samsung warn that a slowdown in AI capital expenditure could soften HBM demand growth next year."),
    dict(id="n13c", date="2026-07-17", entities=["GOOGL", "AMZN", "META"], text="Alphabet, Amazon and Meta all flag rising depreciation and power costs tied to aggressive AI data centre build-outs, reviving AI bubble debate."),
    dict(id="n14", date="2026-07-18", entities=["IBM", "MSFT"], text="IBM and Microsoft both pivot enterprise strategy toward generative AI and agentic software following renewed investor scrutiny of AI monetisation."),
    dict(id="n15", date="2026-07-20", entities=["TSM", "INTC"], text="Intel and TSMC both outline expanded US and Taiwan fabrication capacity amid ongoing export control tensions between the US and China over advanced chips."),
    dict(id="n16", date="2026-07-22", entities=["JPM", "C", "DBK"], text="Global banks JPMorgan, Citigroup and Deutsche Bank increase provisions tied to counterparty credit risk amid volatile rates and geopolitical uncertainty."),
    dict(id="n16b", date="2026-07-23", entities=["BAC", "WFC", "UBS"], text="Bank of America, Wells Fargo and UBS report deposit stability but flag close monitoring of wholesale funding markets amid rate volatility."),
    dict(id="n17", date="2026-07-25", entities=["XOM", "SHEL", "LMT"], text="Energy and defense names ExxonMobil, Shell and Lockheed Martin benefit from elevated geopolitical risk premium tied to the Russia-Ukraine conflict and Middle East tensions."),
    dict(id="n18", date="2026-07-28", entities=["NVDA", "SKHY", "TSM"], text="NVIDIA's next-generation AI accelerator roadmap depends heavily on TSMC's CoWoS advanced packaging and SK Hynix's HBM4 memory supply."),
    dict(id="n19", date="2026-08-01", entities=["AAPL", "TSM", "SSNLF"], text="Apple diversifies chip and display sourcing between TSMC and Samsung as geopolitical risk in the Taiwan Strait weighs on supply chain planning."),
    dict(id="n20", date="2026-08-03", entities=["BA", "LMT", "XOM"], text="Rising defense and energy capital expenditure lifts industrial order books for Boeing, Lockheed Martin and integrated oil majors including ExxonMobil."),
    dict(id="n21", date="2026-08-04", entities=["MAERSK", "SHEL"], text="Container shipping group Maersk flags Red Sea and Middle East routing disruptions, warning of higher freight costs feeding into energy logistics."),
    dict(id="n22", date="2026-08-05", entities=["RIO", "FCX"], text="Rio Tinto and Freeport-McMoRan highlight surging copper demand tied to AI data centre power infrastructure and grid buildout."),
    dict(id="n23", date="2026-08-06", entities=["AIG", "UBS", "CP_NORTHBRIDGE"], text="Insurers and European banks reassess fixed-income counterparty credit risk frameworks as rate volatility and geopolitical tension persist through the second half of 2026."),
    dict(id="n24", date="2026-05-15", entities=["ASML", "AMAT", "TSM"], text="Semiconductor equipment makers ASML and Applied Materials report backlog growth as foundries expand advanced-node and packaging capacity for AI chips."),
    dict(id="n25", date="2026-04-10", entities=["QCOM", "ARM", "AAPL"], text="Qualcomm and Arm continue architecture licensing disputes even as smartphone makers including Apple push further into on-device AI processing."),
]

# ---------------------------------------------------------------------------
# Write outputs
# ---------------------------------------------------------------------------
def main():
    entities = []
    for eid, name, sector, industry, country, region, ticker in ISSUERS:
        entities.append(dict(
            id=eid, name=name, node_type="Company/Issuer", sector=sector, industry=industry,
            country=country, region=region, ticker=ticker,
            has_market_data=(ticker in TICKERS_WITH_PRICES) if ticker else False,
            is_synthetic=False,
        ))
    for cid, name, industry, country, region in COUNTERPARTIES:
        entities.append(dict(
            id=cid, name=name, node_type="Counterparty", sector="Financials", industry=industry,
            country=country, region=region, ticker=None, has_market_data=False,
            is_synthetic=True,
        ))
    # country/region pseudo-nodes referenced by OPERATES_IN facts
    countries = sorted({e["country"] for e in entities if e["country"]})
    for c in countries:
        cid = c.upper().replace(" ", "_")
        entities.append(dict(id=cid, name=c, node_type="Country", sector=None, industry=None,
                              country=c, region=None, ticker=None, has_market_data=False, is_synthetic=False))
    for region_id in ["TAIWAN", "SOUTH_KOREA", "GERMANY", "EUROPE"]:
        # keyword-style geography nodes used directly by OPERATES_IN facts above
        if not any(e["id"] == region_id for e in entities):
            entities.append(dict(id=region_id, name=region_id.replace("_", " ").title(), node_type="Country/Region",
                                  sector=None, industry=None, country=None, region=None, ticker=None,
                                  has_market_data=False, is_synthetic=False))
    sectors = sorted({e["sector"] for e in entities if e.get("sector")})
    for s in sectors:
        sid = "SECTOR_" + s.upper().replace(" ", "_")
        entities.append(dict(id=sid, name=s + " (sector)", node_type="Sector", sector=None, industry=None,
                              country=None, region=None, ticker=None, has_market_data=False, is_synthetic=False))

    with open(os.path.join(DATA_DIR, "entities.json"), "w") as f:
        json.dump({"entities": entities}, f, indent=2)

    with open(os.path.join(DATA_DIR, "fact_edges.json"), "w") as f:
        json.dump({"fact_edges": FACT_EDGES}, f, indent=2)

    keywords = [dict(id=k, label=lbl, synonyms=syns) for k, lbl, syns in KEYWORDS]
    with open(os.path.join(DATA_DIR, "keywords.json"), "w") as f:
        json.dump({"keywords": keywords}, f, indent=2)

    with open(os.path.join(DATA_DIR, "entity_keyword_weights.json"), "w") as f:
        json.dump(ENTITY_KEYWORD_WEIGHTS, f, indent=2)

    counterparties = [dict(id=cid, name=name, industry=industry, country=country, region=region, is_synthetic=True)
                       for cid, name, industry, country, region in COUNTERPARTIES]
    with open(os.path.join(DATA_DIR, "counterparties.json"), "w") as f:
        json.dump({"counterparties": counterparties}, f, indent=2)

    with open(os.path.join(DATA_DIR, "exposure_edges.json"), "w") as f:
        json.dump({"exposure_edges": [dict(e, is_synthetic=True) for e in EXPOSURE_EDGES]}, f, indent=2)

    with open(os.path.join(DATA_DIR, "news_real.json"), "w") as f:
        json.dump({"documents": [dict(d, is_synthetic=False, source_type="REAL_PUBLIC_NEWS") for d in NEWS_REAL]}, f, indent=2)

    # Derive keywords/title/source for synthetic docs from the same
    # synonym list used at query time, so themes.py / event_parser.py can
    # treat real and synthetic news uniformly without special-casing.
    synonym_index = {}
    for kid, lbl, syns in KEYWORDS:
        for s in syns:
            synonym_index[s.lower()] = kid
        synonym_index[lbl.lower()] = kid
    sorted_syns = sorted(synonym_index.keys(), key=len, reverse=True)

    def derive_keywords(text):
        tl = text.lower()
        found = []
        for syn in sorted_syns:
            if syn in tl:
                kid = synonym_index[syn]
                if kid not in found:
                    found.append(kid)
        return found

    def derive_title(text):
        return text if len(text) <= 90 else text[:87].rsplit(" ", 1)[0] + "..."

    synthetic_docs = []
    for d in NEWS_SYNTHETIC:
        synthetic_docs.append(dict(
            d,
            title=derive_title(d["text"]),
            keywords=derive_keywords(d["text"]),
            source="Synthetic Narrative Corpus (POC)",
            snippet=d["text"],
            url=None,
            is_synthetic=True,
            source_type="SYNTHETIC_NARRATIVE",
        ))

    with open(os.path.join(DATA_DIR, "news_synthetic.json"), "w") as f:
        json.dump({"documents": synthetic_docs}, f, indent=2)

    print(f"Wrote {len(entities)} entities ({len(ISSUERS)} issuers, {len(COUNTERPARTIES)} synthetic counterparties, "
          f"{len(countries)} country nodes, {len(sectors)} sector nodes)")
    print(f"Wrote {len(FACT_EDGES)} fact edges")
    print(f"Wrote {len(KEYWORDS)} keywords")
    print(f"Wrote {len(EXPOSURE_EDGES)} exposure edges (SYNTHETIC)")
    print(f"Wrote {len(NEWS_REAL)} real news items + {len(NEWS_SYNTHETIC)} synthetic news items")


if __name__ == "__main__":
    main()
