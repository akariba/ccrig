# Data Intelligence Studio — functional ingestion MVP

Implements the backend of the architecture in `DATA_INTELLIGENCE_STUDIO.md` (animated UI deliberately not built yet).
Code: `backend/app/studio/`, `backend/app/routers/studio.py` (public, read-only) and `studio_ops.py` (operator only), CLI `python -m app.studio`.

## What it does
`acquire → parse → profile → validate → resolve → check → stage → (human review) → approve | reject → rollback / restore`.
A source file becomes a **job**. Each stage records `STARTED`, then `COMPLETED` (real counts, real elapsed milliseconds) or `FAILED`
(error type, code, message). Nothing is promoted automatically, and **nothing in `backend/data` or any scoring input is ever written**:
approval publishes a versioned *release* inside the Studio workspace. Analytics keep reading the canonical files until a person adopts an
export through a separately authorised change.

| Capability | Behaviour |
|---|---|
| Inputs | CSV, JSON (list of records, or one object holding one list), Parquet **only if `pyarrow` is installed** (otherwise an explicit `PARQUET_UNSUPPORTED` rejection). No network fetching; bytes come from a local file (CLI) or an authenticated upload. |
| Limits (env-configurable) | `CCRIG_STUDIO_MAX_BYTES` 10 MB, `_MAX_ROWS` 200 000, `_MAX_COLUMNS` 200, `_MAX_DEPTH` 8, `_MAX_CELL_CHARS` 10 000. |
| Refused outright (never stored) | executables, archives, PDFs, scripts, HTML, NUL-byte "text", extension/content mismatches, bad UTF-8, `NaN`/`Infinity`, over-deep JSON, oversize, too many rows/columns. |
| Manifest | source id, job id, file name (sanitised), format, SHA-256, size, time, classification, operator, tool version, limits. Raw bytes are stored once under their hash and re-verified on every read. |
| Profile | column types, null %, distinct counts, duplicate-row rate, mixed-type and partial columns, exact canonical-identifier coverage, min/max and age of date columns, representative sample rows. Deterministic (reference date is explicit). |
| Validation | typed contracts for `entities`, `fact_edges`, `exposure_edges`, `ccr_counterparties`, `prices` (mirroring the canonical files); required columns/values, enums, ranges, patterns, https links; duplicate detection (identical → collapsed with a warning, conflicting → blocks); cross-record rules (no self-loops, a "documented" relationship needs an https link, a synthetic relationship may not claim to be documented, holdings ≤ 100 %, a limit value needs a limit type, price series gaps/outliers/future dates). `profile_only` profiles any table and promotes nothing. |
| Entity resolution | exact canonical id → exact after trim/upper-case → exact ticker → exact entity name → approved brand alias. Never fuzzy. `AMBIGUOUS` lists every candidate and picks none; `UNRESOLVED` says why (including denied aliases and **wrong universe**: a CCR counterparty id is never resolved as a portfolio counterparty). Only exact ids are applied silently; ticker/name/alias mappings are applied, recorded and must be acknowledged at approval. |
| Staging | the proposal, rows excluded and why, mappings, and a diff against **(a)** the previous approved release and **(b)** the canonical dataset (read-only): new / unchanged / changed with the changed fields. Changes need an explicit acknowledgement. |
| Approval | reviewer and reason mandatory; refused when blocking findings exist, mappings or changes are unacknowledged, the job is not pending, the approved state moved since staging (`STALE_BASE`), or the result would equal the current state (`ALREADY_CURRENT`). |
| Idempotency | same source + same bytes + same target/scope returns the existing job (a `RESUBMITTED` event is logged); `force_new` creates a new, explicitly linked version. |
| Rollback / restore | roll back to the previous approved state (or to "no approved state"); restore any earlier release (hash-verified first). Newer releases become `ROLLED_BACK`; nothing is deleted. |
| Monitoring | per-job event stream and a **hash-chained ledger** (`verify-ledger` detects edited or deleted history); job status, findings by code, record counts, elapsed time, error details, decisions, lineage (job → manifest → SHA-256 → release). |
| Durability | SQLite (WAL) + content-hashed files under the workspace; survives restarts (tested in-process, and across separate OS processes). |

## Running it
```
cd backend
python -m app.studio ingest data/raw_prices/SKHY_price_history_2024-01-01_2026-08-06_1day_310ff2.csv --source-id skhy-prices --target prices --scope SKHY
python -m app.studio jobs | show JOB | staging JOB | events JOB
python -m app.studio approve JOB --reviewer NAME --reason TEXT [--ack-mappings] [--ack-changes]
python -m app.studio reject JOB ... | rollback DATASET [--scope S] ... | restore DATASET --release-id N ... | export DATASET [--scope S] | datasets | releases DATASET | verify-ledger
python scripts/studio_demo.py          # the end-to-end demonstration on real data
```
Workspace: `$CCRIG_STUDIO_DIR` or `~/.ccrig-studio`. It **refuses to live inside `backend/data` or `frontend/public|dist`** (those are published with the static site).

## HTTP API (operator only)
Registered **only** when `CCRIG_ENABLE_STUDIO=1`; every request must carry `X-Studio-Token` equal to `CCRIG_STUDIO_TOKEN`
(disabled → 404, enabled without a token → 503, wrong token → 401). The CORS allow-list does not include that header, so other browser origins cannot use it.
Do **not** enable it on the public Render service: the shared API has no user accounts. `GET /api/studio/status` and `/api/studio/contracts` are always available and read-only.

`POST /api/studio/jobs?source_id&filename&target[&scope&classification&operator&force_new]` (raw file body) · `GET /jobs`, `/jobs/{id}`, `/jobs/{id}/staging` ·
`POST /jobs/{id}/approve|reject` · `GET /datasets`, `/datasets/{d}/releases|export` · `POST /datasets/{d}/rollback|restore` · `GET /ledger/verify`.

## Deployment boundaries
* **GitHub Pages / Pyodide:** read-only. The operator router is not registered, `status` reports `disabled`, no workspace exists, nothing can be ingested or stored. (Request parity and the real-Pyodide check cover the new public routes.)
* **Local / private server:** full ingestion, review and rollback, with a persistent workspace outside the repository.
* Raw sources, staging and decisions never enter `backend/data`, so they cannot be published by `vendor-backend.mjs`. `CONFIDENTIAL` classification is recorded in the manifest; real confidential CCR data must only be processed on an operator machine.

## Known limits (deliberate for the MVP)
* One workspace, one operator at a time (SQLite transactions serialise writers); no multi-user roles, so reviewer independence cannot be enforced.
* Approved releases are **not consumed by analytics**. Adopting one means writing it into the canonical files through the build scripts and running the baseline check; that is a separate decision.
* Merge semantics only: rows missing from a later file are never deleted.
* Scoped datasets: `prices` only (one dataset per entity).
* A promoted record keeps the shape of its canonical file; per-row lineage lives in the job/release records, not inside the rows.
* `pyarrow` is not installed here, so the Parquet read path is covered by a test that is skipped unless the package is present; the "unsupported" path is tested.
