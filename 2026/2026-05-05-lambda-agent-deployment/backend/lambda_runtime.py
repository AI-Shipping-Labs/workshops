import asyncio
import base64
import json
import mimetypes
import os
import posixpath
import queue
import threading
import traceback
from pathlib import Path
from urllib.parse import unquote

import requests
from dotenv import load_dotenv
from openai import AsyncOpenAI

from backend.agent import run_agent
from backend.renderer import BaseRenderer, CollectingRenderer

load_dotenv()

RUNTIME_API = os.environ.get("AWS_LAMBDA_RUNTIME_API")
APP_DIR = Path(__file__).parent
PROJECT_DIR = APP_DIR.parent
STATIC_DIR = PROJECT_DIR / "static"
if not STATIC_DIR.is_dir() and (PROJECT_DIR / "frontend" / "dist").is_dir():
    STATIC_DIR = PROJECT_DIR / "frontend" / "dist"
NULL_DELIMITER = b"\x00" * 8


class SyncSSEQueueRenderer(BaseRenderer):
    def __init__(self, events: queue.Queue):
        self.events = events

    async def _emit(self, event_type: str, payload: dict):
        data = json.dumps(payload, default=str)
        self.events.put(f"event: {event_type}\ndata: {data}\n\n".encode())

    async def handle_status(self, payload):
        await self._emit("status", payload)

    async def handle_iteration(self, payload):
        await self._emit("iteration", payload)

    async def handle_tool_call(self, payload):
        await self._emit("tool_call", payload)

    async def handle_tool_result(self, payload):
        await self._emit("tool_result", {
            "name": payload["name"],
            "result": payload["result"],
        })

    async def handle_token(self, payload):
        await self._emit("token", payload)

    async def handle_done(self, payload):
        await self._emit("done", payload)


def response_metadata(status_code: int, headers: dict[str, str]) -> bytes:
    return json.dumps({
        "statusCode": status_code,
        "headers": headers,
    }, separators=(",", ":")).encode()


def stream_response(status_code: int, headers: dict[str, str], chunks):
    yield response_metadata(status_code, headers)
    yield NULL_DELIMITER
    yield from chunks


def json_response(status_code: int, payload: dict):
    body = json.dumps(payload, default=str).encode()
    return stream_response(
        status_code,
        {"content-type": "application/json"},
        [body],
    )


def text_response(status_code: int, text: str):
    return stream_response(
        status_code,
        {"content-type": "text/plain; charset=utf-8"},
        [text.encode()],
    )


def event_body(event: dict) -> bytes:
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        return base64.b64decode(body)
    return body.encode()


def event_path(event: dict) -> str:
    return event.get("rawPath") or event.get("path") or "/"


def event_method(event: dict) -> str:
    http = event.get("requestContext", {}).get("http", {})
    return (http.get("method") or event.get("httpMethod") or "GET").upper()


def static_file_for_path(path: str) -> Path | None:
    cleaned = posixpath.normpath(unquote(path)).lstrip("/")
    if cleaned in {"", "."}:
        cleaned = "index.html"

    candidate = (STATIC_DIR / cleaned).resolve()
    static_root = STATIC_DIR.resolve()
    if static_root != candidate and static_root not in candidate.parents:
        return None
    if candidate.is_file():
        return candidate
    return None


def static_response(path: str):
    file_path = static_file_for_path(path)
    if file_path is None:
        return text_response(404, "Not found")

    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return stream_response(
        200,
        {
            "content-type": content_type,
            "cache-control": "no-cache" if file_path.name == "index.html" else "public, max-age=31536000, immutable",
        },
        [file_path.read_bytes()],
    )


def ask_response(event: dict):
    try:
        payload = json.loads(event_body(event) or b"{}")
        question = payload["question"].strip()
        if not question:
            return json_response(422, {"detail": "question is required"})
    except (KeyError, TypeError, json.JSONDecodeError):
        return json_response(400, {"detail": "Expected JSON body with a question field"})

    renderer = CollectingRenderer()
    asyncio.run(run_agent(AsyncOpenAI(), question, renderer))
    return json_response(200, {
        "answer": renderer.answer,
        "tool_calls": renderer.tool_calls,
    })


def sse_chunks(question: str):
    events: queue.Queue[bytes | None] = queue.Queue()

    def produce():
        try:
            renderer = SyncSSEQueueRenderer(events)
            asyncio.run(run_agent(AsyncOpenAI(), question, renderer))
        except Exception as exc:
            events.put(
                f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n".encode()
            )
        finally:
            events.put(None)

    thread = threading.Thread(target=produce, daemon=True)
    thread.start()

    while True:
        item = events.get()
        if item is None:
            break
        yield item

    thread.join()


def ask_stream_response(event: dict):
    try:
        payload = json.loads(event_body(event) or b"{}")
        question = payload["question"].strip()
        if not question:
            return json_response(422, {"detail": "question is required"})
    except (KeyError, TypeError, json.JSONDecodeError):
        return json_response(400, {"detail": "Expected JSON body with a question field"})

    return stream_response(
        200,
        {
            "content-type": "text/event-stream; charset=utf-8",
            "cache-control": "no-cache",
            "connection": "keep-alive",
        },
        sse_chunks(question),
    )


def route(event: dict):
    method = event_method(event)
    path = event_path(event)

    if method == "GET" and path == "/health":
        return json_response(200, {"status": "ok"})
    if method == "POST" and path == "/ask":
        return ask_response(event)
    if method == "POST" and path == "/ask/stream":
        return ask_stream_response(event)
    if method == "GET":
        return static_response(path)
    return text_response(405, "Method not allowed")


def next_invocation():
    response = requests.get(
        f"http://{RUNTIME_API}/2018-06-01/runtime/invocation/next",
        timeout=None,
    )
    response.raise_for_status()
    return response.headers["Lambda-Runtime-Aws-Request-Id"], response.json()


def post_response(request_id: str, body_iter):
    response = requests.post(
        f"http://{RUNTIME_API}/2018-06-01/runtime/invocation/{request_id}/response",
        data=body_iter,
        headers={
            "Lambda-Runtime-Function-Response-Mode": "streaming",
            "Transfer-Encoding": "chunked",
            "Content-Type": "application/vnd.awslambda.http-integration-response",
        },
        timeout=None,
    )
    response.raise_for_status()


def post_error(request_id: str, exc: Exception):
    requests.post(
        f"http://{RUNTIME_API}/2018-06-01/runtime/invocation/{request_id}/error",
        json={
            "errorMessage": str(exc),
            "errorType": type(exc).__name__,
            "stackTrace": traceback.format_exc().splitlines(),
        },
        timeout=None,
    ).raise_for_status()


def main():
    if not RUNTIME_API:
        raise RuntimeError("AWS_LAMBDA_RUNTIME_API is not set")

    while True:
        request_id, event = next_invocation()
        try:
            post_response(request_id, route(event))
        except Exception as exc:
            post_error(request_id, exc)


if __name__ == "__main__":
    main()
