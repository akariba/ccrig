import { useCallback, useEffect, useState } from "react";

// Only relevant to the GitHub Pages build, where every API call is actually
// running inside a Python interpreter compiled to WASM (see
// ../api/pyodideClient.ts). First boot fetches ~60-100MB of runtime and
// scientific packages, so this gives the visitor something better than a
// silently empty page for the first request - including a way to retry if
// that download hits a transient network error.
const STATIC_BACKEND = import.meta.env.VITE_STATIC_BACKEND === "true";

export function PyodideBootOverlay() {
  const [message, setMessage] = useState<string | null>(
    STATIC_BACKEND ? "Preparing offline demo..." : null
  );
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const start = useCallback(() => {
    if (!STATIC_BACKEND) return;
    setError(null);
    let cancelled = false;
    import("../api/pyodideClient").then(({ setBootProgressListener, bootPyodide }) => {
      if (cancelled) return;
      setBootProgressListener((msg) => setMessage(msg));
      bootPyodide().catch((err) => {
        if (cancelled) return;
        console.error("[pyodide] boot failed permanently", err);
        setError(err instanceof Error ? err.message : String(err));
      });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => start(), [start, attempt]);

  if (!message && !error) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 12,
        background: "rgba(10, 12, 16, 0.92)",
        color: "#e6e8eb",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      {error ? (
        <>
          <div style={{ fontSize: 14, color: "#f28b82" }}>Failed to start the offline demo</div>
          <div style={{ fontSize: 12, opacity: 0.7, maxWidth: 420, textAlign: "center" }}>{error}</div>
          <button
            onClick={() => setAttempt((n) => n + 1)}
            style={{
              marginTop: 8,
              padding: "6px 16px",
              borderRadius: 6,
              border: "1px solid rgba(255,255,255,0.3)",
              background: "transparent",
              color: "#e6e8eb",
              cursor: "pointer",
            }}
          >
            Retry
          </button>
        </>
      ) : (
        <>
          <div
            style={{
              width: 32,
              height: 32,
              border: "3px solid rgba(255,255,255,0.25)",
              borderTopColor: "#e6e8eb",
              borderRadius: "50%",
              animation: "ccrig-spin 0.8s linear infinite",
            }}
          />
          <style>{`@keyframes ccrig-spin { to { transform: rotate(360deg); } }`}</style>
          <div style={{ fontSize: 14 }}>{message}</div>
          <div style={{ fontSize: 12, opacity: 0.6, maxWidth: 360, textAlign: "center" }}>
            This build runs the full backend inside your browser (no server) - a one-time
            download of the Python runtime and data.
          </div>
        </>
      )}
    </div>
  );
}
