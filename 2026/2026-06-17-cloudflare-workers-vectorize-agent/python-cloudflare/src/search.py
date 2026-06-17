import json

from config import DEFAULT_EMBEDDING_MODEL, DEFAULT_LIMIT
from interop import env_value, parse_jsonish, to_js, to_py
from responses import HttpError

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search",
        "description": "Search the DataTalks.Club course FAQ using semantic vector search.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A concise rewritten search query for the FAQ.",
                },
                "limit": {
                    "type": "number",
                    "description": "Maximum number of FAQ entries to return. Use 5 unless more context is clearly needed.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


def clamp_limit(value, fallback: int = DEFAULT_LIMIT) -> int:
    """Normalizes caller-provided search limits before Vectorize queries."""

    try:
        limit = int(float(value))
    except (TypeError, ValueError):
        limit = fallback
    return max(1, min(10, limit))


def truncate_for_embedding(text: str) -> str:
    """Keeps embedding input under a conservative size."""

    return text[:1800]


def parse_search_args(input_value, fallback_limit: int) -> dict:
    """Parses model-generated JSON arguments for the `search` tool."""

    args = parse_jsonish(input_value)
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        raise HttpError("Search tool arguments must include a string `query`.", 400)
    return {"query": query.strip(), "limit": clamp_limit(args.get("limit"), fallback_limit)}


async def embed_texts(env, texts: list[str]) -> list[list[float]]:
    """Calls Workers AI to embed one or more texts."""

    model = env_value(env, "EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    response = to_py(
        await env.AI.run(
            model,
            to_js({"text": [truncate_for_embedding(text) for text in texts]}),
        )
    )
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, list) or len(data) != len(texts):
        raise HttpError("Embedding model returned an unexpected response.", 502)
    return data


async def vector_search(env, vector: list[float], limit: int) -> list[dict]:
    """Queries Cloudflare Vectorize using the embedded search query."""

    response = to_py(
        await env.FAQ_INDEX.query(
            to_js(vector),
            to_js(
                {
                    "topK": limit,
                    "returnMetadata": "all",
                    "returnValues": False,
                }
            ),
        )
    )
    matches = response.get("matches", []) if isinstance(response, dict) else []
    return [format_match(match) for match in matches]


async def search(env, args: dict, fallback_limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Embeds a query and returns semantic FAQ matches from Vectorize."""

    query = str(args.get("query", "")).strip()
    if not query:
        raise HttpError("Search query cannot be empty.", 400)

    limit = clamp_limit(args.get("limit"), fallback_limit)
    vector = (await embed_texts(env, [query]))[0]
    return await vector_search(env, vector, limit)


def format_match(match) -> dict:
    """Converts one raw Vectorize match into the API result shape."""

    normalized = to_py(match)
    metadata = normalized.get("metadata", {}) if isinstance(normalized, dict) else {}
    return {
        "id": str(metadata.get("id") or normalized.get("id", "")),
        "score": float(normalized.get("score", 0)),
        "question": str(metadata.get("question", "")),
        "answer": str(metadata.get("answer", "")),
        "section": str(metadata.get("section", "")),
        "course": str(metadata.get("course", "data-engineering-zoomcamp")),
        "source": str(metadata.get("source", "")),
    }


def search_results_for_tool(results: list[dict]) -> str:
    """Serializes search results before appending them as a tool message."""

    return json.dumps(results)
