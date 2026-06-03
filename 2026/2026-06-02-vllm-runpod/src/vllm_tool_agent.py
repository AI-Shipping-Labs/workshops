#!/usr/bin/env python3
"""FAQ agent using vLLM's OpenAI-compatible chat completions API.

This ports the workshop's search-tool loop from the OpenAI Responses API to
vLLM's /v1/chat/completions endpoint. It intentionally uses only the standard
library so it can run in this minimal project.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from typing import Any


DEFAULT_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_MODEL = os.environ.get(
    "VLLM_MODEL",
    "stelterlab/DeepSeek-R1-Distill-Qwen-14B-AWQ",
)
DEFAULT_API_KEY = os.environ.get("VLLM_API_KEY", "local-test")
FAQ_URL = "https://datatalks.club/faq/json/data-engineering-zoomcamp.json"
COURSE = "data-engineering-zoomcamp"
MAX_RESULTS = 5
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TOOL_TOKENS = 384

INSTRUCTIONS = """
You're a teaching assistant for DataTalks.Club zoomcamps.

For every user question about the course, your first assistant response must be
a tool call to search. Do not write any natural-language answer before calling
the search tool. You must answer only after the tool result is provided.

If the API does not emit a structured tool call, output exactly this JSON object
and no final answer:
{"name":"search","arguments":{"query":"the user's question"}}

Use only facts from the search results. If the answer isn't in the results, say
so clearly. Do not answer from memory. Do not claim that you checked search
results unless you actually called the search tool and received results.

At the end, list the FAQ entries you used under a "Sources" section, one per
line in the form: "- [id] section > question".
""".strip()


SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search",
        "description": "Search the Data Engineering Zoomcamp FAQ.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for the FAQ.",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


def http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    api_key: str = DEFAULT_API_KEY,
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "curl/8.5.0",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_base_url(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    if base_url.endswith("/v1"):
        return base_url[:-3]
    return base_url


def load_faq() -> list[dict[str, Any]]:
    with urllib.request.urlopen(FAQ_URL, timeout=30) as response:
        documents = json.loads(response.read().decode("utf-8"))

    normalized = []
    for index, document in enumerate(documents):
        item = dict(document)
        item.setdefault("id", str(index))
        normalized.append(item)
    return normalized


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def search_faq(documents: list[dict[str, Any]], query: str, limit: int) -> list[dict]:
    query_terms = tokenize(query)
    if not query_terms:
        return []

    query_counts = Counter(query_terms)
    scored = []
    for document in documents:
        if document.get("course") != COURSE:
            continue

        question = str(document.get("question", ""))
        answer = str(document.get("answer", ""))
        section = str(document.get("section", ""))
        text = f"{question} {question} {question} {section} {answer}"
        doc_counts = Counter(tokenize(text))
        length_norm = max(math.sqrt(sum(doc_counts.values())), 1.0)
        score = sum(query_counts[term] * doc_counts.get(term, 0) for term in query_counts)
        score = score / length_norm
        if score > 0:
            scored.append((score, document))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = []
    for score, document in scored[:limit]:
        results.append(
            {
                "id": document.get("id"),
                "section": document.get("section"),
                "question": document.get("question"),
                "answer": document.get("answer"),
                "score": round(score, 4),
            }
        )
    return results


def chat_completion(
    base_url: str, payload: dict[str, Any], api_key: str
) -> dict[str, Any]:
    try:
        return http_json(
            "POST",
            f"{normalize_base_url(base_url)}/v1/chat/completions",
            payload,
            api_key=api_key,
        )
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"vLLM HTTP {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach vLLM: {exc}") from exc


def model_turn(
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    tool_choice: str,
    max_tokens: int,
    api_key: str,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "tools": [SEARCH_TOOL],
        "tool_choice": tool_choice,
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    if tool_choice == "search":
        payload["tool_choice"] = {
            "type": "function",
            "function": {"name": "search"},
        }
    return chat_completion(base_url, payload, api_key)


def final_answer(
    base_url: str,
    model: str,
    question: str,
    tool_call: dict[str, Any],
    tool_result: list[dict[str, Any]],
    max_tokens: int,
    api_key: str,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": INSTRUCTIONS},
            {"role": "user", "content": question},
            {"role": "assistant", "content": None, "tool_calls": [tool_call]},
            {
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "name": tool_call["function"]["name"],
                "content": json.dumps(tool_result),
            },
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    return chat_completion(base_url, payload, api_key)


def extract_message(response: dict[str, Any]) -> dict[str, Any]:
    return response["choices"][0]["message"]


def parse_content_tool_call(content: str) -> dict[str, Any] | None:
    """Parse a model-written tool call from message content.

    vLLM returns native `tool_calls` only when the model emits text matching the
    configured parser. Some models instead write JSON in normal content. That is
    still a model-selected tool call, so the agent can execute it.
    """
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    tag_match = re.search(r"<tool_call>(.*?)</tool_call>", content, flags=re.DOTALL)
    if tag_match:
        content = tag_match.group(1).strip()

    decoder = json.JSONDecoder()
    for index, char in enumerate(content):
        if char != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(content[index:])
        except json.JSONDecodeError:
            continue
        if (
            isinstance(candidate, dict)
            and candidate.get("name") == "search"
            and isinstance(candidate.get("arguments"), dict)
        ):
            return {
                "id": "call_content_search",
                "type": "function",
                "function": {
                    "name": candidate["name"],
                    "arguments": json.dumps(candidate["arguments"]),
                },
            }
    return None


def clean_assistant_content(content: str) -> str:
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    content = content.replace("<think>", "").replace("</think>", "")
    return content.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a vLLM tool-calling FAQ agent.")
    parser.add_argument("question", nargs="?", default="How do I submit homework?")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--api-key",
        default=DEFAULT_API_KEY,
        help="Bearer token for a vLLM server started with --api-key.",
    )
    parser.add_argument("--limit", type=int, default=MAX_RESULTS)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help="Maximum tokens for a final answer or direct no-tool answer.",
    )
    parser.add_argument(
        "--tool-call-tokens",
        type=int,
        default=DEFAULT_TOOL_TOKENS,
        help="Maximum tokens for the first model turn when tools are enabled.",
    )
    parser.add_argument(
        "--tool-choice",
        choices=["auto", "search", "none"],
        default="auto",
        help="Use auto for normal agent behavior, search to force the tool.",
    )
    parser.add_argument(
        "--tool-retries",
        type=int,
        default=1,
        help="Prompt-only retries when auto mode answers without a tool call.",
    )
    args = parser.parse_args()

    print(f"Loading FAQ index from {FAQ_URL} ...")
    documents = load_faq()

    print(f"Requesting a model response from vLLM with tool_choice={args.tool_choice} ...")
    try:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": INSTRUCTIONS},
            {"role": "user", "content": args.question},
        ]
        response = model_turn(
            args.base_url,
            args.model,
            messages,
            args.tool_choice,
            args.tool_call_tokens if args.tool_choice == "search" else args.max_tokens,
            args.api_key,
        )
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        print(
            "\nIf vLLM rejects tool_choice, restart it with tool support, for example:\n"
            "  vllm serve <model> --enable-auto-tool-choice --tool-call-parser hermes",
            file=sys.stderr,
        )
        return 1

    message = extract_message(response)
    tool_calls = message.get("tool_calls") or []
    if not tool_calls:
        content_tool_call = parse_content_tool_call(message.get("content", ""))
        if content_tool_call:
            tool_calls = [content_tool_call]

    retries_left = args.tool_retries if args.tool_choice == "auto" else 0
    while not tool_calls and retries_left > 0:
        print("The model answered without a tool call; retrying with a stricter prompt ...")
        messages.append(
            {
                "role": "assistant",
                "content": message.get("content", ""),
            }
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    "You did not follow the instruction. Do not answer directly. "
                    "Your next response must be a structured tool call to search "
                    "for this course question."
                ),
            }
        )
        retries_left -= 1
        response = model_turn(
            args.base_url,
            args.model,
            messages,
            args.tool_choice,
            args.tool_call_tokens,
            args.api_key,
        )
        message = extract_message(response)
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            content_tool_call = parse_content_tool_call(message.get("content", ""))
            if content_tool_call:
                tool_calls = [content_tool_call]

    if not tool_calls:
        answer = clean_assistant_content(message.get("content", ""))
        print("The model answered without calling a tool.")
        print("\nFinal answer:")
        print(answer.strip())
        return 0

    tool_call = tool_calls[0]
    function = tool_call["function"]
    arguments = json.loads(function.get("arguments") or "{}")
    query = arguments.get("query") or args.question
    print(f"Tool call: {function['name']}({json.dumps(arguments)})")

    results = search_faq(documents, query=query, limit=args.limit)
    print(f"Tool result: {len(results)} FAQ matches")
    for item in results:
        print(f"- [{item['id']}] {item['section']} > {item['question']}")

    print("\nSending tool result back to vLLM ...")
    response = final_answer(
        args.base_url,
        args.model,
        args.question,
        tool_call,
        results,
        args.max_tokens,
        args.api_key,
    )
    answer = clean_assistant_content(extract_message(response).get("content", ""))

    print("\nFinal answer:")
    print(answer.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
