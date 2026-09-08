"""Universal Search / AI Copilot dispatcher (BUILD_MANDATE section 5).
Handles the four required query types: entity, theme/concept, event/
narrative (free text), counterparty. Intent classification may use the AI
provider (deterministic fallback is always available); the actual lookup
logic is 100% deterministic regardless of which provider classified it.
"""
import re
from fastapi import APIRouter, Query
from ..core.data import STORE
from ..core import themes as theme_mod, event_parser
from ..ai.provider import PROVIDER

router = APIRouter(prefix="/api/search", tags=["search"])


def _match_entity(q):
    ql = q.strip().lower()
    exact = STORE.entities_by_id.get(q.strip().upper())
    if exact and exact["node_type"] in ("Company/Issuer", "Counterparty"):
        return [exact]
    matches = []
    # Word-boundary-anchored, not a raw substring test - "ai" must not match
    # inside "taiwan" (it isn't a word start there), so a theme query like
    # "AI" doesn't get hijacked into an unrelated entity hit. Still matches
    # a partial word start, e.g. "sam" -> "Samsung".
    pattern = re.compile(r"\b" + re.escape(ql), re.IGNORECASE) if ql else None
    for eid in STORE.browsable_ids:
        e = STORE.entity(eid)
        if (pattern and pattern.search(e["name"])) or (e.get("ticker") and ql == e["ticker"].lower()):
            matches.append(e)
    return matches


def _normalize_word(w: str) -> str:
    return w[:-1] if w.endswith("s") and len(w) > 3 else w


def _match_theme(q):
    theme_id = theme_mod.canonicalize(q)
    if theme_id:
        return theme_mod.theme_detail(theme_id)
    ql = q.lower()
    ql_words = {_normalize_word(w) for w in ql.split()}
    for kw in STORE.keywords:
        label = kw["label"].lower()
        # Substring match in EITHER direction - a short query like "rates"
        # matching the longer label "interest rates" was already handled,
        # but a longer natural-language query like "interest rate
        # volatility" containing the shorter theme label "interest rates"
        # was not, since the original check only tested query-in-label.
        if label in ql or ql in label:
            return theme_mod.theme_detail(kw["id"])
        # Word-level fallback (singular/plural normalized): every word in
        # the theme label must appear in the query, e.g. "interest rate
        # volatility" contains {interest, rate} from label "interest rates".
        label_words = {_normalize_word(w) for w in label.split()}
        if label_words and label_words <= ql_words:
            return theme_mod.theme_detail(kw["id"])
    return None


@router.get("")
def universal_search(q: str = Query(..., min_length=1), max_hops: int = 2, min_score: float = 0.05):
    intent = PROVIDER.classify_query_intent(q)
    entity_matches = _match_entity(q)
    theme_match = _match_theme(q)

    result = {
        "query": q,
        "ai_intent_classification": intent,
        "ai_mode": PROVIDER.mode,
        "entity_matches": [{"id": e["id"], "name": e["name"], "node_type": e["node_type"]} for e in entity_matches],
        "theme_match": {"theme_id": theme_match["theme_id"], "label": theme_match["label"]} if theme_match else None,
    }

    # Deterministic dispatch: prefer an exact entity hit, then theme, then
    # treat the whole string as a free-text event/narrative query.
    if len(entity_matches) == 1:
        e = entity_matches[0]
        result["resolved_as"] = "counterparty" if e["node_type"] == "Counterparty" else "entity"
        result["resolved_id"] = e["id"]
    elif theme_match and not entity_matches:
        result["resolved_as"] = "theme"
        result["resolved_id"] = theme_match["theme_id"]
    elif len(q.split()) >= 4:
        result["resolved_as"] = "event"
        result["event_result"] = event_parser.parse_event(q, max_hops=max_hops, min_score=min_score)
        result["ai_event_summary"] = PROVIDER.summarize_event(result["event_result"])
    else:
        result["resolved_as"] = "ambiguous"

    result["ai_followup_suggestions"] = PROVIDER.suggest_followups(f"query={q}, resolved_as={result.get('resolved_as')}")
    return result
