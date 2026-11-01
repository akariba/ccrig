// Connects the bench to its events and reduces them into one state object.
//   live  : GET /api/ingest/runs/{runId}/events (Server-Sent Events, read with fetch so the operator token can be sent); reconnects with backoff and resumes after the last id.
//   demo  : the local simulator, on its own clock (?demo=1, on the public static site, or when no live run answers). Always labelled SIMULATED.
// pause/resume freezes the display: live events keep arriving and are applied on resume; the simulator's clock stops.
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { initialState, reduce } from "./reducer";
import { Simulator } from "./simulator";
import type { BenchState, IngestEvent } from "./types";

const BASE = import.meta.env.VITE_API_HOST ? `https://${import.meta.env.VITE_API_HOST}` : "";
const STATIC_SITE = import.meta.env.VITE_STATIC_BACKEND === "true";
export type Mode = "connecting" | "live" | "reconnecting" | "demo";
const token = () => { try { return sessionStorage.getItem("ccrig.studio.token") ?? ""; } catch { return ""; } };

export interface BenchStream {
  state: BenchState; mode: Mode; note: string | null; paused: boolean; speed: number; canControl: boolean; getElapsed: () => number;
  pause: () => void; resume: () => void; restart: () => void; seekStage: (i: number) => void; setSpeed: (s: number) => void;
}

export function useIngestStream(runId: string | null, demo: boolean): BenchStream {
  const [state, dispatch] = useReducer(reduce, undefined, initialState);
  const [mode, setMode] = useState<Mode>(demo || STATIC_SITE ? "demo" : "connecting");
  const [note, setNote] = useState<string | null>(STATIC_SITE && !demo ? "Public static site: there is no server, so this is the simulator." : null);
  const [paused, setPaused] = useState(false);
  const [speed, setSpeedState] = useState(1);
  const startedAt = useRef<number | null>(null);
  const pausedRef = useRef(false), queue = useRef<IngestEvent[]>([]), sim = useRef<Simulator | null>(null), speedRef = useRef(1);

  const push = useCallback((ev: IngestEvent) => { if (ev.type === "run_started") startedAt.current = performance.now(); if (pausedRef.current) queue.current.push(ev); else dispatch(ev); }, []);

  const startDemo = useCallback((why: string | null) => {
    setMode("demo"); if (why) setNote(why);
    const s = new Simulator((e) => dispatch(e), "sim-14"); s.speed = speedRef.current; sim.current = s; s.start();
  }, []);

  useEffect(() => {
    let stop = false, timer: ReturnType<typeof setInterval> | undefined, retry: ReturnType<typeof setTimeout> | undefined;
    const ctl = new AbortController();
    if (demo || STATIC_SITE) {
      startDemo(null);
      let last = performance.now();
      timer = setInterval(() => { const now = performance.now(), dt = Math.min(0.25, (now - last) / 1000); last = now; if (!pausedRef.current) sim.current?.tick(dt); }, 30);
    } else {
      let lastId = 0, got = false, attempt = 0, finished = false;
      const connect = async () => {
        try {
          const res = await fetch(`${BASE}/api/ingest/runs/${encodeURIComponent(runId ?? "latest")}/events?since=${lastId}`, { headers: { "X-Studio-Token": token() }, signal: ctl.signal });
          if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
          if (!(res.headers.get("content-type") ?? "").startsWith("text/event-stream")) throw new Error("not an event stream");
          setMode("live"); setNote(null); attempt = 0;
          const reader = res.body.getReader(), dec = new TextDecoder();
          let buf = "";
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buf += dec.decode(value, { stream: true });
            let cut: number;
            while ((cut = buf.indexOf("\n\n")) >= 0) {
              const block = buf.slice(0, cut); buf = buf.slice(cut + 2);
              const id = /^id: (\d+)$/m.exec(block)?.[1], data = /^data: (.*)$/m.exec(block)?.[1], kind = /^event: (.*)$/m.exec(block)?.[1];
              if (id) lastId = Number(id);
              if (kind === "ingest" && data) { got = true; const ev = JSON.parse(data) as IngestEvent; push(ev); if (ev.type === "run_completed" || ev.type === "error") finished = true; }
            }
          }
          if (finished || stop) return;
          throw new Error("the stream ended");
        } catch (e) {
          if (stop || ctl.signal.aborted) return;
          if (!got) { startDemo(`No live run answered (${e instanceof Error ? e.message : "unreachable"}): showing the simulator.`); timerStart(); return; }
          setMode("reconnecting"); attempt++;
          retry = setTimeout(connect, Math.min(8000, 500 * 2 ** attempt));
        }
      };
      const timerStart = () => { let last = performance.now(); timer = setInterval(() => { const now = performance.now(), dt = Math.min(0.25, (now - last) / 1000); last = now; if (!pausedRef.current) sim.current?.tick(dt); }, 30); };
      void connect();
    }
    return () => { stop = true; ctl.abort(); if (timer) clearInterval(timer); if (retry) clearTimeout(retry); };
  }, [runId, demo, push, startDemo]);

  const pause = useCallback(() => { pausedRef.current = true; setPaused(true); }, []);
  const resume = useCallback(() => { pausedRef.current = false; setPaused(false); const q = queue.current; queue.current = []; q.forEach((e) => dispatch(e)); }, []);
  const setSpeed = useCallback((s: number) => { speedRef.current = s; setSpeedState(s); if (sim.current) sim.current.speed = s; }, []);
  const restart = useCallback(() => { sim.current?.start(); pausedRef.current = false; setPaused(false); }, []);
  const seekStage = useCallback((i: number) => { sim.current?.seek(i); }, []);
  const getElapsed = useCallback(() => (state.status === "done" ? state.elapsedS : sim.current ? sim.current.t : startedAt.current != null ? (performance.now() - startedAt.current) / 1000 : 0), [state.status, state.elapsedS]);
  return { getElapsed, state, mode, note, paused, speed, canControl: mode === "demo", pause, resume, restart, seekStage, setSpeed };
}
