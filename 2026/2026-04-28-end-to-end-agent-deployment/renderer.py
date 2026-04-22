import asyncio
import json


class BaseRenderer:
    async def handle_event(self, event_type, payload):
        handler = getattr(self, f"handle_{event_type}", self.handle_unknown)
        await handler(payload)

    async def handle_status(self, payload): ...
    async def handle_iteration(self, payload): ...
    async def handle_tool_call(self, payload): ...
    async def handle_tool_result(self, payload): ...
    async def handle_token(self, payload): ...
    async def handle_done(self, payload): ...
    async def handle_unknown(self, payload): ...


class CollectingRenderer(BaseRenderer):
    """Collects streamed tokens and tool events for a JSON response."""

    def __init__(self):
        self.answer_parts: list[str] = []
        self.tool_calls: list[dict] = []

    async def handle_token(self, payload):
        self.answer_parts.append(payload["delta"])

    async def handle_tool_call(self, payload):
        self.tool_calls.append({
            "name": payload["name"],
            "arguments": payload["arguments"],
        })

    @property
    def answer(self) -> str:
        return "".join(self.answer_parts)


class SSEQueueRenderer(BaseRenderer):
    """Pushes events as SSE-formatted strings onto an asyncio queue."""

    def __init__(self, queue: asyncio.Queue):
        self.queue = queue

    async def _emit(self, event_type: str, payload: dict):
        data = json.dumps(payload, default=str)
        await self.queue.put(f"event: {event_type}\ndata: {data}\n\n")

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
