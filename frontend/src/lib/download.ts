// Save text or a data URL as a file (CSV and PNG export). Browser-only.
export function downloadText(filename: string, text: string, mime = "text/plain"): void {
  const url = URL.createObjectURL(new Blob([text], { type: `${mime};charset=utf-8` }));
  downloadUrl(filename, url); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function downloadUrl(filename: string, url: string): void {
  const a = document.createElement("a"); a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
}
