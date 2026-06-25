import { CHAT_MODEL, MODEL_PROVIDER } from "@/lib/agent";
import { COURSE, FAQ_DOCUMENTS } from "@/lib/faq";

/** Health/readiness probe, mirroring the Cloudflare `/health` route. */
export function GET() {
  return Response.json({
    ok: true,
    course: COURSE,
    modelProvider: MODEL_PROVIDER,
    chatModel: CHAT_MODEL,
    search: "minisearch",
    documents: FAQ_DOCUMENTS.length,
  });
}
