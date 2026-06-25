import MiniSearch from "minisearch";
import faqData from "@/data/faq.json";

export const COURSE = "data-engineering-zoomcamp";
export const DEFAULT_LIMIT = 5;

export interface FaqDocument {
  id: string;
  question: string;
  answer: string;
  section: string;
  course: string;
}

export interface SearchResult extends FaqDocument {
  score: number;
}

/** The committed FAQ snapshot, loaded once at module init. */
export const FAQ_DOCUMENTS = faqData as FaqDocument[];

/** Normalizes a caller-provided limit before it reaches the search index. */
export function clampLimit(value: unknown, fallback = DEFAULT_LIMIT): number {
  const limit = typeof value === "number" && Number.isFinite(value) ? value : fallback;
  return Math.max(1, Math.min(10, Math.floor(limit)));
}

/**
 * In-memory full-text index (same approach as Option 1). Built once per server
 * instance; no embeddings and no vector database.
 */
const index = new MiniSearch<FaqDocument>({
  idField: "id",
  fields: ["question", "answer", "section"],
  storeFields: ["question", "answer", "section", "course"],
  searchOptions: {
    boost: { question: 3, section: 2 },
    fuzzy: 0.2,
    prefix: true,
  },
});
index.addAll(FAQ_DOCUMENTS);

const byId = new Map(FAQ_DOCUMENTS.map((doc) => [doc.id, doc]));

/** Runs a keyword search against the FAQ index. Used by the agent's search tool. */
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
