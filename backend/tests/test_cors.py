"""CORS: no wildcard-with-credentials, local development by default, and an
explicit, tested path for the one cross-origin deployment (Render).

The server never refuses to SERVE a request over CORS; the settings decide
whether a browser on another origin may READ the response. So the Vite dev
proxy (same-origin to the browser) and the serverless GitHub Pages build do
not depend on these settings at all.
"""
import os
import re
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import LOCAL_ORIGIN_REGEX, cors_settings  # noqa: E402
from app.main import app  # noqa: E402

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def make_client(environ):
    mini = FastAPI()
    mini.add_middleware(CORSMiddleware, **cors_settings(environ))

    @mini.get("/ping")
    def ping():
        return {"ok": True}

    @mini.post("/echo")
    def echo():
        return {"ok": True}

    return TestClient(mini)


def acao(client, origin, path="/ping"):
    return client.get(path, headers={"Origin": origin}).headers.get("access-control-allow-origin")


def preflight(client, origin, method="POST", headers="content-type"):
    return client.options("/echo", headers={"Origin": origin, "Access-Control-Request-Method": method,
                                            "Access-Control-Request-Headers": headers})


# ------------------------------------------------------------ settings function
def test_defaults_are_local_only_and_never_credentialed():
    s = cors_settings({})
    assert "*" not in s["allow_origins"] and s["allow_origins"] == []
    assert s["allow_origin_regex"] == LOCAL_ORIGIN_REGEX
    assert s["allow_credentials"] is False
    assert s["allow_methods"] == ["GET", "POST", "OPTIONS"] and s["allow_headers"] == ["Content-Type"]


def test_explicit_origins_replace_the_default_and_are_normalised():
    s = cors_settings({"CCRIG_CORS_ORIGINS": " https://a.example.com/ , http://localhost:3000 ,,"})
    assert s["allow_origins"] == ["https://a.example.com", "http://localhost:3000"]
    assert s["allow_origin_regex"] is None            # explicit config does not also open localhost
    assert s["allow_credentials"] is False


def test_wildcard_is_possible_only_as_an_explicit_operator_choice_and_never_with_credentials():
    s = cors_settings({"CCRIG_CORS_ORIGINS": "*"})
    assert s["allow_origins"] == ["*"] and s["allow_credentials"] is False


@pytest.mark.parametrize("bad", ["example.com", "https://", "ftp://x.org", "https://a.com/path",
                                 "https://a.com?x=1", "javascript:alert(1)", "https://a b.com"])
def test_malformed_origins_fail_fast(bad):
    with pytest.raises(ValueError, match="CCRIG_CORS_ORIGINS"):
        cors_settings({"CCRIG_CORS_ORIGINS": bad})


def test_invalid_regex_fails_fast():
    with pytest.raises(ValueError, match="CCRIG_CORS_ORIGIN_REGEX"):
        cors_settings({"CCRIG_CORS_ORIGIN_REGEX": "([unclosed"})


# ----------------------------------------------------------------- behaviour
@pytest.mark.parametrize("origin", [
    "http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://localhost",
    "http://[::1]:5173", "http://localhost:5174",           # vite moves to the next port when 5173 is taken
])
def test_default_allows_local_development_origins(origin):
    client = make_client({})
    assert acao(client, origin) == origin
    pre = preflight(client, origin)
    assert pre.status_code == 200 and pre.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in pre.headers


@pytest.mark.parametrize("origin", [
    "https://evil.example", "http://localhost.evil.example", "http://evil.example:5173",
    "https://localhost:5173.evil.example", "null", "http://127.0.0.1.evil.example",
])
def test_default_denies_everything_else(origin):
    client = make_client({})
    assert acao(client, origin) is None
    assert preflight(client, origin).status_code == 400    # starlette: "Disallowed CORS origin"
    assert client.get("/ping", headers={"Origin": origin}).json() == {"ok": True}   # still SERVED


def test_credentials_are_never_advertised_and_wildcard_is_never_reflected_by_default():
    client = make_client({})
    for origin in ("http://localhost:5173", "https://evil.example"):
        r = client.get("/ping", headers={"Origin": origin})
        assert "access-control-allow-credentials" not in r.headers
        assert r.headers.get("access-control-allow-origin") != "*"


def test_preflight_rejects_unlisted_methods_and_headers():
    client = make_client({})
    origin = "http://localhost:5173"
    assert preflight(client, origin, method="DELETE").status_code == 400
    assert preflight(client, origin, headers="authorization").status_code == 400
    assert preflight(client, origin, method="POST", headers="content-type").status_code == 200


def test_requests_without_an_origin_header_are_unaffected():
    assert make_client({}).get("/ping").json() == {"ok": True}


# ------------------------------------------------- the one cross-origin deployment
def _render_regex():
    text = open(os.path.join(REPO_ROOT, "render.yaml")).read()
    m = re.search(r"key:\s*CCRIG_CORS_ORIGIN_REGEX\s*\n\s*value:\s*'?([^'\n]+)'?", text)
    assert m, "render.yaml must configure CCRIG_CORS_ORIGIN_REGEX for the cross-origin static frontend"
    return m.group(1)


def test_render_frontend_origin_is_allowed_and_nothing_nearby_is():
    regex = _render_regex()
    client = make_client({"CCRIG_CORS_ORIGIN_REGEX": regex})
    for ok in ("https://ccrig-frontend.onrender.com", "https://ccrig-frontend-ab12cd.onrender.com"):
        assert acao(client, ok) == ok
        assert preflight(client, ok).status_code == 200
    for bad in ("https://evil.onrender.com", "https://ccrig-frontend.onrender.com.evil.com",
                "http://ccrig-frontend.onrender.com", "https://xccrig-frontend.onrender.com",
                "https://ccrig-frontend.onrender.com:8443", "http://localhost:5173"):
        assert acao(client, bad) is None, bad


def test_render_backend_service_name_and_frontend_service_name_agree_with_the_regex():
    text = open(os.path.join(REPO_ROOT, "render.yaml")).read()
    frontend_names = re.findall(r"name:\s*(ccrig-frontend)\b", text)
    assert frontend_names, "regex assumes the static service is named ccrig-frontend"
    assert re.fullmatch(_render_regex(), f"https://{frontend_names[0]}.onrender.com")


# ----------------------------------------------------------- the real application
def test_application_uses_the_environment_derived_settings():
    mw = [m for m in app.user_middleware if m.cls is CORSMiddleware]
    assert len(mw) == 1
    assert mw[0].kwargs == cors_settings()
    assert mw[0].kwargs["allow_credentials"] is False


@pytest.mark.skipif(any(k in os.environ for k in ("CCRIG_CORS_ORIGINS", "CCRIG_CORS_ORIGIN_REGEX")),
                    reason="CORS overridden in this environment")
def test_application_default_behaviour_end_to_end():
    client = TestClient(app)
    ok = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    other = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert other.status_code == 200 and "access-control-allow-origin" not in other.headers
    pre = client.options("/api/model-lab/score", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})
    assert pre.status_code == 400
