"""CLI for the validation harness.

    python -m validation.run                   # print the validation report
    python -m validation.run --check           # fail if analytics or validation drift from the baselines
    python -m validation.run --write-baseline  # re-record baselines (only when a change is INTENDED)

Run from the `backend/` directory.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import harness, snapshot


def _print_report(report: dict) -> None:
    print("ground truth:", report["ground_truth"])
    for universe, variants in report["leave_edge_out"].items():
        print(f"\nleave-edge-out | {universe}")
        for name, m in variants.items():
            print(f"  {name:32} n_q={m['n_queries']:2} MAP={m['map']:.3f} CI95={m['map_ci95']} "
                  f"hit@5={m['hit_at_5']:.2f} hit@10={m['hit_at_10']:.2f}")
    print("\ninversions (edges included; lower is better)")
    for name, v in report["inversions"].items():
        a, h = v["all_edges"], v["criticality_ge_0.8"]
        print(f"  {name:22} all: {a['share_with_at_least_one_outranker']:.0%} (mean {a['mean_outrankers']})"
              f" | crit>=0.8: {h['share_with_at_least_one_outranker']:.0%} (mean {h['mean_outrankers']})")
    print("\nhard cases:", json.dumps(report["hard_cases"], indent=1))
    print("\ncaveats:")
    for c in report["caveats"]:
        print("  -", c)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m validation.run")
    parser.add_argument("--check", action="store_true", help="compare against stored baselines")
    parser.add_argument("--write-baseline", action="store_true", help="re-record baselines (intended changes only)")
    args = parser.parse_args(argv)

    report = harness.run_validation()
    snap = snapshot.normalise(snapshot.capture(snapshot.fastapi_request()))

    if args.write_baseline:
        snapshot.write_snapshot(snap)
        snapshot.VALIDATION_FILE.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
        print(f"wrote {snapshot.SNAPSHOT_FILE} and {snapshot.VALIDATION_FILE}")
        return 0

    if args.check:
        failures = []
        for label, expected, actual in (
            ("analytics snapshot", snapshot.load_snapshot(), snap),
            ("validation baseline", json.loads(snapshot.VALIDATION_FILE.read_text()), report),
        ):
            d = snapshot.diff(expected, snapshot.normalise(actual))
            if d:
                failures.append((label, d))
        for label, d in failures:
            print(f"DRIFT in {label}:")
            for p, e, a in d:
                print(f"  {p}: expected {e!r}, got {a!r}")
        print("OK: no drift" if not failures else "FAILED")
        return 1 if failures else 0

    _print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
