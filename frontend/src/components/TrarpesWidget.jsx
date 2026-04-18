import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";

const Plot = createPlotlyComponent(Plotly);

// Exact sample of matplotlib's `terrain` colormap, matching the reference
// notebook's appearance. Plotly's built-in "Earth" is close but not identical.
const TERRAIN_COLORSCALE = [
  [0.0, "rgb(51,51,153)"],
  [0.1, "rgb(18,118,220)"],
  [0.2, "rgb(0,178,178)"],
  [0.25, "rgb(1,204,102)"],
  [0.3, "rgb(49,214,112)"],
  [0.4, "rgb(153,235,133)"],
  [0.5, "rgb(254,254,152)"],
  [0.6, "rgb(204,190,125)"],
  [0.7, "rgb(152,123,97)"],
  [0.8, "rgb(153,124,118)"],
  [0.9, "rgb(205,191,188)"],
  [1.0, "rgb(255,255,255)"],
];

/** Recompute diff-panel contrast locally from a sorted |diff| sample. */
function percentile(sortedAscending, pct) {
  if (!sortedAscending?.length) return 1;
  const p = Math.max(0, Math.min(100, pct)) / 100;
  const idx = Math.min(
    sortedAscending.length - 1,
    Math.max(0, Math.floor(p * (sortedAscending.length - 1))),
  );
  return sortedAscending[idx] || 1;
}

/** Recursively walk a DataTransferItem directory entry, collecting File objects. */
async function traverseEntry(entry, out) {
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

/** Gather files from a drop event, traversing folders if the browser supports it. */
async function gatherDroppedFiles(e) {
  const items = e.dataTransfer?.items;
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
  return Array.from(e.dataTransfer?.files || []);
}

/** Big drag-drop card shown before any data is loaded. */
function UploadStage({
  apiUrl,
  existingScans,
  onUploadComplete,
  onUseExisting,
}) {
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState("");
  const fileInputRef = useRef(null);
  const folderInputRef = useRef(null);
  const dragCounterRef = useRef(0);

  const handleFiles = async (fileList) => {
    const files = Array.from(fileList || []);
    const pxts = files.filter((f) => f.name.endsWith(".pxt"));
    const txts = files.filter((f) => f.name.endsWith(".txt"));
    if (pxts.length === 0) {
      setError(
        "No .pxt files found. Drop scan_NNN.pxt files or a folder containing them.",
      );
      return;
    }
    setUploading(true);
    setProgress({ done: 0, total: pxts.length });
    setError("");
    const uploaded = []; // [{num, compat}]
    const failures = [];
    for (let i = 0; i < pxts.length; i++) {
      const pxt = pxts[i];
      const stem = pxt.name.replace(/\.pxt$/, "");
      const txt = txts.find((t) => t.name === `${stem}.txt`);
      const fd = new FormData();
      fd.append("pxt", pxt);
      if (txt) fd.append("txt", txt);
      try {
        const r = await fetch(`${apiUrl}/trarpes/upload`, {
          method: "POST",
          body: fd,
        });
        if (!r.ok) {
          failures.push(`${pxt.name}: ${await r.text()}`);
        } else {
          const j = await r.json();
          uploaded.push({ num: j.scan_num, compat: j.compat });
        }
      } catch (e) {
        failures.push(`${pxt.name}: ${e.message}`);
      }
      setProgress({ done: i + 1, total: pxts.length });
    }
    setUploading(false);
    setProgress(null);

    if (failures.length) {
      setError(
        `${uploaded.length} succeeded, ${failures.length} failed:\n${failures
          .slice(0, 5)
          .join("\n")}${failures.length > 5 ? `\n…and ${failures.length - 5} more` : ""}`,
      );
    }
    if (uploaded.length > 0) {
      onUploadComplete(uploaded);
    }
  };

  const onDrop = async (e) => {
    e.preventDefault();
    dragCounterRef.current = 0;
    setDragOver(false);
    const files = await gatherDroppedFiles(e);
    handleFiles(files);
  };

  return (
    <div className="border border-gray-200 rounded-xl bg-white p-5 my-2 space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-gray-900">
          TR-ARPES: Load your scans
        </h3>
        <p className="text-xs text-gray-500 mt-0.5">
          Drop one or more <code>scan_NNN.pxt</code> files — or a folder of scans
          — and I'll load them for comparison.
        </p>
      </div>

      <div
        onDragEnter={(e) => {
          e.preventDefault();
          dragCounterRef.current += 1;
          setDragOver(true);
        }}
        onDragLeave={() => {
          dragCounterRef.current -= 1;
          if (dragCounterRef.current <= 0) setDragOver(false);
        }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
        className={`border-2 border-dashed rounded-xl px-4 py-8 text-center transition-colors ${
          dragOver
            ? "border-blue-500 bg-blue-50"
            : "border-gray-300 bg-gray-50"
        }`}
      >
        {uploading ? (
          <div className="space-y-2">
            <div className="text-sm text-gray-700">Uploading…</div>
            {progress && (
              <div className="flex flex-col items-center gap-2">
                <div className="w-48 h-1.5 bg-gray-200 rounded overflow-hidden">
                  <div
                    className="h-full bg-blue-500 transition-all"
                    style={{
                      width: `${(progress.done / Math.max(1, progress.total)) * 100}%`,
                    }}
                  />
                </div>
                <div className="text-xs font-mono text-gray-500">
                  {progress.done}/{progress.total}
                </div>
              </div>
            )}
          </div>
        ) : (
          <>
            <svg
              className="w-10 h-10 mx-auto text-gray-400 mb-3"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={1.5}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M7.5 7.5L12 3m0 0l4.5 4.5M12 3v13.5M4.5 17.25v1.875a2.625 2.625 0 002.625 2.625h9.75a2.625 2.625 0 002.625-2.625V17.25"
              />
            </svg>
            <div className="text-sm text-gray-700">
              {dragOver ? "Drop to upload" : "Drag and drop your scans here"}
            </div>
            <div className="text-xs text-gray-500 mt-1">
              .pxt files (with optional .txt sidecars) or a folder of them
            </div>
            <div className="flex items-center justify-center gap-2 mt-4">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="px-3 py-1.5 text-xs border border-gray-300 rounded-lg bg-white hover:bg-gray-50 text-gray-700"
              >
                Choose files
              </button>
              <button
                type="button"
                onClick={() => folderInputRef.current?.click()}
                className="px-3 py-1.5 text-xs border border-gray-300 rounded-lg bg-white hover:bg-gray-50 text-gray-700"
              >
                Choose folder
              </button>
            </div>
          </>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept=".pxt,.txt"
          multiple
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
        <input
          ref={folderInputRef}
          type="file"
          webkitdirectory=""
          directory=""
          multiple
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {existingScans > 0 && !uploading && (
        <div className="text-xs text-center">
          <button
            type="button"
            onClick={onUseExisting}
            className="text-blue-600 hover:text-blue-800 underline"
          >
            …or use {existingScans} existing scan{existingScans === 1 ? "" : "s"} already on the server
          </button>
        </div>
      )}

      {error && (
        <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2 whitespace-pre-wrap">
          {error}
        </div>
      )}
    </div>
  );
}

/** Three heatmaps + optional EDC plot. Pure presentation — no fetching. */
function PanelsView({ panels, dscale, scanA, scanB, edc, showEDC, height = 340 }) {
  const heatmapCommon = { type: "heatmap", zsmooth: "best", showscale: true };
  const panelLayout = (title, xlabel, ylabel, customHeight = height) => ({
    title: { text: title, font: { size: 12 } },
    xaxis: { title: xlabel, automargin: true },
    yaxis: { title: ylabel, automargin: true },
    margin: { l: 55, r: 30, t: 40, b: 45 },
    autosize: true,
    height: customHeight,
  });
  const plotConfig = { displaylogo: false, responsive: true };
  const plotStyle = { width: "100%", height: "100%" };

  // Put the EDC on its own full-width row below the heatmaps rather than
  // stuffing 4 panels into a single row — matches the notebook's data
  // content (same math, same EDC definition) but reads much better in
  // Plotly's auto-resizing layout.
  const edcHeight = Math.max(260, Math.round(height * 0.72));

  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-3 grid-cols-1 lg:grid-cols-3">
        <Plot
          data={[
            {
              ...heatmapCommon,
              z: panels.specA,
              x: panels.phi,
              y: panels.eV,
              zmin: 0,
              zmax: panels.vmax,
              colorscale: TERRAIN_COLORSCALE,
            },
          ]}
          layout={panelLayout(
            `A: scan_${String(scanA ?? 0).padStart(3, "0")} (ref)`,
            "phi (rad)",
            "eV",
          )}
          style={plotStyle}
          useResizeHandler
          config={plotConfig}
        />
        <Plot
          data={[
            {
              ...heatmapCommon,
              z: panels.specB,
              x: panels.phi,
              y: panels.eV,
              zmin: 0,
              zmax: panels.vmax,
              colorscale: TERRAIN_COLORSCALE,
            },
          ]}
          layout={panelLayout(
            `B: scan_${String(scanB ?? 0).padStart(3, "0")} (pumped)`,
            "phi (rad)",
            "eV",
          )}
          style={plotStyle}
          useResizeHandler
          config={plotConfig}
        />
        <Plot
          data={[
            {
              ...heatmapCommon,
              z: panels.diff,
              x: panels.phi,
              y: panels.eV,
              zmin: -dscale,
              zmax: dscale,
              colorscale: "RdBu",
              reversescale: true,
            },
          ]}
          layout={panelLayout("B − A  (differential)", "phi (rad)", "eV")}
          style={plotStyle}
          useResizeHandler
          config={plotConfig}
        />
      </div>
      {showEDC && edc && (
        <Plot
          data={[
            {
              type: "scatter",
              mode: "lines",
              name: `A (scan_${String(scanA ?? 0).padStart(3, "0")})`,
              x: edc.eV,
              y: edc.edcA,
              line: { color: "#2563eb", width: 1.8 },
            },
            {
              type: "scatter",
              mode: "lines",
              name: `B (scan_${String(scanB ?? 0).padStart(3, "0")})`,
              x: edc.eV,
              y: edc.edcB,
              line: { color: "#dc2626", width: 1.8 },
            },
          ]}
          layout={{
            ...panelLayout(
              `EDC at phi = ${edc.phiUsed.toFixed(3)} rad`,
              "eV",
              "Counts",
              edcHeight,
            ),
            showlegend: true,
            legend: { font: { size: 10 } },
          }}
          style={plotStyle}
          useResizeHandler
          config={plotConfig}
        />
      )}
    </div>
  );
}

/** Inline interactive TR-ARPES widget. */
export default function TrarpesWidget({ apiUrl, initialScanA, initialScanB }) {
  // Stage: "upload" (drop files) → "analysis" (full widget)
  const initialStage =
    initialScanA != null && initialScanB != null ? "analysis" : "upload";
  const [stage, setStage] = useState(initialStage);

  const [scans, setScans] = useState([]);
  const [dataDir, setDataDir] = useState("");
  const [scanA, setScanA] = useState(initialScanA ?? null);
  const [scanB, setScanB] = useState(initialScanB ?? null);
  const [smoothing, setSmoothing] = useState(1.5);
  const [diffScalePct, setDiffScalePct] = useState(95);
  const [showEDC, setShowEDC] = useState(false);
  const [edcPhi, setEdcPhi] = useState(0.0);
  const [panels, setPanels] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);

  // Esc to leave fullscreen
  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e) => {
      if (e.key === "Escape") setFullscreen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [fullscreen]);

  const firstCompatible = useCallback((list, skip = null) => {
    const filtered = list.filter((s) => s.num !== skip);
    const ok = filtered.find((s) => !s.compat || s.compat.ok);
    return (ok || filtered[0] || list[0])?.num ?? null;
  }, []);

  const refreshScans = useCallback(async () => {
    try {
      const r = await fetch(`${apiUrl}/trarpes/scans?check_compat=true`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      const list = j.scans || [];
      setScans(list);
      setDataDir(j.data_dir || "");
      return list;
    } catch (e) {
      setError(`Failed to list scans: ${e.message}`);
      return [];
    }
  }, [apiUrl]);

  // On mount: always refresh so we know how many scans already live on server.
  useEffect(() => {
    refreshScans().then((list) => {
      // If the tool-call pre-specified scan numbers, auto-pick them (already done).
      // If not, and we're in analysis stage with no selections, pick defaults.
      if (stage === "analysis" && list.length) {
        setScanA((cur) => cur ?? firstCompatible(list));
        setScanB((cur) => {
          if (cur != null) return cur;
          const a = firstCompatible(list);
          return firstCompatible(list, a) ?? a;
        });
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleUploadComplete = useCallback(
    async (uploaded) => {
      const list = await refreshScans();
      // Prefer the first two COMPATIBLE uploads as A and B.
      const compat = uploaded.filter((u) => u.compat?.ok !== false);
      if (compat.length >= 1) setScanA(compat[0].num);
      if (compat.length >= 2) setScanB(compat[1].num);
      else if (list.length >= 1) setScanA((cur) => cur ?? firstCompatible(list));
      else if (list.length >= 2)
        setScanB((cur) => cur ?? firstCompatible(list, scanA));
      setStage("analysis");
    },
    [refreshScans, firstCompatible, scanA],
  );

  const handleUseExisting = useCallback(() => {
    if (!scans.length) return;
    setScanA((cur) => cur ?? firstCompatible(scans));
    setScanB((cur) => {
      if (cur != null) return cur;
      const a = firstCompatible(scans);
      return firstCompatible(scans, a) ?? a;
    });
    setStage("analysis");
  }, [scans, firstCompatible]);

  // Debounced compute — skip if either selected scan is known-incompatible
  useEffect(() => {
    if (stage !== "analysis") return;
    if (scanA == null || scanB == null) return;
    const a = scans.find((s) => s.num === scanA);
    const b = scans.find((s) => s.num === scanB);
    if ((a?.compat && !a.compat.ok) || (b?.compat && !b.compat.ok)) {
      setPanels(null);
      return;
    }
    const id = setTimeout(async () => {
      setLoading(true);
      setError("");
      try {
        const r = await fetch(`${apiUrl}/trarpes/compute`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ scan_a: scanA, scan_b: scanB, smoothing }),
        });
        if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
        setPanels(await r.json());
      } catch (e) {
        setError(`Compute failed: ${e.message}`);
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => clearTimeout(id);
  }, [apiUrl, stage, scanA, scanB, smoothing, scans]);

  const dscale = useMemo(() => {
    if (!panels?.abs_diff_sorted) return 1;
    return percentile(panels.abs_diff_sorted, diffScalePct) || 1;
  }, [panels, diffScalePct]);

  const edc = useMemo(() => {
    if (!panels || !showEDC) return null;
    const { eV, phi, specA, specB } = panels;
    if (!phi?.length) return null;
    let idx = 0;
    let best = Infinity;
    for (let i = 0; i < phi.length; i++) {
      const d = Math.abs(phi[i] - edcPhi);
      if (d < best) {
        best = d;
        idx = i;
      }
    }
    const width = 3;
    const lo = Math.max(0, idx - width);
    const hi = Math.min(phi.length, idx + width + 1);
    const avg = (grid) => {
      const out = new Array(grid.length).fill(0);
      for (let e = 0; e < grid.length; e++) {
        let s = 0, n = 0;
        for (let p = lo; p < hi; p++) {
          s += grid[e][p];
          n += 1;
        }
        out[e] = n ? s / n : 0;
      }
      return out;
    };
    return { eV, edcA: avg(specA), edcB: avg(specB), phiUsed: phi[idx] };
  }, [panels, showEDC, edcPhi]);

  const handleExport = async () => {
    if (scanA == null || scanB == null) return;
    setExporting(true);
    try {
      const r = await fetch(`${apiUrl}/trarpes/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scan_a: scanA,
          scan_b: scanB,
          smoothing,
          diff_scale_pct: diffScalePct,
          show_edc: showEDC,
          edc_phi: edcPhi,
        }),
      });
      if (!r.ok) throw new Error(await r.text());
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `trarpes_scan_${String(scanA).padStart(3, "0")}_vs_${String(scanB).padStart(3, "0")}.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(`Export failed: ${e.message}`);
    } finally {
      setExporting(false);
    }
  };

  // ─── UPLOAD STAGE ──────────────────────────────────────────────────────
  if (stage === "upload") {
    return (
      <UploadStage
        apiUrl={apiUrl}
        existingScans={scans.length}
        onUploadComplete={handleUploadComplete}
        onUseExisting={handleUseExisting}
      />
    );
  }

  // ─── ANALYSIS STAGE ────────────────────────────────────────────────────
  const scanOptions = scans.map((s) => {
    const ok = !s.compat || s.compat.ok;
    const prefix = s.compat ? (ok ? "✓ " : "✗ ") : "";
    const base = `${prefix}scan_${String(s.num).padStart(3, "0")}`;
    const info = s.info ? `  (${s.info})` : "";
    const reason = !ok && s.compat?.reason ? ` — ${s.compat.reason}` : "";
    return { value: s.num, label: `${base}${info}${reason}`, ok, compat: s.compat };
  });

  const selectedA = scanOptions.find((o) => o.value === scanA);
  const selectedB = scanOptions.find((o) => o.value === scanB);
  const incompatWarning =
    selectedA && !selectedA.ok
      ? `Scan A is not TR-ARPES compatible: ${selectedA.compat?.reason}`
      : selectedB && !selectedB.ok
        ? `Scan B is not TR-ARPES compatible: ${selectedB.compat?.reason}`
        : null;

  // Plot height scales with fullscreen mode so it uses the available viewport.
  const plotHeight = fullscreen ? Math.max(360, window.innerHeight - 280) : 360;

  const body = (
    <div
      className={
        fullscreen
          ? "flex flex-col h-full bg-white p-4 space-y-3 overflow-auto"
          : "border border-gray-200 rounded-xl bg-white p-4 my-2 space-y-3"
      }
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-gray-900">
            TR-ARPES: Compare Two Scans
          </h3>
          <p className="text-xs text-gray-500 truncate">
            B − A differential. Data dir: <code>{dataDir || "(none)"}</code>
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            type="button"
            onClick={() => setStage("upload")}
            className="text-xs px-2.5 py-1.5 text-gray-600 hover:text-gray-900 hover:bg-gray-50 rounded-lg border border-transparent hover:border-gray-200"
          >
            + Upload more
          </button>
          <button
            onClick={handleExport}
            disabled={exporting || !panels}
            className="text-xs px-3 py-1.5 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            {exporting ? "Exporting…" : "Export PNG"}
          </button>
          <button
            type="button"
            onClick={() => setFullscreen((v) => !v)}
            className="w-8 h-8 flex items-center justify-center rounded-lg border border-gray-300 hover:bg-gray-50 text-gray-600"
            title={fullscreen ? "Exit fullscreen (Esc)" : "Expand to fullscreen"}
          >
            {fullscreen ? (
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
              </svg>
            )}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
        <label className="flex flex-col gap-1">
          <span className="text-gray-600">Scan A (reference)</span>
          <select
            value={scanA ?? ""}
            onChange={(e) => setScanA(Number(e.target.value))}
            className="border border-gray-300 rounded px-2 py-1"
          >
            {scanOptions.length === 0 && <option value="">(no scans)</option>}
            {scanOptions.map((o) => (
              <option key={o.value} value={o.value} disabled={!o.ok}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-gray-600">Scan B (pumped)</span>
          <select
            value={scanB ?? ""}
            onChange={(e) => setScanB(Number(e.target.value))}
            className="border border-gray-300 rounded px-2 py-1"
          >
            {scanOptions.length === 0 && <option value="">(no scans)</option>}
            {scanOptions.map((o) => (
              <option key={o.value} value={o.value} disabled={!o.ok}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-gray-600">Smoothing σ: {smoothing.toFixed(1)}</span>
          <input
            type="range"
            min={0}
            max={5}
            step={0.5}
            value={smoothing}
            onChange={(e) => setSmoothing(Number(e.target.value))}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-gray-600">
            Diff contrast %: {diffScalePct.toFixed(0)}
          </span>
          <input
            type="range"
            min={50}
            max={100}
            step={1}
            value={diffScalePct}
            onChange={(e) => setDiffScalePct(Number(e.target.value))}
          />
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={showEDC}
            onChange={(e) => setShowEDC(e.target.checked)}
          />
          <span className="text-gray-600">Show EDC comparison</span>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-gray-600">EDC at phi: {edcPhi.toFixed(3)}</span>
          <input
            type="range"
            min={-0.3}
            max={0.3}
            step={0.005}
            value={edcPhi}
            disabled={!showEDC}
            onChange={(e) => setEdcPhi(Number(e.target.value))}
          />
        </label>
      </div>

      {error && (
        <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2 whitespace-pre-wrap">
          {error}
        </div>
      )}
      {incompatWarning && !error && (
        <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
          {incompatWarning}
        </div>
      )}
      {loading && <div className="text-xs text-gray-500">Computing…</div>}

      {panels && (
        <div className={fullscreen ? "flex-1 min-h-0" : ""}>
          <PanelsView
            panels={panels}
            dscale={dscale}
            scanA={scanA}
            scanB={scanB}
            edc={edc}
            showEDC={showEDC}
            height={plotHeight}
          />
        </div>
      )}

      {scanA === scanB && scanA != null && (
        <p className="text-xs text-amber-600">
          Same scan selected for A and B — pick different ones to see the differential.
        </p>
      )}
    </div>
  );

  if (fullscreen) {
    return (
      <>
        <div className="border border-gray-200 rounded-xl bg-gray-50 p-4 my-2 text-xs text-gray-500 text-center">
          Opened in fullscreen — press Esc or click ⤡ to return
        </div>
        <div className="fixed inset-0 z-50 bg-black/40 flex items-stretch justify-center p-4 sm:p-6">
          <div className="relative w-full max-w-[1600px] bg-white rounded-xl shadow-2xl overflow-hidden">
            {body}
          </div>
        </div>
      </>
    );
  }

  return body;
}
