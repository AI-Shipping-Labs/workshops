# Vercel FAQ Agent — Workshop

Building and deploying an FAQ agent on **Vercel**, ported from the Cloudflare
Workers + Vectorize workshop. The workshop is split into progressive options,
each a self-contained, separately-deployable app.

## Options

| Option | Folder | Retrieval | Agent framework | Status |
| ------ | ------ | --------- | --------------- | ------ |
| **1. MiniSearch** | [`option-1-minisearch/`](./option-1-minisearch) | MiniSearch (in-memory full-text, no embeddings) | Vercel AI SDK — `ToolLoopAgent` | ✅ done & [deployed](https://faq-agent-option1.vercel.app) |
| **2. Eve** | [`option-2-eve/`](./option-2-eve) | same as Option 1 (MiniSearch) | [Eve](https://vercel.com/eve) — Vercel's agent framework (directory-based agent, durable sessions) | ✅ done & [deployed](https://faq-agent-option2.vercel.app) |
| **3. Upstash** | [`option-3-upstash/`](./option-3-upstash) | Upstash Vector (semantic search; Upstash embeds server-side) | Eve (from Option 2) | ✅ done & [deployed](https://faq-agent-option3.vercel.app) |
| **4. Python backend** | [`option-4-python/`](./option-4-python) | [`minsearch`](https://github.com/alexeygrigorev/minsearch) (Python, in-memory full-text) | hand-written loop on the OpenAI Responses API (FastAPI) | ✅ done & deploy-ready — verified on Vercel (one Python Function serves UI + API), then torn down |

Options 1–3 build on each other. **Option 4 is a variant of Option 1** that swaps
the TypeScript backend for **Python** (FastAPI) while keeping the Next.js frontend —
for teams that prefer Python. Start in `option-1-minisearch/` — its README has
setup, run, and deploy instructions.

## Common stack

- Next.js (App Router) deployed to Vercel
- Vercel AI SDK v6
- `gpt-5.4-mini` for chat, via the Vercel AI Gateway (or OpenAI direct — configurable)
- DataTalks.Club Data Engineering Zoomcamp FAQ as the knowledge base

## Stopping / tearing down

There's no "pause" on Vercel — to stop a deployment you delete its project. To
remove everything this workshop created:

### Vercel deployments

```sh
# Delete each project (takes down all its deployments + the *.vercel.app URL).
# The CLI prompts "Are you sure? (y/N)" — there is no --yes flag, so answer y.
vercel project rm faq-agent-option1
vercel project rm faq-agent-option2
vercel project rm faq-agent-option3
vercel project rm faq-agent-option4

vercel project ls            # verify: "No projects found"
```

Dashboard equivalent: **Project → Settings → Delete Project**. To drop a single
deployment but keep the project, use `vercel remove <deployment-url>` instead.

### Upstash Vector index (Option 3)

```sh
# Basic auth = your-account-email : UPSTASH_DEVELOPER_API_KEY
curl -u "EMAIL:DEV_API_KEY" https://api.upstash.com/v2/vector/index            # list → copy the id
curl -u "EMAIL:DEV_API_KEY" -X DELETE https://api.upstash.com/v2/vector/index/<id>
```

Dashboard equivalent: **console.upstash.com → Vector → the index → Danger Zone →
Delete**.

### Local dev servers

`Ctrl-C` in the terminal running `npm run dev`, or `pkill -f "next dev"`.

### Credentials

The `.env.local` files (and the root `.env`) hold API keys/tokens and are
git-ignored. Delete them if you want the secrets off the machine. Rotate the
Upstash **Developer API key** and OpenAI key if they were ever exposed.
