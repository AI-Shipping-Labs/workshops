"use client";

import { useCallback, useRef, useState } from "react";

/**
 * A tiny chat hook that talks to the Python backend.
 *
 * Option 1 used `useChat` from `@ai-sdk/react`, which speaks the Vercel AI SDK's
 * UI Message Stream protocol — TypeScript-specific. Since the backend is now
 * Python, we own the transport instead: POST the conversation, read back a
 * Server-Sent Events stream, and build up messages as they arrive. Same UI,
 * no AI SDK.
 *
 * The wire protocol matches the backend renderer (renderer.py): each event is
 * `event: <type>\ndata: <json>\n\n`, with types token / tool_call / tool_result /
 * status / iteration / done.
 */

export type Part =
  | { type: "text"; text: string }
  // count is null while the search is running, then the number of hits.
  | { type: "tool-search"; query: string; count: number | null };

export interface Message {
  id: string;
  role: "user" | "assistant";
  parts: Part[];
}

export type Status = "ready" | "submitted" | "streaming";

// Same-origin by default: in dev, next.config rewrites proxy /chat to the Python
// backend; in prod, FastAPI serves this static build and the API together, so a
// relative path works in both. Override with NEXT_PUBLIC_BACKEND_URL if the
// backend lives on a different origin.
const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "";

/** Flatten a message's parts back to plain text for the backend conversation. */
function toText(message: Message): string {
  return message.parts
    .filter((p): p is Extract<Part, { type: "text" }> => p.type === "text")
    .map((p) => p.text)
    .join("");
}

let counter = 0;
const nextId = () => `${Date.now()}-${counter++}`;

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [status, setStatus] = useState<Status>("ready");
  const messagesRef = useRef<Message[]>([]);
  messagesRef.current = messages;

  const sendMessage = useCallback(async (text: string) => {
    const userMessage: Message = {
      id: nextId(),
      role: "user",
      parts: [{ type: "text", text }],
    };
    const assistantId = nextId();
    setMessages((prev) => [
      ...prev,
      userMessage,
      { id: assistantId, role: "assistant", parts: [] },
    ]);
    setStatus("submitted");

    // Backend wants {role, content} pairs. Send the history plus the new turn.
    const history = [...messagesRef.current, userMessage].map((m) => ({
      role: m.role,
      content: toText(m),
    }));

    // Mutate the in-progress assistant message and push a fresh array to React.
    const update = (mutate: (parts: Part[]) => void) =>
      setMessages((prev) =>
        prev.map((m) => {
          if (m.id !== assistantId) return m;
          const parts = [...m.parts];
          mutate(parts);
          return { ...m, parts };
        }),
      );

    try {
      const res = await fetch(`${BACKEND_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: history }),
      });
      if (!res.ok || !res.body) {
        throw new Error(`Backend error: ${res.status}`);
      }
      setStatus("streaming");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      // Read SSE: events are separated by a blank line; each has an
      // `event: <type>` line and a `data: <json>` line.
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let sep: number;
        while ((sep = buffer.indexOf("\n\n")) !== -1) {
          const raw = buffer.slice(0, sep);
          buffer = buffer.slice(sep + 2);

          const lines = raw.split("\n");
          const type = lines.find((l) => l.startsWith("event: "))?.slice(7);
          const dataLine = lines.find((l) => l.startsWith("data: "))?.slice(6);
          if (!type || !dataLine) continue;
          const data = JSON.parse(dataLine);

          if (type === "token") {
            update((parts) => {
              const last = parts[parts.length - 1];
              if (last?.type === "text") last.text += data.delta;
              else parts.push({ type: "text", text: data.delta });
            });
          } else if (type === "tool_call") {
            update((parts) =>
              parts.push({
                type: "tool-search",
                query: String(data.arguments?.query ?? ""),
                count: null,
              }),
            );
          } else if (type === "tool_result") {
            // Fill in the hit count on the most recent running search.
            update((parts) => {
              for (let i = parts.length - 1; i >= 0; i--) {
                const p = parts[i];
                if (p.type === "tool-search" && p.count === null) {
                  p.count = Array.isArray(data.result) ? data.result.length : 0;
                  break;
                }
              }
            });
          }
        }
      }
    } catch (err) {
      update((parts) =>
        parts.push({
          type: "text",
          text: `\n⚠️ ${err instanceof Error ? err.message : "Request failed"}`,
        }),
      );
    } finally {
      setStatus("ready");
    }
  }, []);

  return { messages, sendMessage, status };
}
