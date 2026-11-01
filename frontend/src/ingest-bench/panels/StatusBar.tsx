import type { Mode } from "../useIngestStream";

export type ThemePref = "auto" | "light" | "dark";
export interface StatusProps {
  tone: "run" | "done" | "error" | "idle"; text: string; mode: Mode; simulated: boolean; paused: boolean; done: boolean; speed: number; canControl: boolean; theme: ThemePref;
  onPause: () => void; onResume: () => void; onRestart: () => void; onSpeed: (s: number) => void; onTheme: (t: ThemePref) => void;
}
export function StatusBar(p: StatusProps) {
  const badge = p.mode === "demo" || p.simulated ? "SIMULATED" : p.mode === "live" ? "LIVE" : p.mode === "reconnecting" ? "RECONNECTING" : "CONNECTING";
  return (
    <div className="ib-bar">
      <div className="ib-live" role="status" aria-live="polite">
        <span className={"ib-dot " + p.tone + (p.tone === "run" && !p.paused ? " on" : "")} data-testid="ib-dot" />
        <span className={"ib-badge " + badge.toLowerCase()} data-testid="ib-badge">{badge}</span>
        <span className={"ib-live-t" + (p.tone === "error" ? " err" : "")} data-testid="ib-status">{p.text}</span>
      </div>
      <div className="ib-ctl">
        <button type="button" data-testid="ib-pause" onClick={p.done ? p.onRestart : p.paused ? p.onResume : p.onPause}>{p.done ? "Run again" : p.paused ? "Resume" : "Pause"}</button>
        <button type="button" data-testid="ib-restart" onClick={p.onRestart} disabled={!p.canControl} title={p.canControl ? "" : "A live run cannot be restarted from here"}>Restart</button>
        <div className="ib-seg" role="group" aria-label="Playback speed">
          {[1, 2, 4].map((s) => <button key={s} type="button" data-testid={`ib-speed-${s}`} aria-pressed={p.speed === s} disabled={!p.canControl} onClick={() => p.onSpeed(s)}>{s}×</button>)}
        </div>
        <div className="ib-seg" role="group" aria-label="Theme">
          {(["auto", "light", "dark"] as ThemePref[]).map((t) => <button key={t} type="button" data-testid={`ib-theme-${t}`} aria-pressed={p.theme === t} onClick={() => p.onTheme(t)}>{t}</button>)}
        </div>
      </div>
    </div>
  );
}
