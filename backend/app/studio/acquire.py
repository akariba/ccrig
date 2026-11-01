"""Source acquisition: size and content limits, content sniffing, and parsing to a plain table.

Nothing here executes or evaluates content: only csv, json and (when pyarrow is installed) parquet are read, with hard limits.
There is deliberately no network fetching: bytes arrive from an operator (CLI file or authenticated upload).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from importlib import util as importlib_util

from .config import Limits


class IngestRejected(Exception):
    """The input is refused before any parsing result is trusted. `code` is stable and machine-readable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


_FORBIDDEN_MAGIC = [
    (b"MZ", "a Windows executable"), (b"\x7fELF", "a Linux executable"), (b"\xcf\xfa\xed\xfe", "a macOS executable"), (b"\xca\xfe\xba\xbe", "a macOS/Java binary"),
    (b"PK\x03\x04", "a zip archive"), (b"\x1f\x8b", "a gzip archive"), (b"BZh", "a bzip2 archive"), (b"7z\xbc\xaf\x27\x1c", "a 7z archive"),
    (b"%PDF", "a PDF"), (b"#!", "a script"), (b"\xd0\xcf\x11\xe0", "an Office/OLE document"),
]
_MARKUP = re.compile(rb"^\s*(<\?php|<script|<!doctype|<html|<\?xml)", re.I)
_EXT = {".csv": "csv", ".json": "json", ".parquet": "parquet"}


def parquet_supported() -> bool:
    return importlib_util.find_spec("pyarrow") is not None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_filename(name: str) -> str:
    base = (name or "upload").replace("\\", "/").rsplit("/", 1)[-1]
    base = re.sub(r"[^A-Za-z0-9._\- ]", "_", base)[:120].strip(" .")
    return base or "upload"


def sniff(data: bytes, filename: str, limits: Limits) -> str:
    """Return 'csv' | 'json' | 'parquet' or raise IngestRejected. The declared extension must agree with the content."""
    if not data:
        raise IngestRejected("EMPTY_INPUT", "the file is empty")
    if len(data) > limits.max_bytes:
        raise IngestRejected("OVERSIZE", f"{len(data):,} bytes exceeds the limit of {limits.max_bytes:,}")
    for magic, what in _FORBIDDEN_MAGIC:
        if data.startswith(magic):
            raise IngestRejected("FORBIDDEN_CONTENT", f"the content looks like {what}; only csv, json and parquet tables are accepted")
    if _MARKUP.match(data[:512]):
        raise IngestRejected("FORBIDDEN_CONTENT", "the content looks like markup or script; only csv, json and parquet tables are accepted")
    ext = "." + safe_filename(filename).rsplit(".", 1)[-1].lower() if "." in safe_filename(filename) else ""
    fmt = _EXT.get(ext)
    if fmt is None:
        raise IngestRejected("UNSUPPORTED_EXTENSION", f"extension '{ext or '(none)'}' is not one of .csv, .json, .parquet")
    if fmt == "parquet":
        if not (data[:4] == b"PAR1" and data[-4:] == b"PAR1"):
            raise IngestRejected("CONTENT_MISMATCH", "the file is named .parquet but does not have parquet markers")
        return fmt
    if b"\x00" in data[:65536]:
        raise IngestRejected("BINARY_CONTENT", "NUL bytes found; this is not a text table")
    head = data.lstrip(b"\xef\xbb\xbf \t\r\n")[:1]
    if fmt == "json" and head not in (b"{", b"["):
        raise IngestRejected("CONTENT_MISMATCH", "the file is named .json but does not start like JSON")
    if fmt == "csv" and head in (b"{", b"["):
        raise IngestRejected("CONTENT_MISMATCH", "the file is named .csv but looks like JSON")
    return fmt


@dataclass
class Parsed:
    format: str
    columns: list
    rows: list                                   # list of dict, in file order
    findings: list = field(default_factory=list)  # parse-level findings (dicts)
    wrapper_key: str | None = None
    row_numbers: list = field(default_factory=list)  # 1-based source row/record number for each row


def _finding(severity, code, message, **extra):
    return {"stage": "PARSE", "severity": severity, "code": code, "message": message, **extra}


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestRejected("BAD_ENCODING", f"not valid UTF-8 (byte {exc.start})") from None


def _clip(value, limits: Limits):
    if isinstance(value, str) and len(value) > limits.max_cell_chars:
        raise IngestRejected("CELL_TOO_LONG", f"a cell exceeds {limits.max_cell_chars:,} characters")
    return value


def parse_csv(data: bytes, limits: Limits) -> Parsed:
    text = _decode(data)
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader)
    except StopIteration:
        raise IngestRejected("EMPTY_INPUT", "no header row") from None
    except csv.Error as exc:
        raise IngestRejected("MALFORMED_CSV", str(exc)) from None
    header = [h.strip() for h in header]
    if len(header) > limits.max_columns:
        raise IngestRejected("TOO_MANY_COLUMNS", f"{len(header)} columns exceeds the limit of {limits.max_columns}")
    out = Parsed("csv", header, [])
    seen = set()
    for i, h in enumerate(header):
        if not h:
            out.findings.append(_finding("ERROR", "EMPTY_HEADER", f"column {i + 1} has no name", column=i + 1))
        elif h in seen:
            out.findings.append(_finding("ERROR", "DUPLICATE_HEADER", f"column name '{h}' appears more than once", column=h))
        seen.add(h)
    try:
        for n, raw in enumerate(reader, start=2):               # row 1 is the header
            if not raw or all(not c.strip() for c in raw):
                continue
            if len(out.rows) >= limits.max_rows:
                raise IngestRejected("TOO_MANY_ROWS", f"more than {limits.max_rows:,} rows")
            if len(raw) != len(header):
                out.findings.append(_finding("ERROR", "RAGGED_ROW", f"row {n} has {len(raw)} cells but the header has {len(header)}", row=n))
                raw = (raw + [""] * len(header))[: len(header)]
            row = {h: (_clip(c, limits).strip() or None) for h, c in zip(header, raw) if h}
            out.rows.append(row)
            out.row_numbers.append(n)
    except csv.Error as exc:
        raise IngestRejected("MALFORMED_CSV", str(exc)) from None
    return out


def _depth_ok(obj, limit):
    stack = [(obj, 1)]
    while stack:
        cur, d = stack.pop()
        if d > limit:
            return False
        if isinstance(cur, dict):
            stack.extend((v, d + 1) for v in cur.values() if isinstance(v, (dict, list)))
        elif isinstance(cur, list):
            stack.extend((v, d + 1) for v in cur if isinstance(v, (dict, list)))
    return True


def parse_json(data: bytes, limits: Limits, list_key: str | None = None) -> Parsed:
    text = _decode(data)
    dups: list = []

    def pairs(items):
        keys = [k for k, _ in items]
        for k in set(keys):
            if keys.count(k) > 1:
                dups.append(k)
        return dict(items)

    def no_constant(name):
        raise ValueError(f"{name} is not valid JSON")

    try:
        doc = json.loads(text, object_pairs_hook=pairs, parse_constant=no_constant)
    except (ValueError, RecursionError) as exc:
        raise IngestRejected("MALFORMED_JSON", str(exc)[:200]) from None
    if not _depth_ok(doc, limits.max_depth):
        raise IngestRejected("TOO_DEEP", f"nesting deeper than {limits.max_depth} levels")
    wrapper = None
    if isinstance(doc, dict):
        lists = {k: v for k, v in doc.items() if isinstance(v, list) and v and all(isinstance(x, dict) for x in v)}
        if list_key and list_key in lists:
            wrapper, doc = list_key, lists[list_key]
        elif len(lists) == 1:
            wrapper, doc = next(iter(lists)), next(iter(lists.values()))
        else:
            raise IngestRejected("UNSUPPORTED_JSON_SHAPE", "expected a list of records, or an object holding exactly one list of records")
    if not isinstance(doc, list) or not all(isinstance(x, dict) for x in doc):
        raise IngestRejected("UNSUPPORTED_JSON_SHAPE", "expected a list of JSON objects")
    if len(doc) > limits.max_rows:
        raise IngestRejected("TOO_MANY_ROWS", f"{len(doc):,} records exceeds the limit of {limits.max_rows:,}")
    columns: list = []
    for rec in doc:
        for k in rec:
            if k not in columns:
                columns.append(k)
    if len(columns) > limits.max_columns:
        raise IngestRejected("TOO_MANY_COLUMNS", f"{len(columns)} distinct keys exceeds the limit of {limits.max_columns}")
    for rec in doc:
        for v in rec.values():
            _clip(v, limits)
    out = Parsed("json", columns, doc, wrapper_key=wrapper, row_numbers=list(range(1, len(doc) + 1)))
    if dups:
        out.findings.append(_finding("ERROR", "DUPLICATE_JSON_KEY", f"an object repeats the key(s) {sorted(set(dups))[:5]}; the later value would silently win"))
    return out


def parse_parquet(data: bytes, limits: Limits) -> Parsed:
    if not parquet_supported():
        raise IngestRejected("PARQUET_UNSUPPORTED", "parquet needs the optional 'pyarrow' package, which is not installed here (csv and json are supported)")
    import pyarrow.parquet as pq  # noqa: PLC0415 - optional dependency, only on the operator machine

    try:
        meta = pq.ParquetFile(io.BytesIO(data)).metadata
        if meta.num_rows > limits.max_rows:
            raise IngestRejected("TOO_MANY_ROWS", f"{meta.num_rows:,} rows exceeds the limit of {limits.max_rows:,}")
        if meta.num_columns > limits.max_columns:
            raise IngestRejected("TOO_MANY_COLUMNS", f"{meta.num_columns} columns exceeds the limit of {limits.max_columns}")
        table = pq.read_table(io.BytesIO(data))
    except IngestRejected:
        raise
    except Exception as exc:  # noqa: BLE001 - any reader failure is a rejected input, reported with its type
        raise IngestRejected("MALFORMED_PARQUET", f"{type(exc).__name__}: {str(exc)[:160]}") from None
    rows = table.to_pylist()
    for rec in rows:
        for k, v in list(rec.items()):
            if hasattr(v, "isoformat"):
                rec[k] = v.isoformat()
            _clip(rec[k], limits)
    return Parsed("parquet", list(table.column_names), rows, row_numbers=list(range(1, len(rows) + 1)))


def parse(fmt: str, data: bytes, limits: Limits, list_key: str | None = None) -> Parsed:
    if fmt == "csv":
        return parse_csv(data, limits)
    if fmt == "json":
        return parse_json(data, limits, list_key)
    if fmt == "parquet":
        return parse_parquet(data, limits)
    raise IngestRejected("UNSUPPORTED_FORMAT", fmt)
