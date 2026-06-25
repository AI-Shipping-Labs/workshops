"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { useState } from "react";

export default function Page() {
  const { messages, sendMessage, status } = useChat({
    transport: new DefaultChatTransport({ api: "/api/chat" }),
  });
  const [input, setInput] = useState("");
  const busy = status === "submitted" || status === "streaming";

  return (
    <main>
      <header>
        <h1>DataTalks.Club FAQ Agent</h1>
        <p>Ask about the Data Engineering Zoomcamp. Powered by Vercel AI SDK + MiniSearch.</p>
      </header>

      {messages.map((message) => (
        <div key={message.id} className={`msg ${message.role}`}>
          <div className="role">{message.role === "user" ? "You" : "Agent"}</div>
          {message.parts.map((part, i) => {
            if (part.type === "text") {
              return (
                <div key={i} className="bubble">
                  {part.text}
                </div>
              );
            }
            // Tool steps stream in as `tool-search` parts.
            if (part.type === "tool-search") {
              const query =
                part.input && typeof part.input === "object" && "query" in part.input
                  ? String((part.input as { query?: unknown }).query ?? "")
                  : "";
              const count = Array.isArray(part.output) ? part.output.length : undefined;
              return (
                <div key={i} className="tool">
                  🔍 searched FAQ for <code>{query || "…"}</code>
                  {count !== undefined ? ` — ${count} result${count === 1 ? "" : "s"}` : ""}
                </div>
              );
            }
            return null;
          })}
        </div>
      ))}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          const text = input.trim();
          if (!text || busy) return;
          sendMessage({ text });
          setInput("");
        }}
      >
        <div className="inner">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="How do I install the course dependencies?"
            disabled={busy}
          />
          <button type="submit" disabled={busy || !input.trim()}>
            {busy ? "…" : "Ask"}
          </button>
        </div>
      </form>
    </main>
  );
}
