import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import TrarpesWidget from "./components/TrarpesWidget";
import { gatherDroppedFiles } from "./utils/dragAndDrop";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

/** Replace [Source: filename, Section X] with clickable PDF links */
function CitedMarkdown({ content }) {
  const processed = content.replace(
    /\[Source:\s*([^,\]]+?)(?:,\s*([^\]]+?))?\]/g,
    (_, filename, section) => {
      const trimmed = filename.trim();
      const encoded = encodeURIComponent(trimmed);
      const label = section ? section.trim() : trimmed.replace(".pdf", "");
      return `[${label}](${API_URL}/papers/${encoded})`;
    }
  );

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex]}
      components={{
        a: ({ href, children, ...props }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 underline decoration-blue-300"
            {...props}
          >
            <svg className="w-3 h-3 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
            </svg>
            {children}
          </a>
        ),
      }}
    >
      {processed}
    </ReactMarkdown>
  );
}

/** Collapsible thinking/reasoning block */
function ThinkingBlock({ text, isStreaming }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (isStreaming) setOpen(true);
  }, [isStreaming]);

  if (!text && !isStreaming) return null;

  return (
    <div className="mb-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 text-xs text-amber-700 hover:text-amber-900 transition-colors"
      >
        <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg ${isStreaming ? "bg-amber-50 border border-amber-200" : "bg-gray-50 border border-gray-200"}`}>
          {isStreaming ? (
            <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            <svg className={`w-3 h-3 transition-transform ${open ? "rotate-90" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
            </svg>
          )}
          <span className="font-medium">
            {isStreaming ? "Thinking..." : "View thinking"}
          </span>
        </div>
      </button>
      {open && (
        <div className="mt-2 ml-1 pl-3 border-l-2 border-amber-200 text-xs text-gray-500 leading-relaxed whitespace-pre-wrap max-h-64 overflow-y-auto">
          {text}
        </div>
      )}
    </div>
  );
}

let msgIdCounter = 0;

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("idle"); // idle | thinking | streaming
  const bottomRef = useRef(null);
  const abortRef = useRef(null);

  // Claude-style tool mode + attachments
  const [trarpesMode, setTrarpesMode] = useState(false);
  const [attachments, setAttachments] = useState([]); // [{name, scan_num, compat, status: "uploading"|"done"|"error", error?}]
  const [attachMenuOpen, setAttachMenuOpen] = useState(false);
  const [dropOverlay, setDropOverlay] = useState(false);
  const attachMenuRef = useRef(null);
  const fileInputRef = useRef(null);
  const folderInputRef = useRef(null);
  const dragCounterRef = useRef(0);

  const isLoading = status !== "idle";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, status]);

  // Close the attach popover when clicking outside
  useEffect(() => {
    if (!attachMenuOpen) return;
    const onDown = (e) => {
      if (attachMenuRef.current && !attachMenuRef.current.contains(e.target)) {
        setAttachMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [attachMenuOpen]);

  // ─── Attachment handling ────────────────────────────────────────────────
  const uploadOneFile = useCallback(async (pxt, txt) => {
    const attachId = String(++msgIdCounter);
    setAttachments((prev) => [
      ...prev,
      { id: attachId, name: pxt.name, status: "uploading" },
    ]);
    try {
      const fd = new FormData();
      fd.append("pxt", pxt);
      if (txt) fd.append("txt", txt);
      const r = await fetch(`${API_URL}/trarpes/upload`, {
        method: "POST",
        body: fd,
      });
      if (!r.ok) throw new Error(await r.text());
      const j = await r.json();
      setAttachments((prev) =>
        prev.map((a) =>
          a.id === attachId
            ? { ...a, status: "done", scan_num: j.scan_num, compat: j.compat }
            : a,
        ),
      );
    } catch (e) {
      setAttachments((prev) =>
        prev.map((a) =>
          a.id === attachId ? { ...a, status: "error", error: e.message } : a,
        ),
      );
    }
  }, []);

  const handleFilesToAttach = useCallback(
    async (fileList) => {
      const files = Array.from(fileList || []);
      const pxts = files.filter((f) => f.name.endsWith(".pxt"));
      const txts = files.filter((f) => f.name.endsWith(".txt"));
      if (!pxts.length) return;
      // Turning on TR-ARPES mode is an implicit UX when files are attached
      setTrarpesMode(true);
      for (const pxt of pxts) {
        const stem = pxt.name.replace(/\.pxt$/, "");
        const txt = txts.find((t) => t.name === `${stem}.txt`);
        await uploadOneFile(pxt, txt);
      }
    },
    [uploadOneFile],
  );

  const removeAttachment = useCallback((id) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  }, []);

  const onPageDrop = async (e) => {
    e.preventDefault();
    dragCounterRef.current = 0;
    setDropOverlay(false);
    const files = await gatherDroppedFiles(e);
    handleFilesToAttach(files);
  };

  // ─── Send ───────────────────────────────────────────────────────────────
  const sendMessage = useCallback(async (text) => {
    // When TR-ARPES mode is on, append a structured hint so the LLM knows
    // what tool the user selected and what scans are attached. The LLM
    // will invoke `trarpes_open` with those scan numbers.
    const doneAttached = attachments.filter(
      (a) => a.status === "done" && a.compat?.ok !== false,
    );
    let augmented = text;
    if (trarpesMode) {
      const parts = [text];
      if (doneAttached.length) {
        const list = doneAttached
          .map((a) => `scan_${String(a.scan_num).padStart(3, "0")}`)
          .join(", ");
        parts.push(
          `\n\n[TR-ARPES tool selected by user. Uploaded scans: ${list}.`
            + ` Please invoke trarpes_open with the first two compatible scan numbers`
            + ` as scan_a and scan_b, and include a short physical explanation first.]`,
        );
      } else {
        parts.push(
          `\n\n[TR-ARPES tool selected by user (no scans attached yet).`
            + ` Please invoke trarpes_open with no arguments so the user can upload/pick in the widget.]`,
        );
      }
      augmented = parts.join("");
    }

    const userMsg = {
      id: String(++msgIdCounter),
      role: "user",
      content: text, // user sees their original message in the chat
      reasoning: "",
    };
    const asstId = String(++msgIdCounter);

    setMessages((prev) => [
      ...prev,
      userMsg,
      { id: asstId, role: "assistant", content: "", reasoning: "" },
    ]);
    setStatus("thinking");

    // Send the AUGMENTED message to the backend while keeping the display copy clean.
    const history = [...messages, userMsg].map((m) => ({
      role: m.role,
      content: m.content,
    }));
    if (history.length > 0) {
      history[history.length - 1] = { role: "user", content: augmented };
    }

    // Clear attachments + mode after send (one-shot, like Claude)
    setTrarpesMode(false);
    setAttachments([]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: history }),
        signal: controller.signal,
      });

      if (!res.ok) throw new Error(`Server error: ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line) continue;

          const prefix = line[0];
          const payload = line.slice(2); // skip "X:"

          if (prefix === "g") {
            // Reasoning/thinking chunk
            try {
              const data = JSON.parse(payload);
              setStatus("thinking");
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === asstId
                    ? { ...m, reasoning: m.reasoning + (data.text || "") }
                    : m
                )
              );
            } catch {}
          } else if (prefix === "0") {
            // Text chunk
            try {
              const text = JSON.parse(payload);
              setStatus("streaming");
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === asstId
                    ? { ...m, content: m.content + text }
                    : m
                )
              );
            } catch {}
          } else if (prefix === "9") {
            // Tool-use: model invoked a frontend-rendered tool
            try {
              const data = JSON.parse(payload);
              if (data.toolName === "trarpes_open") {
                const args = data.args || {};
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === asstId
                      ? {
                          ...m,
                          widget: "trarpes",
                          widgetProps: {
                            initialScanA: args.scan_a ?? null,
                            initialScanB: args.scan_b ?? null,
                          },
                        }
                      : m,
                  ),
                );
              }
            } catch {}
          } else if (prefix === "d") {
            // Done
            break;
          }
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        setMessages((prev) => [
          ...prev,
          { id: asstId, role: "assistant", content: `Error: ${err.message}`, reasoning: "" },
        ]);
      }
    } finally {
      setStatus("idle");
      abortRef.current = null;
    }
  }, [messages, trarpesMode, attachments]);

  function submit(text) {
    const msg = (text || input).trim();
    if (isLoading) return;
    // Allow an empty message if TR-ARPES mode is on with at least one
    // successfully-uploaded attachment (the LLM will still respond via
    // the augmentation block).
    const hasReadyAttachments =
      trarpesMode && attachments.some((a) => a.status === "done");
    if (!msg && !hasReadyAttachments) return;
    setInput("");
    // Use a sensible placeholder when the user just clicks send with files attached
    sendMessage(msg || "Analyze these TR-ARPES scans.");
  }

  return (
    <div
      className="h-screen flex flex-col bg-white relative"
      onDragEnter={(e) => {
        if (e.dataTransfer?.types?.includes("Files")) {
          e.preventDefault();
          dragCounterRef.current += 1;
          setDropOverlay(true);
        }
      }}
      onDragOver={(e) => {
        if (e.dataTransfer?.types?.includes("Files")) e.preventDefault();
      }}
      onDragLeave={() => {
        dragCounterRef.current -= 1;
        if (dragCounterRef.current <= 0) setDropOverlay(false);
      }}
      onDrop={onPageDrop}
    >
      {dropOverlay && (
        <div className="fixed inset-0 z-50 bg-blue-500/10 border-4 border-dashed border-blue-500 flex items-center justify-center pointer-events-none">
          <div className="bg-white rounded-xl shadow-lg px-6 py-4 text-sm text-gray-900 font-medium">
            Drop to attach .pxt files or folder
          </div>
        </div>
      )}
      {/* Header */}
      <header className="border-b border-gray-200 px-6 py-4 flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-blue-900 flex items-center justify-center">
          <span className="text-white text-sm font-bold">C</span>
        </div>
        <div>
          <h1 className="text-base font-semibold text-gray-900">ChatARPES</h1>
          <p className="text-xs text-gray-500">TR-ARPES Setup Assistant</p>
        </div>
      </header>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center px-4">
            <div className="w-12 h-12 rounded-full bg-blue-900 flex items-center justify-center mb-6">
              <span className="text-white text-xl font-bold">C</span>
            </div>
            <h2 className="text-xl font-medium text-gray-900 mb-2">
              What can I help you with?
            </h2>
            <p className="text-sm text-gray-500 text-center max-w-md mb-8">
              Ask questions about the lab's TR-ARPES setup, experimental parameters,
              HHG source, or anything covered in the setup paper.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-lg w-full">
              {[
                "What energy resolution does the system achieve?",
                "Describe the HHG source setup",
                "What is the angular resolution?",
                "How does the delay stage work?",
              ].map((q) => (
                <button
                  key={q}
                  onClick={() => submit(q)}
                  className="text-left text-sm text-gray-600 border border-gray-200 rounded-xl px-4 py-3 hover:bg-gray-50 transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div
            className={`mx-auto px-4 py-6 space-y-6 transition-[max-width] ${
              messages.some((m) => m.widget) ? "max-w-6xl" : "max-w-3xl"
            }`}
          >
            {messages.map((msg, idx) => (
              <div key={msg.id}>
                {msg.role === "user" ? (
                  <div className="flex justify-end">
                    <div className="bg-gray-100 rounded-2xl px-4 py-3 max-w-[85%]">
                      <p className="text-sm text-gray-900 whitespace-pre-wrap">
                        {msg.content}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="flex gap-3">
                    <div className="w-7 h-7 rounded-full bg-blue-900 flex-shrink-0 flex items-center justify-center mt-0.5">
                      <span className="text-white text-xs font-bold">C</span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <ThinkingBlock
                        text={msg.reasoning}
                        isStreaming={idx === messages.length - 1 && status === "thinking"}
                      />
                      {msg.content && (
                        <div className="prose prose-sm max-w-none prose-gray prose-headings:font-semibold prose-headings:text-gray-900 prose-p:text-gray-700 prose-p:leading-relaxed prose-a:text-blue-600 prose-pre:bg-gray-50 prose-pre:border prose-pre:border-gray-200 prose-code:text-gray-800 prose-code:before:content-none prose-code:after:content-none mb-2">
                          <CitedMarkdown content={msg.content} />
                        </div>
                      )}
                      {msg.widget === "trarpes" && (
                        <TrarpesWidget
                          apiUrl={API_URL}
                          initialScanA={msg.widgetProps?.initialScanA ?? null}
                          initialScanB={msg.widgetProps?.initialScanB ?? null}
                        />
                      )}
                      {!msg.content &&
                        !msg.widget &&
                        idx === messages.length - 1 &&
                        isLoading &&
                        status !== "thinking" && (
                          <div className="flex items-center gap-1 py-2">
                            <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:0ms]" />
                            <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:150ms]" />
                            <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:300ms]" />
                          </div>
                        )}
                    </div>
                  </div>
                )}
              </div>
            ))}
            {isLoading && messages[messages.length - 1]?.role === "user" && (
              <div className="flex gap-3">
                <div className="w-7 h-7 rounded-full bg-blue-900 flex-shrink-0 flex items-center justify-center">
                  <span className="text-white text-xs font-bold">C</span>
                </div>
                <div className="flex items-center gap-2 py-2">
                  <svg className="w-4 h-4 animate-spin text-gray-400" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  <span className="text-sm text-gray-400">Thinking...</span>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="border-t border-gray-200 px-4 py-4">
        <div className="max-w-3xl mx-auto">
          {/* Attachment chips */}
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-2">
              {attachments.map((a) => {
                const ok = a.status === "done" && a.compat?.ok !== false;
                const bad = a.status === "done" && a.compat?.ok === false;
                const err = a.status === "error";
                return (
                  <div
                    key={a.id}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs border ${
                      err || bad
                        ? "bg-red-50 border-red-200 text-red-700"
                        : ok
                          ? "bg-blue-50 border-blue-200 text-blue-700"
                          : "bg-gray-50 border-gray-200 text-gray-600"
                    }`}
                    title={
                      err
                        ? `Upload failed: ${a.error}`
                        : bad
                          ? `Not TR-ARPES compatible: ${a.compat?.reason}`
                          : a.status === "uploading"
                            ? "Uploading…"
                            : "Ready"
                    }
                  >
                    {a.status === "uploading" && (
                      <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                    )}
                    {ok && <span>✓</span>}
                    {(bad || err) && <span>✗</span>}
                    <span className="font-mono">{a.name}</span>
                    <button
                      type="button"
                      onClick={() => removeAttachment(a.id)}
                      className="ml-0.5 opacity-60 hover:opacity-100"
                      title="Remove"
                    >
                      ×
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          {/* Composer */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
            className="relative flex items-center gap-1.5 border border-gray-300 rounded-2xl px-2 py-1.5 focus-within:ring-2 focus-within:ring-blue-500 focus-within:border-transparent"
          >
            {/* + attach button */}
            <div className="relative" ref={attachMenuRef}>
              <button
                type="button"
                onClick={() => setAttachMenuOpen((v) => !v)}
                disabled={isLoading}
                className="w-8 h-8 rounded-full flex items-center justify-center text-gray-500 hover:bg-gray-100 disabled:opacity-50"
                title="Attach files"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
              </button>
              {attachMenuOpen && (
                <div className="absolute bottom-10 left-0 w-52 bg-white border border-gray-200 rounded-xl shadow-lg py-1 z-20">
                  <button
                    type="button"
                    onClick={() => {
                      setAttachMenuOpen(false);
                      fileInputRef.current?.click();
                    }}
                    className="w-full px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                  >
                    <svg className="w-4 h-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 8.25H7.5a2.25 2.25 0 00-2.25 2.25v9a2.25 2.25 0 002.25 2.25h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25H15m0-3l-3-3m0 0l-3 3m3-3V15" />
                    </svg>
                    Upload files…
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setAttachMenuOpen(false);
                      folderInputRef.current?.click();
                    }}
                    className="w-full px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                  >
                    <svg className="w-4 h-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12.75V12A2.25 2.25 0 014.5 9.75h15A2.25 2.25 0 0121.75 12v.75m-8.69-6.44l-2.12-2.12a1.5 1.5 0 00-1.061-.44H4.5A2.25 2.25 0 002.25 6v12a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9a2.25 2.25 0 00-2.25-2.25h-5.379a1.5 1.5 0 01-1.06-.44z" />
                    </svg>
                    Upload folder…
                  </button>
                </div>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept=".pxt,.txt"
                multiple
                className="hidden"
                onChange={(e) => {
                  handleFilesToAttach(e.target.files);
                  e.target.value = "";
                }}
              />
              <input
                ref={folderInputRef}
                type="file"
                webkitdirectory=""
                directory=""
                multiple
                className="hidden"
                onChange={(e) => {
                  handleFilesToAttach(e.target.files);
                  e.target.value = "";
                }}
              />
            </div>

            {/* TR-ARPES tool pill (toggles mode — no immediate spawn) */}
            <button
              type="button"
              onClick={() => setTrarpesMode((v) => !v)}
              disabled={isLoading}
              className={`text-xs px-2.5 py-1 rounded-full flex items-center gap-1.5 border transition-colors ${
                trarpesMode
                  ? "bg-blue-600 border-blue-600 text-white hover:bg-blue-700"
                  : "bg-white border-gray-300 text-gray-700 hover:bg-gray-50"
              } disabled:opacity-50`}
              title={
                trarpesMode
                  ? "TR-ARPES mode on — next message will open the analysis widget"
                  : "Activate TR-ARPES analysis mode"
              }
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
              </svg>
              TR-ARPES
            </button>

            {/* Text input */}
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                trarpesMode
                  ? "Describe the comparison (or just hit send)…"
                  : "Ask about the TR-ARPES setup…"
              }
              disabled={isLoading}
              className="flex-1 min-w-0 bg-transparent px-2 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none disabled:opacity-60"
            />

            {/* Send */}
            <button
              type="submit"
              disabled={
                isLoading ||
                (!input.trim() &&
                  !(trarpesMode && attachments.some((a) => a.status === "done")))
              }
              className="w-8 h-8 rounded-full bg-blue-900 flex items-center justify-center hover:bg-blue-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex-shrink-0"
            >
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18" />
              </svg>
            </button>
          </form>
          <p className="text-center text-xs text-gray-400 mt-2">
            {trarpesMode
              ? "TR-ARPES mode on — attach scans with + or drag-and-drop"
              : "Answers based on the lab's TR-ARPES setup paper"}
          </p>
        </div>
      </div>
    </div>
  );
}
