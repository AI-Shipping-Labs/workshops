import json
from asyncio import create_task
from urllib.parse import urlparse

from js import TransformStream
from pyodide.ffi import create_proxy
from workers import Response, WorkerEntrypoint, wait_until

from agent import run_agent
from config import COURSE, DEFAULT_CHAT_MODEL, DEFAULT_EMBEDDING_MODEL, DEFAULT_LIMIT
from interop import env_value, to_py
from renderer import SseStreamRenderer
from responses import HttpError, empty_cors_response, error_response, html_response, json_response
from search import clamp_limit, search
from ui import render_home


class Default(WorkerEntrypoint):
    """Cloudflare Python Worker entrypoint used by pywrangler and deploy."""

    async def fetch(self, request):
        """Handles CORS preflight and delegates normal requests to the router."""

        if request.method == "OPTIONS":
            return empty_cors_response()

        try:
            return await route_request(self.env, request)
        except BaseException as error:
            return error_response(error)


async def route_request(env, request) -> Response:
    """Routes UI, health, search, and agent requests by path and method."""

    path = urlparse(str(request.url)).path
    method = str(request.method)

    if path == "/" and method == "GET":
        return html_response(render_home())

    if path == "/health" and method == "GET":
        return json_response(await health(env))

    if path == "/index-info" and method == "GET":
        return json_response(await index_info(env))

    if path == "/search" and method == "POST":
        body = await parse_ask_request(request)
        results = await search(env, {"query": body["question"], "limit": body["limit"]}, body["limit"])
        return json_response({"query": body["question"], "results": results})

    if path == "/ask/stream" and method == "POST":
        body = await parse_ask_request(request)
        return stream_ask(env, body)

    return json_response({"error": "Not found"}, 404)


def stream_ask(env, body: dict) -> Response:
    """Starts `/ask/stream` as a real streaming SSE response."""

    transform = TransformStream.new()
    writer = transform.writable.getWriter()
    renderer = SseStreamRenderer(writer)

    async def run_stream():
        try:
            await run_agent(env, body["question"], renderer, body["limit"], body["maxOutputTokens"])
        except BaseException as error:
            try:
                await renderer.emit("error", {"error": str(error) or "Unknown error"})
            except BaseException:
                pass
        finally:
            await renderer.close()

    wait_until(create_proxy(create_task(run_stream())))

    return Response(
        transform.readable,
        headers={
            "content-type": "text/event-stream; charset=utf-8",
            "cache-control": "no-cache, no-transform",
            "connection": "keep-alive",
            "access-control-allow-origin": "*",
        },
    )


async def parse_ask_request(request) -> dict:
    """Parses JSON bodies for `/search` and `/ask/stream`."""

    body = json.loads(str(await request.text()))
    question = body.get("question") if isinstance(body, dict) else None
    if not isinstance(question, str) or not question.strip():
        raise HttpError("`question` must be a non-empty string.", 400)

    return {
        "question": question.strip(),
        "limit": clamp_limit(body.get("limit") if isinstance(body, dict) else None, DEFAULT_LIMIT),
        "maxOutputTokens": body.get("maxOutputTokens") if isinstance(body, dict) else None,
    }


async def health(env) -> dict:
    """Builds a runtime diagnostic response for `/health`."""

    return {
        "ok": True,
        "course": COURSE,
        "runtime": "python-workers-beta",
        "embeddingModel": env_value(env, "EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        "chatModel": env_value(env, "CHAT_MODEL", DEFAULT_CHAT_MODEL),
        "index": await describe_index(env),
    }


async def index_info(env) -> dict:
    """Returns Vectorize index statistics for `/index-info`."""

    return await describe_index(env)


async def describe_index(env) -> dict:
    """Calls the Vectorize describe binding and normalizes the result."""

    return to_py(await env.FAQ_INDEX.describe())
