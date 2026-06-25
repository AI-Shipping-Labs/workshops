// Downloads the DataTalks.Club FAQ, filters it to one course, and writes
// data/faq.json. This is the Vercel analog of the Cloudflare "ingestion" step:
// instead of embedding documents and upserting them into a vector index, we
// just snapshot the source data so MiniSearch can index it at runtime.
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const FAQ_URL = "https://datatalks.club/faq/json/data-engineering-zoomcamp.json";
const COURSE = "data-engineering-zoomcamp";

const here = dirname(fileURLToPath(import.meta.url));
const outPath = join(here, "..", "data", "faq.json");

/** Computes a stable id for one FAQ document so reruns keep the same ids. */
function stableId(doc, index) {
  const input = `${doc.course}:${doc.section}:${doc.question}:${index}`;
  let hash = 2166136261;
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return `faq-${(hash >>> 0).toString(16)}`;
}

const response = await fetch(FAQ_URL, { headers: { accept: "application/json" } });
if (!response.ok) {
  throw new Error(`Failed to fetch FAQ: ${response.status} ${response.statusText}`);
}

const all = await response.json();
const docs = all
  .filter((doc) => doc.course === COURSE)
  .map((doc, index) => ({
    id: stableId(doc, index),
    question: doc.question,
    answer: doc.answer,
    section: doc.section,
    course: doc.course,
  }));

await mkdir(dirname(outPath), { recursive: true });
await writeFile(outPath, JSON.stringify(docs, null, 2) + "\n", "utf8");

console.log(`Wrote ${docs.length} FAQ documents for "${COURSE}" to data/faq.json`);
