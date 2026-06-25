# Vercel FAQ Agent

A RAG-style FAQ agent for the DataTalks.Club **Data Engineering Zoomcamp**, ported
from the Cloudflare Workers + Vectorize workshop to the **Vercel** stack:

| Concern        | Cloudflare version              | This version                          |
| -------------- | ------------------------------- | ------------------------------------- |
| App framework  | Cloudflare Worker               | Next.js (App Router) on Vercel        |
| Agent loop     | Hand-rolled loop + SSE          | Vercel AI SDK `ToolLoopAgent` (one agent object) |
| Chat model     | Workers AI (`glm-4.7-flash`)    | `gpt-5.4-mini` via Vercel AI Gateway (or OpenAI direct) |
| Retrieval      | Embeddings + Cloudflare Vectorize | **MiniSearch** full-text (in memory) |
| Ingestion      | Embed + upsert to Vectorize     | `npm run fetch-faq` → `data/faq.json` |

There is no embedding step and no vector database — MiniSearch indexes the FAQ
snapshot in memory at startup.

## Setup

```sh
npm install
cp .env.example .env.local   # then configure the model provider (see below)
npm run fetch-faq            # downloads + filters the FAQ into data/faq.json
```

## Choosing the model provider

`MODEL_PROVIDER` selects how the agent reaches `gpt-5.4-mini` (`lib/agent.ts`):

- **`gateway`** (default) — routes through the **Vercel AI Gateway**: one key for
  any provider, swap models by editing `CHAT_MODEL` (e.g. `anthropic/claude-sonnet-4-6`).
  - *On Vercel:* keyless — authenticates automatically via OIDC.
  - *Local dev:* uses the `VERCEL_OIDC_TOKEN` that `vercel link` / `vercel env pull`
    writes to `.env.local` (it expires; re-pull to refresh), or set `AI_GATEWAY_API_KEY`.
  - Requires a credit card on file for the team to unlock the gateway's free credits.
- **`openai`** — calls the OpenAI API directly. Set `OPENAI_API_KEY`. No gateway,
  no card needed.

`GET /api/health` reports the active `modelProvider` and `chatModel`.

## Run locally

```sh
npm run dev
# open http://localhost:3000
```

Run the tests (these cover the retrieval layer — no API key or model needed):

```sh
npm test
```

The only HTTP endpoint the app needs is `POST /api/chat` (used by the UI).
`GET /api/health` is an optional readiness probe.

## Deploy to Vercel (step by step)

The app deploys as **serverless functions**: the chat UI becomes static assets on
Vercel's CDN, and `/api/chat` + `/api/health` become on-demand serverless
functions. There's no always-on server — a function spins up per request, runs
the agent, streams the answer, and spins down. The `OPENAI_API_KEY` is read at
**runtime** inside the function, so it must be set as a Vercel env var (the build
itself doesn't need it).

Run all of these **from inside this `option-1-minisearch/` folder.**

### 1. Install the CLI and log in (once per machine)

```sh
npm i -g vercel
vercel login            # opens a browser / OAuth; stores the credential locally
vercel whoami           # confirms who you're logged in as
```

### 2. Link this folder to a Vercel project (once per folder)

```sh
vercel link --yes --project faq-agent-option1
```

This creates `.vercel/project.json` here, which records the project + team id.
**Every later `vercel` command reads that file** to know which project it acts
on — that's how env vars and deploys target *this* project specifically and not
your others. `.vercel/` is git-ignored (machine-specific).

### 3. Configure the model provider

With the default **`gateway`** provider there's **nothing to add** — deployed
functions authenticate to the AI Gateway via OIDC automatically. (You just need a
credit card on the team to unlock the gateway's free credits — see "Choosing the
model provider" above.)

If you instead want **direct OpenAI** (`MODEL_PROVIDER=openai`), add the key:

```sh
vercel env add OPENAI_API_KEY production   # paste the key, or pipe it in
vercel env add MODEL_PROVIDER production    # value: openai
```

`production` is the environment (you can also add to `preview` / `development`).
Verify with `vercel env ls`.

### 4. Deploy

```sh
vercel --prod          # build in Vercel's cloud + publish to production
```

(Run `vercel` without `--prod` for a throwaway **preview** URL instead.)

### 5. Verify the live deployment

```sh
curl -s https://<your-project>.vercel.app/api/health

curl -sN -X POST https://<your-project>.vercel.app/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"id":"1","role":"user","parts":[{"type":"text","text":"How do I install the course dependencies?"}]}]}'
```

### Redeploying after changes

Just re-run `vercel --prod` (login + link + env are already done). If you change
or rotate the key, run `vercel env rm OPENAI_API_KEY production`, add it again,
then redeploy.

### Alternative: Git-based deploys

Instead of the CLI you can push to GitHub and import the repo at
https://vercel.com/new. Because this is a multi-option monorepo, set
**Root Directory = `option-1-minisearch`** in the project settings, and add
`OPENAI_API_KEY` under Project → Settings → Environment Variables. Vercel then
auto-deploys on every push (preview per branch, production on `main`).

> Note: keep your real key in a plain `.env.local` file in this folder (not a
> symlink). `vercel link`/`vercel env pull` write into `.env.local`, so a symlink
> would leak those writes into whatever it points at.

## Project layout

```
app/
  page.tsx            chat UI (useChat)
  api/chat/route.ts   thin endpoint — imports faqAgent and streams it
  api/health/route.ts optional health probe
lib/
  agent.ts            the agent definition: model + instructions + tools (faqAgent)
  search.ts           MiniSearch index + the search tool
  search.test.ts      tests for the retrieval layer
  faq.ts              FAQ data + types
scripts/fetch-faq.mjs FAQ downloader (the "ingestion" step)
data/faq.json         committed FAQ snapshot
```

The agent is defined once in `lib/agent.ts` as a `ToolLoopAgent`; the API route
contains no agent logic — it just parses the request and streams the agent's
response.
