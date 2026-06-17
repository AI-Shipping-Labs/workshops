import {
  COURSE,
  DEFAULT_LIMIT,
  clampLimit,
  truncateForEmbedding,
  type FaqMetadata,
  type SearchResult,
} from "../../../packages/shared/src/index";
import { embeddingModel, queryVectorize, runAi } from "./cloudflare";
import { HttpError } from "./http";
import type { EmbeddingResponse, Env } from "./schemas";

export const searchTool = {
  type: "function",
  function: {
    name: "search",
    description: "Search the DataTalks.Club course FAQ using semantic vector search.",
    parameters: {
      type: "object",
      properties: {
        query: {
          type: "string",
          description: "A concise rewritten search query for the FAQ.",
        },
        limit: {
          type: "number",
          description: "Maximum number of FAQ entries to return. Use 5 unless more context is clearly needed.",
        },
      },
      required: ["query"],
      additionalProperties: false,
    },
  },
} as const;

export interface SearchArgs {
  query: string;
  limit?: number;
}

/**
 * Embeds a search query and runs semantic search against Vectorize.
 * Used by the raw `/search` endpoint and by the agent's `search` tool calls.
 */
export async function search(env: Env, args: SearchArgs, fallbackLimit = DEFAULT_LIMIT): Promise<SearchResult[]> {
  const query = args.query.trim();
  if (!query) {
    throw new HttpError("Search query cannot be empty.", 400);
  }

  const [queryVector] = await embedTexts(env, [query]);
  const matches = await queryVectorize(env, queryVector, clampLimit(args.limit, fallbackLimit));

  return matches.matches.map((match) => {
    const metadata = match.metadata as Partial<FaqMetadata> | undefined;
    return {
      id: String(metadata?.id ?? match.id ?? ""),
      score: Number(match.score ?? 0),
      question: String(metadata?.question ?? ""),
      answer: String(metadata?.answer ?? ""),
      section: String(metadata?.section ?? ""),
      course: String(metadata?.course ?? COURSE),
      source: String(metadata?.source ?? ""),
    };
  });
}

/**
 * Parses JSON arguments produced by the model for the `search` tool.
 * Used by `agent.ts` before executing a tool call.
 */
export function parseSearchArgs(input: string, fallbackLimit: number): SearchArgs {
  let parsed: unknown;
  try {
    parsed = JSON.parse(input);
  } catch {
    throw new HttpError(`Invalid search tool arguments: ${input}`, 400);
  }

  if (!isRecord(parsed) || typeof parsed.query !== "string") {
    throw new HttpError("Search tool arguments must include a string `query`.", 400);
  }

  return {
    query: parsed.query,
    limit: clampLimit(parsed.limit, fallbackLimit),
  };
}

/**
 * Generates embedding vectors for one or more texts.
 * Used by `search`; calls Workers AI through the Cloudflare adapter.
 */
async function embedTexts(env: Env, texts: string[]): Promise<number[][]> {
  const response = await runAi<EmbeddingResponse>(env, embeddingModel(env), {
    text: texts.map((text) => truncateForEmbedding(text)),
  });

  if (!Array.isArray(response.data) || response.data.length !== texts.length) {
    throw new HttpError("Embedding model returned an unexpected response.", 502);
  }

  return response.data;
}

/**
 * Runtime type guard for plain object-like values.
 * Used by `parseSearchArgs` before reading JSON properties.
 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
