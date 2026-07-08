import json

from openai import AsyncOpenAI

from renderer import BaseRenderer
from search import search, search_tool

MODEL_NAME = "gpt-5.4-mini"
MAX_ITERATIONS = 5

INSTRUCTIONS = """
You're a teaching assistant for DataTalks.Club zoomcamps.

Answer the user's question using the FAQ knowledge base. Use the `search`
tool to look things up. You can call search multiple times with different
queries to explore the topic well.

Rules:
- Use only facts from the search results.
- If the answer isn't in the results, say so clearly.
- At the end, list the FAQ entries you used under a "Sources" section,
  one per line in the form: `- [id] section > question`.
""".strip()


async def request_response(client: AsyncOpenAI, message_history, renderer: BaseRenderer):
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
    message_history.append({
        "type": "function_call",
        "call_id": item.call_id,
        "name": item.name,
        "arguments": item.arguments,
    })
    message_history.append({
        "type": "function_call_output",
        "call_id": item.call_id,
        "output": json.dumps(result),
    })


async def handle_tool_calls(response, message_history, renderer: BaseRenderer):
    has_tool_calls = False

    for item in response.output:
        if item.type != "function_call":
            continue

        has_tool_calls = True

        args = json.loads(item.arguments)
        await renderer.handle_event(
            "tool_call",
            {"name": item.name, "arguments": args},
        )

        result = search(**args)
        await renderer.handle_event(
            "tool_result",
            {"name": item.name, "result": result},
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


async def run_agent(client: AsyncOpenAI, question: str, renderer: BaseRenderer) -> str:
    await renderer.handle_event("status", {"message": "thinking..."})
    message_history = [
        {"role": "system", "content": INSTRUCTIONS},
        {"role": "user", "content": question},
    ]

    final_answer = ""

    for iteration in range(1, MAX_ITERATIONS + 1):
        await renderer.handle_event("iteration", {"n": iteration})

        response = await request_response(client, message_history, renderer)
        has_tool_calls = await handle_tool_calls(response, message_history, renderer)

        if not has_tool_calls:
            final_answer = collect_answer(response)
            await renderer.handle_event("done", {"answer": final_answer})
            return final_answer

    final_answer = "(stopped: reached max iterations)"
    await renderer.handle_event("done", {"answer": final_answer})
    return final_answer
