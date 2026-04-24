---
title: Workshop Overview
sort_order: 1
---

# Workshop Overview

In this workshop we build and deploy an agent from scratch. By the end
you'll have a working FastAPI app that streams answers from an OpenAI
agent over SSE, with a tool-calling loop over an in-memory FAQ search
index — all packaged as a single container ready to deploy.

## What you'll build

- A FastAPI backend with `/ask` (JSON) and `/ask/stream` (SSE) endpoints.
- A tool-calling agent loop built on the OpenAI Responses API.
- A minimal frontend that posts questions and renders streamed tokens
  plus tool-call metadata inline.
- A Dockerfile that builds the frontend with Vite, bundles the assets
  into the Python image, and runs the whole thing under uvicorn.

## Prerequisites

- Python 3.13+
- An OpenAI API key
- Docker (only needed for the deployment section)

## Architecture at a glance

```
Frontend ->  POST /ask/stream  ->  FastAPI  ->  Agent loop  ->  OpenAI Responses API
                                                  |
                                                  +-> FAQ search tool (minsearch)
```

The agent iterates up to five times: on each turn it either returns a
final answer or requests a tool call, the backend runs the tool and
appends the result, and the loop continues.
