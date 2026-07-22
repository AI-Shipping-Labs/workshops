import { NextRequest, NextResponse } from "next/server";

type Params = { params: Promise<{ id: string }> };

function isConversationId(value: string) {
  return /^conv_[A-Za-z0-9_-]+$/.test(value);
}

export async function DELETE(_request: NextRequest, { params }: Params) {
  const { id } = await params;
  const apiKey = process.env.ELEVENLABS_API_KEY;

  if (!apiKey) {
    return NextResponse.json({ error: "ElevenLabs is not configured." }, { status: 500 });
  }
  if (!isConversationId(id)) {
    return NextResponse.json({ error: "Invalid conversation ID." }, { status: 400 });
  }

  const response = await fetch(`https://api.elevenlabs.io/v1/convai/conversations/${id}`, {
    method: "DELETE",
    headers: { "xi-api-key": apiKey },
  });

  if (!response.ok && response.status !== 404) {
    const detail = await response.text();
    console.error("ElevenLabs conversation deletion failed", response.status, detail);
    return NextResponse.json({ error: "Could not delete this session yet." }, { status: 502 });
  }

  return NextResponse.json({ deleted: true });
}
