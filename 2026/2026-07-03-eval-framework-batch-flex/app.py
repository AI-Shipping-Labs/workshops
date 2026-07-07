import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI

from agent import run_agent
from renderer import CollectingRenderer, SSEQueueRenderer
from schemas import AskRequest, AskResponse, ToolCall
from search import init_index

load_dotenv()

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_index()
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


@app.post("/ask/stream")
async def ask_stream(req: AskRequest):
    queue: asyncio.Queue = asyncio.Queue()
    renderer = SSEQueueRenderer(queue)

    async def producer():
        try:
            await run_agent(app.state.openai_client, req.question, renderer)
        finally:
            await queue.put(None)

    async def event_generator():
        task = asyncio.create_task(producer())
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            await task

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
