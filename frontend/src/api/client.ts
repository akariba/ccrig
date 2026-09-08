// Proxied via vite.config.ts in dev; same-origin if combined into one deploy,
// or set VITE_API_HOST at build time when frontend and backend are separate services.
const BASE = import.meta.env.VITE_API_HOST ? `https://${import.meta.env.VITE_API_HOST}` : "";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
}

export const api = {
  health: () => req<any>("/api/health"),

  listEntities: (params: Record<string, string | number> = {}) => {
    const qs = new URLSearchParams(params as any).toString();
    return req<any>(`/api/entities${qs ? "?" + qs : ""}`);
  },
  entity360: (id: string) => req<any>(`/api/entities/${id}`),
  explainRelationship: (a: string, b: string) => req<any>(`/api/entities/${a}/explain/${b}`),

  listCounterparties: () => req<any>("/api/counterparties"),
  counterparty360: (id: string) => req<any>(`/api/counterparties/${id}`),

  listThemes: (q?: string) => req<any>(`/api/themes${q ? "?q=" + encodeURIComponent(q) : ""}`),
  themeDetail: (id: string) => req<any>(`/api/themes/${id}`),

  search: (q: string, opts: Record<string, string | number> = {}) => {
    const qs = new URLSearchParams({ q, ...opts } as any).toString();
    return req<any>(`/api/search?${qs}`);
  },

  parseEvent: (body: any) =>
    req<any>("/api/event/parse", { method: "POST", body: JSON.stringify(body) }),
  sampleScenarios: () => req<any>("/api/event/sample-scenarios"),

  egoGraph: (id: string, params: Record<string, string | number> = {}) => {
    const qs = new URLSearchParams(params as any).toString();
    return req<any>(`/api/graph/ego/${id}${qs ? "?" + qs : ""}`);
  },

  modelLabPresets: () => req<any>("/api/model-lab/presets"),
  modelLabScore: (body: any) =>
    req<any>("/api/model-lab/score", { method: "POST", body: JSON.stringify(body) }),
  modelLabPair: (body: any) =>
    req<any>("/api/model-lab/pair", { method: "POST", body: JSON.stringify(body) }),
  calibrationAnchors: () => req<any>("/api/model-lab/calibration/anchors"),
  calibrationRun: (body: any = {}) =>
    req<any>("/api/model-lab/calibration/run", { method: "POST", body: JSON.stringify(body) }),
  calibrationMarketAgreement: (body: any = {}) =>
    req<any>("/api/model-lab/calibration/market-agreement", { method: "POST", body: JSON.stringify(body) }),

  backtestScenarios: () => req<any>("/api/backtest/scenarios"),
  backtestRun: (scenarioId: string) => req<any>(`/api/backtest/run?scenario_id=${scenarioId}`),

  provenance: () => req<any>("/api/provenance"),
  provenanceCoverage: () => req<any>("/api/provenance/coverage"),

  scalability: () => req<any>("/api/scalability/simulate"),

  priorityQueue: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return req<any>(`/api/priority-queue${qs ? "?" + qs : ""}`);
  },
  priorityDetail: (id: string) => req<any>(`/api/priority-queue/${id}`),
  riskClusters: (id: string) => req<any>(`/api/priority-queue/${id}/risk-clusters`),
  metricDefinition: (id: string) => req<any>(`/api/metric-definitions/${id}`),
  breaches: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return req<any>(`/api/breaches${qs ? "?" + qs : ""}`);
  },
};
