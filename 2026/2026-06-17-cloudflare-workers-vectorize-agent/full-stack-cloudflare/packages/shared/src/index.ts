export const FAQ_URL = "https://datatalks.club/faq/json/data-engineering-zoomcamp.json";
export const COURSE = "data-engineering-zoomcamp";
export const EMBEDDING_MODEL = "@cf/baai/bge-base-en-v1.5";
export const EMBEDDING_DIMENSIONS = 768;
export const DEFAULT_CHAT_MODEL = "@cf/zai-org/glm-4.7-flash";
export const DEFAULT_VECTORIZE_INDEX = "faq-index";
export const DEFAULT_LIMIT = 5;

export interface FaqDocument {
  question: string;
  answer: string;
  section: string;
  course: string;
}

export interface FaqMetadata {
  id: string;
  question: string;
  answer: string;
  section: string;
  course: string;
  source: string;
}

export interface SearchResult extends FaqMetadata {
  score: number;
}

export interface EmbeddingResponse {
  shape?: number[];
  data?: number[][];
}

/**
 * Downloads the source FAQ JSON and filters it to this course.
 * Used by local ingestion and by any future source-data diagnostics.
 */
export async function fetchFaqDocuments(): Promise<FaqDocument[]> {
  const response = await fetch(FAQ_URL, {
    headers: { accept: "application/json" },
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch FAQ: ${response.status} ${response.statusText}`);
  }

  const documents = (await response.json()) as FaqDocument[];
  return documents.filter((doc) => doc.course === COURSE);
}

/**
 * Formats one FAQ entry into the text embedded for vector search.
 * Used by ingestion before calling the embedding model.
 */
export function documentText(doc: FaqDocument): string {
  return [`Section: ${doc.section}`, `Question: ${doc.question}`, `Answer: ${doc.answer}`].join("\n");
}

/**
 * Produces a stable Vectorize ID for one FAQ document.
 * Used by ingestion so repeated upserts replace the same records.
 */
export function stableDocumentId(doc: FaqDocument, index: number): string {
  const input = `${doc.course}:${doc.section}:${doc.question}:${index}`;
  let hash = 2166136261;

  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }

  return `faq-${(hash >>> 0).toString(16)}`;
}

/**
 * Keeps embedding input under a conservative length.
 * Used by ingestion and query embedding before calling Workers AI.
 */
export function truncateForEmbedding(text: string): string {
  return text.length > 1800 ? text.slice(0, 1800) : text;
}

/**
 * Builds the metadata stored next to each vector.
 * Used by ingestion; returned later by Vectorize search results.
 */
export function metadataForDocument(doc: FaqDocument, index: number): FaqMetadata {
  const id = stableDocumentId(doc, index);
  return {
    id,
    question: doc.question,
    answer: doc.answer,
    section: doc.section,
    course: doc.course,
    source: FAQ_URL,
  };
}

/**
 * Formats search results for an answer-generation prompt.
 * Kept for prompt reuse; useful when building non-tool RAG prompts.
 */
export function formatResultsForPrompt(results: SearchResult[]): string {
  return results
    .map((result, index) =>
      [
        `[${result.id}] score=${result.score.toFixed(4)} rank=${index + 1}`,
        `section: ${result.section}`,
        `question: ${result.question}`,
        `answer: ${result.answer}`,
      ].join("\n"),
    )
    .join("\n\n");
}

/**
 * Formats one result in the source-list style expected by the UI/API.
 * Used by `agent.ts` when building the `/ask` JSON response.
 */
export function formatSource(result: SearchResult): string {
  return `[${result.id}] ${result.section} > ${result.question}`;
}

/**
 * Normalizes caller-provided search limits before they reach Vectorize.
 * Used by the Worker request parser and search tool argument parser.
 */
export function clampLimit(value: unknown, fallback = DEFAULT_LIMIT): number {
  const limit = typeof value === "number" ? value : fallback;
  return Math.max(1, Math.min(10, Math.floor(limit)));
}
