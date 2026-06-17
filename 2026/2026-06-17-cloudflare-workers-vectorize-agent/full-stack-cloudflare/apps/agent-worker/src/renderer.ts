export type AgentEvent =
  | "status"
  | "iteration"
  | "reasoning"
  | "model_done"
  | "tool_call"
  | "tool_result"
  | "token"
  | "done"
  | "error";

export interface AgentRenderer {
  handleEvent(event: AgentEvent, payload: Record<string, unknown>): Promise<void> | void;
}

/**
 * Converts agent events into SSE chunks for `/ask/stream`.
 * Used by `app.ts` when creating a streaming response.
 */
export class SseRenderer implements AgentRenderer {
  private readonly encoder = new TextEncoder();
  private closed = false;

  /**
   * Stores the response stream controller for later SSE writes.
   * Constructed by `streamAsk` in `app.ts`.
   */
  constructor(private readonly controller: ReadableStreamDefaultController<Uint8Array>) {}

  /**
   * Emits one typed SSE event.
   * Called by `runAgent` through the `AgentRenderer` interface.
   */
  handleEvent(event: AgentEvent, payload: Record<string, unknown>) {
    if (this.closed) {
      return;
    }

    try {
      this.controller.enqueue(this.encoder.encode(`event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`));
    } catch {
      this.closed = true;
    }
  }

  /**
   * Closes the SSE stream after agent work completes.
   * Called by `streamAsk`; ignores cases where the client disconnected first.
   */
  close() {
    if (this.closed) {
      return;
    }

    try {
      this.controller.close();
    } catch {
      // The browser or curl process may have already closed the connection.
    } finally {
      this.closed = true;
    }
  }
}
