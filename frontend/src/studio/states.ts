// Colour and wording for each recorded state. Colour carries state and nothing else.
export const STATE_COLOR: Record<string, string> = {
  QUEUED: "#566472", RUNNING: "#f2a93b", COMPLETED: "#58BE9C", COMPLETED_WITH_WARNINGS: "#E2AE45", FAILED: "#E07A90", FAILED_CHECKS: "#E07A90", AWAITING_REVIEW: "#f2a93b",
  BLOCKED: "#E07A90", APPROVED: "#58BE9C", REJECTED: "#E07A90", ROLLED_BACK: "#a98ae0", SKIPPED: "#3b4752",
};
export const STATE_LABEL: Record<string, string> = {
  QUEUED: "queued", RUNNING: "running", COMPLETED: "completed", COMPLETED_WITH_WARNINGS: "warnings", FAILED: "failed", FAILED_CHECKS: "checks failed", AWAITING_REVIEW: "awaiting review",
  BLOCKED: "blocked", APPROVED: "approved", REJECTED: "rejected", ROLLED_BACK: "rolled back", SKIPPED: "not reached",
};
