// A compact timeline: one tick per recorded event, in recorded order, lit up to the current point. Hours-long human waits are not stretched across the track;
// a gap longer than a second is labelled with its real duration. Click a tick to move a replay there.
import { clock, fmtMs } from "./reduce";
import { NODE_OF_STAGE, NODE_DEFS } from "./graph";
import { STATE_COLOR } from "./states";
import type { FlowEvent } from "./types";

function gapLabel(ms: number): string { return ms < 60_000 ? `${(ms / 1000).toFixed(1)} s` : ms < 3_600_000 ? `${Math.round(ms / 60_000)} min` : `${(ms / 3_600_000).toFixed(1)} h`; }

export function TimelineStrip({ events, cursor, onSeek, ledger, elapsedMs }: { events: FlowEvent[]; cursor: number; onSeek: (n: number) => void; ledger?: { ok: boolean; events: number }; elapsedMs: number | null }) {
  const n = events.length, cur = events[cursor - 1];
  const firstOfNode = new Map<string, number>();
  events.forEach((e, i) => { if (e.stage_id) { const id = NODE_OF_STAGE[e.stage_id]; if (!firstOfNode.has(id)) firstOfNode.set(id, i); } });
  return (
    <div className="ds-tl-strip" data-testid="timeline-strip">
      <div className="ds-tl-track" role="group" aria-label="Recorded events">
        {n === 0 && <span className="ds-tl-empty">no events recorded yet</span>}
        {events.map((e, i) => {
          const prev = events[i - 1], gap = prev ? Date.parse(e.ts) - Date.parse(prev.ts) : 0, c = e.state ? STATE_COLOR[e.state] ?? "#8aa0b2" : "#8aa0b2";
          return (
            <span key={e.id} className="ds-tl-cell" style={{ left: `${((i + 0.5) / n) * 100}%` }}>
              {gap > 1000 && <em className="ds-tl-gap" title={`${gap} ms between these two recorded events`}>+{gapLabel(gap)}</em>}
              <button type="button" className={"ds-tick" + (i < cursor ? " lit" : "") + (i === cursor - 1 ? " now" : "")} style={{ ["--c" as string]: c }} data-testid="tick" data-event-id={e.id} data-type={e.type}
                aria-label={`${clock(e.ts)} ${e.stage_id ?? "job"} ${e.type.toLowerCase().replace(/_/g, " ")}`} title={`${clock(e.ts)} · ${e.stage_id ?? "JOB"} · ${e.type.toLowerCase().replace(/_/g, " ")}${e.elapsed_ms != null ? ` · ${fmtMs(e.elapsed_ms)}` : ""}`}
                onClick={() => onSeek(i + 1)} />
            </span>
          );
        })}
        {NODE_DEFS.map((d) => firstOfNode.has(d.id) && <span key={d.id} className="ds-tl-label" style={{ left: `${(((firstOfNode.get(d.id) ?? 0) + 0.5) / n) * 100}%` }}>{d.label.replace("Language model", "LLM")}</span>)}
      </div>
      <div className="ds-tl-foot">
        <span className="ds-tl-now" data-testid="timeline-now">{cur ? `${clock(cur.ts)} · ${cur.stage_id ?? "JOB"} · ${cur.type.toLowerCase().replace(/_/g, " ")}${cur.elapsed_ms != null ? ` · ${fmtMs(cur.elapsed_ms)}` : ""}` : "—"}</span>
        <span>{cursor}/{n} events · measured job time {elapsedMs != null ? fmtMs(elapsedMs) : "unavailable"}{ledger ? ` · ledger ${ledger.ok ? "verified" : "BROKEN"}` : ""} · timestamps as recorded</span>
      </div>
    </div>
  );
}
