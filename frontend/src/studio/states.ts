// Colour and wording for each recorded state. State colours: teal completed, amber running / awaiting, gold warnings, rose refused, steel rolled back.
// Category colours (which kind of processing a module is) are separate and never mean a state.
export const STATE_COLOR: Record<string, string> = {
  QUEUED: "#566472", RUNNING: "#f2a93b", COMPLETED: "#58BE9C", COMPLETED_WITH_WARNINGS: "#E2AE45", FAILED: "#E07A90", FAILED_CHECKS: "#E07A90", AWAITING_REVIEW: "#f2a93b",
  BLOCKED: "#E07A90", APPROVED: "#58BE9C", REJECTED: "#E07A90", ROLLED_BACK: "#9db4c8", SKIPPED: "#3f4b57",
};
export const STATE_LABEL: Record<string, string> = {
  QUEUED: "queued", RUNNING: "running", COMPLETED: "completed", COMPLETED_WITH_WARNINGS: "warnings", FAILED: "failed", FAILED_CHECKS: "checks failed", AWAITING_REVIEW: "awaiting review",
  BLOCKED: "blocked", APPROVED: "approved", REJECTED: "rejected", ROLLED_BACK: "rolled back", SKIPPED: "not reached",
};
export const KIND_COLOR: Record<string, string> = { ingest: "#6EA5D8", deterministic: "#5fb7c9", llm: "#a28bf0", verify: "#d9b25a", gate: "#e8e2d0", output: "#7fd69a" };
export const KIND_LABEL: Record<string, string> = { ingest: "source ingestion", deterministic: "deterministic processing", llm: "LLM execution", verify: "evidence verification", gate: "human review", output: "output" };
