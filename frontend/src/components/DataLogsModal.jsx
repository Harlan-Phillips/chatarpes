import { useCallback, useEffect, useRef, useState } from "react";

/** Modal for managing lab data logs — files auto-attached to every chat. */
export default function DataLogsModal({ apiUrl, open, onClose }) {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${apiUrl}/datalogs`);
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
        const r = await fetch(`${apiUrl}/datalogs`, { method: "POST", body: fd });
        if (!r.ok) throw new Error(await r.text());
        const j = await r.json();
        if (j.skipped?.length) {
          setError(
            `Skipped: ${j.skipped.map((s) => `${s.name} (${s.reason})`).join(", ")}`,
          );
        }
        await refresh();
      } catch (e) {
        setError(e.message);
      } finally {
        setUploading(false);
      }
    },
    [apiUrl, refresh],
  );

  const deleteFile = useCallback(
    async (name) => {
      if (!window.confirm(`Delete ${name}? This file will no longer be referenced in chats.`)) {
        return;
      }
      try {
        const r = await fetch(`${apiUrl}/datalogs/${encodeURIComponent(name)}`, {
          method: "DELETE",
        });
        if (!r.ok && r.status !== 204) throw new Error(`Delete failed: ${r.status}`);
        await refresh();
      } catch (e) {
        setError(e.message);
      }
    },
    [apiUrl, refresh],
  );

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-xl max-w-2xl w-full max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Lab data logs</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Persistent reference docs the AI sees on every chat.
            </p>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full flex items-center justify-center text-gray-500 hover:bg-gray-100"
            title="Close"
          >
            ×
          </button>
        </div>

        {/* Drop zone */}
        <div
          className={`mx-6 mt-4 rounded-xl border-2 border-dashed px-4 py-6 text-center transition-colors ${
            dragOver
              ? "border-blue-500 bg-blue-50"
              : "border-gray-300 bg-gray-50 hover:bg-gray-100"
          }`}
          onDragEnter={(e) => {
            if (e.dataTransfer?.types?.includes("Files")) {
              e.preventDefault();
              setDragOver(true);
            }
          }}
          onDragOver={(e) => {
            if (e.dataTransfer?.types?.includes("Files")) e.preventDefault();
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            uploadFiles(e.dataTransfer.files);
          }}
        >
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="text-sm text-blue-700 font-medium hover:underline disabled:opacity-50"
          >
            {uploading ? "Uploading…" : "Choose files"}
          </button>
          <span className="text-sm text-gray-500"> or drag-and-drop</span>
          <p className="text-xs text-gray-400 mt-1">
            .pdf, .xlsx, .csv, .txt, .md — up to 25 MB each
          </p>
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
        </div>

        {/* Error */}
        {error && (
          <div className="mx-6 mt-3 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
            {error}
          </div>
        )}

        {/* File list */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <p className="text-sm text-gray-500">Loading…</p>
          ) : files.length === 0 ? (
            <p className="text-sm text-gray-500">
              No data logs yet. Drop Excel logs, PDFs, or instruction manuals above to get started.
            </p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {files.map((f) => (
                <li key={f.name} className="py-2 flex items-center gap-3">
                  <span className="flex-1 text-sm text-gray-800 font-mono truncate">
                    {f.name}
                  </span>
                  <span className="text-xs text-gray-400">
                    {formatBytes(f.size)}
                  </span>
                  <button
                    onClick={() => deleteFile(f.name)}
                    className="text-xs text-red-600 hover:text-red-800 hover:underline"
                  >
                    delete
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
