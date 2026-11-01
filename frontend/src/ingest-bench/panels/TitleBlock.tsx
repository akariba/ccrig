import { fmt } from "../format";

export interface Kpis { records: number; total: number; tokens: number; loss: number | null; step: number; stageLetter: string; stageCaption: string; runLabel: string; nSources: number }
export function TitleBlock({ k }: { k: Kpis }) {
  const pct = k.total ? Math.round((k.records / k.total) * 100) : 0;
  return (
    <header className="ib-tb">
      <div className="ib-tb-name">
        <h1>Haiku <i>+</i> Sonnet <i>+</i> Opus</h1>
        <p className="ib-sub">Portfolio data load · run {k.runLabel} · {k.nSources} sources → risk dashboard</p>
      </div>
      <div className="ib-kpis">
        <div className="ib-kpi"><div className="ib-lab">Records</div><b data-testid="ib-k-records">{fmt(k.records)}</b><small>of {k.total ? fmt(k.total) : "—"} · {pct}%</small></div>
        <div className="ib-kpi"><div className="ib-lab">Tokens</div><b data-testid="ib-k-tokens">{fmt(k.tokens)}</b><small>this sheet</small></div>
        <div className="ib-kpi"><div className="ib-lab">Eval loss</div><b data-testid="ib-k-loss">{k.loss == null ? "—" : k.loss.toFixed(4)}</b><small>network · step {k.step}</small></div>
        <div className="ib-kpi"><div className="ib-lab">Stage</div><b data-testid="ib-k-stage">{k.stageLetter}</b><small>{k.stageCaption}</small></div>
      </div>
    </header>
  );
}
