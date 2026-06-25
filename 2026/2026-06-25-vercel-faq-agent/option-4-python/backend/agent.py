"""
The FAQ agent — Python port of option 1's `ToolLoopAgent` (lib/agent.ts),
following the structure of the reference Lambda workshop's backend/agent.py.

The Vercel AI SDK gave us the model + tool loop for free. Here we run the same
loop by hand with the OpenAI **Responses API**: stream a model turn, run any
`search` tool calls it requests, feed the results back, and loop until it answers
(or MAX_ITERATIONS). The agent emits events through a renderer (see renderer.py)
rather than knowing how they're delivered.
"""

import json
import os

from openai import AsyncOpenAI

from renderer import BaseRenderer
from search import search, search_tool

# Defaults to OpenAI direct; point OPENAI_BASE_URL at the Vercel AI Gateway
# (OpenAI-compatible) to route through the gateway instead.
MODEL_NAME = os.environ.get("CHAT_MODEL", "gpt-5.4-mini")
MAX_ITERATIONS = 5

INSTRUCTIONS = """
You're a teaching assistant for DataTalks.Club zoomcamps.

Answer the user's question using the FAQ knowledge base. Use the `search` tool
to look things up. You can call search multiple times with different queries
to explore the topic well.

Rules:
- Always call search before answering course FAQ questions.
- Choose the search query yourself. Fix typos, remove filler words, and use
  concise FAQ-style wording.
- If the first search results do not directly answer the user's question, call
  search again with a better query.
- Use only facts from the search results.
- If the answer isn't in the results, say so clearly.
- Never print JSON, tool names, function arguments, or implementation details
  in the final answer.
- At the end, list the FAQ entries you used under a "Sources" section,
  one per line exactly in the form: "- [id] section > question".
""".strip()


async def request_response(client: AsyncOpenAI, message_history, renderer: BaseRenderer):
    """Stream one model turn, forwarding text deltas, and return the final response."""
    async with client.responses.stream(
        model=MODEL_NAME,
        input=message_history,
        tools=[search_tool],
    ) as stream:
        async for event in stream:
            if event.type == "response.output_text.delta":
                await renderer.handle_event("token", {"delta": event.delta})

        return await stream.get_final_response()


def append_tool_messages(message_history, item, result):
    """Record a tool call and its result in the Responses-API input format."""
    message_history.append(
        {
            "type": "function_call",
            "call_id": item.call_id,
            "name": item.name,
            "arguments": item.arguments,
        }
    )
    message_history.append(
        {
            "type": "function_call_output",
            "call_id": item.call_id,
            "output": json.dumps(result),
        }
    )


async def handle_tool_calls(response, message_history, renderer: BaseRenderer) -> bool:
    """Run every tool call in a response; return True if there were any."""
    has_tool_calls = False

    for item in response.output:
        if item.type != "function_call":
            continue

        has_tool_calls = True
        args = json.loads(item.arguments)
        await renderer.handle_event("tool_call", {"name": item.name, "arguments": args})

        result = search(**args)
        await renderer.handle_event(
            "tool_result", {"name": item.name, "result": result}
        )

        append_tool_messages(message_history, item, result)

    return has_tool_calls


def collect_answer(response) -> str:
    answer = ""
    for item in response.output:
        if item.type != "message":
            continue
        for content in item.content:
            if getattr(content, "text", None):
                answer += content.text
    return answer


async def run_agent(client: AsyncOpenAI, messages: list[dict], renderer: BaseRenderer) -> str:
    """Run the tool loop for a conversation, emitting events via the renderer.

    `messages` is the chat history as [{"role", "content"}, ...]; we prepend the
    system instructions.
    """
    await renderer.handle_event("status", {"message": "thinking..."})
    message_history = [{"role": "system", "content": INSTRUCTIONS}, *messages]

    for iteration in range(1, MAX_ITERATIONS + 1):
        await renderer.handle_event("iteration", {"n": iteration})

        response = await request_response(client, message_history, renderer)
        has_tool_calls = await handle_tool_calls(response, message_history, renderer)

        if not has_tool_calls:
            answer = collect_answer(response)
            await renderer.handle_event("done", {"answer": answer})
            return answer

    answer = "(stopped: reached max iterations)"
    await renderer.handle_event("done", {"answer": answer})
    return answer
