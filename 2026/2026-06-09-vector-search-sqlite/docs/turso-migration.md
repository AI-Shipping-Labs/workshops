# Migrating the FAQ agent to Turso (free persistent vector search)

This document records how the FAQ agent was moved off Railway onto a setup that
stays free after trials end, using **Turso** (hosted libSQL) for persistent
vector storage and `sqlitesearch` for the vector index. It's written so the
whole thing can be reproduced from scratch.

## Why

- The Railway trial ended; we needed a host where the app keeps working for free.
- Free tiers rarely include durable disk or free Postgres, which breaks anything
  that stores data locally (a SQLite file gets wiped on every restart).
- **Turso** has a free tier that doesn't expire (~5 GB, 500M row reads/mo) and is
  SQLite-compatible, so it can hold the vector index durably while the app runs
  on any free, even ephemeral, host.

## Architecture

```
                 ingest (offline, one-off)            serve (every request)
  FAQ JSON  ──►  ONNX embed  ──►  sqlitesearch LSH  ─┐
                                  -> local faq.db    │   embedded replica
                                                     ├─►  syncs down once  ──►  local reads
   turso db import faq.db  ──►  Turso (durable)  ────┘        (fast)
```

- **Embeddings:** local ONNX model (`Xenova/all-MiniLM-L6-v2`, 384-dim) via
  `onnxruntime` — free, no OpenAI needed for embeddings. OpenAI is used **only**
  for the chat agent's answers.
- **Vector index:** `sqlitesearch` `VectorSearchIndex`, **LSH** mode
  (`hash_size=8, n_probe=4`, tuned for a few hundred docs).
- **Storage:** Turso. The app opens a libSQL **embedded replica** — data syncs
  down to a local file once on boot, and all search reads are local (fast).
- **Ingest vs serve split:** ingest builds a plain local SQLite file; that file
  is imported into Turso in one shot. See "Key learnings" for why.

### Code layout (what changed)

- `config.py` — `open_vector_index(local=False)` factory. Holds the LSH settings
  in one place so ingest and serve can't drift. Turso-backed when
  `TURSO_DATABASE_URL` is set; `local=True` forces a plain local file.
- `ingest.py` — builds the index into a **local** file (`data/faq.db`), fast.
- `search.py` — opens the Turso-backed index (syncs down), embeds the query,
  vector-searches.
- `Makefile` — `push-turso` target imports `data/faq.db` into Turso.

### sqlitesearch libSQL backend

`sqlitesearch` didn't support remote databases — it used Python's `sqlite3` on a
local file. We added a libSQL/Turso backend to it:

- PR: https://github.com/alexeygrigorev/sqlitesearch/pull/4
- Slow-bulk-write follow-up issue: https://github.com/alexeygrigorev/sqlitesearch/issues/3

It adds `backend` / `sync_url` / `auth_token` params (default `sqlite3`, fully
backward compatible). It ships in `sqlitesearch >= 0.0.6`; install the Turso
client with the extra: `pip install "sqlitesearch[turso]"` (already declared in
`pyproject.toml`).

## Reproduce from scratch

### 0. Prerequisites

- An OpenAI API key (for the chat agent).
- A Turso account (free): https://turso.tech
- Python 3.14 + `uv`.

### 1. Install the Turso CLI and authenticate

```bash
curl -sSfL https://get.tur.so/install.sh | bash
# add ~/.turso to PATH (the installer updates your shell profile)

turso auth signup            # or: turso auth login  (opens a browser)
```

Non-interactive alternative: create a **platform API token** in the Turso
dashboard and export it so the CLI works without a browser:

```bash
export TURSO_API_TOKEN="<platform-api-token>"
turso db list                # verifies auth
```

### 2. Configure `.env`

In the repo root `.env`:

```
OPENAI_API_KEY=sk-...
TURSO_API_KEY=<platform-api-token>     # optional, lets the CLI run non-interactively
TURSO_DATABASE_URL=                    # filled in after step 4
TURSO_AUTH_TOKEN=                      # filled in after step 4
```

### 3. Install dependencies and build the index locally

```bash
make install          # uv sync
make download         # download the ONNX embedding model into models/
make ingest           # fetch FAQ, embed (ONNX), build data/faq.db  (~seconds)
```

`make ingest` builds a **local** SQLite file. It does not write to Turso
directly (that path is slow — see Key learnings).

### 4. Push the index to Turso (one-shot import)

```bash
make push-turso       # turso db create faq --from-file data/faq.db
turso db show faq --url           # -> libsql://faq-<org>.turso.io
turso db tokens create faq        # -> auth token
```

Put the URL and token into `.env` as `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN`.

Verify server-side:

```bash
turso db shell faq "SELECT count(*) FROM docs;"   # -> 402
```

### 5. Run and test

```bash
make run              # uvicorn app:app
curl -s localhost:8000/health
curl -s -X POST localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"How do I install the dependencies for the course?"}'
```

On boot, `search.init_index()` opens the embedded replica (`db_path` defaults to
`data/faq-replica.db`), syncs the 402 docs down from Turso, and serves searches
locally. `/ask` runs the agent, which calls the `search` tool, embeds the query
with ONNX, and answers from the retrieved FAQ docs.

## Key learnings

1. **Bulk writes through the embedded replica are very slow.** Each INSERT is
   forwarded to the remote primary, so `fit()`-ing a few hundred docs directly
   into Turso took minutes (402 docs timed out at 300s; 5000 hung). A *local*
   libsql build of the same data was ~0.6s. Fix = build a local file, then
   `turso db import` it in one shot. Reads via the replica are fast, so only
   bulk ingest needed this split. (Tracked in sqlitesearch issue #3.)

2. **Don't reuse a just-destroyed Turso DB name.** `turso db destroy faq-agent`
   followed immediately by `turso db create faq-agent --from-file ...` failed
   with a stale-namespace 404. Use a fresh name (we moved to `faq`).

3. **libSQL's Python client has no `row_factory`** and returns plain tuples, so
   `sqlitesearch`'s `row["col"]` access breaks unless wrapped. The PR adds a row
   adapter that makes libsql rows behave like `sqlite3.Row`.

4. **Vector search is libsql-friendly.** `sqlitesearch` bulk-loads vectors into
   NumPy once and computes in-process, so there are no per-query network
   round-trips — Turso latency only costs a one-time sync-down on boot.

5. **HNSW build is slow in pure Python** (~21s for 5000×1536) vs LSH/IVF (<1s).
   For a few hundred docs use LSH or IVF; they're correct and instant.

## Next steps

- [ ] **Investigate fast direct ingest to Turso** (issue #3): wrap `fit()` writes
      in a single transaction or add a bulk/import helper so the local-build +
      import dance isn't needed.
- [ ] **Dockerfile for deploy:** bake `models/` (ONNX) into the image so query
      embedding works with no runtime download; copy the new modules
      (`config.py`, `embedder.py`, `download.py`); do **not** run ingest at deploy
      time (data already lives in Turso). `data/` (the replica cache) can be
      ephemeral.
- [ ] **Pick a free host** (Render / Hugging Face Spaces / Fly) and set three
      secrets: `OPENAI_API_KEY`, `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`.
- [ ] **Re-ingest workflow:** when the FAQ changes, re-run `make ingest` +
      `make push-turso` (or, once issue #3 is fixed, ingest straight to Turso).
