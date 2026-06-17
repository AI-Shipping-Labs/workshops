# Python Cloudflare Worker

Python-only rewrite of the FAQ agent. It keeps the same deployed architecture as
the TypeScript Worker:

- Cloudflare Python Worker serves the UI and API.
- Workers AI creates query embeddings and generates answers.
- Cloudflare Vectorize performs semantic FAQ search.
- Ingestion stays outside the Worker. Use the existing populated `faq-index` or
  run ingestion separately before testing queries.

## Beta Status

Cloudflare Python Workers are beta. Expect more runtime and tooling risk than
the TypeScript Worker version. The project uses the required `python_workers`
compatibility flag and `pywrangler`.

## Prerequisites

The repository root `.env` must contain:

```bash
CLOUDFLARE_ACCOUNT_ID=...
CLOUDFLARE_API_TOKEN=...
VECTORIZE_INDEX_NAME=faq-index
EMBEDDING_MODEL=@cf/baai/bge-base-en-v1.5
CHAT_MODEL=@cf/zai-org/glm-4.7-flash
```

The API token needs Workers Scripts edit permissions plus access to Workers AI
and Vectorize for the target account.

## Local Run

Run from the repository root:

```bash
make python-dev
```

Or from this folder:

```bash
make dev
```

Then open:

```text
http://localhost:8792
```

The local Worker uses real remote Cloudflare AI and Vectorize bindings, so this
is not a mock.

Useful direct checks:

```bash
curl http://localhost:8792/health
curl http://localhost:8792/index-info
curl -X POST http://localhost:8792/search \
  -H 'content-type: application/json' \
  -d '{"question":"I just discoverd the coure can I join it now","limit":5}'
```

## Deploy

Run from the repository root:

```bash
make python-deploy
```

Or from this folder:

```bash
make deploy
```

Expected workers.dev URL:

```text
https://cloudflare-ai-agent-python.<your-workers-dev-subdomain>.workers.dev
```

## Stop And Clean Up

Delete the Python Worker:

```bash
make python-delete
```

Or from this folder:

```bash
make delete
```

If Wrangler delete fails because the token lacks unrelated account permissions,
delete the Worker through the Cloudflare Workers API:

```bash
curl -s -X DELETE \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/services/cloudflare-ai-agent-python"
```

Confirm no Workers services remain:

```bash
curl -s \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/services"
```

Verify the worker URL is gone. A deleted workers.dev Worker returns Cloudflare
error `1042`:

```bash
curl -i https://cloudflare-ai-agent-python.<your-workers-dev-subdomain>.workers.dev/health
```

Delete the Vectorize index when you no longer need the ingested FAQ data:

```bash
npx wrangler vectorize delete faq-index --force
```

Verify no Vectorize indexes remain:

```bash
npx wrangler vectorize list
```
