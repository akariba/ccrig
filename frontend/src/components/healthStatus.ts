// What the sidebar badge says about the backend. Kept as a pure function so
// the wording is testable and cannot drift into claiming a mode that was
// never actually reported by the backend.

export type BackendHealth =
  | { unreachable: true }
  | { ai_enabled?: boolean; ai_model?: string | null }
  | null;

export interface BackendStatus {
  title: string;
  detail: string;
  tone: "pending" | "ok" | "error";
}

export function describeBackendStatus(health: BackendHealth): BackendStatus {
  if (health === null) {
    return { title: "Connecting...", detail: "", tone: "pending" };
  }
  if ("unreachable" in health) {
    return {
      title: "Backend unreachable",
      detail: "The API did not respond - data on this page may be missing or out of date. Retrying...",
      tone: "error",
    };
  }
  return {
    title: health.ai_enabled ? "Enhanced AI mode" : "Offline deterministic mode",
    detail: health.ai_model ? `Model: ${health.ai_model}` : "No AI_API_KEY set \u2014 full functionality retained",
    tone: "ok",
  };
}
