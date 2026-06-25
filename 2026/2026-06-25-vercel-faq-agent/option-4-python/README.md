# Option 4 — Python backend

Same FAQ agent as the other options, but the **backend is Python** instead of
TypeScript. The frontend stays **Next.js** — only the one piece that talked to the
Vercel AI SDK changed.

| Layer | Option 1 (TypeScript) | Option 4 (this one) |
| ----- | --------------------- | ------------------- |
| Frontend | Next.js + `useChat` from `@ai-sdk/react` | Next.js + a small custom `useChat` hook (`lib/useChat.ts`) |
| Transport | Vercel AI SDK UI Message Stream | plain **Server-Sent Events** (`event:` / `data:`) |
| Agent loop | `ToolLoopAgent` (Vercel AI SDK) | hand-written loop on the **OpenAI Responses API** (`backend/agent.py`) |
| Search | MiniSearch (JS) | [`minsearch`](https://github.com/alexeygrigorev/minsearch) (DataTalks.Club's Python search lib) |
| Model | `gpt-5.4-mini` | `gpt-5.4-mini` (same) |

The backend structure mirrors the DataTalks.Club
[Lambda agent deployment workshop](https://github.com/AI-Shipping-Labs/workshops/tree/main/2026/2026-05-05-lambda-agent-deployment)
(`agent.py` / `search.py` / `renderer.py`). Like that workshop, the Python service
can **serve its own frontend**: the Next.js app is built to static files and
FastAPI serves them alongside the API — one process, one deploy.

## How it works

### One service serves everything

There's a single FastAPI app. It serves the built web page **and** runs the agent —
no separate frontend server:

```
Browser ──►  FastAPI app
             ├─ GET /            → the Next.js UI (static files in backend/static)
             ├─ GET /_next/...   → JS / CSS assets
             ├─ POST /chat       → run the agent, stream the answer (SSE)
             ├─ GET /search?q=   → search only, no model (debug)
             └─ GET /health      → liveness
```

In production on Vercel, every path is routed to one Python Function that *is* this
app (see Deploy). Locally it's the same app under `uvicorn`.

### What happens on a question

1. **You type + click Ask.** `lib/useChat.ts` sends `POST /chat` with the full
   conversation and opens a streaming response.
2. **The agent runs** (`backend/agent.py`) — a hand-written loop on the OpenAI
   **Responses API**, with one tool exposed to the model: `search`.
3. **The model searches first.** Per its instructions it doesn't answer from memory;
   it rewrites your question into a clean query and calls the `search` tool.
4. **Search is local** (`backend/search.py`) — `minsearch` does keyword full-text
   search over the 404-entry FAQ (`backend/data/faq.json`). No embeddings, no vector
   DB. Returns the top matches.
5. **Results feed back to the model**, which may search again (up to `MAX_ITERATIONS`
   = 5 rounds), then writes the final answer **using only those FAQ entries**, ending
   with a `Sources` list.
6. **Everything streams to the browser** as it happens (see the event table below):
   the search chip, its hit count, then the answer token-by-token.

The core idea (same as every option): the model is **forced to ground its answer in
the FAQ** via the search tool, so it stays accurate and cites sources.

### The streaming protocol

`backend/renderer.py` turns agent events into Server-Sent Events; `lib/useChat.ts`
parses them. Same event names the reference Lambda workshop uses:

| Event | Payload | UI effect |
| ----- | ------- | --------- |
| `status` | `{message}` | (ignored) |
| `iteration` | `{n}` | (ignored) |
| `tool_call` | `{name, arguments}` | shows "🔍 searched FAQ for …" |
| `tool_result` | `{name, result}` | fills in the hit count |
| `token` | `{delta}` | appends to the streamed answer |
| `done` | `{answer}` | end of stream |

### Why the `renderer` indirection?

`agent.py` never formats SSE or touches HTTP — it just calls
`renderer.handle_event(type, payload)`. A renderer decides what to do: stream it to
the browser (`SSEQueueRenderer`), or collect it into a plain JSON response
(`CollectingRenderer`). That's how the same agent can power a streaming endpoint and
a non-streaming one without changes.

## Layout

```
option-4-python/
├── backend/              # Python (FastAPI)
│   ├── main.py           # HTTP: /chat (SSE), /search, /health + serves static/
│   ├── agent.py          # OpenAI Responses API tool loop
│   ├── search.py         # minsearch over data/faq.json
│   ├── renderer.py       # turns agent events into SSE
│   ├── data/faq.json     # FAQ snapshot (same as option 1)
│   ├── static/           # built frontend (generated; gitignored)
│   └── pyproject.toml    # deps, managed with uv
├── frontend/             # Next.js (App Router), output: "export"
│   ├── app/page.tsx      # chat UI (same look as option 1)
│   ├── lib/useChat.ts    # custom hook: POST + read SSE
│   └── next.config.ts    # static export + dev API proxy → :8000
├── api/index.py          # Vercel function entrypoint (re-exports the app)
├── vercel.json           # Vercel deploy config
├── requirements.txt      # pinned deps for Vercel (uv export)
└── build.sh              # build frontend → backend/static + export requirements
```

## Run it locally

Two ways: a **dev setup** with hot reload (two servers), or a **single-service
preview** that mirrors production (one server).

### Dev (hot reload)

Backend on :8000, Next.js dev server on :3000. `next.config.ts` proxies `/chat`,
`/search`, `/health` to the backend, so the browser uses same-origin paths.

```bash
# terminal 1 — backend (uses uv: https://docs.astral.sh/uv/)
cd backend
uv sync                              # create .venv from uv.lock
cp .env.example .env                 # add OPENAI_API_KEY=sk-...
uv run uvicorn main:app --reload --port 8000

# terminal 2 — frontend
cd frontend
npm install
npm run dev                          # http://localhost:3000
```

Sanity-check the backend on its own:

```bash
curl localhost:8000/health
curl "localhost:8000/search?q=docker%20network&limit=2"   # search only, no model
```

### Single-service preview (one server, like prod)

Build the frontend into `backend/static` and let FastAPI serve everything:

```bash
./build.sh                           # builds frontend → backend/static, exports requirements.txt
cd backend && uv run uvicorn main:app --port 8000
# open http://localhost:8000  — UI + API on one port, no CORS
```

## How the streaming works

The frontend POSTs the conversation to `POST /chat` and reads an SSE stream. The
backend's renderer (`renderer.py`) emits these event types:

| Event | Payload | UI effect |
| ----- | ------- | --------- |
| `status` | `{message}` | (ignored) |
| `iteration` | `{n}` | (ignored) |
| `tool_call` | `{name, arguments}` | shows "🔍 searched FAQ for …" |
| `tool_result` | `{name, result}` | fills in the hit count |
| `token` | `{delta}` | appends to the streamed answer |
| `done` | `{answer}` | end of stream |

## Model access

Defaults to calling OpenAI directly with `OPENAI_API_KEY`. To route through the
Vercel AI Gateway (OpenAI-compatible) instead, set `OPENAI_BASE_URL` to the
gateway endpoint and use a gateway key. Change the model with `CHAT_MODEL`.

## Deploy to Vercel

> This option **was deployed to Vercel and verified end-to-end** (UI + streaming
> chat), then **torn down**. The config below is exactly what worked and is ready
> to redeploy with `vercel deploy --prod`.

This deploys as **one Vercel Python Function that serves everything** — the static
UI *and* the API — exactly the single-service (Lambda-style) model. One project,
one origin, no CORS.

How the pieces map (`vercel.json`):

- **`builds`** builds `api/index.py` with `@vercel/python`. `api/index.py` puts
  `backend/` on the path and re-exports the FastAPI `app`; Vercel serves the ASGI
  app and bundles `backend/**` (code + `data/faq.json` + the built `static/`) via
  `includeFiles` (`maxLambdaSize: 250mb` — the deps are heavy, see below).
- **`routes`** send *every* path to the Function. FastAPI serves `backend/static`
  for the UI and handles `/chat`, `/search`, `/health`. SSE streams fine.
- The frontend is **pre-built locally** into `backend/static` (Vercel's `builds`
  doesn't run a Node build), so `./build.sh` must run before deploy.
- `.vercelignore` makes the gitignored `backend/static` upload while keeping
  secrets (`backend/.env`) and `node_modules`/`frontend` out.

### Steps

```bash
cd option-4-python

# 1. Build the frontend into backend/static + export a pinned requirements.txt.
#    (Vercel's build image has no uv and ignores uv.lock, so we ship requirements.txt.)
./build.sh

# 2. Link, set the API key, deploy. The Function needs a REAL key — Python can't
#    use the keyless OIDC gateway that options 1–3 rely on.
vercel link                                  # scope: ai-shipping-labs
vercel env add OPENAI_API_KEY production     # paste your sk-... key
vercel deploy --prod
```

> ⚠️ Set the key on the **same project you deploy to**. `vercel deploy` can create
> a project named after the folder (`option-4-python`); make sure `vercel env add`
> targets that one (`vercel env ls` to check), or the Function 500s with
> "Missing credentials".

Optional env vars (Vercel project settings): `CHAT_MODEL` (default `gpt-5.4-mini`),
`OPENAI_BASE_URL` (to route through the Vercel AI Gateway / an OpenAI-compatible
router instead of OpenAI direct).

### Notes / gotchas

- **Bundle size** — `minsearch` pulls in scikit-learn/scipy/numpy/pandas; the
  Function is ~278 MB and Vercel auto-optimizes it. Under the limit, but chunky
  and slow to cold-start. (A lighter search lib would shrink this a lot.)
- **Lazy OpenAI client** — `main.py` builds the client on first `/chat`, not at
  import, so a missing key only breaks `/chat`, not the UI / `/health`.
- **Function timeout** — `maxLambdaSize`/`maxDuration` aside, multi-search runs can
  be slow; bump the function timeout in project settings if you hit it.
- **Non-Vercel hosts** — the same `./build.sh` output runs anywhere: one Python
  process serving UI + API (container, Render, Fly, AWS Lambda like the reference).
- **Two-project fallback** — if you'd rather serve the UI from Vercel's CDN, split
  into a static frontend project + a Python API project and set
  `NEXT_PUBLIC_BACKEND_URL`; the CORS middleware is already there (tighten
  `ALLOWED_ORIGINS`).
