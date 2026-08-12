import { useState } from "react";
import { api } from "../api/client";

// Module-level cache (not per-component state) so every page that opens
// the same metric's definition is guaranteed to read the exact same
// fetched object - the whole point of a central registry is that it can't
// drift between pages, and a per-instance cache wouldn't guarantee that
// two components requesting the same id ever converge on identical data
// (e.g. one still loading while another already has a stale copy).
const cache = new Map<string, any>();
const pending = new Map<string, Promise<any>>();

async function fetchDefinition(id: string): Promise<any> {
  if (cache.has(id)) return cache.get(id);
  if (!pending.has(id)) {
    pending.set(id, api.metricDefinition(id).then((d: any) => { cache.set(id, d); return d; }).catch(() => null));
  }
  return pending.get(id);
}

// Subtle by design: a small "Definition" / "How calculated?" link, never a
// paragraph of methodology sitting on the default page. Opens inline only
// on request.
export function MetricDefinitionLink({ id, label = "Definition" }: { id: string; label?: string }) {
  const [def, setDef] = useState<any>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  async function toggle() {
    if (open) { setOpen(false); return; }
    if (!def) {
      setLoading(true);
      const d = await fetchDefinition(id);
      setDef(d);
      setLoading(false);
    }
    setOpen(true);
  }

  return (
    <span style={{ display: "inline-block" }}>
      <button
        onClick={toggle}
        style={{ background: "none", border: "none", padding: 0, cursor: "pointer", font: "inherit", fontSize: 11, color: "var(--text-faint)", textDecoration: "underline" }}
      >
        {loading ? "…" : label}
      </button>
      {open && def && (
        <div style={{
          marginTop: 6, marginBottom: 6, padding: "10px 12px", fontSize: 12,
          border: "1px solid var(--border)", borderRadius: "var(--radius)", background: "var(--surface-alt)",
          maxWidth: 440,
        }}>
          <div style={{ fontWeight: 700, marginBottom: 3 }}>{def.label}</div>
          {def.formula && <div className="mono" style={{ marginBottom: 4, color: "var(--primary)" }}>{def.formula}</div>}
          <div style={{ marginBottom: def.what_it_is_not?.length ? 6 : 0 }}>{def.meaning}</div>
          {def.what_it_is_not?.length > 0 && (
            <div style={{ color: "var(--text-muted)" }}>
              <strong>Not:</strong> {def.what_it_is_not.join(", ")}
            </div>
          )}
          {def.limitations?.length > 0 && (
            <div style={{ color: "var(--text-faint)", marginTop: 4, fontSize: 11 }}>
              {def.limitations.join(" ")}
            </div>
          )}
        </div>
      )}
      {open && !def && !loading && <div style={{ fontSize: 11, color: "var(--text-faint)" }}>No definition on file.</div>}
    </span>
  );
}
