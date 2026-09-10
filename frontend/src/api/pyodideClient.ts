// Runs the actual Python FastAPI backend (routers + core logic, unmodified)
// entirely in-browser via Pyodide (CPython compiled to WASM), so the static
// GitHub Pages build needs no separately hosted server. See
// backend/app/browser_dispatch.py for the in-process call dispatcher this
// drives, and scripts/vendor-backend.mjs for how backend/app + backend/data
// end up served as static files at `${BASE_URL}backend/`.
import type { PyodideInterface } from "pyodide";

type StatusBody = [number, unknown];

let pyodidePromise: Promise<PyodideInterface> | null = null;
let onBootProgress: ((message: string) => void) | null = null;

export function setBootProgressListener(fn: ((message: string) => void) | null) {
  onBootProgress = fn;
}

async function fetchText(url: string): Promise<string> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch ${url}: ${res.status}`);
  return res.text();
}

async function withRetries<T>(label: string, attempts: number, fn: () => Promise<T>): Promise<T> {
  let lastErr: unknown;
  for (let i = 0; i < attempts; i++) {
    try {
      return await fn();
    } catch (err) {
      lastErr = err;
      console.warn(`[pyodide] ${label} failed (attempt ${i + 1}/${attempts})`, err);
      if (i < attempts - 1) await new Promise((r) => setTimeout(r, 1000 * (i + 1)));
    }
  }
  throw lastErr;
}

async function boot(): Promise<PyodideInterface> {
  const { loadPyodide } = await import("pyodide");

  onBootProgress?.("Starting Python runtime...");
  // Vite bundles pyodide.mjs itself but can't bundle its binary runtime
  // assets (wasm/zip); pin indexURL to the matching version on jsdelivr,
  // which is Pyodide's own documented CDN distribution for exactly this.
  // The whole boot sequence is retried on transient network failures - a
  // single flaky DNS lookup or CDN hiccup shouldn't strand the visitor on
  // the loading screen forever.
  const pyodide = await withRetries("loadPyodide", 3, () =>
    loadPyodide({ indexURL: "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/" })
  );

  onBootProgress?.("Loading numpy, pandas, scipy, scikit-learn...");
  await withRetries("loadPackage", 3, () =>
    pyodide.loadPackage(["numpy", "pandas", "scipy", "scikit-learn", "micropip"])
  );

  onBootProgress?.("Installing networkx, fastapi, pydantic...");
  const micropip = pyodide.pyimport("micropip");
  await withRetries("micropip.install", 3, () => micropip.install(["networkx", "fastapi", "pydantic"]));

  onBootProgress?.("Loading application code and data...");
  const base = import.meta.env.BASE_URL;
  const manifest: string[] = JSON.parse(await fetchText(`${base}backend/manifest.json`));

  const dirsMade = new Set<string>();
  const ensureDir = (path: string) => {
    if (dirsMade.has(path)) return;
    pyodide.FS.mkdirTree(path);
    dirsMade.add(path);
  };
  ensureDir("/backend");
  for (const relPath of manifest) {
    ensureDir(`/backend/${relPath}`.split("/").slice(0, -1).join("/"));
  }

  // Fetch all files concurrently - sequential round-trips for ~70 small
  // files added noticeable, needless latency to every cold boot.
  await withRetries("fetch application files", 3, () =>
    Promise.all(
      manifest.map(async (relPath) => {
        const fullPath = `/backend/${relPath}`;
        const isText = /\.(py|json|csv|txt)$/.test(relPath);
        if (isText) {
          pyodide.FS.writeFile(fullPath, await fetchText(`${base}backend/${relPath}`));
        } else {
          const buf = new Uint8Array(await (await fetch(`${base}backend/${relPath}`)).arrayBuffer());
          pyodide.FS.writeFile(fullPath, buf);
        }
      })
    )
  );

  onBootProgress?.("Starting application...");
  pyodide.runPython(`
import sys
sys.path.insert(0, "/backend")
from app.browser_dispatch import dispatch as _dispatch
`);

  onBootProgress?.(null as unknown as string);
  return pyodide;
}

// Lets the boot overlay proactively kick off (and retry) the boot sequence
// so it can show a terminal error + retry affordance, rather than only
// finding out something failed the first time a page calls the API.
export function bootPyodide(): Promise<PyodideInterface> {
  return getPyodide();
}

function getPyodide(): Promise<PyodideInterface> {
  if (!pyodidePromise) {
    pyodidePromise = boot().catch((err) => {
      pyodidePromise = null; // allow the next call to retry from scratch
      throw err;
    });
  }
  return pyodidePromise;
}

export async function callApi(method: string, path: string, query: Record<string, unknown> = {}, body: unknown = null): Promise<unknown> {
  const pyodide = await getPyodide();
  const dispatchFn = pyodide.globals.get("_dispatch");
  try {
    const result = dispatchFn(method, path, pyodide.toPy(query), body === null ? pyodide.toPy(null) : pyodide.toPy(body));
    try {
      const [status, data] = result.toJs({ dict_converter: Object.fromEntries }) as StatusBody;
      if (status >= 400) {
        throw new Error(`${status}: ${JSON.stringify(data)}`);
      }
      return data;
    } finally {
      result.destroy();
    }
  } finally {
    dispatchFn.destroy();
  }
}
