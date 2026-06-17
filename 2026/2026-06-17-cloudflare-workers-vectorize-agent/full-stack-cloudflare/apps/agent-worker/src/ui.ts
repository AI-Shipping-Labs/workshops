import homeHtml from "./index.html";

/**
 * Renders the small browser UI served from `/`.
 * Used by `app.ts`; the embedded script calls `/ask/stream`.
 */
export function renderHome(): string {
  return homeHtml;
}
