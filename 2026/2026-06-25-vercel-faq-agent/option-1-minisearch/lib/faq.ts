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
