// The single source for a page's filters and selections: they live in the URL (validated with zod), never in component state.
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { z } from "zod";
import { applyState, parseState, type Spec, type State } from "./urlStateCore";

function schemaFor(spec: Spec) {
  const shape: Record<string, z.ZodType> = {};
  for (const [key, def] of Object.entries(spec)) {
    shape[key] = typeof def === "number" ? z.number().finite() : typeof def === "boolean" ? z.boolean() : Array.isArray(def) ? z.array(z.string()) : z.string().max(2000);
  }
  return z.object(shape);
}

export function useUrlState<S extends Spec>(spec: S): [State<S>, (patch: Partial<State<S>>, opts?: { replace?: boolean }) => void] {
  const [params, setParams] = useSearchParams();
  const schema = useMemo(() => schemaFor(spec), [spec]);
  const state = useMemo(() => {
    const parsed = parseState(spec, params), checked = schema.safeParse(parsed);
    return (checked.success ? checked.data : parseState(spec, new URLSearchParams())) as State<S>;
  }, [spec, params, schema]);
  const set = useCallback((patch: Partial<State<S>>, opts?: { replace?: boolean }) => {
    setParams((prev) => applyState(spec, prev, patch), { replace: opts?.replace ?? true });
  }, [spec, setParams]);
  return [state, set];
}
