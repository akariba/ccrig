// Shapes returned by the Studio's flow endpoints (backend/app/studio/flow.py) and by a saved recording of them. Fields not needed by the page are left out.

export type StageId = "SOURCE" | "PARSE" | "PROFILE" | "VALIDATE" | "RESOLVE" | "LLM" | "EVIDENCE" | "REVIEW" | "PROMOTE";

export interface Records { unit: string; processed: number | null; accepted: number | null; rejected: number | null; columns?: number | null; duplicate_rows?: number | null }
export interface LlmCall { provider: string | null; model: string | null; calls: number | null; latency_ms: number | null; input_tokens: number | null; output_tokens: number | null }
export interface Destination { dataset: string; scope: string; version: number; release_id: number; rows: number; kind: string; canonical_data_modified: boolean }

export interface FlowEvent {
  id: string; seq: number; hash: string; job_id: string | null; source_id: string | null; source_sha256: string | null; ts: string;
  pipeline_stage: string; type: string; message: string; elapsed_ms: number | null; error: { type: string; code?: string | null; message: string } | null;
  stage_id: StageId | null; state: string | null; records: Records | null;
  resolution: { distinct_identifiers: number; resolved: number; mapped: number; ambiguous: number; unresolved: number } | null;
  evidence: { references: { source_sha256: string; source_url?: string; source_publisher?: string; source_tier?: string; source_published_date?: string }[] } | null;
  review_state: string | null; destination: Destination | null; llm?: LlmCall | null; validation: { errors: number; warnings: number; codes: Record<string, number> } | null;
}

export interface Finding { severity: string; code: string; message: string; row?: number | null; field?: string | null }
export interface StageInfo {
  id: StageId; label: string; state: string; started_at: string | null; finished_at: string | null; duration_ms: number | null; records: Records | null; events: string[];
  findings: Finding[]; resolution: FlowEvent["resolution"]; llm?: LlmCall | null; message: string | null; inputs?: Record<string, unknown>; outputs?: Record<string, unknown>;
}
export interface Connection { from: StageId; to: StageId; state: string; what: string | null }

export interface QuoteAssessment {
  quote: string; found_in_stored_source: boolean | null; both?: boolean; order?: string | null; cue?: string | null; orientation?: string | null; direction_ok?: boolean | null;
  spans: { entity_id: string; start: number; end: number; role: "source" | "target" }[]; between: string | null;
}
export interface Assessment {
  row: number; source: string; relation: string; target: string; semantics: { direction: string; symmetric: boolean } | null; as_of: string; assertion: Record<string, unknown>;
  quotes: QuoteAssessment[]; verdict: string; why: string; findings: { severity: string; code: string; message: string }[];
}
export interface MentionItem { entity_id: string; matched_text: string; rule: string; start: number; end: number; context: string; context_offset: number }
export interface MentionSummary { entity_id: string; name: string; ticker?: string | null; count: number }
export interface SourceDocument {
  source_sha256: string; source_url?: string; source_publisher?: string; source_tier?: string; source_published_date?: string; stored: boolean; bytes?: number; text_chars?: number;
  mentions: MentionItem[]; entities: MentionSummary[]; mention_total: number; note?: string; problem?: string;
}
export interface Proposal {
  source: string; relation: string; target: string; semantics: { direction: string } | null; as_of: string; quotes: string[]; assertion: Record<string, unknown>;
  provenance: Record<string, string | null>; verification: Record<string, unknown>; is_synthetic: boolean;
}
export interface DestinationView {
  dataset: string; kind: string; canonical_data_modified: boolean; status: string; current_release: Record<string, unknown> | null; edges: { source: string; relation: string; target: string }[];
  links: { label: string; href: string; testid: string }[];
  adoption: { connectivity: Record<string, unknown>; scoring_changed_by_approval: boolean; linked_counterparties: { portfolio_holdings: { counterparty: string }[]; ccr_reference_entities: Record<string, { ccr_counterparty: string; product: string }[]> }; gaps: string[] } | null;
}
export interface ReviewView {
  state: string; decisions: { decision: string; reviewer: string; reason: string; at: string; detail: unknown }[]; can_approve: boolean;
  requires: { acknowledge_assertions: boolean; acknowledge_mappings: boolean; acknowledge_changes: boolean; assertions_to_confirm: string[][] } | null;
  blocked_because: { code: string; message: string }[] | null;
}
export interface Projection {
  job: { job_id: string; source_id: string; filename: string; format: string | null; sha256: string | null; bytes: number | null; target: string; scope: string; classification: string; operator: string;
         status: string; blocking: boolean; created_at: string; updated_at: string; elapsed_ms: number | null; error_code: string | null; error_message: string | null };
  state: string | null; stages: StageInfo[]; connections: Connection[]; events: FlowEvent[]; review: ReviewView; source_documents: SourceDocument[]; assessments: Assessment[];
  quality: { summary: { errors: number; warnings: number; blocking: boolean } | null; findings: (Finding & { stage?: string })[] };
  proposal: Proposal[]; destination: DestinationView;
  metrics: { measured: { job_elapsed_ms: number | null; stage_ms: Record<string, number>; bytes: number | null; rows_parsed: number | null }; unavailable: { metric: string; reason: string }[] };
  ledger: { ok: boolean; events: number; first_bad_seq: number | null }; manifest: Record<string, unknown>;
}

export interface SupportMatrix {
  domains: { dataset: string; label: string; level: string; supported: string; limits: string; contract: boolean }[];
  formats: { format: string; level: string; note: string }[];
}
export interface Preview {
  id: string; title: string; source_url: string; source_title: string; published_date: string; sha256: string; bytes: number; text_chars: number; quote: string; quote_found_verbatim: boolean;
  mentions: MentionItem[]; mention_total: number; entities: MentionSummary[]; note: string;
}
export interface ScenarioInfo { id: string; title: string; description: string; available: boolean; source_url: string | null; bytes: number; published_date: string; claims: { id: string; label: string; meaning: string }[]; note: string | null }

export interface Recording {
  schema: string; label: string; scenario: string; recorded_at: string; recorded_by: string; note: string; preview: Preview; scenario_info: ScenarioInfo; support: SupportMatrix;
  cooccurrence: { after_ingest: Projection };
  asserted: { after_ingest: Projection; after_approval: Projection; after_rollback: Projection; duplicate_submission: { job_id: string; duplicate: boolean } };
  graph_proof: { before_approval: GraphProof; after_approval: GraphProof; after_rollback: GraphProof; note: string };
}
export interface GraphProof {
  edge_present: boolean; overlay: { available?: boolean; edges_added?: number };
  edge?: { source: string; relation: string; target: string; weight: number | null; evidence_status: string; provenance: Record<string, string>; assertion: string };
}
