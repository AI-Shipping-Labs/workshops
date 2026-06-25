"""
Keyword full-text search over the FAQ.

This is the Python counterpart of option 1's MiniSearch index (lib/search.ts).
We use **minsearch** — DataTalks.Club's own in-memory search library and the same
one used in their agent workshops — over the committed FAQ snapshot in
`data/faq.json` (the same file option 1 uses, so all options share one knowledge base).

Mirrors the reference Lambda workshop's backend/search.py, but reads the local
snapshot instead of fetching the FAQ over HTTP, so it works offline.
"""

import json
from pathlib import Path

from minsearch import AppendableIndex

COURSE = "data-engineering-zoomcamp"
DEFAULT_LIMIT = 5
DATA_PATH = Path(__file__).parent / "data" / "faq.json"

# Field boosts, mirroring the MiniSearch `boost` config in option 1.
BOOST = {"question": 3.0, "section": 2.0, "answer": 1.0}

_index: AppendableIndex | None = None


def init_index() -> AppendableIndex:
    """Build the in-memory index once from the committed FAQ snapshot."""
    global _index
    documents = json.loads(DATA_PATH.read_text())
    index = AppendableIndex(
        text_fields=["question", "answer", "section"],
        keyword_fields=["course"],
    )
    index.fit(documents)
    _index = index
    return index


def search(query: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Search the FAQ for one course using the in-memory minsearch index.

    Args:
        query: Student question to look up.
        limit: Maximum number of matching FAQ entries to return.

    Returns:
        A list of matching FAQ documents.
    """
    if _index is None:
        init_index()

    return _index.search(
        query=query,
        filter_dict={"course": COURSE},
        boost_dict=BOOST,
        num_results=limit,
    )


# The `search` tool schema exposed to the model (OpenAI Responses API, flat shape).
search_tool = {
    "type": "function",
    "name": "search",
    "description": "Search the DataTalks.Club course FAQ using keyword full-text search.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A concise rewritten search query for the FAQ.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of FAQ entries to return. Use 5 unless more context is clearly needed.",
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}
