# Option 2 — FAQ Agent on Eve

The same DataTalks.Club FAQ agent as Option 1, rebuilt on **[Eve](https://vercel.com/eve)**,
Vercel's filesystem-first agent framework. The agent logic, retrieval, and model
are unchanged — what changes is *how the agent is defined and run*.

## Option 1 vs. Option 2

| | Option 1 (`option-1-minisearch`) | Option 2 (this folder) |
| --- | --- | --- |
| Agent definition | a `ToolLoopAgent` object + a hand-written `/api/chat` route | **files under `agent/`** — Eve discovers and compiles them |
| Instructions | a TS string (`INSTRUCTIONS`) | `agent/instructions.md` (markdown system prompt) |
| Tools | `tool()` passed to the agent | `agent/tools/*.ts` — **filename = tool name**, auto-registered |
| Model | `openai(...)` / gateway string | `defineAgent({ model: "openai/gpt-5.4-mini" })` |
| HTTP API | we wrote it | **built in** — durable sessions at `/eve/v1/session` |
| Execution | one serverless request | **durable sessions** (Vercel Workflows) that resume after restarts |
| Retrieval | MiniSearch (in-memory full-text) | MiniSearch — **identical** (`lib/faq-search.ts`) |

## Project layout

```
agent/
  instructions.md        the system prompt (markdown)
  agent.ts               defineAgent({ model }) — runtime config
  tools/search.ts        the `search` tool (filename = tool name)
  channels/eve.ts        HTTP channel + auth
lib/faq-search.ts        MiniSearch index + search() (shared logic)
data/faq.json            committed FAQ snapshot (404 docs)
scripts/fetch-faq.mjs    FAQ downloader ("ingestion")
app/                     Next.js Web Chat UI (useEveAgent) — added via --channel-web-nextjs
```

`next.config.ts` wraps the config in `withEve(...)`, which mounts the agent's
HTTP API into the Next.js app — so `next dev` / `next build` serve **both** the
chat UI and the agent.

## Setup & run locally

```sh
npm install
npm run fetch-faq          # downloads + filters the FAQ into data/faq.json

# Gateway credentials for local model calls (one of):
eve link                   # links a Vercel project and pulls AI Gateway creds (recommended)
# ...or put a VERCEL_OIDC_TOKEN / AI_GATEWAY_API_KEY in .env.local

npm run dev                # Next dev server on http://localhost:3000 (web chat + agent)
```

Test the agent's HTTP API directly (no browser):

```sh
# Start a durable session
curl -i -X POST http://localhost:3000/eve/v1/session \
  -H 'content-type: application/json' \
  -d '{"message":"How do I install the course dependencies?"}'
# -> returns x-eve-session-id header + a continuationToken

# Stream that session's NDJSON lifecycle events
curl -N http://localhost:3000/eve/v1/session/<sessionId>/stream
```

You can also explore the agent in Eve's terminal UI with `npx eve dev`.

➡️ **[docs/testing-the-api.md](./docs/testing-the-api.md)** walks through the full
two-step session/stream protocol with the exact commands and the event sequence
to expect — this is how the agent is verified end to end without a browser.

## Deploy to Vercel (step by step)

This is the exact sequence used to deploy this agent (production URL:
https://faq-agent-option2.vercel.app). Run everything **from this `option-2-eve/`
folder.**

### 0. Decide on auth (one-time code change)

`agent/channels/eve.ts` ships with `placeholderAuth()`, which **blocks browser
requests in production** — so the deployed web chat wouldn't work. For a public
demo, switch it to `none()`:

```ts
import { localDev, none, vercelOidc } from "eve/channels/auth";

export default eveChannel({
  auth: [localDev(), vercelOidc(), none()],
});
```

> ⚠️ `none()` makes the agent **public and unauthenticated** — anyone with the URL
> can use it and spend your AI Gateway credits. For a real app, wire an auth
> provider (Auth.js, Clerk, …) instead.

### 1. Log in to Vercel (once per machine)

```sh
npm i -g vercel
vercel login
```

### 2. Link this folder to a Vercel project

`eve link` needs an interactive terminal to pick the team/project. The
non-interactive equivalent (what we used) is the standard Vercel CLI — Eve reads
the `.vercel/project.json` it produces:

```sh
vercel link --yes --project faq-agent-option2
```

This creates a **separate** Vercel project from Option 1 and writes
`.vercel/project.json` (plus a fresh `VERCEL_OIDC_TOKEN` into `.env.local`).

### 3. Deploy

```sh
npx eve deploy
```

`eve deploy` installs deps, runs the build (Nitro compiles the agent into a
single Vercel Function), and publishes to **production**. Model calls are
**keyless** — they authenticate to the AI Gateway via OIDC, so there's no API key
to set. (The team still needs a card on file to unlock gateway credits.)

### 4. Verify (no browser needed)

Use the two-step session API — see **[docs/testing-the-api.md](./docs/testing-the-api.md)**:

```sh
SID=$(curl -s -i -X POST https://faq-agent-option2.vercel.app/eve/v1/session \
  -H 'content-type: application/json' \
  -d '{"message":"How do I install the course dependencies?"}' \
  | grep -i '^x-eve-session-id:' | tr -d '\r' | awk '{print $2}')

curl -N https://faq-agent-option2.vercel.app/eve/v1/session/$SID/stream
```

You should see `session.started → tool-call "search" → tool-result → message.appended`.

### Redeploying after changes

Just re-run `npx eve deploy` (login + link are already done).
