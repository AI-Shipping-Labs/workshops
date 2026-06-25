import { Index } from "@upstash/vector";

export const COURSE = "data-engineering-zoomcamp";
export const DEFAULT_LIMIT = 5;

export interface SearchResult {
  id: string;
  score: number;
  question: string;
  answer: string;
  section: string;
  course: string;
}

/**
 * Lazily-created Upstash Vector client. Reads UPSTASH_VECTOR_REST_URL and
 * UPSTASH_VECTOR_REST_TOKEN from the environment. Lazy so that importing this
 * module (e.g. during build) doesn't require the credentials to be present.
 */
let client: Index | null = null;
function index(): Index {
  if (!client) {
    client = new Index();
  }
  return client;
}

/** Normalizes a caller-provided limit before it reaches the index. */
export function clampLimit(value: unknown, fallback = DEFAULT_LIMIT): number {
  const limit = typeof value === "number" && Number.isFinite(value) ? value : fallback;
  return Math.max(1, Math.min(10, Math.floor(limit)));
}

/**
 * Semantic search against the Upstash Vector index. We pass raw text as `data`;
 * Upstash embeds it server-side with the index's embedding model. The vectors
 * themselves were created offline by the Python ingestion process (`ingestion/`).
 */
export async function search(query: string, limit = DEFAULT_LIMIT): Promise<SearchResult[]> {
  const trimmed = query.trim();
  if (!trimmed) {
    return [];
  }

  const matches = await index().query({
    data: trimmed,
    topK: clampLimit(limit),
    includeMetadata: true,
  });

  return matches.map((match) => {
    const md = (match.metadata ?? {}) as Record<string, unknown>;
    return {
      id: String(match.id),
      score: match.score,
      question: String(md.question ?? ""),
      answer: String(md.answer ?? ""),
      section: String(md.section ?? ""),
      course: String(md.course ?? COURSE),
    };
  });
}
