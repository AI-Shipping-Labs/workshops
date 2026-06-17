# Option 2: Hybrid Services

This option is intentionally not implemented yet. It is here to keep the comparison explicit while we finish Option 1 first.

Potential architecture:

```text
Python ingestion app
  -> shared chunking and metadata schema
  -> embedding provider directly for batch mode
  -> Cloudflare Vectorize upsert

TypeScript Cloudflare agent Worker
  -> online API/UI
  -> Vectorize query
  -> LLM answer

Optional embedder service
  -> stable POST /embed API
  -> hides provider choice from both ingestion and online query code
```

The key decision to test later is whether the separate embedder service is worth the additional network hop and deployment surface. It is valuable if multiple systems need the same embedding API or if we expect to switch embedding providers often. It is unnecessary if only this agent uses embeddings and the ingestion pipeline can call the provider directly.
