from config import DEFAULT_CHAT_MODEL, DEFAULT_LIMIT, DEFAULT_MAX_OUTPUT_TOKENS, MAX_ITERATIONS
from interop import env_value, to_js, to_py
from search import SEARCH_TOOL, parse_search_args, search, search_results_for_tool

INSTRUCTIONS = """
You're a teaching assistant for DataTalks.Club zoomcamps.

Answer the user's question using the FAQ knowledge base. Use the search tool
to look things up. You can call search multiple times with different queries
to explore the topic well.

Rules:
- The FAQ knowledge base is for the Data Engineering Zoomcamp. If the user says
  "the course" or makes a typo like "coure", assume they mean this course.
- Always call search before answering course FAQ questions.
- Choose the search query yourself. Fix typos, remove filler words, and use
  concise FAQ-style wording.
- If the first search results do not directly answer the user's question, call
  search again with a better query.
- Once the search results contain a direct answer, stop searching and answer.
- Usually one or two search calls are enough; do not repeat near-identical
  searches.
- Do not search repeatedly for live/current registration status. If the FAQ says
  to check the course repo README for current cohort details, include that in
  the answer.
- Use only facts from the search results.
- If the answer isn't in the results, say so clearly.
- Never print JSON, tool names, function arguments, or implementation details
  in the final answer.
- At the end, list the FAQ entries you used under a "Sources" section,
  one per line exactly in the form: "- [id] section > question".
""".strip()


def clamp_max_output_tokens(value) -> int:
    """Clamps UI-provided model output budget to the supported range."""

    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = DEFAULT_MAX_OUTPUT_TOKENS
    return max(256, min(16384, parsed))


async def run_agent(env, question: str, renderer, limit: int = DEFAULT_LIMIT, max_output_tokens=None) -> dict:
    """Runs the multi-iteration FAQ agent loop used by `/ask/stream`."""

    await renderer.emit("status", {"message": "thinking..."})

    messages = [
        {"role": "system", "content": INSTRUCTIONS},
        {"role": "user", "content": question},
    ]
    all_results: list[dict] = []
    token_budget = clamp_max_output_tokens(max_output_tokens)

    for iteration in range(1, MAX_ITERATIONS + 1):
        await renderer.emit("iteration", {"n": iteration})
        response = await request_response(env, messages, renderer, token_budget)

        await renderer.emit(
            "model_done",
            {
                "completionTokens": response.get("completion_tokens"),
                "finishReason": response.get("finish_reason") or "unknown",
                "iteration": iteration,
                "maxOutputTokens": token_budget,
                "totalTokens": response.get("total_tokens"),
            },
        )

        tool_calls = response.get("tool_calls", [])
        if not tool_calls:
            answer = response.get("answer", "")
            if answer:
                await renderer.emit("token", {"delta": answer})
            await renderer.emit(
                "done",
                {
                    "answer": answer,
                    "finishReason": response.get("finish_reason") or "unknown",
                    "maxOutputTokens": token_budget,
                    "stoppedBy": "token_limit"
                    if response.get("finish_reason") == "length"
                    else "model",
                },
            )
            return {"answer": answer, "results": all_results}

        results = await handle_tool_calls(env, messages, tool_calls, renderer, limit)
        all_results.extend(results)

    answer = "(stopped: reached max iterations)"
    await renderer.emit(
        "done",
        {"answer": answer, "maxIterations": MAX_ITERATIONS, "stoppedBy": "max_iterations"},
    )
    return {"answer": answer, "results": all_results}


async def request_response(env, messages: list[dict], renderer, max_tokens: int) -> dict:
    """Sends one model turn to Workers AI with the `search` tool available."""

    model = env_value(env, "CHAT_MODEL", DEFAULT_CHAT_MODEL)
    response = to_py(
        await env.AI.run(
            model,
            to_js(
                {
                    "messages": messages,
                    "tools": [SEARCH_TOOL],
                    "tool_choice": "auto",
                    "temperature": 0.2,
                    "max_tokens": max_tokens,
                }
            ),
        )
    )

    parsed = parse_model_response(response)
    reasoning = parsed.get("reasoning")
    if reasoning:
        await renderer.emit("reasoning", {"delta": reasoning})
    return parsed


async def handle_tool_calls(env, messages: list[dict], tool_calls: list[dict], renderer, limit: int) -> list[dict]:
    """Executes model-requested search calls and appends tool results to chat history."""

    results: list[dict] = []
    messages.append({"role": "assistant", "content": "", "tool_calls": tool_calls})

    for call in tool_calls:
        function = call.get("function", {})
        if function.get("name") != "search":
            continue

        args = parse_search_args(function.get("arguments", "{}"), limit)
        await renderer.emit("tool_call", {"name": "search", "arguments": args})

        tool_result = await search(env, args, limit)
        await renderer.emit("tool_result", {"name": "search", "result": tool_result})

        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.get("id", "search-call"),
                "name": "search",
                "content": search_results_for_tool(tool_result),
            }
        )
        results.extend(tool_result)

    return results


def parse_model_response(response) -> dict:
    """Normalizes Workers AI chat responses into answer, tool-call, and token fields."""

    if not isinstance(response, dict):
        return {"answer": "", "tool_calls": [], "finish_reason": "unknown"}

    usage = response.get("usage", {}) if isinstance(response.get("usage"), dict) else {}
    choice = first_choice(response)
    message = choice.get("message", {}) if isinstance(choice.get("message"), dict) else {}

    return {
        "answer": str(message.get("content") or response.get("response") or ""),
        "reasoning": message.get("reasoning_content") or message.get("reasoning") or response.get("reasoning"),
        "tool_calls": normalize_tool_calls(message.get("tool_calls") or response.get("tool_calls") or []),
        "finish_reason": choice.get("finish_reason") or response.get("finish_reason"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


def first_choice(response: dict) -> dict:
    """Returns the first OpenAI-style choice from a Workers AI response."""

    choices = response.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        return choices[0]
    return {}


def normalize_tool_calls(raw_calls) -> list[dict]:
    """Normalizes model tool calls so the agent can execute search uniformly."""

    calls = raw_calls if isinstance(raw_calls, list) else []
    normalized = []
    for index, call in enumerate(calls):
        if not isinstance(call, dict):
            continue
        function = call.get("function", {})
        if not isinstance(function, dict):
            continue
        normalized.append(
            {
                "id": str(call.get("id") or f"tool-call-{index}"),
                "type": "function",
                "function": {
                    "name": str(function.get("name", "")),
                    "arguments": function.get("arguments", "{}"),
                },
            }
        )
    return normalized

