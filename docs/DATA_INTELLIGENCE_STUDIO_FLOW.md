# Data Intelligence Studio: watching a real source move through the pipeline

Page: **Data Intelligence Studio** (`/data-studio`, under System). Design: the "Ingest Bench" sheet (title block, status bar, three instrument panels, specification table, event log) with "Neural Cable Graph" cables and node cards. No simulated network, loss curves, token counts or model names.

## What it is built on (nothing rebuilt)
The branch lineage is linear (`phase2/event-impact-map` -> `data-studio` -> `event-discovery` -> `relationship-ccr-integration` -> this branch), so no merge was needed. The page reuses the existing pipeline (acquire, parse, profile, validate, resolve, check, stage), the hash-chained event ledger, review (approve/reject with explicit acknowledgements), release/rollback, the relationship overlay and the Graph Explorer / Impact Map integration. New code: `backend/app/studio/flow.py` (a view over recorded data) and the page under `frontend/src/studio/`.

## Eight stages and the structured event contract
SOURCE -> PARSE -> PROFILE -> VALIDATE -> RESOLVE -> EVIDENCE -> REVIEW -> PROMOTE. Pipeline stages map as ACQUIRE=SOURCE, CHECK+STAGE=EVIDENCE; REVIEW and PROMOTE come from the review/release mechanism.

Each structured event is derived from exactly one persisted ledger row (`id` = ledger sequence, `hash` = ledger hash, `ts` = recorded time). A few rows expand into several events (an approval is a REVIEW and a PROMOTE event: ids `41`, `41.1`). Fields: job id, source id and sha-256 fingerprint, stage id, type, state, `records {processed, accepted, rejected}`, error, `resolution` counts, `evidence` references (stored document hashes), `review_state`, `destination` (dataset, release, kind `STUDIO_OVERLAY`, `canonical_data_modified: false`), `validation` (errors, warnings, codes).

States: queued, running, completed, completed with warnings, failed, checks failed, awaiting review, blocked, approved, rejected, rolled back, not reached. A stage that failed outright stays failed; a stage whose findings contain errors shows "checks failed"; a proposal with blocking findings is held at the gate and promote is "not reached".

Endpoints (operator only; absent unless `CCRIG_ENABLE_STUDIO=1`; all need `X-Studio-Token`): `GET /api/studio/flow/scenarios`, `/flow/scenarios/{id}` (preview and mentions), `POST /flow/run`, `GET /flow/jobs/{id}` (projection), `GET /flow/events?since=` (polling), `GET /flow/stream?since=` (Server-Sent Events, read with fetch so the token header can be sent), `GET /flow/support`. Processing is never delayed for the animation: events are applied as they arrive.

## The canvas
Cables are bright where data passed, dim where nothing did, dashed rose where the next stage refused it (with a refusal mark), pulsing amber at the approval gate. Particles run along a cable only for ~1.7 s after a recorded event for the stage it feeds, or while that stage is recorded as running. With "reduce motion" the same states are drawn without movement. Clicking a stage shows its input, output, findings and history; clicking a cable explains what passed. **Recorded replay** steps through a job's recorded events (pacing compressed for viewing, timestamps shown unchanged); it is always labelled.

## Panels
* **Source Inspector**: submitted file (format, bytes, hash, source id, contract, rows, columns), the stored evidence document (title, date, publisher, tier, URL, hash), and company mentions found by the deterministic name/brand/ticker rules, with the reminder that a mention is not a relationship.
* **Quality & Resolution Inspector**: findings by stage, resolution counts (exact first, never fuzzy; universes never merged), and per-relationship evidence assessments: the quote with both names highlighted, the words between them, whether wording for the relation was found, and whether the quote is found verbatim in the stored document.
* **Execution Timeline**: the recorded events with real timestamps, gaps and durations.
* Metrics come from recording. Measured: stage durations, bytes, rows, job elapsed time, ledger status. Unavailable and stated as such: throughput, latency percentiles, model usage (no language model takes part), quality score.

## The Oracle-NVIDIA journey
1. Select the stored excerpt (company mentions appear). 2. Run claim A (co-occurrence): parsed, validated and resolved, then **failed at the evidence stage** ("both companies are named but nothing states a SUPPLIES relationship"), held at the gate, promote not reached; it cannot be approved. 3. Run claim B (asserted with a written rationale): runs through every stage and **pauses at the approval gate**. 4. The reviewer enters a name, a reason and the explicit acknowledgement (unchecked by default; approval stays disabled without it). 5. Approval publishes to the Studio overlay only. The destination panel shows the overlay edge, the effect (issuers with a documented relationship 21 -> 22, ORCL newly connected, scoring unchanged) and the gaps (no CCR reference to ORCL, no measured exposure, wrong-way risk not assessed). 6. Buttons open the Graph Explorer (approved relationships on) and the Impact Map. 7. Rollback reverses the overlay; approval, rollback and every event stay in the history. Resubmitting identical content creates no new job and records the resubmission.

## Deployment and security
* Operator mode needs the Studio enabled locally with a token (`CCRIG_ENABLE_STUDIO=1 CCRIG_STUDIO_TOKEN=...`); the token is entered in the page and kept for the browser tab only. Nothing here reopens public ingestion.
* The public/static site and any server without the Studio show a **saved recording** (`frontend/public/studio-recordings/oracle-nvidia.json`, produced by `backend/scripts/record_flow.py` from a real run through the operator API). It is labelled "Recorded replay", offers no run, approve, rollback or token controls, and makes no operator request. In the recording, approval and rollback were performed by the script acting as `recording-reviewer`; in live use a person decides.
* The excerpt is a public release; no confidential data is involved. The Studio uses no language model and sends nothing to external services. Do not connect confidential datasets to public hosting or external AI services without explicit authorization and controls.

## Supported domains (stated, not implied)
Relationship evidence: supported end to end. Event evidence, reference entities, portfolio holdings, CCR exposures and limits, CCR counterparties, fact edges, entities, prices: **partial** (contract, validation, review, release, rollback; no live consumer until a person adopts an export; no measured exposures are bundled; no wrong-way-risk interpretation). Unsupported source types: PDF, Word, scans, raw web pages, databases, live feeds.

## Reproduce
`python backend/scripts/relationship_demo.py` (CLI), `python backend/scripts/record_flow.py` (recording), `node frontend/e2e/studio-e2e.mjs` (browser journey against a real operator backend; see the file header), `pytest backend/tests/test_studio_flow.py`, `npm test` (client reduction equals the backend's states for every recorded snapshot).

## Limits
One scenario (Oracle-NVIDIA) is wired to the page; other jobs can be opened from the job list if they target relationship evidence. Throughput and latency are not measured. The recording shows a past run, not the current state of any workspace. Live "streaming" of a ~20 ms job is brief by nature; the afterglow of particles is display only.
