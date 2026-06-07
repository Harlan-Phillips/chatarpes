import { useCallback, useEffect, useRef, useState } from "react";

/** Inline panel showing user-uploaded files with checkbox selection.
 *
 * Props:
 *   apiUrl
 *   open               — whether the panel is expanded
 *   onClose            — close handler
 *   selectedNames      — array of currently selected filenames (controlled)
 *   onSelectionChange  — (names: string[]) => void
 */
export default function UploadsPanel({
  apiUrl,
  open,
  onClose,
  selectedNames,
  onSelectionChange,
}) {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${apiUrl}/uploads`);
      if (!r.ok) throw new Error(`Server error: ${r.status}`);
      const j = await r.json();
      setFiles(j.files || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [apiUrl]);

  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  const uploadFiles = useCallback(
    async (fileList) => {
      const list = Array.from(fileList || []);
      if (!list.length) return;
      setUploading(true);
      setError(null);
      try {
        const fd = new FormData();
        for (const f of list) fd.append("files", f);
        const r = await fetch(`${apiUrl}/uploads`, { method: "POST", body: fd });
        if (!r.ok) throw new Error(await r.text());
        const j = await r.json();
        if (j.skipped?.length) {
          setError(
            `Skipped: ${j.skipped.map((s) => `${s.name} (${s.reason})`).join(", ")}`,
          );
        }
        // Auto-select newly uploaded files for the next message.
        const newNames = (j.uploaded || []).map((u) => u.name);
        if (newNames.length) {
          onSelectionChange(
            Array.from(new Set([...(selectedNames || []), ...newNames])),
          );
        }
        await refresh();
      } catch (e) {
        setError(e.message);
      } finally {
        setUploading(false);
      }
    },
    [apiUrl, refresh, selectedNames, onSelectionChange],
  );

  const deleteFile = useCallback(
    async (name) => {
      try {
        const r = await fetch(`${apiUrl}/uploads/${encodeURIComponent(name)}`, {
          method: "DELETE",
        });
        if (!r.ok && r.status !== 204) throw new Error(`Delete failed: ${r.status}`);
        onSelectionChange((selectedNames || []).filter((n) => n !== name));
        await refresh();
      } catch (e) {
        setError(e.message);
      }
    },
    [apiUrl, refresh, selectedNames, onSelectionChange],
  );

  const toggleSelected = (name) => {
    const set = new Set(selectedNames || []);
    if (set.has(name)) set.delete(name);
    else set.add(name);
    onSelectionChange(Array.from(set));
  };

  if (!open) return null;

  return (
    <div className="mb-2 border border-gray-200 rounded-xl bg-white overflow-hidden">
      <div className="px-3 py-2 border-b border-gray-100 flex items-center justify-between">
        <div className="text-xs font-medium text-gray-700">
          Files{" "}
          <span className="text-gray-400 font-normal">
            (check to include in next message)
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="text-xs px-2 py-1 rounded-md bg-blue-50 text-blue-700 hover:bg-blue-100 disabled:opacity-50"
          >
            {uploading ? "Uploading…" : "+ Upload"}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="text-xs text-gray-400 hover:text-gray-600"
            title="Close panel"
          >
            ×
          </button>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".pdf,.xlsx,.xls,.xlsm,.csv,.tsv,.txt,.md,.log,.json,.yaml,.yml"
        className="hidden"
        onChange={(e) => {
          uploadFiles(e.target.files);
          e.target.value = "";
        }}
      />

      {error && (
        <div className="px-3 py-2 bg-red-50 border-b border-red-100 text-xs text-red-700">
          {error}
        </div>
      )}

      <div className="max-h-40 overflow-y-auto">
        {loading ? (
          <div className="px-3 py-2 text-xs text-gray-500">Loading…</div>
        ) : files.length === 0 ? (
          <div className="px-3 py-3 text-xs text-gray-400">
            No files uploaded yet. Click + Upload to add documents the AI can reference.
          </div>
        ) : (
          <ul className="divide-y divide-gray-100">
            {files.map((f) => {
              const checked = (selectedNames || []).includes(f.name);
              return (
                <li key={f.name} className="px-3 py-1.5 flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleSelected(f.name)}
                    className="w-3.5 h-3.5"
                  />
                  <span className="flex-1 text-xs text-gray-700 font-mono truncate">
                    {f.name}
                  </span>
                  <button
                    onClick={() => deleteFile(f.name)}
                    className="text-xs text-gray-400 hover:text-red-600"
                    title="Delete"
                  >
                    ×
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
