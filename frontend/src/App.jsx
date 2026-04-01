import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

const API_URL = "http://localhost:8000";

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

  const isLoading = status !== "idle";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, status]);

  const sendMessage = useCallback(async (text) => {
    const userMsg = { id: String(++msgIdCounter), role: "user", content: text, reasoning: "" };
    const asstId = String(++msgIdCounter);

    // Add both user + empty assistant message immediately so thinking shows right away
    setMessages((prev) => [
      ...prev,
      userMsg,
      { id: asstId, role: "assistant", content: "", reasoning: "" },
    ]);
    setStatus("thinking");

    // Build history for the API (only role + content)
    const history = [...messages, userMsg].map((m) => ({
      role: m.role,
      content: m.content,
    }));

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
  }, [messages]);

  function submit(text) {
    const msg = (text || input).trim();
    if (!msg || isLoading) return;
    setInput("");
    sendMessage(msg);
  }

  return (
    <div className="h-screen flex flex-col bg-white">
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
          <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
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
                      {msg.content ? (
                        <div className="prose prose-sm max-w-none prose-gray prose-headings:font-semibold prose-headings:text-gray-900 prose-p:text-gray-700 prose-p:leading-relaxed prose-a:text-blue-600 prose-pre:bg-gray-50 prose-pre:border prose-pre:border-gray-200 prose-code:text-gray-800 prose-code:before:content-none prose-code:after:content-none">
                          <CitedMarkdown content={msg.content} />
                        </div>
                      ) : idx === messages.length - 1 && status === "thinking" ? null : (
                        idx === messages.length - 1 && isLoading && (
                          <div className="flex items-center gap-1 py-2">
                            <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:0ms]" />
                            <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:150ms]" />
                            <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:300ms]" />
                          </div>
                        )
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
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
          className="max-w-3xl mx-auto relative"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about the TR-ARPES setup..."
            disabled={isLoading}
            className="w-full border border-gray-300 rounded-2xl px-5 py-3.5 pr-14 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 w-8 h-8 rounded-full bg-blue-900 flex items-center justify-center hover:bg-blue-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18" />
            </svg>
          </button>
        </form>
        <p className="text-center text-xs text-gray-400 mt-2">
          Answers based on the lab's TR-ARPES setup paper
        </p>
      </div>
    </div>
  );
}
