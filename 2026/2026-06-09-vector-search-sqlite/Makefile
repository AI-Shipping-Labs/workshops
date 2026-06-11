.PHONY: install download ingest run dev

install:
	uv sync

# Download the ONNX embedding model into models/
download:
	uv run python download.py

# Fetch the FAQ, embed it, and build the vector index. Writes to Turso when
# DB_PATH is a libsql:// URL in .env, otherwise to a local SQLite file.
ingest:
	uv run python ingest.py

run:
	uv run uvicorn app:app

dev:
	uv run uvicorn app:app --reload
