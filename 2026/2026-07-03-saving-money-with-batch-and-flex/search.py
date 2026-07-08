import requests
from minsearch import AppendableIndex

FAQ_URL = "https://datatalks.club/faq/json/data-engineering-zoomcamp.json"
COURSE = "data-engineering-zoomcamp"

_index: AppendableIndex | None = None


def init_index() -> AppendableIndex:
    global _index
    documents = requests.get(FAQ_URL).json()
    index = AppendableIndex(
        text_fields=["question", "answer", "section"],
        keyword_fields=["course"],
    )
    index.fit(documents)
    _index = index
    return index


def search(query: str, limit: int = 5):
    """Search the FAQ for one course using the in-memory minsearch index.

    Args:
        query: Student question to look up.
        limit: Maximum number of matching FAQ entries to return.

    Returns:
        A list of matching FAQ documents.
    """
    if _index is None:
        raise RuntimeError("Search index not initialized. Call init_index() first.")

    return _index.search(
        query=query,
        filter_dict={"course": COURSE},
        boost_dict={"question": 3.0, "section": 0.5, "answer": 1.0},
        num_results=limit,
    )


search_tool = {
    "type": "function",
    "name": "search",
    "description": "Search the course FAQ.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}
