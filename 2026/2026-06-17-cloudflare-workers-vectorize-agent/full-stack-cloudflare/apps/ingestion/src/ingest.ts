import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  DEFAULT_VECTORIZE_INDEX,
  EMBEDDING_MODEL,
  documentText,
  fetchFaqDocuments,
  metadataForDocument,
  truncateForEmbedding,
  type EmbeddingResponse,
  type FaqMetadata,
} from "../../../packages/shared/src/index";

const EMBED_BATCH_SIZE = 50;
const VECTORIZE_BATCH_SIZE = 5000;

interface Config {
  accountId: string;
  apiToken: string;
  indexName: string;
  embeddingModel: string;
}

interface VectorizeVector {
  id: string;
  values: number[];
  metadata: FaqMetadata;
}

loadDotEnvFiles();

const config = readConfig();
const documents = await fetchFaqDocuments();
console.log(`Fetched ${documents.length} FAQ documents.`);

const vectors: VectorizeVector[] = [];

for (let start = 0; start < documents.length; start += EMBED_BATCH_SIZE) {
  const batch = documents.slice(start, start + EMBED_BATCH_SIZE);
  const texts = batch.map((doc) => truncateForEmbedding(documentText(doc)));
  const embeddings = await embedTexts(config, texts);

  for (let i = 0; i < batch.length; i++) {
    const metadata = metadataForDocument(batch[i], start + i);
    vectors.push({
      id: metadata.id,
      values: embeddings[i],
      metadata,
    });
  }

  console.log(`Embedded ${Math.min(start + batch.length, documents.length)} / ${documents.length}.`);
}

for (let start = 0; start < vectors.length; start += VECTORIZE_BATCH_SIZE) {
  const batch = vectors.slice(start, start + VECTORIZE_BATCH_SIZE);
  const result = await upsertVectors(config, batch);
  console.log(
    `Upserted ${Math.min(start + batch.length, vectors.length)} / ${vectors.length}. Mutation: ${result.result?.mutationId ?? "unknown"}`,
  );
}

console.log("Done. Vectorize mutations are asynchronous; wait a few seconds before querying.");

/**
 * Calls Workers AI to embed a batch of FAQ document texts.
 * Used by the top-level ingestion loop before building Vectorize records.
 */
async function embedTexts(config: Config, texts: string[]): Promise<number[][]> {
  const response = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${config.accountId}/ai/run/${config.embeddingModel}`,
    {
      method: "POST",
      headers: {
        authorization: `Bearer ${config.apiToken}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({ text: texts }),
    },
  );

  const body = (await response.json()) as { result?: EmbeddingResponse; errors?: unknown };

  if (!response.ok || !body.result?.data || body.result.data.length !== texts.length) {
    throw new Error(`Workers AI embedding failed: ${response.status} ${JSON.stringify(body.errors ?? body)}`);
  }

  return body.result.data;
}

/**
 * Sends one NDJSON batch of vectors to Cloudflare Vectorize.
 * Used by the top-level ingestion loop after all embeddings are prepared.
 */
async function upsertVectors(config: Config, vectors: VectorizeVector[]) {
  const ndjson = vectors.map((vector) => JSON.stringify(vector)).join("\n");
  const response = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${config.accountId}/vectorize/v2/indexes/${config.indexName}/upsert`,
    {
      method: "POST",
      headers: {
        authorization: `Bearer ${config.apiToken}`,
        "content-type": "application/x-ndjson",
      },
      body: ndjson,
    },
  );

  const body = (await response.json()) as {
    success?: boolean;
    result?: { mutationId?: string };
    errors?: unknown;
  };

  if (!response.ok || !body.success) {
    throw new Error(`Vectorize upsert failed: ${response.status} ${JSON.stringify(body.errors ?? body)}`);
  }

  return body;
}

/**
 * Reads Cloudflare and model settings from environment variables.
 * Used once at script startup after `.env` files are loaded.
 */
function readConfig(): Config {
  return {
    accountId: requireEnv("CLOUDFLARE_ACCOUNT_ID"),
    apiToken: requireEnv("CLOUDFLARE_API_TOKEN"),
    indexName: process.env.VECTORIZE_INDEX_NAME || DEFAULT_VECTORIZE_INDEX,
    embeddingModel: process.env.EMBEDDING_MODEL || EMBEDDING_MODEL,
  };
}

/**
 * Reads one required environment variable or fails clearly.
 * Used by `readConfig` for credentials that cannot have defaults.
 */
function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

/**
 * Loads app-local and root `.env` files for the ingestion script.
 * Used at script startup; root `.env` wins over app-local placeholders.
 */
function loadDotEnvFiles() {
  const appRoot = dirname(dirname(fileURLToPath(import.meta.url)));
  const repoRoot = join(appRoot, "../../..");

  loadDotEnv(join(appRoot, ".env"), false);
  loadDotEnv(join(repoRoot, ".env"), true);
}

/**
 * Minimal `.env` parser for KEY=value lines.
 * Used by `loadDotEnvFiles`; avoids adding a runtime dotenv dependency.
 */
function loadDotEnv(path: string, override: boolean) {
  if (!existsSync(path)) {
    return;
  }

  const contents = readFileSync(path, "utf8");
  for (const line of contents.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }

    const separator = trimmed.indexOf("=");
    if (separator === -1) {
      continue;
    }

    const key = trimmed.slice(0, separator).trim();
    const value = trimmed.slice(separator + 1).trim().replace(/^["']|["']$/g, "");
    if (override || process.env[key] === undefined) {
      process.env[key] = value;
    }
  }
}
