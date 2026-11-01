// Loads a TypeScript source file for node:test without a test framework or a
// build step: transpile with the TypeScript compiler (already a devDependency)
// and import the result. Only for dependency-free pure modules.
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";
import ts from "typescript";

const root = fileURLToPath(new URL("../", import.meta.url));

export async function loadTs(relativePath) {
  const source = readFileSync(join(root, relativePath), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  });
  const file = join(mkdtempSync(join(tmpdir(), "ccrig-ts-")), "module.mjs");
  writeFileSync(file, outputText);
  return import(pathToFileURL(file).href);
}
