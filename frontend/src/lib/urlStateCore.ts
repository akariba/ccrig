// Dependency-free core of the URL state: every filter, selection, tab, as-of date and scenario lives in the query string,
// so a view can be shared and survives a reload. A field is described by its default; the type of the default decides how
// the string is read ("number" and "boolean" are coerced, a string array is comma-separated). A value equal to its default,
// or empty, is not written, so URLs stay short and a default can change without breaking old links.
export type Field = string | number | boolean | string[];
export type Spec = Record<string, Field>;
export type State<S extends Spec> = { [K in keyof S]: S[K] };

const sameArray = (a: string[], b: string[]) => a.length === b.length && a.every((v, i) => v === b[i]);

export function parseField(raw: string | null, def: Field): Field {
  if (raw === null || raw === "") return def;
  if (typeof def === "number") { const n = Number(raw); return Number.isFinite(n) ? n : def; }
  if (typeof def === "boolean") return raw === "1" || raw === "true" ? true : raw === "0" || raw === "false" ? false : def;
  if (Array.isArray(def)) return raw.split(",").map((s) => s.trim()).filter(Boolean);
  return raw;
}

export function parseState<S extends Spec>(spec: S, params: URLSearchParams): State<S> {
  const out: Record<string, Field> = {};
  for (const key of Object.keys(spec)) out[key] = parseField(params.get(key), spec[key]);
  return out as State<S>;
}

export function isDefault(value: Field, def: Field): boolean {
  if (Array.isArray(def)) return Array.isArray(value) && sameArray(value, def);
  return value === def;
}

/** The new query string after applying `patch`: keys outside the spec are kept, keys at their default (or null) are removed. */
export function applyState<S extends Spec>(spec: S, params: URLSearchParams, patch: Partial<State<S>>): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of Object.keys(patch)) {
    if (!(key in spec)) continue;
    const value = patch[key] as Field | null | undefined, def = spec[key];
    if (value === null || value === undefined || isDefault(value, def) || (Array.isArray(value) && value.length === 0)) next.delete(key);
    else next.set(key, Array.isArray(value) ? value.join(",") : String(value));
  }
  return next;
}
