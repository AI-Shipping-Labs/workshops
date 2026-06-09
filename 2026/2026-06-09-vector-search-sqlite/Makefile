.PHONY: install download ingest push-turso run dev

# Turso database name (the app reads its URL/token from .env at runtime)
TURSO_DB ?= faq

install:
	uv sync

# Download the ONNX embedding model into models/
download:
	uv run python download.py

# Fetch the FAQ, embed it, and build the vector index into a local SQLite file
ingest:
	uv run python ingest.py

# Push the locally-built index up to Turso in one shot. Importing the whole
# SQLite file is fast; writing row-by-row through the replica is not.
push-turso:
	turso db create $(TURSO_DB) --from-file data/faq.db
	turso db show $(TURSO_DB) --url
	@echo "Now: turso db tokens create $(TURSO_DB), then set TURSO_DATABASE_URL / TURSO_AUTH_TOKEN in .env"

run:
	uv run uvicorn app:app

dev:
	uv run uvicorn app:app --reload
