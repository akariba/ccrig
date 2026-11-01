import type { Revision } from "../types";

export interface RevRow extends Revision { shownResidual: number | null; shownLoss: number | null }
export function RevisionTable({ rows, canJump, onJump }: { rows: RevRow[]; canJump: boolean; onJump: (i: number) => void }) {
  return (
    <div className="ib-scroll">
      <table>
        <thead><tr><th>Rev</th><th>Change</th><th>By</th><th className="num">Residual bp</th><th className="num">Loss</th><th className="num">Status</th></tr></thead>
        <tbody>
          {rows.map((r, i) => {
            const go = () => canJump && onJump(i);
            return (
              <tr key={r.rev} tabIndex={0} className={r.status === "active" ? "on" : r.status === "error" ? "err" : ""} data-testid={`ib-rev-${r.rev}`} data-status={r.status} aria-disabled={!canJump}
                title={canJump ? "Jump the run to this stage" : "Jumping is available in simulator mode only"} onClick={go} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } }}>
                <td>{r.rev}</td><td>{r.change}</td><td>{r.by}</td>
                <td className="num">{r.shownResidual == null ? "—" : r.shownResidual.toFixed(0)}</td><td className="num">{r.shownLoss == null ? "—" : r.shownLoss.toFixed(4)}</td>
                <td className={"num st " + (r.status === "queued" ? "queued" : r.status === "done" ? "done" : r.status === "error" ? "error" : "active")}>{r.status === "done" ? "done" : r.status === "error" ? "error" : r.status}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
