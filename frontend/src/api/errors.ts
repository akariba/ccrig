/**
 * Human-readable text for a failed API call. Works for both transports: the
 * HTTP server (`422 Unprocessable Entity: {...}`) and the in-browser
 * dispatcher (`422: {...}`); FastAPI validation errors are flattened to
 * "field: message".
 */
export function apiErrorMessage(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err);
  const start = raw.indexOf("{");
  if (start >= 0) {
    try {
      const detail = JSON.parse(raw.slice(start)).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail) && detail.length) {
        return detail
          .map((e: { loc?: unknown[]; msg?: string }) => {
            const field = (e.loc ?? []).filter((p) => p !== "body" && p !== "query" && p !== "path").join(".");
            return field ? `${field}: ${e.msg}` : String(e.msg);
          })
          .join("; ");
      }
    } catch {
      /* not JSON - fall through to the raw message */
    }
  }
  return raw;
}
