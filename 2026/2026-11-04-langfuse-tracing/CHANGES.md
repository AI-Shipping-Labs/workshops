# Changes vs upstream workshop

Upstream: https://github.com/AI-Shipping-Labs/workshops/tree/main/2026/2026-04-21-end-to-end-agent-deployment
 Snapshot date: 2026-11-04. Agent loop, prompts, retrieval logic, and frontend are unchanged —
 this copy only adds **Langfuse tracing** via the recommended SDK path.

## TL;DR

| Area | Upstream | This copy |
|---|---|---|
| LLM client | `from openai import AsyncOpenAI` | `from langfuse.openai import AsyncOpenAI` (drop-in, auto-traces generations: input/output, tokens, cost) |
| Agent trace | none | `@observe(as_type="agent", name="agent.run")` on `run_agent` |
| Tool trace | none | `@observe(as_type="tool", name="tool.search")` on new `call_search_tool` wrapper |
| Retrieval trace | none | `@observe(as_type="retriever", name="retrieval.minsearch")` on `search` |
| `/ask` response | `{answer, tool_calls}` | unchanged |
| Deps | no `langfuse` | `langfuse>=3.0.0` added |
| New files | — | `.env.example`, `docker-compose.yml` (optional self-hosted Langfuse stack) |
| Unchanged | — | `renderer.py`, `schemas.py`, `frontend/`, `notebook.ipynb`, `Makefile`, `Dockerfile`, prompts, model, loop |

## File-by-file

### `agent.py`
- Imports: `from langfuse import observe` and `from langfuse.openai import AsyncOpenAI` replace `from openai import AsyncOpenAI`.
- `request_response()`: logic identical (Responses API streaming + token events); tracing is automatic via the wrapper client.
- Added `call_search_tool()` — thin `@observe(as_type="tool")` wrapper around `search()`; `handle_tool_calls()` calls it instead of `search()` directly.
- `run_agent()`: decorated with `@observe(as_type="agent", name="agent.run", capture_output=True)`; loop, `MAX_ITERATIONS`, instructions, and renderer events unchanged.

### `search.py`
- Added `@observe(as_type="retriever", name="retrieval.minsearch")` to `search()`. Index building, query logic, and `search_tool` schema unchanged.

### `app.py`
- Uses Langfuse's wrapped `AsyncOpenAI`; `lifespan` calls `get_client().flush()` on shutdown so spans queued at exit aren't lost on restarts.
- `GET /health` unchanged (`{"status": "ok"}`).
- `POST /ask` unchanged.
- `POST /ask/stream`, static serving, lifespan index init: unchanged.

### `pyproject.toml`
- One line added: `"langfuse>=3.0.0"`.

### New files
- `.env.example`: `OPENAI_API_KEY` plus `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_BASE_URL` (defaults to `https://cloud.langfuse.com`).
- `docker-compose.yml`: optional self-hosted Langfuse v4 (UI `:3331`) + `faq-agent` (`:8000`), with headless-init vars documented in `.env.example`.

## Resulting trace shape in Langfuse

```
agent.run (agent, input=question, output=answer)
├── generation (per OpenAI Responses call, via wrapper)
├── tool.search (per tool call, input=args, output=results)
│   └── retrieval.minsearch (retriever)
└── generation (final answer)
```

Input/output, token usage, and cost are captured automatically — no manual span attributes.

## What was tried and removed

An earlier iteration used manual OpenTelemetry spans (`tracing.py` with a custom `TracerProvider`, `span()` helpers, `langfuse.observation.input/output` attributes, `/metrics` + `/stats` endpoints). It worked but reimplemented what the SDK does for free and left Input/Output empty until the exact attribute names were mapped. It was deleted in favor of the SDK path above (~10 added lines total vs ~300 lines of manual OTEL).

## Setup

Post-session reproducibility fixes: the Compose FAQ container always uses the
internal `http://langfuse-web:3000` endpoint, independent of the host application's
`LANGFUSE_BASE_URL`. Langfuse's event and media storage credentials inherit the
configured MinIO username/password unless explicitly overridden, so generated
MinIO passwords don't leave the upload clients using the old default password.

```bash
cp .env.example .env  # fill in OPENAI_API_KEY + Langfuse keys
uv sync --locked
uv run uvicorn app:app
curl -X POST localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question": "When does the zoomcamp start?"}'
# find the trace in Langfuse Cloud (or http://localhost:3331 self-hosted)
```

## Verification (2026-11-04)

- `GET /health` → `{"status": "ok"}`
- `POST /ask` → `200`, non-empty answer, 1 tool call; trace visible in Langfuse
- `search()` wrapper returns 5 hits; spans flush without errors
