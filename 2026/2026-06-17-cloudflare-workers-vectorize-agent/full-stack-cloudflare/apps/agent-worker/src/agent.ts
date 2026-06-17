import { DEFAULT_LIMIT, type SearchResult } from "../../../packages/shared/src/index";
import { chatModel, streamAi } from "./cloudflare";
import { readAiStream } from "./ai-stream";
import type { AgentRenderer } from "./renderer";
import { parseSearchArgs, search, searchTool } from "./search";
import type { ChatMessage, Env, ToolCall } from "./schemas";

const MAX_ITERATIONS = 5;
export const DEFAULT_MAX_OUTPUT_TOKENS = 8192;

const INSTRUCTIONS = `
You're a teaching assistant for DataTalks.Club zoomcamps.

Answer the user's question using the FAQ knowledge base. Use the search tool
to look things up. You can call search multiple times with different queries
to explore the topic well.

Rules:
- Always call search before answering course FAQ questions.
- Choose the search query yourself. Fix typos, remove filler words, and use
  concise FAQ-style wording.
- If the first search results do not directly answer the user's question, call
  search again with a better query.
- Use only facts from the search results.
- If the answer isn't in the results, say so clearly.
- Never print JSON, tool names, function arguments, or implementation details
  in the final answer.
- At the end, list the FAQ entries you used under a "Sources" section,
  one per line exactly in the form: "- [id] section > question".
`.trim();

/**
 * Runs the multi-iteration FAQ agent.
 * Used by `/ask/stream`; lets the model call `search`, executes
 * those calls, appends tool results, and stops when the model returns an answer.
 */
export async function runAgent(
  env: Env,
  question: string,
  renderer: AgentRenderer,
  limit = DEFAULT_LIMIT,
  maxOutputTokens = DEFAULT_MAX_OUTPUT_TOKENS,
): Promise<{ answer: string; results: SearchResult[] }> {
  await renderer.handleEvent("status", { message: "thinking..." });

  const messages: ChatMessage[] = [
    { role: "system", content: INSTRUCTIONS },
    { role: "user", content: question },
  ];
  const allResults: SearchResult[] = [];
  const maxOutputTokensForRun = clampMaxOutputTokens(maxOutputTokens);

  for (let iteration = 1; iteration <= MAX_ITERATIONS; iteration++) {
    await renderer.handleEvent("iteration", { n: iteration });

    const response = await requestResponse(env, messages, renderer, maxOutputTokensForRun);
    await renderer.handleEvent("model_done", {
      completionTokens: response.completionTokens,
      finishReason: response.finishReason ?? "unknown",
      iteration,
      maxOutputTokens: maxOutputTokensForRun,
      totalTokens: response.totalTokens,
    });

    if (response.toolCalls.length === 0) {
      await renderer.handleEvent("done", {
        answer: response.answer,
        finishReason: response.finishReason ?? "unknown",
        maxOutputTokens: maxOutputTokensForRun,
        stoppedBy: response.finishReason === "length" ? "token_limit" : "model",
      });
      return { answer: response.answer, results: allResults };
    }

    const results = await handleToolCalls(env, messages, response.toolCalls, renderer, limit);
    allResults.push(...results);
  }

  const answer = "(stopped: reached max iterations)";
  await renderer.handleEvent("done", {
    answer,
    maxIterations: MAX_ITERATIONS,
    stoppedBy: "max_iterations",
  });
  return { answer, results: allResults };
}

/**
 * Sends one chat turn to Workers AI with the `search` tool available.
 * Used by `runAgent` on every iteration; streams reasoning and answer tokens into the renderer.
 */
async function requestResponse(
  env: Env,
  messages: ChatMessage[],
  renderer: AgentRenderer,
  maxTokens: number,
): Promise<{
  answer: string;
  completionTokens?: number;
  finishReason?: string;
  toolCalls: ToolCall[];
  totalTokens?: number;
}> {
  const stream = await streamAi(env, chatModel(env), {
    messages,
    tools: [searchTool],
    tool_choice: "auto",
    temperature: 0.2,
    max_tokens: maxTokens,
  });

  return readAiStream(stream, {
    onReasoning: (delta) => {
      void renderer.handleEvent("reasoning", { delta });
    },
    onToken: (delta) => {
      void renderer.handleEvent("token", { delta });
    },
  });
}

/**
 * Executes model-requested tool calls and appends tool outputs to chat history.
 * Used by `runAgent` after each model response that contains tool calls.
 */
async function handleToolCalls(
  env: Env,
  messages: ChatMessage[],
  toolCalls: ToolCall[],
  renderer: AgentRenderer,
  limit: number,
): Promise<SearchResult[]> {
  const results: SearchResult[] = [];
  messages.push({ role: "assistant", content: "", tool_calls: toolCalls });

  for (const call of toolCalls) {
    if (call.function.name !== "search") {
      continue;
    }

    const args = parseSearchArgs(call.function.arguments, limit);
    await renderer.handleEvent("tool_call", { name: "search", arguments: args });

    const toolResult = await search(env, args, limit);
    await renderer.handleEvent("tool_result", { name: "search", result: toolResult });

    messages.push({
      role: "tool",
      tool_call_id: call.id,
      name: "search",
      content: JSON.stringify(toolResult),
    });
    results.push(...toolResult);
  }

  return results;
}

/**
 * Clamps user-provided model output budget to a practical range.
 * Used by `runAgent` so the UI can tune reasoning models per request.
 */
export function clampMaxOutputTokens(value: unknown): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return DEFAULT_MAX_OUTPUT_TOKENS;
  }

  return Math.max(256, Math.min(16384, Math.floor(parsed)));
}
