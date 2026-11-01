import { fmt } from "../format";

export interface Spec { sheet: number; sources: number; throughput: number | null; latencyMs: number | null; elapsedS: number }
export function SpecStrip({ s }: { s: Spec }) {
  return (
    <div className="ib-spec">
      <div className="task"><div className="ib-lab">Task</div><div className="v">Load portfolio data for the CCR dashboard</div></div>
      <div><div className="ib-lab">Drawn by</div><div className="v">3 models</div></div>
      <div><div className="ib-lab">Sheet</div><div className="v" data-testid="ib-sheet">{s.sheet} / 4</div></div>
      <div><div className="ib-lab">Sources</div><div className="v">{s.sources}</div></div>
      <div><div className="ib-lab">Throughput</div><div className="v">{s.throughput == null ? "—" : `${fmt(s.throughput)} rec/s`}</div></div>
      <div><div className="ib-lab">Latency p95</div><div className="v">{s.latencyMs == null ? "— ms" : `${Math.round(s.latencyMs)} ms`}</div></div>
      <div><div className="ib-lab">Elapsed</div><div className="v">{s.elapsedS.toFixed(1)} s</div></div>
      <div><div className="ib-lab">Network</div><div className="v">22·48·26·32·6</div></div>
      <div><div className="ib-lab">Scale</div><div className="v">10 : 1</div></div>
    </div>
  );
}
