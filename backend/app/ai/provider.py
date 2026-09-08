"""AIProvider abstraction (BUILD_MANDATE section 27).

AI is used ONLY for: intent classification of the universal search box,
entity/event/concept extraction assistance, theme labelling, evidence
summarisation, natural-language explanation of ALREADY-COMPUTED facts, and
suggested follow-up questions. It is NEVER used for bulk pairwise scoring -
that is entirely deterministic/statistical (core/scoring.py).

DeterministicProvider has zero external dependencies and is always
available, so the whole application works with no API key configured
(DEMO/OFFLINE mode). OpenAICompatibleProvider is used automatically instead
when AI_BASE_URL/AI_API_KEY/AI_MODEL are all set (ENHANCED AI mode), and
falls back to the deterministic provider on any request failure so the app
never breaks because AI isn't configured or is unreachable.
"""
import json
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from ..core.config import AI_ENABLED, AI_BASE_URL, AI_API_KEY, AI_MODEL


class AIProvider(ABC):
    @abstractmethod
    def classify_query_intent(self, text):
        ...

    @abstractmethod
    def explain_relationship(self, entity_a_name, entity_b_name, vector, composite):
        ...

    @abstractmethod
    def explain_path(self, path_obj):
        ...

    @abstractmethod
    def summarize_event(self, event_result):
        ...

    @abstractmethod
    def label_theme(self, top_terms):
        ...

    @abstractmethod
    def suggest_followups(self, context_summary):
        ...

    @abstractmethod
    def answer_query(self, query, context_snippets):
        ...

    @abstractmethod
    def extract_entities(self, text):
        """Return a list of RAW candidate entity-name strings mentioned in
        text (NER only) - never entity ids, scores, or relationships. The
        caller (core/event_parser.py) is solely responsible for resolving
        each candidate against the known entity universe and discarding
        anything that doesn't match; the provider must never be trusted to
        know the graph."""
        ...

    @abstractmethod
    def extract_event_context(self, text):
        """Structured NER/understanding pass over free text. Returns a dict:

            {"entity_candidates": [{"text": str, "type": str}, ...],
             "countries": [str, ...],
             "concept_candidates": [str, ...],
             "event_type": str | None,
             "reasoning_summary": str}

        The provider may ONLY return raw candidate strings and a short
        rationale - never entity ids, scores, weights, or graph edges, and
        no chain-of-thought. core/event_parser.py is solely responsible for
        resolving every candidate against the known entity/theme universe
        and discarding (or marking EPHEMERAL) anything that doesn't
        resolve. This method must NEVER raise - on any failure it returns
        the same empty shape DeterministicProvider does, so the rest of
        the pipeline always sees a well-formed dict."""
        ...


class DeterministicProvider(AIProvider):
    """Always-available, template/rule-based fallback. Every string it
    produces is built strictly from values already present in the
    deterministic result object passed in - it never invents an edge,
    score, or entity that isn't already there (Invariant #7)."""

    mode = "DETERMINISTIC_OFFLINE"

    def classify_query_intent(self, text):
        t = text.strip()
        if len(t.split()) <= 3 and t.upper() == t and t.isalpha():
            return {"intent": "entity", "confidence_basis": "short all-caps token, likely a ticker/entity id"}
        if any(w in t.lower() for w in ["cp_", "counterparty", "fund", "capital"]):
            return {"intent": "counterparty", "confidence_basis": "keyword match on counterparty vocabulary"}
        if len(t.split()) >= 5:
            return {"intent": "event", "confidence_basis": "long free-text narrative, likely an event/news query"}
        return {"intent": "theme", "confidence_basis": "short phrase, treated as a theme/concept lookup"}

    def explain_relationship(self, entity_a_name, entity_b_name, vector, composite):
        bits = []
        cv = composite.get("component_values", {})
        if cv.get("supply_chain"):
            bits.append(f"a documented supply-chain link (strength {cv['supply_chain']:.2f})")
        if cv.get("sector"):
            bits.append("shared sector classification" if cv["sector"] == 1.0 else "different sectors")
        if cv.get("semantic") is not None:
            bits.append(f"business-description similarity of {cv['semantic']:.2f}")
        if cv.get("market_positive"):
            bits.append(f"positive market co-movement ({cv['market_positive']:.2f})")
        if cv.get("market_negative"):
            bits.append(f"negative/inverse market co-movement ({cv['market_negative']:.2f})")
        if cv.get("news"):
            bits.append(f"shared news/theme co-mention signal of {cv['news']:.2f}")
        score = composite.get("score")
        score_txt = f"{score:.2f}" if score is not None else "unavailable (insufficient data)"
        body = "; ".join(bits) if bits else "only weak or missing signals across all measured components"
        return (f"AI explanation (deterministic): {entity_a_name} and {entity_b_name} have a composite "
                f"relatedness score of {score_txt}, driven by {body}. "
                f"Missing components: {', '.join(composite.get('missing_components', [])) or 'none'}.")

    def explain_path(self, path_obj):
        pattern = path_obj.get("pattern", "UNKNOWN_PATTERN")
        hops = path_obj.get("hops", [])
        if not hops:
            return f"AI explanation (deterministic): path pattern {pattern} has no traversable hops in the current dataset."
        hop_desc = []
        for h in hops:
            if "relation" in h:
                hop_desc.append(f"{h.get('from', h.get('theme_id',''))} --{h['relation']}--> {h.get('to','')}")
            else:
                hop_desc.append(str(h))
        return f"AI explanation (deterministic): {pattern} — " + " then ".join(hop_desc)

    def summarize_event(self, event_result):
        n_direct = len(event_result.get("direct_relevance", []))
        n_m1 = len(event_result.get("mode1_bounded_traversal", {}).get("results", []))
        n_m2 = len(event_result.get("mode2_personalized_pagerank", {}).get("results", []))
        n_cp = len(event_result.get("relevant_counterparties", []))
        themes = ", ".join(t["label"] for t in event_result.get("detected_themes", [])) or "none detected"
        return (f"AI explanation (deterministic): classified as '{event_result.get('event_type')}'. "
                f"Directly mentioned/theme-relevant entities: {n_direct}. Themes detected: {themes}. "
                f"Bounded typed-path traversal (Mode 1) surfaced {n_m1} propagated entities; "
                f"relation-aware Personalized PageRank (Mode 2) surfaced {n_m2} entities (different units - not directly comparable). "
                f"{n_cp} synthetic counterparties are exposed to the resulting relevant issuer set via the Layer C exposure join.")

    def label_theme(self, top_terms):
        if not top_terms:
            return "Unlabelled theme"
        def _cap(term):
            # Preserve existing casing for tickers/acronyms (e.g. AAPL, HBM);
            # only title-case plain lowercase words.
            return term if term.isupper() else term.capitalize()
        return " / ".join(_cap(t) for t in top_terms[:3])

    def suggest_followups(self, context_summary):
        return [
            "Show the relationship vector decomposition for the top-ranked entity.",
            "Open Graph Explorer for a 2-hop ego view of this entity.",
            "Run this same query through the Model Lab with the Supply-chain shock preset.",
        ]

    def answer_query(self, query, context_snippets):
        joined = " ".join(context_snippets[:5])
        return (f"AI explanation (deterministic): based only on the computed results already shown "
                f"({len(context_snippets)} evidence item(s)), here is a plain-language summary: {joined}")

    def extract_entities(self, text):
        # No LLM available offline; core/event_parser.py's own alias-based
        # matcher is the sole (and sufficient) source of entity detection.
        return [c["text"] for c in self.extract_event_context(text)["entity_candidates"]]

    def extract_event_context(self, text):
        # No LLM available offline; core/event_parser.py's own rule-based
        # detectors are the sole source of entities/countries/themes. This
        # empty shape is also the universal fallback OpenAICompatibleProvider
        # returns on any request failure, so downstream code only ever
        # handles one dict shape.
        return {"entity_candidates": [], "countries": [], "concept_candidates": [],
                "event_type": None, "reasoning_summary": "Deterministic offline mode: no LLM-assisted "
                "extraction available; relying entirely on rule-based entity/theme/country detection."}


class OpenAICompatibleProvider(AIProvider):
    """Thin client for any OpenAI-compatible /chat/completions endpoint.
    Every method still receives the deterministic result object and is
    instructed, via the system prompt, to summarise ONLY that object - it
    is a phrasing layer on top of DeterministicProvider's structured
    inputs, not a source of new facts. Falls back to DeterministicProvider
    on any error."""

    mode = "ENHANCED_AI"

    def __init__(self):
        self._fallback = DeterministicProvider()

    def _chat(self, system, user, max_tokens=220):
        try:
            payload = json.dumps({
                "model": AI_MODEL,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_tokens": max_tokens,
                "temperature": 0.2,
            }).encode()
            req = urllib.request.Request(
                AI_BASE_URL.rstrip("/") + "/chat/completions",
                data=payload,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {AI_API_KEY}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:  # noqa: BLE001 - AI must never break the app
            return None

    SYSTEM_PROMPT = ("You are a credit/counterparty-risk analyst assistant. Summarise ONLY the structured "
                      "facts given to you in plain, precise language. Never invent an entity, edge, score, or "
                      "source that is not explicitly present in the provided data. If data is missing, say so.")

    def classify_query_intent(self, text):
        out = self._chat(self.SYSTEM_PROMPT,
                          f"Classify this search query as one of: entity, theme, event, counterparty. "
                          f"Reply with just the single word. Query: {text}")
        if out and out.strip().lower() in ("entity", "theme", "event", "counterparty"):
            return {"intent": out.strip().lower(), "confidence_basis": "LLM intent classification"}
        return self._fallback.classify_query_intent(text)

    def explain_relationship(self, entity_a_name, entity_b_name, vector, composite):
        det = self._fallback.explain_relationship(entity_a_name, entity_b_name, vector, composite)
        out = self._chat(self.SYSTEM_PROMPT,
                          f"Rephrase this analyst note in 2-3 fluent sentences, keeping every number: {det}")
        return f"AI explanation ({self.mode}): {out}" if out else det

    def explain_path(self, path_obj):
        det = self._fallback.explain_path(path_obj)
        out = self._chat(self.SYSTEM_PROMPT, f"Rephrase this path explanation in one fluent sentence: {det}")
        return f"AI explanation ({self.mode}): {out}" if out else det

    def summarize_event(self, event_result):
        det = self._fallback.summarize_event(event_result)
        out = self._chat(self.SYSTEM_PROMPT, f"Rephrase this event-analysis summary for a risk committee, 3-4 sentences: {det}")
        return f"AI explanation ({self.mode}): {out}" if out else det

    def label_theme(self, top_terms):
        out = self._chat(self.SYSTEM_PROMPT, f"Give a short (2-4 word) label for a news theme with top terms: {', '.join(top_terms)}")
        return out or self._fallback.label_theme(top_terms)

    def suggest_followups(self, context_summary):
        out = self._chat(self.SYSTEM_PROMPT,
                          f"Given this analysis context, suggest 3 short follow-up questions an analyst could ask next, one per line: {context_summary}")
        if out:
            lines = [l.strip("- ").strip() for l in out.splitlines() if l.strip()]
            if lines:
                return lines[:3]
        return self._fallback.suggest_followups(context_summary)

    def answer_query(self, query, context_snippets):
        det = self._fallback.answer_query(query, context_snippets)
        out = self._chat(self.SYSTEM_PROMPT,
                          f"Answer the analyst's question using ONLY these evidence snippets (do not add outside facts). "
                          f"Question: {query}\nEvidence: {' | '.join(context_snippets[:8])}")
        return f"AI explanation ({self.mode}): {out}" if out else det

    def extract_entities(self, text):
        return [c["text"] for c in self.extract_event_context(text)["entity_candidates"]]

    EXTRACTION_SYSTEM_PROMPT = (
        "You are a named-entity and concept extractor for a counterparty-risk analyst platform. "
        "Extract ONLY what is literally present or clearly implied in the text. Never invent facts, "
        "relationships, scores, or graph edges - you are producing RAW CANDIDATES for a separate "
        "deterministic resolver, not final answers. Reply with ONLY a single JSON object, no prose, "
        "no markdown fences, matching exactly this shape:\n"
        '{"entity_candidates": [{"text": "<company/org name as written>", "type": "company"}], '
        '"countries": ["<country name>"], '
        '"concept_candidates": ["<short concept/theme phrase>"], '
        '"event_type": "<SHORT_SNAKE_CASE_LABEL>", '
        '"reasoning_summary": "<one short sentence>"}'
    )

    def extract_event_context(self, text):
        fallback = self._fallback.extract_event_context(text)
        out = self._chat(self.EXTRACTION_SYSTEM_PROMPT, f"Text: {text}", max_tokens=350)
        if not out:
            return fallback
        cleaned = out.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned[cleaned.find("{"):cleaned.rfind("}") + 1]
        try:
            parsed = json.loads(cleaned)
        except Exception:
            return fallback
        if not isinstance(parsed, dict):
            return fallback

        entity_candidates = []
        for c in parsed.get("entity_candidates", []) or []:
            if isinstance(c, dict) and c.get("text"):
                entity_candidates.append({"text": str(c["text"]), "type": str(c.get("type", "company"))})
            elif isinstance(c, str) and c.strip():
                entity_candidates.append({"text": c.strip(), "type": "company"})

        countries = [str(c) for c in (parsed.get("countries") or []) if isinstance(c, (str, int))]
        concept_candidates = [str(c) for c in (parsed.get("concept_candidates") or []) if isinstance(c, (str, int))]
        event_type = parsed.get("event_type")
        reasoning = parsed.get("reasoning_summary")

        return {
            "entity_candidates": entity_candidates,
            "countries": countries,
            "concept_candidates": concept_candidates,
            "event_type": str(event_type) if event_type else None,
            "reasoning_summary": str(reasoning) if reasoning else fallback["reasoning_summary"],
        }


def get_provider():
    if AI_ENABLED:
        return OpenAICompatibleProvider()
    return DeterministicProvider()


PROVIDER = get_provider()
