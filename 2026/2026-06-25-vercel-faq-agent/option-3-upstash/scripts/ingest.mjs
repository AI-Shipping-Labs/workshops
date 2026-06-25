// Ingestion: read the committed FAQ snapshot and upsert it into Upstash Vector.
// We send raw text as `data`, so Upstash embeds it server-side with the index's
// embedding model (BAAI/bge-base-en-v1.5) — no embedding step in our code.
//
// This is the Option 3 replacement for Option 1/2's `fetch-faq` step. Run it
// once (or whenever the FAQ changes); the deployed agent only *queries* the index.
//
// Usage: npm run ingest   (reads UPSTASH_VECTOR_REST_URL/TOKEN from .env.local)
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { Index } from "@upstash/vector";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const BATCH_SIZE = 100;

// Minimal .env.local loader so `npm run ingest` works without extra flags.
loadEnvLocal(join(root, ".env.local"));

const url = process.env.UPSTASH_VECTOR_REST_URL;
const token = process.env.UPSTASH_VECTOR_REST_TOKEN;
if (!url || !token) {
  throw new Error(
    "Missing UPSTASH_VECTOR_REST_URL / UPSTASH_VECTOR_REST_TOKEN. Add them to .env.local (see .env.example).",
  );
}

const index = new Index({ url, token });

const docs = JSON.parse(readFileSync(join(root, "data", "faq.json"), "utf8"));
console.log(`Loaded ${docs.length} FAQ documents.`);

let upserted = 0;
for (let start = 0; start < docs.length; start += BATCH_SIZE) {
  const batch = docs.slice(start, start + BATCH_SIZE).map((doc) => ({
    id: doc.id,
    // The text Upstash embeds. Querying embeds the user's question the same way.
    data: `${doc.question} ${doc.answer}`,
    metadata: {
      id: doc.id,
      question: doc.question,
      answer: doc.answer,
      section: doc.section,
      course: doc.course,
    },
  }));

  await index.upsert(batch);
  upserted += batch.length;
  console.log(`Upserted ${upserted} / ${docs.length}.`);
}

console.log("Done. Upstash indexes asynchronously; wait a few seconds before querying.");

/** Loads KEY=value lines from a .env file into process.env (no dependency). */
function loadEnvLocal(path) {
  if (!existsSync(path)) return;
  for (const line of readFileSync(path, "utf8").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    const value = trimmed.slice(eq + 1).trim().replace(/^["']|["']$/g, "");
    if (process.env[key] === undefined) process.env[key] = value;
  }
}
