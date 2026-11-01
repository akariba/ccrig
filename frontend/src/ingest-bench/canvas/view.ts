// What the drawings need, derived from the (interpolated) bench state. Draw functions are pure: (ctx, view, colors, timeMs) => void.
export interface GaugeRow { name: string; v: number; text: string }
export interface View {
  k: number; stage: number;                                  // stage: 0..3 running, 4 = run complete
  running: boolean; reduced: boolean; simulated: boolean;
  rms: [number, number, number]; loss: number | null; checks: GaugeRow[]; activeOut: number; fieldIndex: number | null; history: [number, number][];
  openSources: number; latencyP95Ms: number | null;
}
export const DOMS = ["Credit", "Market", "Signals"];
export const MONO = "'IBM Plex Mono',ui-monospace,Menlo,monospace", DISPLAY = "Archivo,'Helvetica Neue',Arial,sans-serif";
