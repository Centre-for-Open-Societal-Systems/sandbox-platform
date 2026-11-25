/** A safe file name from a product name: "Farmer Registry" -> "farmer-registry". */
export function fileSlug(name: string): string {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    // Runs of "-" were already collapsed to one, so at most one is left at each end.
    .replace(/^-|-$/g, "");
  return slug || "api";
}

/** Save `data` as a pretty-printed JSON file through the browser's download. */
export function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
