import { NextResponse } from "next/server";

type ElevenVoice = {
  voice_id: string;
  name: string;
  category?: string;
  preview_url?: string | null;
  labels?: Record<string, string>;
};

export const dynamic = "force-dynamic";

export async function GET() {
  const apiKey = process.env.ELEVENLABS_API_KEY;
  const agentId = process.env.ELEVENLABS_AGENT_ID;

  if (!apiKey || !agentId) {
    return NextResponse.json({ error: "ElevenLabs is not configured." }, { status: 500 });
  }

  const headers = { "xi-api-key": apiKey };
  const voicesUrl = new URL("https://api.elevenlabs.io/v2/voices");
  voicesUrl.searchParams.set("page_size", "100");
  voicesUrl.searchParams.set("sort", "name");
  voicesUrl.searchParams.set("sort_direction", "asc");
  voicesUrl.searchParams.set("include_total_count", "false");

  const [voicesResponse, agentResponse] = await Promise.all([
    fetch(voicesUrl, { headers, cache: "no-store" }),
    fetch(`https://api.elevenlabs.io/v1/convai/agents/${agentId}`, {
      headers,
      cache: "no-store",
    }),
  ]);

  if (!voicesResponse.ok || !agentResponse.ok) {
    console.error("Could not load ElevenLabs voices", voicesResponse.status, agentResponse.status);
    return NextResponse.json({ error: "Could not load voices." }, { status: 502 });
  }

  const voicesBody = (await voicesResponse.json()) as { voices: ElevenVoice[] };
  const agent = (await agentResponse.json()) as { conversation_config?: { tts?: { voice_id?: string } } };
  const defaultVoiceId = agent.conversation_config?.tts?.voice_id ?? "";

  const voices = voicesBody.voices
    .filter((voice) => voice.labels?.language === "en" || voice.voice_id === defaultVoiceId)
    .map((voice) => ({
      voiceId: voice.voice_id,
      name: voice.name,
      category: voice.category ?? "voice",
      previewUrl: voice.preview_url ?? null,
      accent: voice.labels?.accent ?? null,
      gender: voice.labels?.gender ?? null,
      description: voice.labels?.descriptive ?? voice.labels?.use_case ?? null,
    }));

  return NextResponse.json({ voices, defaultVoiceId });
}
