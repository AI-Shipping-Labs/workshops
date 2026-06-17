import { COURSE, DEFAULT_LIMIT, clampLimit } from "../../../packages/shared/src/index";
import { clampMaxOutputTokens, runAgent } from "./agent";
import { chatModel, describeIndex, embeddingModel, indexInfo, runtimeMode } from "./cloudflare";
import { emptyCorsResponse, htmlResponse, HttpError, jsonResponse } from "./http";
import { SseRenderer } from "./renderer";
import { search } from "./search";
import type { AskRequest, Env } from "./schemas";
import { renderHome } from "./ui";

export default {
  /**
   * Worker entrypoint used by Wrangler and Cloudflare.
   * It only handles CORS preflight and delegates real routing to `routeRequest`.
   */
  async fetch(request, env, ctx): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return emptyCorsResponse();
    }

    try {
      return await routeRequest(request, env, ctx, url);
    } catch (error) {
      return errorResponse(error);
    }
  },
} satisfies ExportedHandler<Env>;

/**
 * Central HTTP router for the Worker.
 * Called by `fetch`; it dispatches to UI, health, search, and agent handlers.
 */
async function routeRequest(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
  url: URL,
): Promise<Response> {
  if (url.pathname === "/" && request.method === "GET") {
    return htmlResponse(renderHome());
  }

  if (url.pathname === "/health" && request.method === "GET") {
    return jsonResponse(await health(env));
  }

  if (url.pathname === "/index-info" && request.method === "GET") {
    return jsonResponse(await indexInfo(env));
  }

  if (url.pathname === "/search" && request.method === "POST") {
    const { question, limit } = await parseAskRequest(request);
    return jsonResponse({ query: question, results: await search(env, { query: question, limit }, limit) });
  }

  if (url.pathname === "/ask/stream" && request.method === "POST") {
    const { maxOutputTokens, question, limit } = await parseAskRequest(request);
    return streamAsk(env, ctx, question, limit, maxOutputTokens);
  }

  return jsonResponse({ error: "Not found" }, 404);
}

/**
 * Builds the `/health` response.
 * Used by `routeRequest` to verify runtime mode, models, and Vectorize access.
 */
async function health(env: Env) {
  return {
    ok: true,
    course: COURSE,
    mode: runtimeMode(env),
    embeddingModel: embeddingModel(env),
    chatModel: chatModel(env),
    index: await describeIndex(env),
  };
}

/**
 * Starts the SSE response for `/ask/stream`.
 * Used by `routeRequest`; connects `runAgent` to `SseRenderer`.
 */
function streamAsk(
  env: Env,
  ctx: ExecutionContext,
  question: string,
  limit: number,
  maxOutputTokens: number,
): Response {
  const stream = new ReadableStream<Uint8Array>({
    /**
     * Starts the background agent run that writes SSE chunks.
     * Called by the platform when `/ask/stream` begins reading the response.
     */
    start(controller) {
      const renderer = new SseRenderer(controller);
      ctx.waitUntil(
        runAgent(env, question, renderer, limit, maxOutputTokens)
          .catch((error) => {
            const message = error instanceof Error ? error.message : "Unknown error";
            renderer.handleEvent("error", { error: message });
          })
          .finally(() => renderer.close()),
      );
    },
  });

  return new Response(stream, {
    headers: {
      "content-type": "text/event-stream; charset=utf-8",
      "cache-control": "no-cache",
      connection: "keep-alive",
      "access-control-allow-origin": "*",
    },
  });
}

/**
 * Parses and validates JSON bodies for `/search` and `/ask/stream`.
 * Used by `routeRequest`; trims the question and clamps per-request options.
 */
async function parseAskRequest(
  request: Request,
): Promise<{ maxOutputTokens: number; question: string; limit: number }> {
  let body: AskRequest;
  try {
    body = (await request.json()) as AskRequest;
  } catch {
    throw new HttpError("Request body must be JSON.", 400);
  }

  if (typeof body.question !== "string" || body.question.trim().length === 0) {
    throw new HttpError("`question` must be a non-empty string.", 400);
  }

  return {
    question: body.question.trim(),
    limit: clampLimit(body.limit, DEFAULT_LIMIT),
    maxOutputTokens: clampMaxOutputTokens(body.maxOutputTokens),
  };
}

/**
 * Converts thrown errors to JSON HTTP responses.
 * Used by the top-level `fetch` catch block.
 */
function errorResponse(error: unknown): Response {
  const message = error instanceof Error ? error.message : "Unknown error";
  const status = error instanceof HttpError ? error.status : 500;
  return jsonResponse({ error: message }, status);
}
