"""
FastAPI backend for the FAQ agent (option 4 — Python).

This is the equivalent of option 1's `app/api/chat/route.ts`: a thin HTTP layer
that adapts requests to the agent and streams the result back. The agent logic
lives in agent.py, search in search.py, and event delivery in renderer.py.

The frontend POSTs the conversation to `/chat` and reads back a Server-Sent
Events stream (`event: <type>` + `data: <json>`); event types are token,
tool_call, tool_result, status, iteration, done — see renderer.py.
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from pydantic import BaseModel

from agent import run_agent
from renderer import SSEQueueRenderer
from search import search

load_dotenv()

# The built Next.js frontend (next build → out/, copied here). Present in prod;
# absent during local `next dev` (which serves the UI itself and proxies the API).
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="FAQ Agent — Python backend")

# Allow the Next.js dev server (and any local origin) to call us in the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    """Build the OpenAI client lazily, so a missing key fails only /chat — not
    module import (which would 500 even the static UI and /health)."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            base_url=os.environ.get("OPENAI_BASE_URL") or None,
        )
    return _client


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]


@app.get("/health")
async def health():
    return {"status": "ok", "model": os.environ.get("CHAT_MODEL", "gpt-5.4-mini")}


@app.get("/search")
async def search_endpoint(q: str, limit: int = 5):
    """Debug endpoint: hit the search index directly without the model."""
    return {"query": q, "results": search(q, limit)}


@app.post("/chat")
async def chat(req: ChatRequest):
    """Run the agent and stream SSE events back to the client."""
    messages = [m.model_dump() for m in req.messages]
    queue: asyncio.Queue = asyncio.Queue()
    renderer = SSEQueueRenderer(queue)

    async def produce():
        try:
            await run_agent(get_client(), messages, renderer)
        finally:
            await queue.put(None)  # sentinel: stream finished

    async def event_stream():
        task = asyncio.create_task(produce())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Serve the built frontend for any non-API path, like the Lambda reference serves
# its static dist. Mounted last so the API routes above win. `html=True` serves
# index.html at "/". Skipped if the build isn't present (e.g. local `next dev`).
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
