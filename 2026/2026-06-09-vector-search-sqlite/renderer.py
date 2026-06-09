"""Output adapter for the agent loop.

The agent emits events (status, iteration, tool_call, tool_result, token, done)
via `handle_event`. `CollectingRenderer` accumulates the streamed answer tokens
and tool calls so the `/ask` endpoint can return one final JSON object. Events
it doesn't care about fall through to the no-op handlers on `BaseRenderer`.
"""


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
