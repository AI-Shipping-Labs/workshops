import { convertToModelMessages, type UIMessage } from "ai";
import { faqAgent } from "@/lib/agent";

// Allow streamed agent runs up to 30s on Vercel.
export const maxDuration = 30;

/**
 * The chat endpoint. It only adapts HTTP <-> the agent: parse the incoming UI
 * messages, run the agent (defined in lib/agent.ts), stream the result back.
 * No agent logic lives here.
 */
export async function POST(req: Request) {
  const { messages }: { messages: UIMessage[] } = await req.json();

  const result = await faqAgent.stream({
    messages: await convertToModelMessages(messages),
  });

  return result.toUIMessageStreamResponse();
}
