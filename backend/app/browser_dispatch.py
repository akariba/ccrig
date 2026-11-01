"""In-process request dispatcher used when this app runs inside Pyodide
(GitHub Pages build - see frontend/src/api/pyodideClient.ts). There is no
ASGI server or network socket in that environment, and Starlette's
TestClient needs real OS threads for its sync/async bridge, which Pyodide's
single-threaded runtime doesn't provide.

Instead, this reuses FastAPI's own compiled route table (path matching,
path-param conversion) from `app.router.routes` and calls each endpoint
function directly with plain Python arguments, bypassing HTTP entirely.

Request parameters are validated with pydantic from the endpoint's own
signature - the same constraints (`Query(ge=...)`, request-model fields,
validators) that FastAPI enforces on the server - and failures come back as
FastAPI-shaped 422 bodies, so the browser build rejects exactly what the
server rejects. `tests/test_dispatcher_parity.py` drives the same requests
through both and requires identical status codes and error locations.

Supported parameter kinds: path params, query params (plain annotation or
`Query(...)`), and a single pydantic request-body model. Anything else
(`Depends`, `Header`, `Request`, ...) is rejected at import time so a new
endpoint cannot silently misbehave in the static build.
"""
import inspect
import sys
import traceback
from typing import Annotated, Any

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined
from starlette.routing import compile_path

from .main import app

_EMPTY = inspect.Parameter.empty


def _iter_routes(routes):
    for route in routes:
        if hasattr(route, "endpoint"):
            yield route
        elif hasattr(route, "original_router"):
            yield from _iter_routes(route.original_router.routes)


class _Param:
    """How one endpoint argument is filled: ('path'|'query'|'body', ...)."""

    def __init__(self, name, kind, *, adapter=None, model=None, required=False, default=None):
        self.name, self.kind = name, kind
        self.adapter, self.model = adapter, model
        self.required, self.default = required, default


def _plan_endpoint(route, path_names):
    plan = []
    for name, param in inspect.signature(route.endpoint).parameters.items():
        annotation, default = param.annotation, param.default

        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            plan.append(_Param(name, "body", model=annotation))
            continue

        marker = default if isinstance(default, FieldInfo) else None
        unsupported = None
        if hasattr(default, "dependency"):
            unsupported = "Depends()/Security()"
        elif marker is not None and type(marker).__name__ not in ("Query", "Path", "FieldInfo"):
            unsupported = f"{type(marker).__name__}()"
        elif getattr(annotation, "__module__", "").startswith(("starlette.", "fastapi.")):
            unsupported = f"a framework object ({annotation.__name__})"
        if unsupported:
            raise RuntimeError(
                f"{route.path}: parameter '{name}' uses {unsupported}, which the in-browser dispatcher "
                "does not support (only path, query and one pydantic body model)."
            )

        base = Any if annotation is _EMPTY else annotation
        if marker is not None:
            required = marker.is_required()
            if marker.default is not PydanticUndefined:
                value = marker.default
            elif marker.default_factory is not None:
                value = marker.default_factory()
            else:
                value = None
            adapter = TypeAdapter(Annotated[base, marker])
        else:
            required = default is _EMPTY
            value = None if required else default
            adapter = TypeAdapter(base)
        plan.append(_Param(name, "path" if name in path_names else "query",
                           adapter=adapter, required=required, default=value))
    return plan


_ROUTES = []
for _route in _iter_routes(app.router.routes):
    # Only the application's own endpoints; FastAPI's built-in /docs, /redoc
    # and /openapi.json routes take a raw Request and are never called by the
    # static frontend.
    if not getattr(_route.endpoint, "__module__", "").startswith("app."):
        continue
    _path_regex, _path_format, _param_convertors = compile_path(_route.path)
    _ROUTES.append((_route.methods, _path_regex, _param_convertors, _route.endpoint,
                    _plan_endpoint(_route, set(_param_convertors))))


def _errors(kind, name, exc: ValidationError):
    """FastAPI-shaped error entries: loc = (kind, [name], *field path)."""
    prefix = [kind] + ([name] if name else [])
    return [{**err, "loc": prefix + list(err["loc"])} for err in exc.errors(include_url=False)]


def _missing(kind, name):
    return {"type": "missing", "loc": [kind, name] if name else [kind], "msg": "Field required", "input": None}


def dispatch(method: str, path: str, query: dict | None = None, body: Any = None):
    """Returns (status_code, json_safe_body)."""
    query = query or {}
    method = method.upper()
    path_matched = False
    for methods, regex, convertors, endpoint, plan in _ROUTES:
        m = regex.match(path)
        if not m:
            continue
        path_matched = True
        if method not in methods:
            continue

        path_params = {k: convertors[k].convert(v) for k, v in m.groupdict().items()}
        kwargs, errors = {}, []
        for p in plan:
            if p.kind == "body":
                if body is None:
                    if any(f.is_required() for f in p.model.model_fields.values()):
                        errors.append(_missing("body", None))
                        continue
                    kwargs[p.name] = p.model.model_validate({})
                    continue
                try:
                    # from_attributes=True mirrors FastAPI's own body validation (same error types)
                    kwargs[p.name] = p.model.model_validate(body, from_attributes=True)
                except ValidationError as exc:
                    errors.extend(_errors("body", None, exc))
                continue

            source = path_params if p.kind == "path" else query
            if p.name not in source:
                if p.required:
                    errors.append(_missing(p.kind, p.name))
                else:
                    kwargs[p.name] = p.default
                continue
            try:
                kwargs[p.name] = p.adapter.validate_python(source[p.name])
            except ValidationError as exc:
                errors.extend(_errors(p.kind, p.name, exc))

        if errors:
            return 422, {"detail": jsonable_encoder(errors)}

        try:
            return 200, jsonable_encoder(endpoint(**kwargs))
        except HTTPException as exc:
            return exc.status_code, {"detail": exc.detail}
        except Exception:
            # Same contract as the real server: an unexpected error is a 500,
            # not a validation error. Keep the traceback visible in the console.
            traceback.print_exc(file=sys.stderr)
            return 500, {"detail": "Internal Server Error"}

    return (404, {"detail": "Not Found"}) if not path_matched else (405, {"detail": "Method Not Allowed"})
