import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  const apiKey = process.env.ELEVENLABS_API_KEY;
  const agentId = process.env.ELEVENLABS_AGENT_ID;

  if (!apiKey || !agentId) {
    return NextResponse.json(
      { error: "ElevenLabs is not configured on the server." },
      { status: 500 },
    );
  }

  const url = new URL("https://api.elevenlabs.io/v1/convai/conversation/get-signed-url");
  url.searchParams.set("agent_id", agentId);

  const response = await fetch(url, {
    headers: { "xi-api-key": apiKey },
    cache: "no-store",
  });

  if (!response.ok) {
    const detail = await response.text();
    console.error("ElevenLabs signed URL request failed", response.status, detail);
    const status = response.status === 429 ? 429 : 502;
    const error = response.status === 429
      ? "ElevenLabs is at its current conversation limit. Please try again shortly."
      : "Could not start a private voice session.";
    return NextResponse.json({ error }, { status });
  }

  const { signed_url: signedUrl } = (await response.json()) as { signed_url: string };
  return NextResponse.json({ signedUrl });
}
