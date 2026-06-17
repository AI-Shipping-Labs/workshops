export interface Env {
  AI?: Ai;
  FAQ_INDEX?: Vectorize;
  CLOUDFLARE_ACCOUNT_ID?: string;
  CLOUDFLARE_API_TOKEN?: string;
  CHAT_MODEL?: string;
  EMBEDDING_MODEL?: string;
  LOCAL_CLOUDFLARE_REST?: string;
  VECTORIZE_INDEX_NAME?: string;
}

export interface AskRequest {
  question?: unknown;
  limit?: unknown;
  maxOutputTokens?: unknown;
}

export interface ChatMessage {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  name?: string;
}

export interface ToolCall {
  id: string;
  type: "function";
  function: {
    name: string;
    arguments: string;
  };
}

export interface AiTextResponse {
  response?: string | null;
  result?: {
    response?: string;
    output_text?: string;
  };
  output_text?: string;
  choices?: Array<{
    message?: {
      content?: string | null;
      tool_calls?: ToolCall[];
    };
  }>;
  tool_calls?: Array<{
    name: string;
    arguments: Record<string, unknown>;
  }>;
}

export interface EmbeddingResponse {
  shape?: number[];
  data?: number[][];
}

export interface VectorizeQueryResponse {
  count?: number;
  matches?: Array<{
    id?: string;
    score?: number;
    metadata?: unknown;
  }>;
}

export interface CloudflareApiResponse<T> {
  success?: boolean;
  result?: T;
  errors?: unknown;
}
