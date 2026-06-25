import MiniSearch from "minisearch";
import { tool } from "ai";
import { z } from "zod";
import {
  clampLimit,
  DEFAULT_LIMIT,
  FAQ_DOCUMENTS,
  type FaqDocument,
  type SearchResult,
} from "@/lib/faq";

/**
 * Builds the in-memory full-text index once per server instance.
 * This replaces the Cloudflare embedding + Vectorize pipeline: instead of
 * semantic vector search, MiniSearch does fuzzy/prefix keyword search over the
 * FAQ text. The index is cheap to build, so it lives in module scope.
 */
const index = buildIndex(FAQ_DOCUMENTS);
const byId = new Map(FAQ_DOCUMENTS.map((doc) => [doc.id, doc]));

function buildIndex(documents: FaqDocument[]): MiniSearch<FaqDocument> {
  const mini = new MiniSearch<FaqDocument>({
    idField: "id",
    fields: ["question", "answer", "section"],
    storeFields: ["question", "answer", "section", "course"],
    searchOptions: {
      boost: { question: 3, section: 2 },
      fuzzy: 0.2,
      prefix: true,
    },
  });
  mini.addAll(documents);
  return mini;
}

/**
 * Runs a keyword search against the FAQ index.
 * Used by the raw `/api/search` endpoint and by the agent's `search` tool.
 */
export function search(query: string, limit = DEFAULT_LIMIT): SearchResult[] {
  const trimmed = query.trim();
  if (!trimmed) {
    return [];
  }

  return index
    .search(trimmed)
    .slice(0, clampLimit(limit))
    .map((match) => {
      const doc = byId.get(String(match.id));
      return {
        id: String(match.id),
        score: match.score,
        question: doc?.question ?? "",
        answer: doc?.answer ?? "",
        section: doc?.section ?? "",
        course: doc?.course ?? "",
      };
    });
}

/**
 * The `search` tool exposed to the model via the Vercel AI SDK.
 * Replaces the hand-written tool schema + manual tool-call dispatch from the
 * Cloudflare worker; the SDK validates input and runs `execute` automatically.
 */
export const searchTool = tool({
  description: "Search the DataTalks.Club course FAQ using keyword full-text search.",
  inputSchema: z.object({
    query: z.string().describe("A concise rewritten search query for the FAQ."),
    limit: z
      .number()
      .optional()
      .describe("Maximum number of FAQ entries to return. Use 5 unless more context is clearly needed."),
  }),
  execute: async ({ query, limit }) => search(query, limit ?? DEFAULT_LIMIT),
});
