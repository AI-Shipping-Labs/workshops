# AI Shipping Labs Workshops

We keep the public code from AI Shipping Labs sessions in this repository. Each
dated directory contains the working project, setup instructions, and notes from
the session.

## [End-to-End Agent Deployment](2026/2026-04-21-end-to-end-agent-deployment)

April 21, 2026

Build a deployable FAQ agent from the model call to the browser. You write a
tool-calling agent loop and stream its tokens over Server-Sent Events. You also
serve a small chat UI and package the finished app in Docker.

Tech: Python · FastAPI · OpenAI Responses API · `minsearch` · Pydantic · Vite ·
Server-Sent Events · Docker · `uv` · Railway

## [Lambda Agent Deployment](2026/2026-05-05-lambda-agent-deployment)

May 5, 2026

Take the streaming FAQ agent to AWS Lambda without creating separate frontend
and backend deployments. You package both in one container and implement the
Lambda runtime integration. You then test the container with the Runtime
Interface Emulator and deploy a Function URL.

Tech: Python · OpenAI Responses API · `minsearch` · Vite · AWS Lambda · Lambda
Function URLs · SAM · CloudFormation · ECR · Docker · Server-Sent Events

## [Investment Coach Bot](2026/2026-05-19-home-assignment-investment-coach-bot)

May 19, 2026

Build a public-company research assistant around free SEC EDGAR data. The agent
looks up tickers, XBRL company facts, filing metadata, and filing text. It
returns a concise research summary without crossing into personalized financial
advice. You can use it from a CLI or Telegram and evaluate saved scenarios.

Tech: Python · PydanticAI · OpenAI · SEC EDGAR · XBRL · Telegram Bot API ·
Pydantic · `uv` · pytest · CSV-based evaluations

## [Serving Open-Source Models with vLLM and RunPod](2026/2026-06-02-vllm-runpod)

June 2, 2026

Deploy an open-source quantized reasoning model on a rented GPU. You expose it
through an OpenAI-compatible API and verify GPU access. You also configure vLLM
tool calling, persist the Hugging Face model cache, and connect an FAQ agent.

Tech: Python · vLLM · RunPod · NVIDIA GPUs · CUDA · Hugging Face ·
DeepSeek-R1-Distill-Qwen-14B-AWQ · OpenAI-compatible APIs · `runpodctl` · `uv`

## [Deploying Vector Search with SQLite](2026/2026-06-09-vector-search-sqlite)

June 9, 2026

Replace an in-memory keyword index with persistent semantic search in a SQLite
file. You generate embeddings locally with ONNX and build an approximate vector
index. Turso stores the index while an embedded local replica serves searches.

Tech: Python · FastAPI · OpenAI · SQLite · `sqlitesearch` · LSH · ONNX Runtime ·
MiniLM embeddings · Turso · libSQL · `uv`

## [Cloudflare AI Agent Architecture Comparison](2026/2026-06-17-cloudflare-workers-vectorize-agent)

June 17, 2026

Run a retrieval agent on Cloudflare and compare the available architectures. In
the main track, you deploy the UI and API as a TypeScript Worker. Workers AI
generates embeddings and answers while Cloudflare Vectorize handles semantic
search. In the other tracks, you try a Python Worker and a hybrid service split.

Tech: TypeScript · Cloudflare Workers · Workers AI · Vectorize · Wrangler ·
streaming tool calls · Python Workers · Node.js

## [Vercel FAQ Agent](2026/2026-06-25-vercel-faq-agent)

June 25, 2026

Build and deploy the same FAQ product through progressive options. You start
with in-memory text search and add durable agent sessions with Eve. Next, you
switch retrieval to Upstash Vector. Finally, you replace the TypeScript backend
with Python and FastAPI.

Tech: Next.js · TypeScript · Vercel · Vercel AI SDK 6 · AI Gateway · Eve ·
MiniSearch · Upstash Vector · Python · FastAPI · OpenAI Responses API

## [Saving Money with Batch and Flex](2026/2026-07-03-saving-money-with-batch-and-flex)

July 3, 2026

Measure and reduce the model cost of an FAQ-agent evaluation pipeline. You
generate synthetic questions, run agent evaluations, and judge the answers.
You then move independent offline calls to the Batch API and compare standard
requests with Flex processing and prompt caching.

Tech: Python · OpenAI Responses API · Batch API · Flex processing · prompt
caching · structured outputs · LLM-as-a-judge evaluations · `uv`

## [AI CV Pipeline](2026/2026-07-08-ai-cv-pipeline)

July 8, 2026

Turn structured CV data into focused and ATS-friendly resumes. You keep one YAML
source, select role-specific variants, and render print-ready HTML. A headless
browser creates the PDFs, so you don't need to maintain several documents.

Tech: Python · YAML · PyYAML · `uv` scripts · semantic HTML · CSS · headless
Chromium · PDF generation

## [NVC Voice Coach with ElevenLabs](2026/2026-07-22-nvc-voice-coach)

July 22, 2026

Build a natural voice coach for preparing difficult conversations with
Nonviolent Communication. You configure an ElevenLabs agent and stream private
voice sessions with interruption support. The web app shows a live transcript,
switches voices, tracks session costs, and deletes sensitive conversations.

Tech: TypeScript · Next.js 16 · React 19 · ElevenLabs ElevenAgents · streaming
WebSockets · browser audio · Playwright · ESLint
