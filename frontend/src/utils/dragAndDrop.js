/**
 * Drag-and-drop helpers for collecting files from a drop event, including
 * files inside dropped folders (via the HTML5 FileSystem API —
 * `DataTransferItem.webkitGetAsEntry`, `DirectoryEntry.createReader`).
 *
 * Used by both the top-level chat composer and the TR-ARPES widget so the
 * behaviour stays consistent.
 */

/** Recursively walk a DataTransferItem entry, collecting `File` objects into `out`. */
export async function traverseEntry(entry, out) {
  if (!entry) return;
  if (entry.isFile) {
    await new Promise((resolve) => {
      entry.file(
        (f) => {
          out.push(f);
          resolve();
        },
        () => resolve(),
      );
    });
  } else if (entry.isDirectory) {
    const reader = entry.createReader();
    // `readEntries` returns at most ~100 entries per call — loop until empty.
    let chunk;
    do {
      chunk = await new Promise((resolve) =>
        reader.readEntries(resolve, () => resolve([])),
      );
      for (const child of chunk) {
        await traverseEntry(child, out);
      }
    } while (chunk.length > 0);
  }
}

/**
 * Gather all files from a `drop` event, expanding folders if the browser
 * supports the FileSystem API. Falls back to `dataTransfer.files` on
 * older browsers (which don't include folder contents).
 */
export async function gatherDroppedFiles(event) {
  const items = event?.dataTransfer?.items;
  if (items && items.length && items[0].webkitGetAsEntry) {
    const out = [];
    const entries = Array.from(items)
      .map((it) => it.webkitGetAsEntry && it.webkitGetAsEntry())
      .filter(Boolean);
    for (const entry of entries) {
      await traverseEntry(entry, out);
    }
    return out;
  }
  return Array.from(event?.dataTransfer?.files || []);
}
