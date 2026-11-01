"""The static (GitHub Pages) build runs this backend inside Pyodide. Its
runtime must be pinned and consistent with the rest of the repo, and must not
carry dependencies the code never imports.

These checks are offline. `npm run verify:static` (in frontend/) additionally
boots the pinned runtime and proves it works.
"""
import json
import os
import re

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
FRONTEND = os.path.join(ROOT, "frontend")
PINS = json.load(open(os.path.join(FRONTEND, "src", "api", "pyodide-pins.json")))
NORM = lambda n: n.lower().replace("_", "-")  # noqa: E731


def _requirements():
    out = {}
    for line in open(os.path.join(ROOT, "backend", "requirements.txt")):
        line = line.strip()
        if line and not line.startswith("#"):
            name, _, version = line.partition("==")
            out[NORM(re.sub(r"\[.*\]", "", name))] = version
    return out


def _python_sources():
    for base in ("app", "scripts", "tests", "validation"):
        for dirpath, _, files in os.walk(os.path.join(ROOT, "backend", base)):
            for f in files:
                if f.endswith(".py"):
                    yield os.path.join(dirpath, f)


def test_pandas_is_not_a_dependency_anywhere():
    assert "pandas" not in _requirements()
    assert "pandas" not in map(NORM, PINS["loadPackages"])
    importing = [p for p in _python_sources()
                 if re.search(r"^\s*(import|from)\s+pandas\b", open(p).read(), re.MULTILINE)
                 and not p.endswith("test_static_build_pins.py")]
    assert importing == [], f"pandas is imported by {importing}"
    client = open(os.path.join(FRONTEND, "src", "api", "pyodideClient.ts")).read()
    assert "pandas" not in client


def test_every_micropip_requirement_is_an_exact_pin():
    assert PINS["micropip"], "the runtime installs at least fastapi"
    for spec in PINS["micropip"]:
        assert re.fullmatch(r"[A-Za-z0-9_.-]+==\d+(\.\d+)*", spec), f"not an exact pin: {spec}"
    assert len({NORM(s.split("==")[0]) for s in PINS["micropip"]}) == len(PINS["micropip"])


def test_fastapi_in_the_browser_is_the_version_the_tests_run_against():
    pinned = dict(s.split("==") for s in PINS["micropip"])
    assert pinned["fastapi"] == _requirements()["fastapi"]


def test_pyodide_npm_dependency_is_exact_and_agrees_with_the_pins():
    pkg = json.load(open(os.path.join(FRONTEND, "package.json")))
    assert pkg["dependencies"]["pyodide"] == PINS["pyodide"], "must be exact (no ^ or ~): the CDN URL is fixed"
    lock = json.load(open(os.path.join(FRONTEND, "package-lock.json")))
    assert lock["packages"][""]["dependencies"]["pyodide"] == PINS["pyodide"]
    assert lock["packages"]["node_modules/pyodide"]["version"] == PINS["pyodide"]


def test_client_takes_every_version_from_the_pins_file():
    client = open(os.path.join(FRONTEND, "src", "api", "pyodideClient.ts")).read()
    assert "./pyodide-pins.json" in client
    assert "pins.pyodide" in client and "pins.loadPackages" in client and "pins.micropip" in client
    assert not re.search(r"v\d+\.\d+\.\d+", client), "a Pyodide version is hard-coded in the client"
    assert not re.search(r"micropip\.install\(\[", client), "micropip packages must come from the pins file"


def test_micropip_pins_for_bundled_packages_equal_what_pyodide_ships():
    pinned = {NORM(s.split("==")[0]): s.split("==")[1] for s in PINS["micropip"]}
    for name, version in PINS["bundledByPyodide"].items():
        if NORM(name) in pinned:
            assert pinned[NORM(name)] == version, name


@pytest.mark.skipif(not os.path.exists(os.path.join(FRONTEND, "node_modules", "pyodide", "pyodide-lock.json")),
                    reason="frontend dependencies not installed")
def test_bundled_versions_match_the_pyodide_lockfile():
    """What Pyodide ships is fixed by its release; the pins file must say so."""
    lock = json.load(open(os.path.join(FRONTEND, "node_modules", "pyodide", "pyodide-lock.json")))
    shipped = {NORM(k): v["version"] for k, v in lock["packages"].items()}
    # the lockfile tags itself within the release line (e.g. 0.28.0.dev0 for 0.28.3)
    assert lock["info"]["version"].split(".")[:2] == PINS["pyodide"].split(".")[:2]
    for name, version in PINS["bundledByPyodide"].items():
        assert shipped.get(NORM(name)) == version, f"{name}: pins {version}, lockfile {shipped.get(NORM(name))}"
    for name in PINS["loadPackages"]:
        assert NORM(name) in shipped, f"{name} is not in the Pyodide {PINS['pyodide']} lockfile"


def test_vendored_build_ships_only_application_code_and_data():
    """backend/validation and tests are verification tools, not part of the site."""
    script = open(os.path.join(FRONTEND, "scripts", "vendor-backend.mjs")).read()
    assert '["app", "data"]' in script
