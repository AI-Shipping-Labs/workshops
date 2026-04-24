---
title: Setup and Running Locally
sort_order: 2
---

# Setup and Running Locally

## Clone and install

```bash
git clone https://github.com/AI-Shipping-Labs/workshops-content.git
cd workshops-content/2026/2026-04-21-end-to-end-agent-deployment
uv sync --locked
```

## Configure your OpenAI key

```bash
export OPENAI_API_KEY=sk-...
```

## Run the backend

```bash
uv run fastapi dev app.py
```

This starts FastAPI on `http://localhost:8000` with auto-reload. You
can hit `/health` to verify it's up.

## Run the frontend

In a second terminal, from the same workshop directory:

```bash
cd frontend
npm install
npm run dev
```

Vite serves the frontend on `http://localhost:5173` and proxies
API calls to the FastAPI backend.

## Build and run the container

```bash
make build
make run
```

The `Dockerfile` builds the Vite frontend first, copies the bundle
into `./static` in the Python image, installs backend deps with `uv`,
and starts `uvicorn`. The resulting image serves both the frontend
and the `/ask` endpoints from a single container.
