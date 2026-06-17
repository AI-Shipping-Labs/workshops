import {
  DEFAULT_CHAT_MODEL,
  DEFAULT_VECTORIZE_INDEX,
  EMBEDDING_MODEL,
} from "../../../packages/shared/src/index";
import { HttpError } from "./http";
import type { CloudflareApiResponse, Env } from "./schemas";

/**
 * Resolves the chat model configured for this Worker.
 * Used by `agent.ts` and `/health`.
 */
export function chatModel(env: Env): string {
  return env.CHAT_MODEL || DEFAULT_CHAT_MODEL;
}

/**
 * Resolves the embedding model configured for search.
 * Used by `search.ts` and `/health`.
 */
export function embeddingModel(env: Env): string {
  return env.EMBEDDING_MODEL || EMBEDDING_MODEL;
}

/**
 * Reports whether we are using deployed bindings or local REST transport.
 * Used by `/health` so local debugging shows the active execution mode.
 */
export function runtimeMode(env: Env): string {
  if (env.AI && env.FAQ_INDEX) {
    return "cloudflare-bindings";
  }
  if (env.LOCAL_CLOUDFLARE_REST === "true") {
    return "local-worker-real-cloudflare-rest";
  }
  return "unconfigured";
}

/**
 * Reads Vectorize index metadata for the health endpoint.
 * Used by `/health`; uses bindings when deployed and REST during local dev.
 */
export async function describeIndex(env: Env): Promise<unknown> {
  if (env.FAQ_INDEX) {
    return env.FAQ_INDEX.describe();
  }

  const config = cloudflareConfig(env);
  return cloudflareFetch<unknown>(
    env,
    `/accounts/${config.accountId}/vectorize/v2/indexes/${config.indexName}`,
    { method: "GET" },
  );
}

/**
 * Reads Vectorize index processing/count information.
 * Used by `/index-info` to confirm ingestion state.
 */
export async function indexInfo(env: Env): Promise<unknown> {
  if (env.FAQ_INDEX) {
    return env.FAQ_INDEX.describe();
  }

  const config = cloudflareConfig(env);
  return cloudflareFetch<unknown>(
    env,
    `/accounts/${config.accountId}/vectorize/v2/indexes/${config.indexName}/info`,
    { method: "GET" },
  );
}

/**
 * Runs a non-streaming Workers AI request.
 * Used by `search.ts` for embeddings; switches between binding and REST.
 */
export async function runAi<T>(env: Env, model: string, input: Record<string, unknown>): Promise<T> {
  if (env.AI) {
    return (await env.AI.run(model, input)) as T;
  }

  const config = cloudflareConfig(env);
  return cloudflareFetch<T>(env, `/accounts/${config.accountId}/ai/run/${model}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(input),
  });
}

/**
 * Runs a streaming Workers AI chat request.
 * Used by `agent.ts`; returns the raw SSE byte stream for `ai-stream.ts`.
 */
export async function streamAi(
  env: Env,
  model: string,
  input: Record<string, unknown>,
): Promise<ReadableStream<Uint8Array>> {
  if (env.AI) {
    const response = (await env.AI.run(model, { ...input, stream: true })) as unknown;
    return normalizeAiStream(response);
  }

  const config = cloudflareConfig(env);
  const path = `/accounts/${config.accountId}/ai/run/${model}`;
  const started = Date.now();
  const response = await fetch(`https://api.cloudflare.com/client/v4${path}`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${config.apiToken}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({ ...input, stream: true }),
  });

  logCloudflareCall("POST", path, config.accountId, response.status, started, true);

  if (!response.ok || !response.body) {
    const body = await response.text();
    throw new HttpError(`Cloudflare streaming API request failed: ${response.status} ${body}`, 502);
  }

  return response.body;
}

/**
 * Queries Vectorize with an embedding vector.
 * Used by `search.ts`; switches between native binding and REST query API.
 */
export async function queryVectorize(
  env: Env,
  vector: number[],
  limit: number,
): Promise<VectorizeMatches | { matches: Array<{ id?: string; score?: number; metadata?: unknown }> }> {
  if (env.FAQ_INDEX) {
    return env.FAQ_INDEX.query(vector, {
      topK: limit,
      returnMetadata: "all",
      returnValues: false,
    });
  }

  const config = cloudflareConfig(env);
  return cloudflareFetch(env, `/accounts/${config.accountId}/vectorize/v2/indexes/${config.indexName}/query`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      vector,
      topK: limit,
      returnMetadata: "all",
      returnValues: false,
    }),
  });
}

/**
 * Shared Cloudflare REST helper.
 * Used by local-dev implementations in this module for AI and Vectorize APIs.
 */
async function cloudflareFetch<T>(env: Env, path: string, init: RequestInit): Promise<T> {
  const config = cloudflareConfig(env);
  const started = Date.now();
  const response = await fetch(`https://api.cloudflare.com/client/v4${path}`, {
    ...init,
    headers: {
      authorization: `Bearer ${config.apiToken}`,
      ...init.headers,
    },
  });

  const body = (await response.json()) as CloudflareApiResponse<T>;
  logCloudflareCall(init.method ?? "GET", path, config.accountId, response.status, started);

  if (!response.ok || body.success === false || body.result === undefined) {
    throw new HttpError(`Cloudflare API request failed: ${response.status} ${JSON.stringify(body.errors ?? body)}`, 502);
  }

  return body.result;
}

/**
 * Extracts required REST credentials from Worker env.
 * Used only by local REST mode helpers in this module.
 */
function cloudflareConfig(env: Env): { accountId: string; apiToken: string; indexName: string } {
  if (!env.CLOUDFLARE_ACCOUNT_ID) {
    throw new HttpError("Missing CLOUDFLARE_ACCOUNT_ID for local Cloudflare REST mode.", 500);
  }
  if (!env.CLOUDFLARE_API_TOKEN) {
    throw new HttpError("Missing CLOUDFLARE_API_TOKEN for local Cloudflare REST mode.", 500);
  }

  return {
    accountId: env.CLOUDFLARE_ACCOUNT_ID,
    apiToken: env.CLOUDFLARE_API_TOKEN,
    indexName: env.VECTORIZE_INDEX_NAME || DEFAULT_VECTORIZE_INDEX,
  };
}

/**
 * Normalizes Workers AI binding streaming return values.
 * Used by `streamAi` because bindings may return either a stream or Response.
 */
function normalizeAiStream(response: unknown): ReadableStream<Uint8Array> {
  if (response instanceof ReadableStream) {
    return response;
  }
  if (response instanceof Response && response.body) {
    return response.body;
  }
  throw new HttpError("Workers AI streaming returned an unexpected response.", 502);
}

/**
 * Emits structured local-dev logs for real Cloudflare API calls.
 * Used by REST helpers to prove requests are going to Cloudflare, not mocks.
 */
function logCloudflareCall(
  method: string,
  path: string,
  accountId: string,
  status: number,
  started: number,
  streaming = false,
) {
  console.log(
    JSON.stringify({
      event: "cloudflare_api",
      method,
      path: path.replace(accountId, "<account>"),
      status,
      ms: Date.now() - started,
      streaming,
    }),
  );
}
