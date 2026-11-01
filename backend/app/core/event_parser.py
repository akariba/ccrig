"""Event Studio pipeline (BUILD_MANDATE section 14): free-text event/
narrative -> detected entities/themes -> event type -> direct issuer
relevance -> propagated (2nd order) relevance via TWO ranking modes ->
counterparty relevance via an EXPLICIT exposure join performed only after
issuer relevance is already known.

Mode 1 = bounded deterministic typed-path traversal (meta-path).
Mode 2 = relation-aware Personalized PageRank (core/ppr.py).
The two modes are never averaged into a single number - both are exposed
side by side, in their own units, exactly as BUILD_MANDATE requires.
"""
import re
from .data import STORE
from . import paths as path_mod
from . import ppr as ppr_mod
from .config import DEFAULT_WEIGHTS

LEGAL_SUFFIX_RE = re.compile(
    r"\b(incorporated|corporation|holdings?|group|company|limited|"
    r"inc|corp|co|ltd|plc|se|sa|ag|n\.?v\.?|llc|lp)\b\.?", re.IGNORECASE)
_PAREN_RE = re.compile(r"\(([^)]+)\)")

EVENT_TYPE_RULES = [
    ("Geographic / Natural Disaster", {"earthquake", "disaster", "flood", "typhoon", "tsunami"}),
    ("Market / Funding Stress", {"bank", "funding", "collapse", "svb", "run", "liquidity", "deposit"}),
    ("Geopolitical / Sanctions", {"war", "sanction", "sanctions", "invasion", "escalation", "conflict", "nato"}),
    ("Thematic / Technology Shock", {"ai", "semiconductor", "chip", "export control", "gpu"}),
    ("Supply Chain Disruption", {"supply", "shortage", "bottleneck", "fab", "foundry"}),
]

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\.\-]*")


_ALIAS_INDEX_CACHE = None


def _entity_aliases(e):
    """Deterministic alias set for an entity: its ticker, any parenthetical
    abbreviation in the legal name (e.g. "...Co (TSMC)" -> "tsmc"), and the
    legal name with common corporate suffixes (Inc/Corp/Co/Ltd/plc/...)
    stripped, since news prose almost never uses the full legal form."""
    name = e["name"]
    aliases = set()
    for paren in _PAREN_RE.findall(name):
        p = paren.strip().lower()
        if p:
            aliases.add(p)
    base = _PAREN_RE.sub("", name).split(",")[0].strip()
    if base:
        aliases.add(base.lower())
        stripped = LEGAL_SUFFIX_RE.sub("", base).strip(" .,")
        if stripped:
            aliases.add(stripped.lower())
    if e.get("ticker"):
        aliases.add(e["ticker"].lower())
    return aliases


def _alias_index():
    """{alias: entity_id} built once from the entity master. Longer aliases
    are inserted after shorter ones don't matter here since lookup is by
    regex word-boundary match per alias, not longest-match-wins."""
    global _ALIAS_INDEX_CACHE
    if _ALIAS_INDEX_CACHE is None:
        idx = {}
        for e in STORE.entities_raw:
            if e["node_type"] not in ("Company/Issuer", "Counterparty"):
                continue
            for alias in _entity_aliases(e):
                idx.setdefault(alias, e["id"])
        _ALIAS_INDEX_CACHE = idx
    return _ALIAS_INDEX_CACHE


def _alias_only_entities(text):
    """The purely deterministic (RULE-source) match set, with no LLM
    involvement at all - used both by detect_entities() and by
    extract_ai_context() to distinguish DETERMINISTIC_MATCH from
    LLM_CANDIDATE_RESOLVED provenance."""
    tl = text.lower()
    found = set()
    for alias, eid in _alias_index().items():
        if re.search(r"\b" + re.escape(alias) + r"\b", tl):
            found.add(eid)
    return found


def get_ai_context(text):
    """Single point of contact with the AI provider for event understanding
    (BUILD_MANDATE AI usage rules): returns the provider's raw structured
    candidates (never trusted directly). Never raises - both provider
    implementations guarantee a well-formed dict even on failure."""
    from ..ai.provider import PROVIDER
    try:
        return PROVIDER.extract_event_context(text)
    except Exception:
        return {"entity_candidates": [], "countries": [], "concept_candidates": [],
                "event_type": None, "reasoning_summary": "AI extraction failed; deterministic-only fallback."}


def resolve_entity_candidates(candidate_texts):
    """Deterministic resolver: each raw candidate string is matched against
    the SAME alias index used for rule-based detection (exact alias match,
    or substring match above a conservative length-3 floor). Anything that
    doesn't resolve to a known entity is discarded here - the caller never
    sees an unresolved candidate as if it were a real entity_id."""
    idx = _alias_index()
    resolved, unresolved = set(), []
    for cand in candidate_texts:
        cl = str(cand).strip().lower()
        if not cl:
            continue
        if cl in idx:
            resolved.add(idx[cl])
            continue
        match = next((eid for alias, eid in idx.items() if len(alias) >= 3 and (alias in cl or cl in alias)), None)
        if match:
            resolved.add(match)
        else:
            unresolved.append(str(cand))
    return resolved, unresolved


def resolve_llm_entity_candidates(text, ai_context=None):
    """LLM/NER-assisted extraction -> entity resolver -> deterministic
    validation (BUILD_MANDATE AI usage rules): the provider may only return
    raw candidate name strings, never entity ids, scores, or edges. Each
    candidate is resolved against the SAME deterministic alias index used
    for rule-based detection; anything that doesn't resolve to a known
    entity is discarded. With the DeterministicProvider (no AI configured)
    this is a no-op (empty candidate list in, empty set out)."""
    ctx = ai_context if ai_context is not None else get_ai_context(text)
    candidate_texts = [c.get("text", c) if isinstance(c, dict) else c for c in ctx.get("entity_candidates", [])]
    resolved, _unresolved = resolve_entity_candidates(candidate_texts)
    return resolved


def detect_entities(text, ai_context=None):
    """Deterministic NER over the known entity universe: whole-word match
    against each entity's alias set (ticker / bracketed abbreviation /
    suffix-stripped legal name). Optionally augmented by an LLM-assisted
    candidate pass (see resolve_llm_entity_candidates) when an AI provider
    is configured; unresolved LLM candidates are always dropped, never
    trusted directly, so the offline deterministic path is unaffected when
    no provider is available. Pass a precomputed ai_context (from
    get_ai_context()) to avoid a second LLM round-trip within the same
    parse_event() call."""
    found = _alias_only_entities(text)
    found |= resolve_llm_entity_candidates(text, ai_context=ai_context)
    return sorted(found)


def detect_themes(text):
    tl = text.lower()
    found = {}
    for syn, theme_id in STORE.synonym_index.items():
        if re.search(r"\b" + re.escape(syn) + r"\b", tl):
            found[theme_id] = found.get(theme_id, 0) + 1
    return list(found.keys())


def detect_countries(text):
    tl = text.lower()
    countries = set()
    for e in STORE.entities_raw:
        c = e.get("country")
        if c and c.lower() in tl:
            countries.add(c)
    return sorted(countries)


def classify_event_type(text):
    tl = text.lower()
    for label, terms in EVENT_TYPE_RULES:
        for t in terms:
            if t in tl:
                return label
    return "General / Uncategorized"


def extract_ai_context(text, ai_context=None):
    """Structured, provenance-tagged extraction record for Event Studio's
    transparency panel (BUILD_MANDATE AI usage rules). Combines deterministic
    rule-based detection with validated LLM-assisted candidates; every item
    is tagged with exactly where it came from:

        DETERMINISTIC_MATCH        - rule/alias/synonym match, no AI involved
        LLM_CANDIDATE_RESOLVED     - AI candidate, resolved against the known
                                      entity/country universe
        LLM_CANDIDATE_UNVALIDATED  - AI candidate that did not resolve
        CURATED_THEME              - concept matched the curated 47-theme
                                      synonym index
        DISCOVERED_THEME           - concept matched an already-discovered
                                      cluster (core/themes.py)
        EPHEMERAL_EVENT_CONCEPT    - AI concept candidate that matched
                                      neither; kept for THIS extraction only,
                                      never persisted as a taxonomy node

    This is purely additive/auditable - it does not change which entities
    or themes feed Mode 1 / Mode 2 / the exposure join (detect_entities()
    already unions LLM-resolved entities on its own account)."""
    from . import themes as theme_mod

    ctx = ai_context if ai_context is not None else get_ai_context(text)

    alias_only_ids = _alias_only_entities(text)
    llm_candidate_texts = [c.get("text", c) if isinstance(c, dict) else c for c in ctx.get("entity_candidates", [])]
    llm_resolved_ids, llm_unresolved = resolve_entity_candidates(llm_candidate_texts)

    entity_records = [{"entity_id": eid, "name": STORE.entity(eid)["name"], "source": "DETERMINISTIC_MATCH"}
                       for eid in sorted(alias_only_ids)]
    entity_records += [{"entity_id": eid, "name": STORE.entity(eid)["name"], "source": "LLM_CANDIDATE_RESOLVED"}
                        for eid in sorted(llm_resolved_ids - alias_only_ids)]

    deterministic_countries = set(detect_countries(text))
    known_countries = {e.get("country") for e in STORE.entities_raw if e.get("country")}
    country_records = [{"country": c, "source": "DETERMINISTIC_MATCH"} for c in sorted(deterministic_countries)]
    for c in ctx.get("countries", []):
        if c in deterministic_countries:
            continue
        source = "LLM_CANDIDATE_RESOLVED" if c in known_countries else "LLM_CANDIDATE_UNVALIDATED"
        country_records.append({"country": c, "source": source})

    deterministic_theme_ids = set(detect_themes(text))
    concept_records = [{"concept": STORE.keywords_by_id[tid]["label"], "theme_id": tid, "source": "CURATED_THEME"}
                        for tid in sorted(deterministic_theme_ids) if tid in STORE.keywords_by_id]
    discovered = theme_mod.discover_themes()

    def _discovered_match(tl_term, disc_theme):
        # Require >=2 overlapping words (not a single generic term like
        # "equipment") between the candidate phrase and the cluster's own
        # representative terms/label - a single shared common word is not
        # a reliable enough signal for a POC-scale keyphrase match.
        term_words = set(tl_term.split())
        rep_words = {t.lower() for t in disc_theme.get("representative_terms", [])}
        rep_words |= set(disc_theme["label"].lower().replace("/", " ").split())
        return len(term_words & rep_words) >= 2

    for term in ctx.get("concept_candidates", []):
        tl_term = str(term).lower().strip()
        if not tl_term:
            continue
        tid = theme_mod.canonicalize(tl_term)
        if tid:
            if tid not in deterministic_theme_ids:
                concept_records.append({"concept": STORE.keywords_by_id[tid]["label"], "theme_id": tid, "source": "CURATED_THEME"})
            continue  # already represented (either just added, or found earlier) - never falls through to ephemeral
        disc_match = next((d for d in discovered if _discovered_match(tl_term, d)), None)
        if disc_match:
            concept_records.append({"concept": disc_match["label"], "theme_id": disc_match["theme_id"], "source": "DISCOVERED_THEME"})
            continue
        concept_records.append({"concept": str(term), "theme_id": None, "source": "EPHEMERAL_EVENT_CONCEPT"})

    from ..ai.provider import PROVIDER
    return {
        "entities": entity_records,
        "unresolved_llm_entity_candidates": llm_unresolved,
        "countries": country_records,
        "concepts": concept_records,
        "ai_event_type_suggestion": ctx.get("event_type"),
        "ai_reasoning_summary": ctx.get("reasoning_summary"),
        "ai_mode": PROVIDER.mode,
    }


def direct_relevance(entities, themes):
    """Entities directly mentioned (weight 1.0, source=MENTION) union
    entities strongly weighted on a detected theme (source=THEME)."""
    relevance = {eid: {"score": 1.0, "sources": ["MENTION"]} for eid in entities}
    for theme_id in themes:
        weights = {eid: STORE.entity_keyword_weights.get(eid, {}).get(theme_id)
                   for eid in STORE.browsable_ids}
        for eid, w in weights.items():
            if w and w > 0.3:
                if eid in relevance:
                    relevance[eid]["sources"].append(f"THEME:{theme_id}")
                    relevance[eid]["score"] = max(relevance[eid]["score"], w)
                else:
                    relevance[eid] = {"score": w, "sources": [f"THEME:{theme_id}"]}
    return relevance


def mode1_bounded_traversal(direct_ids, themes, max_hops=2, decay=0.65):
    """Deterministic meta-path propagation: walk supply-chain fact edges
    outward from each directly-relevant entity, decaying score per hop."""
    propagated = {}
    typed_paths = []
    theme_for_path = themes[0] if themes else "UNSPECIFIED"
    for root in direct_ids:
        chain_paths = path_mod.supply_chain_propagation_paths(theme_for_path, root, max_hops=max_hops)
        for p in chain_paths:
            hop_count = len(p["hops"])
            last_hop = p["hops"][-1]
            target = last_hop["to"] if last_hop["direction"] == "FORWARD" else last_hop["from"]
            crit = last_hop.get("criticality") or 0.5
            score = crit * (decay ** (hop_count - 1))
            if target not in propagated or propagated[target]["score"] < score:
                propagated[target] = {"score": round(score, 4), "via": root, "hops": hop_count}
            typed_paths.append(p)
    return propagated, typed_paths


def event_relevance_map(direct, mode1_ranked, mode2_ranked):
    """Single per-issuer EventRelevance(E,i) used ONLY to weight the Layer C
    exposure join below - it is never substituted for, or displayed as,
    Mode 1 or Mode 2's own results, which stay separate per BUILD_MANDATE.

    direct mentions/theme hits and Mode 1's decayed-criticality score are
    already on a comparable 0-1 scale and are taken as-is (max across
    sources). Mode 2's PPR probability mass is on a different,
    corpus-size-dependent scale, so it is normalised against its own max
    and damped (0.5x) before contributing here, reflecting that
    PPR-only support is a weaker signal than a direct hit or a typed-path
    match."""
    rel = {}
    for eid, d in direct.items():
        rel[eid] = max(rel.get(eid, 0.0), d["score"])
    for r in mode1_ranked:
        rel[r["entity_id"]] = max(rel.get(r["entity_id"], 0.0), r["score"])
    if mode2_ranked:
        max_ppr = max((r["ppr_score"] for r in mode2_ranked), default=0.0) or 1.0
        for r in mode2_ranked:
            normalized = (r["ppr_score"] / max_ppr) * 0.5
            rel[r["entity_id"]] = max(rel.get(r["entity_id"], 0.0), normalized)
    return rel


def counterparty_join(relevant_issuer_ids, event_relevance):
    """Layer C join - executed ONLY after issuer relevance is finalised.

    CPRelevance(C, E) = Sum over relevant issuers i of
    Exposure(C, i) * EventRelevance(E, i) - NOT a raw sum of exposure_pct.
    Portfolios sum to ~100% exposure, so a raw sum would let a
    fully-diversified counterparty with zero real linkage to the event
    still score near 1.0 just from portfolio breadth; weighting by each
    issuer's event relevance fixes that."""
    cp_paths = []
    cp_scores = {}
    # callers pass an ORDERED sequence (see parse_event); a set would make the
    # path order and the float accumulation order depend on the hash seed
    for issuer_id in relevant_issuer_ids:
        rel = event_relevance.get(issuer_id, 0.0)
        for p in path_mod.counterparty_exposure_paths(issuer_id):
            cp_paths.append(p)
            cp = p["counterparty"]
            exposure = p.get("exposure_pct") or 0
            entry = cp_scores.setdefault(cp, {"exposure_weighted_relevance": 0.0, "issuers": []})
            entry["exposure_weighted_relevance"] += exposure * rel
            entry["issuers"].append({
                "issuer": issuer_id, "exposure_pct": exposure,
                "event_relevance": round(rel, 4), "relation": p["relation"],
            })
    for cp, entry in cp_scores.items():
        entry["exposure_weighted_relevance"] = round(entry["exposure_weighted_relevance"], 4)
    return cp_scores, cp_paths


def parse_event(text, max_hops=2, min_score=0.05, sector=None, geography=None, top_k=15,
                 news_cutoff_date=None):
    ai_context = get_ai_context(text)  # single AI round-trip, reused below
    entities = detect_entities(text, ai_context=ai_context)
    themes = detect_themes(text)
    countries = detect_countries(text)
    event_type = classify_event_type(text)
    ai_extraction = extract_ai_context(text, ai_context=ai_context)

    # geographic propagation: entities headquartered/operating in a
    # detected country also become directly relevant (P4 pattern).
    geo_entities = []
    for c in countries:
        for p in path_mod.geographic_paths(c):
            geo_entities.append(p["company"])

    # Order matters downstream (Mode 1 path order, tie-breaks, the 40-path cap),
    # so it is explicit: mentioned entities first (detect_entities returns them
    # sorted by id), then geographic ones in entity-master order, no duplicates.
    direct = direct_relevance(list(dict.fromkeys(entities + geo_entities)), themes)
    direct_ids = list(direct.keys())

    propagated, typed_paths = mode1_bounded_traversal(direct_ids, themes, max_hops=max_hops)
    ppr_result = ppr_mod.personalized_pagerank(direct_ids, top_k=top_k * 2) if direct_ids else {"results": []}

    def passes_filters(eid):
        e = STORE.entity(eid)
        if not e:
            return False
        if sector and e.get("sector") != sector:
            return False
        if geography and e.get("country") != geography and e.get("region") != geography:
            return False
        return True

    mode1_ranked = sorted(
        [{"entity_id": eid, **data} for eid, data in propagated.items() if data["score"] >= min_score and passes_filters(eid)],
        key=lambda r: (-r["score"], r["entity_id"]),   # ties: entity id, never insertion order
    )[:top_k]
    mode2_ranked = [r for r in ppr_result.get("results", []) if passes_filters(r["entity_id"])][:top_k]

    relevant_issuers = set(direct_ids) | {r["entity_id"] for r in mode1_ranked} | {r["entity_id"] for r in mode2_ranked}
    relevant_issuers &= set(STORE.issuer_ids)
    event_relevance = event_relevance_map(direct, mode1_ranked, mode2_ranked)
    # The join accumulates floating-point sums and lists issuers per
    # counterparty, so its iteration order must be fixed: most event-relevant
    # issuer first, ties by issuer id.
    ordered_issuers = sorted(relevant_issuers, key=lambda i: (-event_relevance.get(i, 0.0), i))
    cp_scores, cp_paths = counterparty_join(ordered_issuers, event_relevance)

    return {
        "input_text": text,
        "event_type": event_type,
        "ai_context_extraction": ai_extraction,
        "detected_entities": entities,
        "detected_themes": [{"id": t, "label": STORE.keywords_by_id[t]["label"]} for t in themes if t in STORE.keywords_by_id],
        "detected_countries": countries,
        "direct_relevance": [{"entity_id": eid, **data} for eid, data in direct.items()],
        "mode1_bounded_traversal": {
            "description": "Deterministic bounded typed-path traversal (meta-path), decay=0.65 per hop",
            "max_hops": max_hops,
            "results": mode1_ranked,
        },
        "mode2_personalized_pagerank": {
            "description": "Relation-aware Personalized PageRank over Layer A (fact) + Layer B (derived) edges only. Units are NOT comparable to Mode 1 decayed-criticality scores.",
            "results": mode2_ranked,
        },
        "typed_paths": typed_paths[:40],
        "relevant_counterparties": [
            {"counterparty": cp, **data} for cp, data in
            sorted(cp_scores.items(), key=lambda x: (-x[1]["exposure_weighted_relevance"], x[0]))
        ],
        "counterparty_exposure_paths": cp_paths,
        "filters_applied": {"max_hops": max_hops, "min_score": min_score, "sector": sector, "geography": geography},
    }
