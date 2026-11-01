"""Self-check of the in-browser backend: the analytical baseline and every
shared request case, driven through `app.browser_dispatch.dispatch`.

Runs natively (`python -m validation.static_check`) and inside Pyodide, where
`frontend/scripts/verify-static-backend.mjs` boots the exact pinned runtime
and calls `run()`. It reports, it does not decide: the Node driver compares
the reported package versions with `frontend/src/api/pyodide-pins.json`.
"""
import json
import sys
from importlib import metadata
from importlib.util import find_spec
from urllib.parse import parse_qsl, urlsplit

PACKAGES = (
    "fastapi", "starlette", "annotated-doc", "typing-inspection", "typing-extensions", "pydantic",
    "pydantic-core", "networkx", "numpy", "scipy", "scikit-learn", "anyio", "annotated-types",
)


def _versions():
    out = {}
    for name in PACKAGES:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


def run():
    from app.browser_dispatch import dispatch
    from . import request_cases, snapshot

    snapshot_diffs = snapshot.diff(
        snapshot.load_snapshot(),
        snapshot.normalise(snapshot.capture(snapshot.dispatch_request())),
    )

    failures = []
    for name, method, path, body, expected in request_cases.INVALID + request_cases.VALID:
        parts = urlsplit(path)
        status, data = dispatch(method, parts.path, dict(parse_qsl(parts.query, keep_blank_values=True)), body)
        ok = status == expected
        if expected == 422:
            detail = data.get("detail") if isinstance(data, dict) else None
            if isinstance(detail, list):       # request-validation error
                ok = ok and bool(detail) and detail[0]["loc"][0] in ("query", "body", "path")
            else:                              # explicit "cannot be calculated" explanation
                ok = ok and isinstance(detail, str) and bool(detail.strip())
        if not ok:
            failures.append([name, expected, status, str(data)[:160]])

    return {
        "python": sys.version.split()[0],
        "versions": _versions(),
        "pandas_importable": find_spec("pandas") is not None,
        "snapshot_entries": len(snapshot.load_snapshot()),
        "snapshot_diffs": [[p, repr(e)[:80], repr(a)[:80]] for p, e, a in snapshot_diffs[:10]],
        "request_cases": len(request_cases.INVALID) + len(request_cases.VALID),
        "request_case_failures": failures,
    }


def main():
    report = run()
    print(json.dumps(report, indent=1))
    return 0 if not report["snapshot_diffs"] and not report["request_case_failures"] else 1


if __name__ == "__main__":
    sys.exit(main())
