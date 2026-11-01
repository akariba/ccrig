// Theme mode: "system" follows the OS, "light" and "dark" are explicit. The choice is a per-viewer convenience kept in
// localStorage (every access guarded: it can be blocked, full, or absent), and applied as <html data-theme>.
export type ThemeMode = "system" | "light" | "dark";
const KEY = "ccrig.theme";
export const THEME_EVENT = "ccrig-theme-change";

export function readThemeMode(): ThemeMode {
  try { const v = localStorage.getItem(KEY); if (v === "light" || v === "dark") return v; } catch { /* storage unavailable: follow the system */ }
  return "system";
}

export function applyTheme(mode: ThemeMode): void {
  const root = document.documentElement;
  if (mode === "system") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", mode);
  window.dispatchEvent(new Event(THEME_EVENT));
}

export function setThemeMode(mode: ThemeMode): void {
  try { if (mode === "system") localStorage.removeItem(KEY); else localStorage.setItem(KEY, mode); } catch { /* the choice then lasts for this page only */ }
  applyTheme(mode);
}

/** Whether the page is currently dark, after the mode and the OS preference are both taken into account. */
export function isDark(): boolean {
  const explicit = document.documentElement.getAttribute("data-theme");
  if (explicit) return explicit === "dark";
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

/** Current value of a CSS custom property (charts and canvases cannot use var(--x) directly). */
export function cssVar(name: string, fallback = ""): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

/** Calls `fn` when the mode changes or the OS preference flips while the mode is "system". Returns an unsubscribe. */
export function onThemeChange(fn: () => void): () => void {
  const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
  window.addEventListener(THEME_EVENT, fn); mq?.addEventListener("change", fn);
  return () => { window.removeEventListener(THEME_EVENT, fn); mq?.removeEventListener("change", fn); };
}
