# Cloudflare AI Agent Architecture Comparison

[Follow the tutorial on AI Shipping Labs](https://aishippinglabs.com/workshops/cloudflare-workers-vectorize-agent).

Published workshop:
[AI-Shipping-Labs/workshops/2026/2026-06-17-cloudflare-workers-vectorize-agent](https://github.com/AI-Shipping-Labs/workshops/tree/main/2026/2026-06-17-cloudflare-workers-vectorize-agent)

This repo is organized as two architecture tracks.

## `full-stack-cloudflare`

Focus for now. The online app is fully deployed on Cloudflare:

- Cloudflare Worker serves the UI and API.
- Workers AI creates query embeddings and generates answers.
- Cloudflare Vectorize performs semantic search.
- A local ingestion script runs from your machine and writes to Cloudflare, so ingestion is not exposed as a web endpoint.

## `hybrid-services`

Placeholder for the second option. This will compare a split architecture where some services are TypeScript Workers and some services are Python services or jobs. See [hybrid-services/README.md](./hybrid-services/README.md).

## `python-cloudflare`

Python-only rewrite of the Cloudflare Worker app.

Important: Cloudflare Python Workers are currently beta. This track is useful
for trying the same Worker + Workers AI + Vectorize architecture in Python, but
runtime APIs, `pywrangler` behavior, and package support may change more often
than the stable TypeScript Worker path.

## Current Work

We are implementing `full-stack-cloudflare` first.

## Project-local Cloudflare skills

Cloudflare skills are installed only for this repository under `.agents/skills`.
Do not install them globally; global skills load in unrelated projects and add
Cloudflare-specific context where it is not needed.

Use this command from the repo root to install or refresh the official
Cloudflare skill bundle locally:

```bash
npx -y skills add cloudflare/skills --skill '*' --agent codex --yes
```

This installs the official `cloudflare/skills` set:

- `agents-sdk`
- `cloudflare`
- `cloudflare-email-service`
- `cloudflare-one`
- `cloudflare-one-migrations`
- `durable-objects`
- `sandbox-sdk`
- `turnstile-spin`
- `web-perf`
- `workers-best-practices`
- `wrangler`

The installer writes `skills-lock.json`; keep it with the repo so the same skill
set can be restored later.

Avoid Wrangler's skill installer on any Wrangler command:

```bash
npx wrangler setup --install-skills
```

Wrangler currently passes `global: true` to the skills installer. That writes
Cloudflare skills into user-level agent folders, which pollutes Codex context
for other projects that do not use Cloudflare.
