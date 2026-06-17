import type { ToolCall } from "./schemas";

interface AiStreamChunk {
  choices?: Array<{
    finish_reason?: string | null;
    stop_reason?: unknown;
    delta?: {
      content?: string;
      reasoning?: string;
      reasoning_content?: string;
      tool_calls?: ToolCallDelta[];
    };
  }>;
  response?: string;
  usage?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
}

interface ToolCallDelta {
  index?: number;
  id?: string | null;
  type?: "function" | null;
  function?: {
    name?: string | null;
    arguments?: string;
  };
}

export interface AiStreamResult {
  answer: string;
  completionTokens?: number;
  finishReason?: string;
  reasoning: string;
  totalTokens?: number;
  toolCalls: ToolCall[];
}

export interface AiStreamCallbacks {
  onReasoning: (token: string) => void;
  onToken: (token: string) => void;
}

/**
 * Parses a Workers AI SSE stream into reasoning tokens, text tokens, and final tool calls.
 * Used by `agent.ts` after `streamAi` returns the raw model stream.
 */
export async function readAiStream(
  stream: ReadableStream<Uint8Array>,
  callbacks: AiStreamCallbacks,
): Promise<AiStreamResult> {
  const state = new StreamState(callbacks);
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let pendingEventText = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }

    // Network chunks can split one SSE event, so keep only the incomplete tail.
    pendingEventText += decoder.decode(value, { stream: true });
    const completeEvents = pendingEventText.split("\n\n");
    pendingEventText = completeEvents.pop() ?? "";

    for (const event of completeEvents) {
      state.consumeEvent(event);
    }
  }

  pendingEventText += decoder.decode();
  if (pendingEventText.trim()) {
    state.consumeEvent(pendingEventText);
  }

  return state.result();
}

/**
 * Mutable parser state for one model stream.
 * Used only by `readAiStream` to accumulate reasoning, answer text, and streamed tool args.
 */
class StreamState {
  private answer = "";
  private completionTokens: number | undefined;
  private finishReason: string | undefined;
  private reasoning = "";
  private totalTokens: number | undefined;
  private readonly toolCalls = new Map<number, ToolCall>();

  /**
   * Stores the stream callbacks for this parser instance.
   * Created only by `readAiStream` for one Workers AI response stream.
   */
  constructor(private readonly callbacks: AiStreamCallbacks) {}

  /**
   * Consumes one SSE event block.
   * Called by `readAiStream` after splitting the byte stream on blank lines.
   */
  consumeEvent(event: string) {
    for (const line of event.split("\n")) {
      if (!line.startsWith("data:")) {
        continue;
      }

      const data = line.slice("data:".length).trim();
      if (!data || data === "[DONE]") {
        continue;
      }

      this.consumeData(data);
    }
  }

  /**
   * Returns the completed answer and any fully assembled tool calls.
   * Called by `readAiStream` after the stream ends.
   */
  result(): AiStreamResult {
    return {
      answer: this.answer,
      completionTokens: this.completionTokens,
      finishReason: this.finishReason,
      reasoning: this.reasoning,
      totalTokens: this.totalTokens,
      toolCalls: [...this.toolCalls.values()].filter((call) => call.function.name),
    };
  }

/**
 * Parses one `data:` payload from Workers AI.
 * Used by `consumeEvent`; forwards reasoning, text deltas, and tool-call deltas.
 */
  private consumeData(data: string) {
    let chunk: AiStreamChunk;
    try {
      chunk = JSON.parse(data) as AiStreamChunk;
    } catch {
      return;
    }

    const delta = chunk.choices?.[0]?.delta;
    const finishReason = chunk.choices?.[0]?.finish_reason;
    if (finishReason) {
      this.finishReason = finishReason;
    }

    this.completionTokens = chunk.usage?.completion_tokens ?? this.completionTokens;
    this.totalTokens = chunk.usage?.total_tokens ?? this.totalTokens;

    const reasoningToken = delta?.reasoning_content ?? delta?.reasoning ?? "";
    if (reasoningToken) {
      this.reasoning += reasoningToken;
      this.callbacks.onReasoning(reasoningToken);
    }

    const token = delta?.content ?? chunk.response ?? "";
    if (token) {
      this.answer += token;
      this.callbacks.onToken(token);
    }

    for (const toolCallDelta of delta?.tool_calls ?? []) {
      this.mergeToolCall(toolCallDelta);
    }
  }

  /**
   * Merges partial streamed tool-call chunks into one complete call.
   * Used by `consumeData` because Workers AI streams function arguments in pieces.
   */
  private mergeToolCall(delta: ToolCallDelta) {
    const index = delta.index ?? 0;
    const current = this.toolCalls.get(index) ?? emptyToolCall(index);

    current.id = delta.id ?? current.id;
    current.type = delta.type ?? current.type;
    current.function.name = delta.function?.name ?? current.function.name;
    current.function.arguments += delta.function?.arguments ?? "";

    this.toolCalls.set(index, current);
  }
}

/**
 * Creates placeholder state for a streamed tool call.
 * Used by `StreamState.mergeToolCall` before all deltas have arrived.
 */
function emptyToolCall(index: number): ToolCall {
  return {
    id: `tool-call-${index}`,
    type: "function",
    function: {
      name: "",
      arguments: "",
    },
  };
}
