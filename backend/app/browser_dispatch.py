"""In-process request dispatcher used when this app runs inside Pyodide
(GitHub Pages build - see frontend/src/api/pyodideClient.ts). There is no
ASGI server or network socket in that environment, and Starlette's
TestClient needs real OS threads for its sync/async bridge, which Pyodide's
single-threaded runtime doesn't provide.

Instead, this reuses FastAPI's own compiled route table (path matching,
path-param conversion) from `app.router.routes` and calls each endpoint
function directly with plain Python arguments, bypassing HTTP entirely.
Behavior (routing, 404s, HTTPException status codes, JSON shape) is meant
to match the real server for every route this frontend actually calls.
"""
import inspect
import typing

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from starlette.routing import compile_path

from .main import app

def _iter_routes(routes):
    for route in routes:
        if hasattr(route, "endpoint"):
            yield route
        elif hasattr(route, "original_router"):
            yield from _iter_routes(route.original_router.routes)


_ROUTES = []
for _route in _iter_routes(app.router.routes):
    _path_regex, _path_format, _param_convertors = compile_path(_route.path)
    _ROUTES.append((_route.methods, _path_regex, _param_convertors, _route.endpoint))


def _coerce_scalar(value, annotation):
    if value is None or annotation is inspect.Parameter.empty:
        return value
    origin = typing.get_origin(annotation)
    if origin is typing.Union:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        annotation = args[0] if args else str
    if annotation is bool:
        return str(value).lower() in ("1", "true", "yes", "on")
    if annotation is int:
        return int(value)
    if annotation is float:
        return float(value)
    return value


def dispatch(method: str, path: str, query: dict | None = None, body: dict | None = None):
    """Returns (status_code, json_safe_body)."""
    query = query or {}
    method = method.upper()
    path_matched = False
    for methods, regex, convertors, endpoint in _ROUTES:
        m = regex.match(path)
        if not m:
            continue
        path_matched = True
        if method not in methods:
            continue

        path_params = {k: convertors[k].convert(v) for k, v in m.groupdict().items()}
        sig = inspect.signature(endpoint)
        kwargs = {}
        for name, param in sig.parameters.items():
            if name in path_params:
                kwargs[name] = path_params[name]
                continue
            annotation = param.annotation
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                kwargs[name] = annotation(**(body or {}))
                continue
            if name in query:
                kwargs[name] = _coerce_scalar(query[name], annotation)
                continue
            # Otherwise leave unset - FastAPI's Query(...)/Path(...) marker
            # objects and plain defaults both fall through to the
            # function's own default value here.

        try:
            result = endpoint(**kwargs)
            return 200, jsonable_encoder(result)
        except HTTPException as exc:
            return exc.status_code, {"detail": exc.detail}
        except TypeError as exc:
            return 422, {"detail": str(exc)}

    return (404, {"detail": f"Not Found: {path}"}) if not path_matched else (405, {"detail": "Method Not Allowed"})
