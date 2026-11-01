"""Responses must not depend on the process: not on Python's per-process
string-hash randomisation, not on set iteration order, not on restarts.

Two kinds of test:
* a cross-process sweep (~370 requests: every issuer, counterparty, theme,
  priority record, Event Studio scenario, search and Model Lab call) run in
  separate interpreters with different PYTHONHASHSEED values and compared
  byte for byte - nothing sorted or masked;
* tests of the explicit ordering rules that make the output deterministic
  (so stability is by design, not by luck of small sets).
"""
import json
import os
import subprocess
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app  # noqa: E402
from validation import determinism  # noqa: E402

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
client = TestClient(app)


def _sweep_in_subprocesses(seeds):
    with tempfile.TemporaryDirectory() as tmp:
        procs = []
        for seed in seeds:
            out = os.path.join(tmp, f"sweep_{seed}.json")
            env = {**os.environ, "PYTHONHASHSEED": str(seed), "PYTHONWARNINGS": "ignore"}
            procs.append((seed, out, subprocess.Popen(
                [sys.executable, "-m", "validation.determinism", "--out", out],
                cwd=BACKEND_DIR, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)))
        results = {}
        for seed, out, proc in procs:
            stdout, stderr = proc.communicate(timeout=600)
            assert proc.returncode == 0, stderr
            results[seed] = json.load(open(out))
        return results


def test_every_response_is_identical_across_processes_and_hash_seeds():
    runs = _sweep_in_subprocesses([0, 1, 987654])
    base_seed, *others = runs
    assert len(runs[base_seed]) > 300
    for seed in others:
        diffs = determinism.compare(runs[base_seed], runs[seed])
        assert not diffs, f"hash seed {base_seed} vs {seed}: " + "; ".join(
            f"{n} @ {p}" for n, p, _, _ in diffs[:5])


def test_repeated_calls_in_one_process_are_identical():
    first = determinism.sweep(lambda m, p, b: _call(m, p, b))
    second = determinism.sweep(lambda m, p, b: _call(m, p, b))
    assert determinism.compare(first, second) == []


def _call(method, path, body):
    resp = client.request(method, path, json=body) if body is not None else client.request(method, path)
    return resp.status_code, resp.json()


# ----------------------------------------------------- explicit ordering rules
def test_counterparty_indirect_relationships_follow_the_exposure_rule():
    """Direct holdings are visited largest total exposure first (ties: issuer id);
    the 20-row cap therefore keeps relationships reached via the biggest positions."""
    ids = [r["counterparty_id"] for r in client.get("/api/distance-map/counterparties").json()["results"]]
    capped = 0
    for cp in ids:
        body = client.get(f"/api/counterparties/{cp}").json()
        exposure = {}
        for h in body["direct_holdings"]:
            exposure[h["issuer"]] = exposure.get(h["issuer"], 0) + (h.get("exposure_pct") or 0)
        visit_order = sorted(exposure, key=lambda i: (-exposure[i], i))
        rows = body["indirect_relationships"]
        assert len(rows) <= 20
        groups = [r["via_direct_holding"] for r in rows]
        seen = list(dict.fromkeys(groups))
        assert seen == [i for i in visit_order if i in seen], (cp, seen, visit_order)
        # each group is contiguous (no interleaving between holdings)
        assert groups == sorted(groups, key=seen.index)
        capped += len(rows) == 20
    assert capped >= 1, "at least one shipped counterparty exercises the cap"


def test_entity_evidence_sources_are_sorted():
    for ent in ("TSM", "SKHY", "NVDA", "JPM"):
        sources = client.get(f"/api/entities/{ent}").json()["evidence"]["fact_edge_sources"]
        assert sources == sorted(set(sources))


@pytest.mark.parametrize("text", determinism.EVENT_TEXTS)
def test_event_studio_ordering_rules(text):
    r = client.post("/api/event/parse", json={"text": text}).json()

    direct = [d["entity_id"] for d in r["direct_relevance"]]
    assert len(direct) == len(set(direct))
    mentioned = [e for e in direct if e in set(r["detected_entities"])]
    assert mentioned == sorted(mentioned)                           # mentions first, sorted by id
    assert direct[:len(mentioned)] == mentioned

    m1 = r["mode1_bounded_traversal"]["results"]
    assert m1 == sorted(m1, key=lambda x: (-x["score"], x["entity_id"]))      # ties: entity id

    cps = r["relevant_counterparties"]
    assert cps == sorted(cps, key=lambda x: (-x["exposure_weighted_relevance"], x["counterparty"]))

    relevance = {}
    for cp in cps:
        for i in cp["issuers"]:
            relevance[i["issuer"]] = i["event_relevance"]
    order = []
    for p in r["counterparty_exposure_paths"]:
        if not order or order[-1] != p["issuer"]:
            order.append(p["issuer"])
    assert len(order) == len(set(order))                             # issuers are contiguous groups
    # most event-relevant issuer first (the response shows relevance rounded to
    # 4 dp while the sort uses the unrounded value, hence the tolerance; exact
    # tie-breaking is covered by the cross-process sweep above)
    for earlier, later in zip(order, order[1:]):
        assert relevance[earlier] >= relevance[later] - 1e-4, (earlier, later)
