import { useEffect, useRef } from "react";
import { CHANNELS, CHANNEL_ORDER, type Channel } from "../channels";
import { useThemeVersion } from "../chartTokens";
import { readPalette } from "./palette";
import { drawCounterparty, drawFactor, drawIssuer } from "./drawNodes";
import type { GNode } from "./types";

const SAMPLE: GNode = { id: "guide", kind: "counterparty", label: "Example", tag: "Example", cp: { utilisation: 92, rating: "A-", outlook: null, priority: "HIGH", ews: null, holdingsOnly: false, flags: { wwr: true, overdue: true, nearLimit: true, negativeOutlook: false } } };
const ISSUER: GNode = { id: "i", kind: "issuer", label: "Issuer", tag: "XYZ", group: "Technology" };
const FACTOR: GNode = { id: "f", kind: "factor", label: "Factor", tag: "FX" };

/** The anatomy of a node, drawn with the same functions the graph uses. The example is an illustration with made-up values, labelled as such. */
export function NodeGuide({ onClose, inline = false }: { onClose?: () => void; inline?: boolean }) {
  const cv = useRef<HTMLCanvasElement>(null), theme = useThemeVersion();
  useEffect(() => {
    const c = cv.current?.getContext("2d"); if (!c || !cv.current) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1), p = readPalette(), W = 250, H = 92;
    cv.current.width = W * dpr; cv.current.height = H * dpr; cv.current.style.width = `${W}px`; cv.current.style.height = `${H}px`;
    c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, W, H);
    const mix = [{ channel: "exposure" as Channel, share: 0.5 }, { channel: "supply" as Channel, share: 0.3 }, { channel: "shared" as Channel, share: 0.2 }];
    drawCounterparty(c, SAMPLE, { x: 52, y: 46 }, { selected: false, hover: false, dim: false, time: 0, reduced: true, mix }, p, 22);
    drawIssuer(c, ISSUER, { x: 140, y: 46 }, { selected: false, hover: false, dim: false, time: 0, reduced: true, mix: [] }, p);
    drawFactor(c, FACTOR, { x: 205, y: 46 }, { selected: false, hover: false, dim: false, time: 0, reduced: true, mix: [] }, p);
  }, [theme]);
  return (
    <aside className={`nc-guide${inline ? " inline" : ""}`} aria-label="Node guide" data-testid="node-guide">
      <div className="u-sec">Node guide{onClose && <button type="button" className="u-link" onClick={onClose}>Hide</button>}</div>
      <canvas ref={cv} role="img" aria-label="An example counterparty, issuer and risk-factor glyph" />
      <ul>
        <li><b>Outer arc</b> limit utilisation: green, amber from 85%, red at 100%; a red tick when over the limit</li>
        <li><b>Inner ring</b> link mix by channel (share of link weight)</li>
        <li><b>Core</b> rating (a dash when none is recorded), edged in the priority colour</li>
        <li><b>Badges</b> W wrong-way risk · ! overdue breach · ▲ near limit · ↓ negative outlook</li>
        <li><b>Amber pulse</b> early-warning score above its threshold</li>
        <li><b>Hexagon</b> issuer, coloured by sector · <b>Diamond</b> risk factor</li>
      </ul>
      <p className="u-muted">Illustration with made-up values.</p>
    </aside>
  );
}

export function ChannelLegend({ visible, onToggle, counts }: { visible: ReadonlySet<Channel>; onToggle: (c: Channel) => void; counts?: Partial<Record<Channel, number>> }) {
  return (
    <div className="nc-legend" role="group" aria-label="Relationship channels">
      {CHANNEL_ORDER.map((c) => (
        <button key={c} type="button" className="nc-chan" aria-pressed={visible.has(c)} onClick={() => onToggle(c)} title={CHANNELS[c].desc} disabled={counts ? !counts[c] : false} style={{ ["--c" as string]: `var(${CHANNELS[c].cssVar})` }}>
          <svg width="22" height="8" aria-hidden="true"><line x1="1" y1="4" x2="21" y2="4" stroke="var(--c)" strokeWidth="2.4" strokeDasharray={CHANNELS[c].dash || undefined} strokeLinecap="round" /></svg>{CHANNELS[c].label}{counts && <span className="nc-n">{counts[c] ?? 0}</span>}
        </button>
      ))}
    </div>
  );
}
