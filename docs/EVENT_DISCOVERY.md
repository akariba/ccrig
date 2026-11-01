# AI event discovery and verified news ingestion

Extends the Data Intelligence Studio so that, for a company the user names, an **operator** can search the **configured approved sources**, retrieve documents,
extract and verify candidate events, and stage the evidence for review. The Global Event Impact Map can then show those events beside (never instead of) the
curated register. Code: `backend/app/discovery/`, configuration: `backend/data/discovery/providers.json`.

## What runs where
| Where | What is available |
|---|---|
| Operator machine / private server with `CCRIG_ENABLE_STUDIO=1` | `python -m app.studio discover NVIDIA` (or `POST /api/studio/discovery/run`); live retrieval only with `CCRIG_DISCOVERY_NETWORK=1`; results staged for review; the map's **Dynamic discovery** mode shows the latest run. |
| Public deployment and GitHub Pages / Pyodide | **Curated register only.** Choosing Dynamic discovery shows "not available here: nothing is searched live and no result is simulated". The comparison still shows the curated side. |

Nothing searches the web when a page loads. A run is an explicit operator action, with its provenance stored.

## The workflow (every stage records real counts and elapsed time in the Studio ledger)
1. **Resolve the entity** to one canonical issuer (exact id / ticker / name / approved alias / core name). Ambiguous or denied names (for example "Samsung") and unknown names stop here: nothing is searched.
2. **Names, aliases, identifiers:** search terms come from the canonical name (legal suffix removed) and approved brand aliases. Tickers identify but are not search terms.
3. **Search configured approved providers.** Each provider is bound to one approved source and its domains; a company-newsroom feed is used only for that company. Unapproved hosts (for example `blogs.nvidia.com`) are listed as excluded and never requested.
4. **Retrieve** documents and metadata (hardened: https only, approved host, public addresses only with the address pinned, size/time limits, bounded redirects, no DTD/entities in feeds). The raw bytes are stored under their SHA-256.
5. **Extract candidates** deterministically: title, publication date (from the source's metadata and confirmed in the text), event date with its stated basis, category by disclosed keyword rules, verbatim quotes, and a place only if the source prints one (dateline, or the issuing country for a government notice).
6. **Deduplicate** reports of the same event (same document, shared quote, or same day with the same title words); the best source is kept, the others recorded as "also reported by".
7. **Verify** against the retrieved text: every quote verbatim, the title, the publication date, the dateline. Failures are excluded with the reason.
8. **Find who is named** with the platform's precise entity rules, and **find documented relationship paths** with the same graph traversal the curated map uses.
9. **Select up to five** with the same rules as the curated register and **disclose them**: eligible = approved source + verified evidence + the company named in the evidence + inside the window; excluded = scenarios, background, duplicates, outside the window; ranking = newest first, then named-in-title, then source tier, then number of verified passages. **This is not a ranking by financial impact.** If fewer than five qualify, fewer are returned and the explanation says why.
10. **Stage** the selected events as a Studio job (`discovered_events`). Validation **re-verifies every row against the stored raw document**, so an edited or forged row cannot pass. A person approves or rejects it; approval, rejection and rollback work exactly as for any Studio dataset.
11. **Feed the map:** the map reads the latest run. Events show their review state: *machine-verified, awaiting review*, *approved* or (rejected runs are hidden, with the reason).

## Where AI is used, and where it is not
| AI may (only if a model is configured via `AI_BASE_URL`/`AI_API_KEY`/`AI_MODEL`) | Deterministic code always decides |
|---|---|
| suggest a category, extra verbatim quotes, and relationship statements for a document | identifiers, entity resolution, dates, places, quote verification, deduplication, selection, graph paths, provenance, every number |

The guard keeps a suggestion only if: the category is one of the allowed ones; each quote is found **verbatim** in the retrieved text (and is then re-verified like any other); each company name appears in its quote and resolves **by the deterministic resolver** to exactly one canonical entity (identifiers the model supplies are ignored). A relationship survives only as a **candidate** labelled `AI_PROPOSED_UNREVIEWED`: it is never an edge, never verified, never used for a path or a score. The model cannot add or remove events, set an impact, or write a canonical record. A run states whether AI was used ("deterministic extraction only (no language model was configured or reachable)" when it was not).

## Current coverage (honest)
Providers today: the **NVIDIA Newsroom RSS feed** (NVDA only) and the **Federal Register** API (any company; the evidence is the title and abstract it returns). For a company with neither a newsroom provider nor a regulator document that names it, discovery finds nothing and says so. SK hynix's newsroom feed redirects and is not configured; SEC EDGAR needs a registered contact and is not configured. Adding a provider means adding it to `providers.json` for an already approved source; adding a source means adding it to `data/events/approved_sources.json`.

## Curated register vs dynamic discovery
| | Curated register | Dynamic discovery |
|---|---|---|
| Built | once, by a script, human-reviewed, committed | by an operator, at run time, staged for review |
| Changes | never until rebuilt | with each run (new events appear; old ones can fall out of the window) |
| Works on Pages / public API | yes | no (disclosed) |
| Role | reproducible fallback and regression benchmark (its output is byte-for-byte unchanged by this feature) | current coverage within configured providers |
| Selection rules, graph, limitations | same | same |

`GET /api/impact-map/{entity}/compare` and the **Compare the two modes** card on the page show counts, the events in both (matched by source document), and what only one mode has.

## Not in this phase
No financial-impact estimate, no exposure amounts, no relationship verified by AI, no automatic promotion, no live search on page load, no provider that is not tied to an approved source.
