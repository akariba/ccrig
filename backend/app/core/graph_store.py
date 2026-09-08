"""Builds the typed, layered graph structures.

BUILD_MANDATE section 6 requires that FACT RELATIONS, DERIVED RELATIONSHIPS
and EXPOSURE stay logically separate. We therefore keep THREE independent
NetworkX MultiDiGraphs rather than one undifferentiated graph, and never
write derived-similarity weights and exposure percentages into the same
edge attribute namespace.
"""
import networkx as nx
from .data import STORE

# Layer A: FACT RELATIONS (directional, sourced)
FACT_GRAPH = nx.MultiDiGraph()
for e in STORE.entities_raw:
    FACT_GRAPH.add_node(e["id"], **e)
for fe in STORE.fact_edges:
    FACT_GRAPH.add_edge(fe["source"], fe["target"], key=fe["relation"], layer="FACT", **fe)

# Layer C: EXPOSURE (Counterparty -> Issuer only; never merged with Layer B)
EXPOSURE_GRAPH = nx.MultiDiGraph()
for e in STORE.entities_raw:
    EXPOSURE_GRAPH.add_node(e["id"], **e)
for xe in STORE.exposure_edges:
    EXPOSURE_GRAPH.add_edge(xe["counterparty"], xe["issuer"], key=xe["relation"], layer="EXPOSURE", **xe)

# Layer B: DERIVED RELATIONSHIPS graph is populated lazily by scoring.py
# (it depends on candidate generation, which must run first per mandate
# section 9) via `set_derived_graph()` below.
DERIVED_GRAPH = nx.MultiDiGraph()


def set_derived_graph(g):
    global DERIVED_GRAPH
    DERIVED_GRAPH = g


def fact_neighbors(entity_id, max_hops=1):
    """Deterministic factual neighbours (both directions), used as a
    candidate-generation source. Returns dict[node_id] -> list of fact
    edge dicts connecting entity_id to that node (either direction)."""
    out = {}
    if entity_id not in FACT_GRAPH:
        return out
    for _, tgt, data in FACT_GRAPH.out_edges(entity_id, data=True):
        out.setdefault(tgt, []).append({**data, "direction": "OUT"})
    for src, _, data in FACT_GRAPH.in_edges(entity_id, data=True):
        out.setdefault(src, []).append({**data, "direction": "IN"})
    return out


def exposure_of_counterparty(cp_id):
    return [data for _, _, data in EXPOSURE_GRAPH.out_edges(cp_id, data=True)]


def counterparties_exposed_to(issuer_id):
    return [{**data, "counterparty": src} for src, _, data in EXPOSURE_GRAPH.in_edges(issuer_id, data=True)]
