# Option 1: Full-Stack Cloudflare

This option keeps the deployed application on Cloudflare:

```text
local ingestion script
  -> Workers AI REST API for batch document embeddings
  -> Vectorize REST API for vector upsert

browser/user
  -> Cloudflare Worker
  -> Workers AI binding for query embedding
  -> Vectorize binding for similarity search
  -> Workers AI binding for answer generation
```

There is intentionally no `/ingest` endpoint in the Worker. Ingestion is an operator action run locally.

## Setup

Install dependencies for all subprojects:

```sh
npm --prefix packages/shared install
npm --prefix apps/agent-worker install
npm --prefix apps/ingestion install
```

## Cloudflare Credentials

Use a Cloudflare API token rather than relying on Wrangler OAuth. This is useful when `wrangler login` is blocked by browser, SSO, or OAuth errors.

Create the token:

1. Open the Cloudflare dashboard.
2. Go to `My Profile` > `API Tokens`.
3. Click `Create Token`.
4. Choose `Create Custom Token`.
5. Add these account permissions:

```text
Account / Workers AI / Read
Account / Vectorize / Edit
```

For deploying the Worker with Wrangler, also add:

```text
Account / Workers Scripts / Edit
```

For account resources, choose the specific account if you know it. If you cannot find the account yet, choose `All accounts`, then narrow it later.

Copy the token and use it to find your account ID:

```sh
export CLOUDFLARE_API_TOKEN="your-token"

curl -s \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts" \
  | jq -r '.result[] | "\(.name)\t\(.id)"'
```

The second column is `CLOUDFLARE_ACCOUNT_ID`.

Create a root `.env` file:

```sh
CLOUDFLARE_ACCOUNT_ID=your-account-id
CLOUDFLARE_API_TOKEN=your-token
VECTORIZE_INDEX_NAME=faq-index
EMBEDDING_MODEL=@cf/baai/bge-base-en-v1.5
CHAT_MODEL=@cf/zai-org/glm-4.7-flash
```

`CHAT_MODEL` defaults to `@cf/zai-org/glm-4.7-flash` because it supports streamed function calling through the same `/ai/run` path used by Workers AI bindings. The browser UI includes a **Max tokens** control for the per-request streaming chat budget; reasoning-capable models may spend part of this budget on streamed reasoning before emitting tool calls or final answer text.

Wrangler can also use the same token without `wrangler login`:

```sh
CLOUDFLARE_API_TOKEN="your-token" npx wrangler whoami
CLOUDFLARE_API_TOKEN="your-token" npx wrangler vectorize create faq-index --dimensions=768 --metric=cosine
CLOUDFLARE_API_TOKEN="your-token" npm --prefix apps/agent-worker run deploy
```

Create the Vectorize index after the token works. The default embedding model is `@cf/baai/bge-base-en-v1.5`, which returns 768-dimensional vectors:

```sh
CLOUDFLARE_API_TOKEN="your-token" npx wrangler vectorize create faq-index --dimensions=768 --metric=cosine
```

## Ingest Locally

The local ingestion script reads the root `.env`:

```sh
CLOUDFLARE_ACCOUNT_ID=your-account-id
CLOUDFLARE_API_TOKEN=your-api-token
VECTORIZE_INDEX_NAME=faq-index
EMBEDDING_MODEL=@cf/baai/bge-base-en-v1.5
```

The ingestion app loads the root `.env` as the source of truth. If `apps/ingestion/.env` exists, root values still take precedence.

Run:

```sh
npm --prefix apps/ingestion run ingest
```

Vectorize upserts are asynchronous, so wait a few seconds before querying.

## Test Locally

Run checks before starting the local Worker:

```sh
npm run option1:typecheck
npm --prefix apps/agent-worker run dry-run
```

Run the Worker locally before deploy:

```sh
npm --prefix apps/agent-worker run dev
```

This runs the Worker process locally and calls real Cloudflare services through the REST API:

```text
localhost Worker
  -> Workers AI REST API
  -> Vectorize REST API
  -> Workers AI REST API
```

This is not a mock. It uses the account, token, models, and Vectorize index from the root `.env`.

The deployed Worker uses native Cloudflare bindings instead of REST:

```text
deployed Worker
  -> Workers AI binding
  -> Vectorize binding
  -> Workers AI binding
```

The app logic, prompts, endpoints, models, and index are the same. The transport is different because native bindings only exist inside Cloudflare's Worker runtime.

After the dev server starts, test it:

```sh
curl -s http://localhost:8788/health | jq

curl -s -X POST "http://localhost:8788/search" \
  -H "Content-Type: application/json" \
  -d '{"question":"How do I install dependencies?","limit":3}' | jq

curl -sN -X POST "http://localhost:8788/ask/stream" \
  -H "Content-Type: application/json" \
  -d '{"question":"How do I install dependencies?","limit":3}'
```

Check only the vector index and search layer:

```sh
curl -s "http://localhost:8788/index-info" | jq

curl -s -X POST "http://localhost:8788/search" \
  -H "Content-Type: application/json" \
  -d '{"question":"I just discoverd the coure can I join it now","limit":5}' \
  | jq '{count: (.results | length), results: [.results[] | {score, question, section}]}'
```

If you want to test native bindings locally, use:

```sh
npm --prefix apps/agent-worker run dev:bindings
```

Cloudflare currently requires a `workers.dev` subdomain for the remote-bindings dev path. If you see an error about `workers/subdomain/edge-preview`, register the subdomain here:

```text
https://dash.cloudflare.com/<account-id>/workers/onboarding
```

If you want Wrangler's older remote preview mode instead, run this after registering a `workers.dev` subdomain:

```sh
npm --prefix apps/agent-worker run dev:remote-preview
```

Ask:

```sh
curl -sN -X POST "http://localhost:8787/ask/stream" \
  -H "Content-Type: application/json" \
  -d '{"question":"How do I install the dependencies for the course?"}'
```

## Deploy

The Worker is configured with `workers_dev: true` in `apps/agent-worker/wrangler.jsonc`, so Wrangler publishes it to:

```text
https://<worker-name>.<account-workers-subdomain>.workers.dev
```

For this project, `<worker-name>` is `cloudflare-ai-agent-option1`.

Before deploying, run the same checks locally:

```sh
npm run option1:typecheck
npm --prefix apps/agent-worker run dry-run
```

Then deploy:

```sh
npm --prefix apps/agent-worker run deploy
```

### First Deploy On A New Cloudflare Account

If the account does not have a `workers.dev` subdomain yet, deploy can upload the Worker but fail to publish with:

```text
You need to register a workers.dev subdomain before publishing to workers.dev
```

You can fix this from the dashboard:

```text
https://dash.cloudflare.com/<account-id>/workers/onboarding
```

Or with the Cloudflare API:

```sh
export CLOUDFLARE_ACCOUNT_ID="your-account-id"
export CLOUDFLARE_API_TOKEN="your-token"

curl -s -X PUT \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json" \
  "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/subdomain" \
  -d '{"subdomain":"your-unique-workers-subdomain"}' | jq
```

After that, rerun:

```sh
npm --prefix apps/agent-worker run deploy
```

You can verify the deployment with:

```sh
curl -s "https://cloudflare-ai-agent-option1.<your-unique-workers-subdomain>.workers.dev/health" | jq
```

## Stop Or Clean Up The Deployed TypeScript Worker

Use this when you want to make sure the TypeScript Worker is no longer publicly reachable and cannot receive traffic.

Delete the deployed Worker:

```sh
npm --prefix apps/agent-worker exec -- wrangler delete cloudflare-ai-agent-option1 --force
```

If Wrangler delete fails because the token lacks unrelated account permissions, use the Cloudflare Workers Scripts API directly:

```sh
export CLOUDFLARE_ACCOUNT_ID="your-account-id"
export CLOUDFLARE_API_TOKEN="your-token"

curl -s -X DELETE \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/services/cloudflare-ai-agent-option1" | jq
```

Confirm no Workers services remain:

```sh
curl -s \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/services" | jq
```

Verify the route is gone:

```sh
curl -i "https://cloudflare-ai-agent-option1.<your-unique-workers-subdomain>.workers.dev/health"
```

For this project, the verification URL has this shape:

```text
https://cloudflare-ai-agent-option1.<your-unique-workers-subdomain>.workers.dev/health
```

Deleting the Worker removes the public app and its `workers.dev` route. It does not delete the account-level `workers.dev` subdomain, because that subdomain is useful for future deployments such as the Python port.

If you are done with `workers.dev` entirely and have no other Workers using it, you can remove the account-level subdomain too:

```sh
export CLOUDFLARE_ACCOUNT_ID="your-account-id"
export CLOUDFLARE_API_TOKEN="your-token"

curl -s -X DELETE \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/subdomain" | jq
```

This project also created a Vectorize index named `faq-index`. Keep it if you plan to reuse the ingested FAQ data for the Python implementation. Delete it only if you want to remove the stored vectors too:

```sh
npm --prefix apps/agent-worker exec -- wrangler vectorize delete faq-index --force
```

Verify no Vectorize indexes remain:

```sh
npm --prefix apps/agent-worker exec -- wrangler vectorize list
```

The local `.env` file contains the Cloudflare token and account ID. It is ignored by git; delete it locally if you want to remove credentials from the machine:

```sh
rm .env
```

If you have a local Wrangler dev server running, stop it with `Ctrl+C` in that terminal. To check for leftover local dev processes:

```sh
pgrep -af 'wrangler dev|with-root-env'
```

If needed, terminate only those local dev PIDs:

```sh
kill <pid>
```
