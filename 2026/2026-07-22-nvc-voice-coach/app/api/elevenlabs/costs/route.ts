import { NextResponse } from "next/server";

type ConversationSummary = { conversation_id: string };
type ConversationsPage = {
  conversations: ConversationSummary[];
  has_more: boolean;
  next_cursor?: string | null;
};
type ConversationDetails = {
  metadata?: {
    cost_fiat?: number | null;
  };
};

export const dynamic = "force-dynamic";

async function fetchAllConversationIds(apiKey: string, agentId: string) {
  const ids: string[] = [];
  let cursor: string | null = null;

  do {
    const url = new URL("https://api.elevenlabs.io/v1/convai/conversations");
    url.searchParams.set("agent_id", agentId);
    url.searchParams.set("page_size", "100");
    if (cursor) url.searchParams.set("cursor", cursor);

    const response = await fetch(url, {
      headers: { "xi-api-key": apiKey },
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`Conversation list returned ${response.status}`);

    const page = (await response.json()) as ConversationsPage;
    ids.push(...page.conversations.map((conversation) => conversation.conversation_id));
    cursor = page.has_more && page.next_cursor ? page.next_cursor : null;
  } while (cursor);

  return ids;
}

async function fetchCosts(apiKey: string, ids: string[]) {
  const costs: number[] = [];
  const batchSize = 8;

  for (let index = 0; index < ids.length; index += batchSize) {
    const batch = ids.slice(index, index + batchSize);
    const details = await Promise.all(batch.map(async (id) => {
      const response = await fetch(`https://api.elevenlabs.io/v1/convai/conversations/${id}`, {
        headers: { "xi-api-key": apiKey },
        cache: "no-store",
      });
      if (!response.ok) return null;
      return (await response.json()) as ConversationDetails;
    }));

    for (const detail of details) {
      const cost = detail?.metadata?.cost_fiat;
      if (typeof cost === "number" && Number.isFinite(cost)) costs.push(cost);
    }
  }

  return costs;
}

export async function GET() {
  const apiKey = process.env.ELEVENLABS_API_KEY;
  const agentId = process.env.ELEVENLABS_AGENT_ID;

  if (!apiKey || !agentId) {
    return NextResponse.json({ error: "ElevenLabs is not configured." }, { status: 500 });
  }

  try {
    const ids = await fetchAllConversationIds(apiKey, agentId);
    const costs = await fetchCosts(apiKey, ids);
    const totalUsd = costs.reduce((total, cost) => total + cost, 0);

    return NextResponse.json({
      totalUsd,
      conversationCount: ids.length,
      pricedConversationCount: costs.length,
      currency: "USD",
      scope: "retained_agent_history",
      updatedAt: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Could not calculate ElevenLabs conversation cost", error);
    return NextResponse.json({ error: "Could not load spending." }, { status: 502 });
  }
}
