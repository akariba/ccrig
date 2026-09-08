// Copies the Python backend (app/ source + data/) into public/backend/ so the
// static (GitHub Pages) build can fetch it and run it in-browser via Pyodide
// (see src/api/pyodideClient.ts). Also writes a manifest of every file copied
// since the browser can't list a directory over plain HTTP.
import { cpSync, mkdirSync, rmSync, writeFileSync, existsSync, readdirSync } from "node:fs";
import { join, dirname, relative } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const backendSrc = join(here, "..", "..", "backend");
const outDir = join(here, "..", "public", "backend");

if (existsSync(outDir)) rmSync(outDir, { recursive: true });
mkdirSync(outDir, { recursive: true });

function shouldSkip(path) {
  return path.includes("__pycache__") || path.endsWith(".pyc");
}

for (const sub of ["app", "data"]) {
  cpSync(join(backendSrc, sub), join(outDir, sub), {
    recursive: true,
    filter: (src) => !shouldSkip(src),
  });
}

const manifest = [];
function walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(full);
    } else {
      manifest.push(relative(outDir, full).split("\\").join("/"));
    }
  }
}
walk(outDir);

writeFileSync(join(outDir, "manifest.json"), JSON.stringify(manifest.sort()));
console.log(`Vendored ${manifest.length} backend files into ${outDir}`);
