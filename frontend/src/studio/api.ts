// Client for the operator-only Studio endpoints. These exist only when the operator enabled the Studio on their own machine or private server; the public site has no
// server at all, so none of this is reachable there (the page then offers a saved recording instead). The operator token is kept for the browser session only.
import type { FlowEvent, Preview, Projection, Recording, ScenarioInfo, SupportMatrix } from "./types";

const BASE = import.meta.env.VITE_API_HOST ? `https://${import.meta.env.VITE_API_HOST}` : "";
export const STATIC_SITE = import.meta.env.VITE_STATIC_BACKEND === "true";
const TOKEN_KEY = "ccrig.studio.token";

export const getToken = (): string => { try { return sessionStorage.getItem(TOKEN_KEY) ?? ""; } catch { return ""; } };
export const setToken = (t: string): void => {
  try {
    if (t) sessionStorage.setItem(TOKEN_KEY, t);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch { /* storage unavailable: the token lives in the page only */ }
};

export class OpError extends Error {
  status: number; code: string;
  constructor(status: number, code: string, message: string) { super(message); this.status = status; this.code = code; }
}

async function op<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, { ...init, headers: { "Content-Type": "application/json", "X-Studio-Token": getToken(), ...(init.headers ?? {}) } });
  if (!res.ok) {
    let code = String(res.status), message = res.statusText;
    try { const d = (await res.json()).detail; if (typeof d === "string") message = d; else if (d?.message) { message = d.message; code = d.code ?? code; } } catch { /* body was not JSON */ }
    throw new OpError(res.status, code, message);
  }
  return res.json();
}

export interface StudioStatus { enabled: boolean; mode: string }
/** What this deployment can do: 'static' (no server), 'offline' (server unreachable), 'disabled' (server without the Studio), or the status document. */
export async function readStatus(): Promise<{ kind: "static" | "offline" | "disabled" | "enabled"; status?: StudioStatus }> {
  if (STATIC_SITE) return { kind: "static" };
  try {
    const res = await fetch(BASE + "/api/studio/status");
    if (!res.ok) return { kind: "offline" };
    const status: StudioStatus = await res.json();
    return { kind: status.enabled ? "enabled" : "disabled", status };
  } catch { return { kind: "offline" }; }
}

export interface JobRow { job_id: string; source_id: string; status: string; created_at: string; blocking: boolean }
export const studioApi = {
  scenarios: () => op<{ scenarios: ScenarioInfo[]; last_seq: number; jobs: JobRow[] }>("/api/studio/flow/scenarios"),
  preview: (id: string) => op<Preview>(`/api/studio/flow/scenarios/${id}`),
  support: () => op<SupportMatrix>("/api/studio/flow/support"),
  run: (scenario: string, claim: string, operator: string) => op<{ job: { job_id: string }; duplicate: boolean }>("/api/studio/flow/run", { method: "POST", body: JSON.stringify({ scenario, claim, operator }) }),
  job: (id: string) => op<Projection>(`/api/studio/flow/jobs/${id}`),
  approve: (id: string, body: { reviewer: string; reason: string; acknowledge_assertions: boolean }) => op<{ release_id: number }>(`/api/studio/jobs/${id}/approve`, { method: "POST", body: JSON.stringify(body) }),
  reject: (id: string, body: { reviewer: string; reason: string }) => op<{ status: string }>(`/api/studio/jobs/${id}/reject`, { method: "POST", body: JSON.stringify(body) }),
  rollback: (dataset: string, body: { reviewer: string; reason: string }) => op<unknown>(`/api/studio/datasets/${dataset}/rollback`, { method: "POST", body: JSON.stringify(body) }),
  events: (since: number, jobId?: string) => op<{ events: FlowEvent[]; last_seq: number }>(`/api/studio/flow/events?since=${since}${jobId ? `&job_id=${encodeURIComponent(jobId)}` : ""}`),
};

/** Server-Sent Events over fetch (EventSource cannot send the token header). Resolves when the server ends the stream; rejects on a network or HTTP error. */
export async function streamEvents(since: number, onEvent: (e: FlowEvent) => void, signal: AbortSignal, timeoutS = 20): Promise<void> {
  const res = await fetch(`${BASE}/api/studio/flow/stream?since=${since}&timeout=${timeoutS}`, { headers: { "X-Studio-Token": getToken() }, signal });
  if (!res.ok || !res.body) throw new OpError(res.status, "STREAM", "the event stream is not available");
  const reader = res.body.getReader(), dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buf += dec.decode(value, { stream: true });
    let cut: number;
    while ((cut = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, cut); buf = buf.slice(cut + 2);
      const kind = /^event: (.*)$/m.exec(block)?.[1], data = /^data: (.*)$/m.exec(block)?.[1];
      if (kind === "flow" && data) onEvent(JSON.parse(data) as FlowEvent);
      if (kind === "end") return;
    }
  }
}

/** The saved recording shipped with the site (read-only; produced by backend/scripts/record_flow.py). */
export async function loadRecording(): Promise<Recording | null> {
  try {
    const res = await fetch(`${import.meta.env.BASE_URL}studio-recordings/oracle-nvidia.json`);
    return res.ok ? ((await res.json()) as Recording) : null;
  } catch { return null; }
}
