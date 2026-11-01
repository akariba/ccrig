import type { LogLine } from "../types";
export function AgentLog({ lines }: { lines: LogLine[] }) {
  return (
    <div className="ib-logbox">
      <div className="ib-lab">Agent log</div>
      <ul className="ib-log" data-testid="ib-log">{lines.map((g, i) => <li key={`${g.ts}-${i}`}><em>{g.ts.toFixed(1).padStart(5, "0")}s</em> <b>{g.agent}</b> {g.message}</li>)}</ul>
    </div>
  );
}
