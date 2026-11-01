"""TF-IDF-based semantic/business-similarity space over entity descriptive
text (sector, industry, country, name). This is the deterministic
"semantic similarity" feature used everywhere the mandate calls for
business/semantic similarity, without requiring any external embedding
model or API key (offline-mode requirement, section 4/27).

Deliberately simple: a defensible, inspectable baseline. An LLM/embedding
upgrade path is documented in ARCHITECTURE.md but not required for the POC
to run.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from .data import STORE


def _doc_text(entity):
    parts = [
        entity.get("name") or "",
        entity.get("sector") or "",
        entity.get("industry") or "",
        entity.get("country") or "",
        entity.get("region") or "",
    ]
    return " ".join(parts)


class SemanticSpace:
    def __init__(self):
        self.ids = STORE.browsable_ids
        docs = [_doc_text(STORE.entity(i)) for i in self.ids]
        self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
        self.matrix = self.vectorizer.fit_transform(docs)
        self.index = {eid: i for i, eid in enumerate(self.ids)}

    def similarity(self, a, b):
        if a not in self.index or b not in self.index:
            return None
        va = self.matrix[self.index[a]]
        vb = self.matrix[self.index[b]]
        sim = cosine_similarity(va, vb)[0][0]
        return float(sim)

    def nearest(self, entity_id, top_k, among=None):
        """Top-k most similar entities. `among` (a collection of ids) restricts
        the candidates BEFORE the cut, so a restricted pool still yields k
        neighbours. The TF-IDF space itself is fitted on all entities either
        way, so similarity values do not depend on `among`."""
        if entity_id not in self.index:
            return []
        v = self.matrix[self.index[entity_id]]
        sims = cosine_similarity(v, self.matrix)[0]
        order = np.argsort(-sims)
        allowed = None if among is None else set(among)
        out = []
        for idx in order:
            cand = self.ids[idx]
            if cand == entity_id or (allowed is not None and cand not in allowed):
                continue
            out.append((cand, float(sims[idx])))
            if len(out) >= top_k:
                break
        return out


SEMANTIC = SemanticSpace()
