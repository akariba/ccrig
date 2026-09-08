"""Dynamic Theme Radar pipeline (BUILD_MANDATE section 26): NOT a word
cloud. Two distinct kinds, always labelled apart:

CURATED_THEME (theme_stats): the 47-entry hand-maintained KEYWORDS taxonomy
in scripts/build_dataset.py, matched/canonicalised via the synonym index,
with salience & velocity aggregated per theme.

DISCOVERED_THEME (discover_themes): a real concept-discovery pipeline over
the same news corpus, independent of the curated taxonomy -

    news text -> TF-IDF (1-2gram) representation -> agglomerative clustering
    -> per-cluster c-TF-IDF keyphrase label -> canonicalisation/dedup
    against curated synonyms -> entity linking (alias-resolved against the
    known entity universe, not just each doc's pre-tagged 'entities' field)
    -> emerging-theme ranking by mention velocity/coverage.

A concept NOT already in the curated 47-theme list CAN surface here. The
pipeline reruns from scratch whenever ingest_news_document() adds a
document or invalidate_discovery_cache() is called directly - it is never
hard-coded. POC-scale (small corpus): clusters are small and labels are
crude top-TF-IDF-term phrases, not a production topic model. Optional LLM
labelling (label_discovered_theme) may only SUMMARISE an already-formed
cluster's representative headlines - it never invents a theme independent
of source documents.
"""
import re
from collections import defaultdict
from datetime import datetime
from .data import STORE
from . import event_parser


def _parse_date(d):
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except Exception:
        return None


def _all_dates():
    ds = [_parse_date(n["date"]) for n in STORE.news_all]
    return [d for d in ds if d]


def theme_stats():
    """Compute, for every canonical keyword/theme: mention count, mention
    velocity (recent half vs earlier half of the corpus timeline), entity
    coverage, source diversity, and representative evidence snippets."""
    dates = sorted(_all_dates())
    if not dates:
        return []
    midpoint = dates[len(dates) // 2]

    mention_docs = defaultdict(list)
    for doc in STORE.news_all:
        d = _parse_date(doc["date"])
        for kw in doc.get("keywords", []):
            mention_docs[kw].append((doc, d))

    out = []
    for kw in STORE.keywords:
        kid = kw["id"]
        docs = mention_docs.get(kid, [])
        mention_count = len(docs)
        recent = sum(1 for _, d in docs if d and midpoint and d >= midpoint)
        earlier = mention_count - recent
        velocity = None
        if earlier > 0:
            velocity = (recent - earlier) / earlier
        elif recent > 0:
            velocity = float("inf")

        entity_set = set()
        source_set = set()
        for doc, _ in docs:
            entity_set.update(doc.get("entities", []))
            source_set.add(doc.get("source", "unknown"))

        # portfolio relevance: how many synthetic counterparties hold
        # issuers that are covered by this theme (Layer C joined AFTER
        # theme relevance is computed, per mandate section on exposure
        # join order).
        covered_issuers = entity_set & set(STORE.issuer_ids)
        exposed_cps = set()
        for xe in STORE.exposure_edges:
            if xe["issuer"] in covered_issuers:
                exposed_cps.add(xe["counterparty"])

        evidence = [
            {"title": doc["title"], "source": doc["source"], "date": doc["date"], "url": doc.get("url"),
             "is_synthetic": doc.get("is_synthetic", False)}
            for doc, _ in sorted(docs, key=lambda x: x[1] or dates[0], reverse=True)[:3]
        ]

        out.append({
            "theme_id": kid,
            "id": kid,
            "label": kw["label"],
            "kind": "CURATED_THEME",
            "source_type": "CURATED_TAXONOMY",
            "mention_count": mention_count,
            "mention_velocity": None if velocity in (None,) else (velocity if velocity != float("inf") else 999.0),
            "entity_coverage": len(entity_set),
            "covered_entities": sorted(entity_set),
            "source_diversity": len(source_set),
            "portfolio_relevance": len(exposed_cps),
            "exposed_counterparties": sorted(exposed_cps),
            "evidence": evidence,
        })
    out.sort(key=lambda t: -t["mention_count"])
    return out


def theme_detail(theme_id):
    stats = {t["theme_id"]: t for t in theme_stats()}
    if theme_id in stats:
        return stats[theme_id]
    discovered = {t["theme_id"]: t for t in discover_themes()}
    return discovered.get(theme_id)


def canonicalize(term):
    """Map a free-text term/synonym to a canonical theme id, or None."""
    return STORE.synonym_index.get(term.lower())


# ---------------------------------------------------------------------------
# DISCOVERED_THEME: news/text -> TF-IDF representation -> clustering ->
# c-TF-IDF keyphrase label -> canonicalisation/dedup vs curated taxonomy ->
# entity linking -> emerging-theme ranking.
# ---------------------------------------------------------------------------
_DISCOVERY_CACHE = None
_SLUG_RE = re.compile(r"[^A-Z0-9]+")


def invalidate_discovery_cache():
    global _DISCOVERY_CACHE
    _DISCOVERY_CACHE = None


def ingest_news_document(doc):
    """Simple ingestion path (POC scope: in-memory, no external feed):
    append a news document to the live corpus and invalidate the discovery
    cache so the NEXT discover_themes() call re-runs the full pipeline over
    the enlarged corpus - proving new concepts can emerge from new text
    rather than being hard-coded. Required fields: id, date, title,
    snippet. Optional: entities, keywords, source, url, is_synthetic."""
    required = {"id", "date", "title", "snippet"}
    missing = required - set(doc.keys())
    if missing:
        raise ValueError(f"news document missing required fields: {sorted(missing)}")
    doc = {
        "entities": [], "keywords": [], "source": "INGESTED", "url": None,
        "is_synthetic": True, "source_type": "SYNTHETIC_NARRATIVE",
        **doc,
    }
    STORE.news_all.append(doc)
    invalidate_discovery_cache()
    return doc


def _news_doc_text(doc):
    return f"{doc.get('title', '')}. {doc.get('snippet', '')}"


def _matches_curated_theme(top_terms):
    """Canonicalisation/dedup: if a cluster's top keyphrase terms overlap a
    curated theme's own synonyms/label, treat the cluster as that curated
    theme (already represented) rather than emitting a duplicate 'new'
    theme - curated and discovered must never double-count the same
    concept."""
    term_set = {t.lower() for t in top_terms}
    for kw in STORE.keywords:
        syns = {s.lower() for s in kw["synonyms"]} | {kw["label"].lower()}
        if term_set & syns:
            return kw["id"]
    return None


def _linked_entities_for_docs(docs_subset):
    """Entity linking for a discovered cluster: union of each document's
    pre-tagged 'entities' field AND a fresh alias-resolved NER pass over
    the document's own text (core/event_parser.detect_entities, the same
    resolver used for Event Studio) - so linking does not depend solely on
    documents having been pre-tagged at ingestion time."""
    entity_set = set()
    for doc in docs_subset:
        entity_set.update(doc.get("entities", []))
        entity_set.update(event_parser.detect_entities(_news_doc_text(doc)))
    return entity_set


def discover_themes(min_cluster_size=2, max_clusters=14):
    """Real (if POC-scale) concept-discovery pipeline over the LIVE news
    corpus (STORE.news_all, which ingest_news_document() can grow),
    independent of the hard-coded KEYWORDS taxonomy: a concept not already
    in the curated 47-theme list can appear here. Cached per-process but
    invalidated by ingest_news_document()/invalidate_discovery_cache(); not
    intended to compete with the curated taxonomy's precision, only to
    surface candidates for it."""
    global _DISCOVERY_CACHE
    if _DISCOVERY_CACHE is not None:
        return _DISCOVERY_CACHE

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.cluster import AgglomerativeClustering

    docs = STORE.news_all
    if len(docs) < 4:
        _DISCOVERY_CACHE = []
        return _DISCOVERY_CACHE

    dates = sorted(_all_dates())
    midpoint = dates[len(dates) // 2] if dates else None

    texts = [_news_doc_text(d) for d in docs]
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1, max_df=0.9)
    matrix = vectorizer.fit_transform(texts).toarray()
    terms = vectorizer.get_feature_names_out()

    n_clusters = max(2, min(max_clusters, len(docs) // 3))
    model = AgglomerativeClustering(n_clusters=n_clusters, metric="cosine", linkage="average")
    labels = model.fit_predict(matrix)

    clusters = defaultdict(list)
    for i, lab in enumerate(labels):
        clusters[lab].append(i)

    discovered = []
    for idxs in clusters.values():
        if len(idxs) < min_cluster_size:
            continue
        member_docs = [docs[i] for i in idxs]

        # c-TF-IDF-style keyphrase: mean TF-IDF vector across cluster
        # members, top terms by weight = representative_terms.
        centroid = matrix[idxs].mean(axis=0)
        top_idx = centroid.argsort()[::-1][:6]
        top_terms = [terms[j] for j in top_idx if centroid[j] > 0]
        if not top_terms:
            continue
        if _matches_curated_theme(top_terms):
            continue  # already represented in the curated taxonomy - dedup

        label_phrase = " / ".join(t.title() for t in top_terms[:3])
        theme_id = "DISCOVERED_" + _SLUG_RE.sub("_", top_terms[0].upper()).strip("_")

        entity_set = _linked_entities_for_docs(member_docs)
        covered_issuers = entity_set & set(STORE.issuer_ids)
        exposed_cps = {xe["counterparty"] for xe in STORE.exposure_edges if xe["issuer"] in covered_issuers}

        member_dated = [(doc, _parse_date(doc["date"])) for doc in member_docs]
        recent_mentions = sum(1 for _, d in member_dated if d and midpoint and d >= midpoint)
        prior_mentions = len(member_docs) - recent_mentions
        if prior_mentions > 0:
            velocity = round((recent_mentions - prior_mentions) / prior_mentions, 4)
        elif recent_mentions > 0:
            velocity = 999.0
        else:
            velocity = None

        # novelty: fraction of member documents that share NO curated
        # keyword tag at all - a directly-observable, non-fabricated proxy
        # for "how much of this cluster is outside the curated taxonomy's
        # own coverage" (not a probability/confidence score).
        untagged = sum(1 for doc in member_docs if not doc.get("keywords"))
        novelty_score = round(untagged / len(member_docs), 4)

        representative_headlines = [
            doc["title"] for doc, _ in sorted(member_dated, key=lambda x: x[1] or dates[0], reverse=True)[:3]
        ]

        discovered.append({
            "theme_id": theme_id,
            "id": theme_id,
            "label": label_phrase,
            "kind": "DISCOVERED_THEME",
            "source_type": "DERIVED_DATA",
            "method": "tfidf_agglomerative_clustering_ctfidf_keyphrase",
            "member_document_ids": [doc["id"] for doc in member_docs],
            "representative_terms": top_terms,
            "keyphrase_terms": top_terms,  # kept for backward-compat callers
            "representative_headlines": representative_headlines,
            "entity_ids": sorted(entity_set),
            "covered_entities": sorted(entity_set),  # kept for backward-compat / shared UI with CURATED_THEME
            "document_count": len(member_docs),
            "mention_count": len(member_docs),  # kept for backward-compat sort/UI
            "recent_mentions": recent_mentions,
            "prior_mentions": prior_mentions,
            "velocity": velocity,
            "mention_velocity": velocity,  # kept for backward-compat / shared UI with CURATED_THEME
            "novelty_score": novelty_score,
            "entity_coverage": len(entity_set),
            "portfolio_relevance": len(exposed_cps),
            "exposed_counterparties": sorted(exposed_cps),
            "evidence": [
                {"title": doc["title"], "source": doc["source"], "date": doc["date"],
                 "url": doc.get("url"), "is_synthetic": doc.get("is_synthetic", False)}
                for doc, _ in sorted(member_dated, key=lambda x: x[1] or dates[0], reverse=True)[:3]
            ],
        })
    discovered.sort(key=lambda t: -t["document_count"])
    _DISCOVERY_CACHE = discovered
    return discovered


def label_discovered_theme(discovered_theme, ai_provider):
    """Optional LLM labelling step: summarise an ALREADY-DISCOVERED
    cluster's representative headlines into a short label. Never invents a
    theme independent of source documents - it only rephrases the label
    for a cluster discover_themes() already formed deterministically."""
    return ai_provider.label_theme(
        [discovered_theme["label"]] + discovered_theme.get("representative_terms", [])[:3]
    )


def all_themes(q=None):
    """Combined CURATED_THEME + DISCOVERED_THEME listing, each explicitly
    tagged via 'kind' so the UI can distinguish them (BUILD_MANDATE
    requirement - the two must never be presented as the same kind of
    thing)."""
    combined = theme_stats() + discover_themes()
    if q:
        combined = [t for t in combined if q.lower() in t["label"].lower()]
    return combined
