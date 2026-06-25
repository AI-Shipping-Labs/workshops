"use client";

import { useState } from "react";
import { useChat } from "@/lib/useChat";

export default function Page() {
  const { messages, sendMessage, status } = useChat();
  const [input, setInput] = useState("");
  const busy = status === "submitted" || status === "streaming";

  return (
    <main>
      <header>
        <h1>DataTalks.Club FAQ Agent</h1>
        <p>Ask about the Data Engineering Zoomcamp. Next.js frontend + Python (FastAPI) backend.</p>
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
              return (
                <div key={i} className="tool">
                  🔍 searched FAQ for <code>{part.query || "…"}</code>
                  {part.count === null
                    ? " — searching…"
                    : ` — ${part.count} result${part.count === 1 ? "" : "s"}`}
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
          sendMessage(text);
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
