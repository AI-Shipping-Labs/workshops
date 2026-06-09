"""Serve-side search: read the prebuilt SQLite vector index.

This module never builds or fetches anything at request time. On startup it
opens the vector SQLite database produced by `ingest.py` and loads the ONNX
embedder (used only to embed the incoming query). `search()` then embeds the
query and returns the nearest FAQ documents by cosine similarity.
"""

from sqlitesearch import VectorSearchIndex

from config import COURSE, open_vector_index
from embedder import Embedder

_vector_index: VectorSearchIndex | None = None
_embedder: Embedder | None = None


def init_index() -> None:
    """Open the SQLite vector index and load the query embedder.

    Raises if the database is empty, which means `ingest.py` hasn't been run.
    """
    global _vector_index, _embedder

    # Opening the index syncs the latest data down from Turso (when configured).
    vector_index = open_vector_index()

    if vector_index.count() == 0:
        raise RuntimeError(
            "Vector index is empty. Run the ingest process first: "
            "`uv run python ingest.py` (or `make ingest`)."
        )

    _vector_index = vector_index
    _embedder = Embedder()


def search(query: str, limit: int = 5):
    """Search the course FAQ using semantic (vector) search.

    Args:
        query: Student question to look up.
        limit: Maximum number of matching FAQ entries to return.

    Returns:
        A list of matching FAQ documents, ranked by cosine similarity.
    """
    if _vector_index is None or _embedder is None:
        raise RuntimeError("Search index not initialized. Call init_index() first.")

    query_vector = _embedder.encode(query)
    return _vector_index.search(
        query_vector=query_vector,
        filter_dict={"course": COURSE},
        num_results=limit,
    )


search_tool = {
    "type": "function",
    "name": "search",
    "description": "Search the course FAQ using semantic (vector) search.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}
