// Boots the EXACT pinned in-browser runtime (Pyodide + pinned micropip
// packages) headlessly in Node, loads the vendored backend files the way the
// GitHub Pages build does, and checks that
//   1. every installed package is the pinned version (src/api/pyodide-pins.json),
//   2. the packages bundled by Pyodide are what the pins file says they are,
//   3. pandas is not part of the runtime,
//   4. the analytical baseline and all shared request cases pass through the
//      in-browser dispatcher (backend/validation/static_check.py).
//
//   npm run verify:static          (needs network: Pyodide CDN + PyPI)
//
// Exit code 0 = the static build's backend is functional and as pinned.
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontend = join(here, "..");
const backend = join(frontend, "..", "backend");
const vendored = join(frontend, "public", "backend");
const pins = JSON.parse(readFileSync(join(frontend, "src", "api", "pyodide-pins.json"), "utf8"));
const t0 = Date.now();
const log = (m) => console.log(`[${((Date.now() - t0) / 1000).toFixed(1)}s] ${m}`);
const norm = (n) => n.toLowerCase().replace(/_/g, "-");
const problems = [];

if (!existsSync(join(vendored, "manifest.json"))) {
  console.error("public/backend is missing - run `npm run verify:static` (it vendors first) or scripts/vendor-backend.mjs");
  process.exit(2);
}

// Pyodide derives file locations from its own path and mishandles parentheses
// (e.g. a checkout in "Project (1)"). Run from a copy of the same package then.
let pyodideDir = join(frontend, "node_modules", "pyodide");
const installed = JSON.parse(readFileSync(join(pyodideDir, "package.json"), "utf8")).version;
if (installed !== pins.pyodide) problems.push(`npm pyodide is ${installed}, pins say ${pins.pyodide}`);
if (/[()]/.test(pyodideDir)) {
  const copy = mkdtempSync(join(tmpdir(), "ccrig-pyodide-"));
  cpSync(pyodideDir, copy, { recursive: true });
  pyodideDir = copy;
  log("path contains parentheses: using a copy of the pyodide package in a temp dir");
}
const { loadPyodide } = await import(pathToFileURL(join(pyodideDir, "pyodide.mjs")).href);

// Without an explicit cache dir Pyodide writes downloaded wheels into a
// directory named after the CDN URL under the current working directory.
const packageCacheDir = join(tmpdir(), "ccrig-pyodide-package-cache");
mkdirSync(packageCacheDir, { recursive: true });

const py = await loadPyodide({
  packageBaseUrl: `https://cdn.jsdelivr.net/pyodide/v${pins.pyodide}/full/`,
  packageCacheDir,
  stdout: () => {},
  stderr: (s) => console.error("[python]", s),
});
log(`Pyodide ${py.version}`);
if (py.version !== pins.pyodide) problems.push(`runtime is ${py.version}, pins say ${pins.pyodide}`);

await py.loadPackage(pins.loadPackages);
const micropip = py.pyimport("micropip");
await micropip.install(pins.micropip);
log(`installed: ${pins.loadPackages.join(", ")} + ${pins.micropip.join(", ")}`);

// the files the browser fetches, exactly as listed in the manifest
const manifest = JSON.parse(readFileSync(join(vendored, "manifest.json"), "utf8"));
for (const rel of manifest) {
  const target = `/backend/${rel}`;
  py.FS.mkdirTree(dirname(target));
  py.FS.writeFile(target, readFileSync(join(vendored, rel)));
}
// verification-only extras (never shipped): the baselines and request cases
function copyTree(src, dst) {
  py.FS.mkdirTree(dst);
  for (const e of readdirSync(src, { withFileTypes: true })) {
    if (e.name === "__pycache__" || e.name.endsWith(".pyc") || e.name === ".DS_Store") continue;
    if (e.isDirectory()) copyTree(join(src, e.name), `${dst}/${e.name}`);
    else py.FS.writeFile(`${dst}/${e.name}`, readFileSync(join(src, e.name)));
  }
}
copyTree(join(backend, "validation"), "/backend/validation");
log(`loaded ${manifest.length} shipped backend files (+ validation extras)`);

const report = JSON.parse(await py.runPythonAsync(`
import sys, json
sys.path.insert(0, "/backend")
from validation import static_check
json.dumps(static_check.run())
`));

// 1. pinned packages are what is installed
for (const spec of pins.micropip) {
  const [name, version] = spec.split("==");
  const got = Object.entries(report.versions).find(([n]) => norm(n) === norm(name))?.[1];
  if (got !== version) problems.push(`${name}: pinned ${version}, runtime has ${got}`);
}
// 2. what Pyodide bundles has not drifted from the pins file
for (const [name, version] of Object.entries(pins.bundledByPyodide)) {
  const got = Object.entries(report.versions).find(([n]) => norm(n) === norm(name))?.[1];
  if (got !== version) problems.push(`bundled ${name}: pins say ${version}, runtime has ${got}`);
}
// 3. no pandas
if (report.pandas_importable) problems.push("pandas is importable in the runtime but nothing uses it");
// 4. behaviour
if (report.snapshot_diffs.length) problems.push(`analytics differ from the baseline: ${JSON.stringify(report.snapshot_diffs)}`);
if (report.request_case_failures.length) problems.push(`request cases failed: ${JSON.stringify(report.request_case_failures)}`);

console.log(JSON.stringify({ python: report.python, versions: report.versions, snapshot_entries: report.snapshot_entries,
  request_cases: report.request_cases }, null, 1));
if (problems.length) {
  console.error("\nSTATIC BACKEND VERIFICATION FAILED:\n - " + problems.join("\n - "));
  process.exit(1);
}
log("static backend verified: pinned runtime, no pandas, baseline and request cases pass");
