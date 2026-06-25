# Option 3 — FAQ Agent on Eve + Upstash Vector

Option 2 (the Eve agent), but retrieval is swapped from **MiniSearch** (in-memory
keyword search) to **[Upstash Vector](https://upstash.com/docs/vector)** (managed
**semantic** vector search). This is the closest design to the original Cloudflare
Workers + Vectorize workshop — just without managing an embedding model:
**Upstash embeds text server-side** with `BAAI/bge-base-en-v1.5` (the same model
the Cloudflare workshop used).

## Option 2 vs. Option 3

| | Option 2 (`option-2-eve`) | Option 3 (this folder) |
| --- | --- | --- |
| Retrieval | MiniSearch — in-memory keyword | **Upstash Vector — semantic** |
| Embeddings | none | created **server-side by Upstash** (`bge-base-en-v1.5`) |
| Data at runtime | `data/faq.json` bundled & indexed in memory | lives in the **Upstash index**; agent only queries |
| Ingestion | `fetch-faq` snapshots JSON | **`npm run ingest`** upserts the FAQ into Upstash |
| `search` returns | keyword hits | nearest-neighbour matches by meaning |

Everything else (Eve `agent/` layout, model, web chat, durable session API) is
identical to Option 2.

## Two processes

1. **Ingestion (offline, run once)** — `scripts/ingest.mjs` reads `data/faq.json`
   and upserts each entry to Upstash as raw text + metadata. Upstash embeds it.
2. **The agent (deployed)** — `lib/faq-search.ts` queries Upstash with the user's
   text at request time. No embedding code, no bundled data.

> We considered a separate **Python** ingestion process (like the Cloudflare
> Python track), but since Upstash generates the vectors, ingestion is just
> "fetch + upsert" — so it stays in TypeScript.

## Cost — fits the Upstash free tier

- **404** vectors × 768 dims ≈ 0.3M of the **200M** free budget.
- Ingest = **404 upserts once**; runtime ≈ 1–2 queries per question — vs the
  **10K ops/day** free limit. Storage <1 MB of 1 GB. **No credit card required.**

## Setup

**1. Create the index** — two ways:

#### Option A — Upstash console (clicks)

In the [Upstash console](https://console.upstash.com/) → **Vector** → create an
index with embedding model **`BAAI/bge-base-en-v1.5`** (768 dims, cosine). Open
the index → **Connect / .env** section and copy its **REST URL** and **token**.

#### Option B — Upstash Developer API (scriptable — what we used)

The [Developer API](https://upstash.com/docs/devops/developer-api/introduction)
lets you provision the index from the command line.

1. **Get an API key.** Upstash console → top-right account menu → **Management
   API** (a.k.a. Developer API) → **Create API Key**. The key authenticates via
   **HTTP Basic auth** as `your-account-email:THE_API_KEY`.
2. **Create the index** with `POST /v2/vector/index`. Note the model is passed as
   the enum `BGE_BASE_EN_V1_5` (not the `BAAI/...` string), and `region` should
   match your Vercel function region (`us-east-1` ≈ Vercel `iad1`):

   ```sh
   curl -X POST https://api.upstash.com/v2/vector/index \
     -u "your-email@example.com:YOUR_DEVELOPER_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "faq-index",
       "region": "us-east-1",
       "similarity_function": "COSINE",
       "dimension_count": 768,
       "embedding_model": "BGE_BASE_EN_V1_5"
     }'
   ```

3. The JSON response contains **`endpoint`** (the REST host) and **`token`**.
   Put them in `.env.local` as `UPSTASH_VECTOR_REST_URL` (prefix `https://`) and
   `UPSTASH_VECTOR_REST_TOKEN`.

> The Developer API key is an **account-level** secret (it can create/delete
> resources). Keep it out of git and rotate it if it leaks. It is *not* the same
> as the per-index REST token the app uses at runtime.

**2. Configure + ingest:**

```sh
npm install
cp .env.example .env.local     # if you didn't already write it in step 1
npm run ingest                 # upserts 404 FAQ entries into Upstash (one-time)
```

## Run locally

```sh
# model calls go through the AI Gateway; for local dev get an OIDC token:
vercel link                    # (or eve link) pulls VERCEL_OIDC_TOKEN into .env.local
npm run dev                    # http://localhost:3000 — web chat + agent
```

Verify the agent over its HTTP API (durable session + stream) — see
**[docs/testing-the-api.md](./docs/testing-the-api.md)**.

## Deploy to Vercel

Same Eve flow as Option 2, **plus** the Upstash credentials as env vars (the
model stays keyless via OIDC, but Upstash needs its REST creds at runtime):

```sh
vercel link --yes --project faq-agent-option3   # eve link needs an interactive TTY; this is the non-interactive form
vercel env add UPSTASH_VECTOR_REST_URL production
vercel env add UPSTASH_VECTOR_REST_TOKEN production
npx eve deploy
```

> **Auth:** `agent/channels/eve.ts` uses `none()` (public demo). Swap for a real
> auth provider to lock it down.
