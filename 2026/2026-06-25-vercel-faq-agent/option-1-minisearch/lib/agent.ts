import { openai } from "@ai-sdk/openai";
import { ToolLoopAgent, stepCountIs, type LanguageModel } from "ai";
import { searchTool } from "@/lib/search";

/**
 * How we reach the chat model:
 *  - "gateway" (default): route through the Vercel AI Gateway. One key for any
 *    provider; on Vercel it's keyless (authenticates via OIDC).
 *  - "openai": call the OpenAI API directly (needs OPENAI_API_KEY).
 */
export const MODEL_PROVIDER = process.env.MODEL_PROVIDER ?? "gateway";

/** Bare model name, e.g. "gpt-5.4-mini" (no provider prefix). */
export const CHAT_MODEL = process.env.CHAT_MODEL ?? "gpt-5.4-mini";

/**
 * Resolves the configured model into something `ToolLoopAgent` accepts.
 * Direct mode returns an OpenAI provider instance; gateway mode returns a
 * plain "provider/model" string, which the AI SDK routes through the gateway.
 */
function resolveModel(): LanguageModel {
  if (MODEL_PROVIDER === "openai") {
    return openai(CHAT_MODEL);
  }
  // Gateway expects a "provider/model" id; default the provider to openai.
  return CHAT_MODEL.includes("/") ? CHAT_MODEL : `openai/${CHAT_MODEL}`;
}

/** Max agent steps (model turn + tool call) per request. */
const MAX_STEPS = 5;

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
 * The FAQ agent: model + instructions + tools + loop, all in one place.
 * This is the single definition of the agent — the API route just imports
 * and runs it. (`ToolLoopAgent` calls the model, runs any tool calls, and
 * loops until the model answers or `stopWhen` is hit.)
 */
export const faqAgent = new ToolLoopAgent({
  model: resolveModel(),
  instructions: INSTRUCTIONS,
  tools: { search: searchTool },
  stopWhen: stepCountIs(MAX_STEPS),
});
