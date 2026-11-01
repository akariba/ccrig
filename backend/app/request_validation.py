"""Shared request-validation building blocks.

Routers declare constraints with these types / `Query(...)` bounds. They are
enforced identically by FastAPI (server) and by `browser_dispatch` (the
in-browser Pyodide build), because both validate through pydantic.

Only genuinely invalid input is rejected. Nothing here changes how a valid
request is computed.
"""
import math
from typing import Annotated, Dict

from pydantic import AfterValidator, StringConstraints

from .core.config import DEFAULT_WEIGHTS, MAX_TOP_K, WEIGHT_PRESETS  # noqa: F401  (MAX_TOP_K re-exported for routers)

MAX_TEXT_CHARS = 20_000       # headline / narrative / search box: far above any real input
MAX_ID_CHARS = 64             # entity / theme / scenario identifiers
MAX_FILTER_CHARS = 100        # free-text filters (sector, country, kind, ...)

WEIGHT_KEYS = tuple(DEFAULT_WEIGHTS)


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


def _check_weights(weights: Dict[str, float]) -> Dict[str, float]:
    unknown = sorted(set(weights) - set(WEIGHT_KEYS))
    if unknown:
        raise ValueError(f"unknown weight component(s) {unknown}; allowed: {sorted(WEIGHT_KEYS)}")
    bad = {k: v for k, v in weights.items() if not math.isfinite(v) or v < 0 or v > 1}
    if bad:
        raise ValueError(f"weights must be finite numbers between 0 and 1; got {bad}")
    if sum(weights.values()) <= 0:
        raise ValueError("at least one weight must be greater than 0")
    return weights


def _check_preset(preset: str) -> str:
    if preset not in WEIGHT_PRESETS:
        raise ValueError(f"unknown preset '{preset}'; allowed: {sorted(WEIGHT_PRESETS)}")
    return preset


EntityId = Annotated[str, StringConstraints(min_length=1, max_length=MAX_ID_CHARS)]
NonBlankText = Annotated[str, StringConstraints(max_length=MAX_TEXT_CHARS), AfterValidator(_non_blank)]
Weights = Annotated[Dict[str, float], AfterValidator(_check_weights)]
Preset = Annotated[str, AfterValidator(_check_preset)]
