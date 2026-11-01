"""Studio settings. Read from the environment at call time (so tests and operators can change them without re-importing)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..core import config as core_config

_TRUE = {"1", "true", "yes", "on"}


def studio_enabled() -> bool:
    """Off unless explicitly switched on. Never on for the public static build (no environment, no server)."""
    return os.environ.get("CCRIG_ENABLE_STUDIO", "").strip().lower() in _TRUE


def studio_token() -> str:
    return os.environ.get("CCRIG_STUDIO_TOKEN", "").strip()


class UnsafeWorkspace(Exception):
    pass


def studio_dir() -> Path:
    """The durable workspace. Must not be inside anything the static build publishes (backend/data) or the frontend's public folder."""
    root = Path(os.environ.get("CCRIG_STUDIO_DIR", "") or Path.home() / ".ccrig-studio").expanduser().resolve()
    repo = core_config.BACKEND_DIR.parent
    forbidden = [core_config.DATA_DIR.resolve(), (repo / "frontend" / "public").resolve(), (repo / "frontend" / "dist").resolve()]
    for bad in forbidden:
        if root == bad or bad in root.parents:
            raise UnsafeWorkspace(f"the Studio workspace may not live inside {bad} (that folder is published with the static site)")
    return root


@dataclass(frozen=True)
class Limits:
    max_bytes: int = 10_000_000
    max_rows: int = 200_000
    max_columns: int = 200
    max_depth: int = 8
    max_cell_chars: int = 10_000
    max_findings: int = 500
    sample_rows: int = 8


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default
    return value if value > 0 else default


def limits() -> Limits:
    d = Limits()
    return Limits(
        max_bytes=_int_env("CCRIG_STUDIO_MAX_BYTES", d.max_bytes), max_rows=_int_env("CCRIG_STUDIO_MAX_ROWS", d.max_rows),
        max_columns=_int_env("CCRIG_STUDIO_MAX_COLUMNS", d.max_columns), max_depth=_int_env("CCRIG_STUDIO_MAX_DEPTH", d.max_depth),
        max_cell_chars=_int_env("CCRIG_STUDIO_MAX_CELL_CHARS", d.max_cell_chars), max_findings=_int_env("CCRIG_STUDIO_MAX_FINDINGS", d.max_findings),
    )
