"""FastAPI app exposing the FAQ agent.

Minimal JSON API: on startup it opens the (Turso-backed) vector index and an
OpenAI client, then answers questions at POST /ask.
"""

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from openai import AsyncOpenAI

from agent import run_agent
from renderer import CollectingRenderer
from schemas import AskRequest, AskResponse, ToolCall
from search import init_index

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_index()  # opens the vector index (syncs down from Turso when configured)
    app.state.openai_client = AsyncOpenAI()
    yield


app = FastAPI(title="FAQ Agent", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    renderer = CollectingRenderer()
    await run_agent(app.state.openai_client, req.question, renderer)
    return AskResponse(
        answer=renderer.answer,
        tool_calls=[ToolCall(**tc) for tc in renderer.tool_calls],
    )
