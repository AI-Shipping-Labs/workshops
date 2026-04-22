# End-to-End Agent Deployment

This directory contains the workshop code for the AI Shipping Labs session "End-to-End Agent Deployment" on April 28, 2026.

The code in this folder is taken from the `alexeygrigorev/faq-agent` project and published here as the workshop code snapshot.

## Prerequisites

- Python 3.13+
- OpenAI API key
- Docker if you want to build the container image

## What's In This Code

- `app.py`: FastAPI app with `/health`, `/ask`, and `/ask/stream` endpoints plus static frontend serving.
- `agent.py`: the FAQ agent loop that streams model output and handles tool calls.
- `search.py`: loads the Data Engineering Zoomcamp FAQ into an in-memory `minsearch` index and exposes the `search` tool.
- `renderer.py`: renderers for collecting responses and streaming SSE events.
- `schemas.py`: request and response models for the API.
- `frontend/`: browser UI assets.
- `notebook.ipynb`: notebook version of the workshop code.
- `Dockerfile`: container build for the app.
- `Makefile`: helper commands from the source repo.

## Running Locally

```bash
uv sync --locked
export OPENAI_API_KEY=sk-...
uv run fastapi dev app.py
```

## CI/CD

- The source project includes `.github/workflows/deploy.yml`.
- That workflow deploys to Railway, not Fly.
- In this repository the code lives under a workshop subfolder, so the copied workflow is part of the snapshot, not an active repo-level workflow.
