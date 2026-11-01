// The typed event schema streamed by the backend (backend/app/ingest_events.py) and consumed by the UI, and the state the UI reduces it into.
export type Stage = "A" | "B" | "C" | "D";
export type Domain = "credit" | "market" | "signals";
export type CheckName = "completeness" | "schemaMatch" | "duplicates" | "ratingMap" | "creditEvents" | "freshness";
export interface SourceInfo { name: string; totalRows: number; domain: Domain }

export type IngestEvent =
  | { type: "run_started"; runId: string; sources: SourceInfo[]; simulated?: boolean; targets?: Partial<Record<CheckName, number>> }
  | { type: "progress"; stage: Stage; agent: string; rowsBySource: Record<string, number>; tokens: number; loss: number; rmsByDomain: Record<Domain, number>;
      checks: Record<CheckName, number>; throughput: number; latencyP95Ms: number; activeField?: string; progress?: number }
  | { type: "log"; ts: number; agent: string; message: string }
  | { type: "stage_completed"; stage: Stage; residualBp: number; loss: number }
  | { type: "run_completed"; elapsedS: number }
  | { type: "error"; stage: string; message: string };

export interface LogLine { ts: number; agent: string; message: string }
export type RevStatus = "queued" | "active" | "done" | "error";
export interface Revision { rev: Stage; change: string; by: string; residualBp: number | null; loss: number | null; status: RevStatus }

export interface BenchState {
  status: "waiting" | "running" | "done" | "error";
  runId: string | null; simulated: boolean; sources: SourceInfo[]; targets: Record<CheckName, number>;
  rowsBySource: Record<string, number>; stage: Stage; agent: string; tokens: number; loss: number | null;
  rms: Record<Domain, number> | null; checks: Record<CheckName, number> | null; throughput: number | null; latencyP95Ms: number | null; activeField: string | null;
  k: number; history: [number, number][]; logs: LogLine[]; revisions: Revision[]; elapsedS: number; error: { stage: string; message: string } | null; eventCount: number;
}
