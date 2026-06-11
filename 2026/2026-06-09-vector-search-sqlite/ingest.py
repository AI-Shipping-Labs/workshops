"""Ingest process: build the SQLite vector search index.

This is the offline half of the system. It:
  1. downloads the ONNX embedding model (if not already present),
  2. fetches the course FAQ,
  3. embeds each document with the lightweight ONNX embedder,
  4. writes a vector index into SQLite.

The serve process (`app.py` / `search.py`) then only ever reads this database
— it never recomputes document embeddings.

Run it with:  uv run python ingest.py   (or: make ingest)
"""

import numpy as np
import requests

from config import (
    COURSE,
    DATA_DIR,
    DB_PATH,
    FAQ_URL,
    open_vector_index,
)
from download import download
from embedder import Embedder

BATCH_SIZE = 32


def fetch_documents():
    documents = requests.get(FAQ_URL).json()
    print(f"Fetched {len(documents)} FAQ documents")
    return documents


def embed_documents(embedder, documents):
    # Embed question + answer together so retrieval matches on either.
    texts = [f"{d['question']}\n{d['answer']}" for d in documents]
    batches = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        batches.append(embedder.encode_batch(batch))
        print(f"  embedded {min(start + BATCH_SIZE, len(texts))}/{len(texts)}")
    return np.vstack(batches)


def build_vector_index(documents, vectors):
    # Build into whatever the factory opens: a local SQLite file for dev, or
    # Turso when DB_PATH is a libsql:// URL. sqlitesearch batches the inserts, so
    # writing straight to Turso is fast.
    index = open_vector_index()
    index.clear()
    index.fit(vectors, documents)
    print(f"Vector index: {index.count()} documents -> {DB_PATH}")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Downloading embedding model...")
    download()

    documents = fetch_documents()
    documents = [d for d in documents if d.get("course") == COURSE]
    print(f"{len(documents)} documents for course {COURSE!r}")

    print("Embedding documents...")
    embedder = Embedder()
    vectors = embed_documents(embedder, documents)

    build_vector_index(documents, vectors)
    print("Ingest complete.")


if __name__ == "__main__":
    main()
