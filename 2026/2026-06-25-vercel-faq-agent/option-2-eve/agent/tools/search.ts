import { defineTool } from "eve/tools";
import { z } from "zod";
import { DEFAULT_LIMIT, search } from "@/lib/faq-search";

// The filename is the tool name, so the model sees this as `search`.
export default defineTool({
  description: "Search the DataTalks.Club course FAQ using keyword full-text search.",
  inputSchema: z.object({
    query: z.string().describe("A concise rewritten search query for the FAQ."),
    limit: z
      .number()
      .optional()
      .describe("Maximum number of FAQ entries to return. Use 5 unless more context is clearly needed."),
  }),
  async execute({ query, limit }) {
    return search(query, limit ?? DEFAULT_LIMIT);
  },
});
