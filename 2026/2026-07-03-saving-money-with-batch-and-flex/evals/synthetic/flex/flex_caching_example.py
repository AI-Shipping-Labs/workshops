"""Flex processing + prompt caching, demonstrated on ONE synthetic-gen example.

This is a focused demo, not a full runner. It shows two things working together:

  1. Prompt caching — we build ONE large, stable prompt prefix (the generation
     instructions + a single FAQ document with line numbers). Only a short tail
     varies between requests, so the big prefix is identical every time.
  2. Flex processing — every request is sent with `service_tier="flex"` (Batch-
     level pricing, real-time). Flex can return 429 "resource unavailable", so we
     retry with backoff and fall back to `service_tier="auto"` as a last resort.

The first request populates the cache (cached_tokens = 0). Subsequent requests
reuse the prefix, so you'll see cached_tokens jump to (most of) the prefix size.

Prompt caching only applies to prompts above ~1024 tokens, so we deliberately
pick the longest FAQ answer to make the shared prefix comfortably large.

Run:
    uv run python -m evals.synthetic.flex.flex_caching_example
    uv run python -m evals.synthetic.flex.flex_caching_example --requests 5

Docs:
    https://developers.openai.com/api/docs/guides/flex-processing
"""

import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

# Make project-root + eval modules importable when run as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from evals.synthetic.generate import (  # noqa: E402
    INSTRUCTIONS,
    MODEL_NAME,
    QUESTIONS_PER_DOC,
    QuestionsResponse,
    add_line_numbers,
    load_documents,
)

FLEX_TIMEOUT = 900.0  # 15 min, recommended for flex (default is 10 min)
MAX_FLEX_RETRIES = 4


def build_input(numbered_doc: str, num_questions: int, attempt: int) -> str:
    """Big stable prefix (numbered_doc) + a short varying tail.

    Keeping the variation at the END means the prefix is byte-identical across
    requests, which is what lets prompt caching kick in.
    """
    return (
        f"{numbered_doc}\n\n"
        "---\n"
        f"Generation attempt #{attempt}. Generate {num_questions} realistic "
        "student questions for the document above."
    )


def parse_with_flex(client: OpenAI, **kwargs):
    """responses.parse with service_tier='flex', retrying 429s, then falling back to auto."""
    for attempt in range(MAX_FLEX_RETRIES):
        try:
            return client.responses.parse(service_tier="flex", **kwargs)
        except RateLimitError:
            wait = 2 ** attempt
            print(f"    (429 flex unavailable — retrying in {wait}s)")
            time.sleep(wait)
    print("    (flex still unavailable — falling back to service_tier='auto')")
    return client.responses.parse(service_tier="auto", **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=4,
                        help="How many flex requests to send with the shared prefix.")
    parser.add_argument("--num-questions", type=int, default=QUESTIONS_PER_DOC)
    args = parser.parse_args()

    load_dotenv()

    # One example: the longest FAQ answer, so the shared prefix clears the
    # ~1024-token prompt-cache minimum.
    documents = load_documents()
    doc = max(documents, key=lambda d: len(d["answer"]))
    numbered_doc = add_line_numbers(doc["answer"])
    print(f"Using doc id={doc['id']} | section={doc['section']}")
    print(f"Shared prefix ≈ instructions + document (~{(len(INSTRUCTIONS) + len(numbered_doc)) // 4} tokens)\n")

    client = OpenAI(timeout=FLEX_TIMEOUT)

    print(f"{'#':>2}  {'tier':>5}  {'input':>6}  {'cached':>6}  {'output':>6}  {'time':>6}")
    print("-" * 48)
    for i in range(1, args.requests + 1):
        input_text = build_input(numbered_doc, args.num_questions, i)
        t0 = time.perf_counter()
        resp = parse_with_flex(
            client,
            model=MODEL_NAME,
            instructions=INSTRUCTIONS,
            input=input_text,
            text_format=QuestionsResponse,
        )
        elapsed = time.perf_counter() - t0

        u = resp.usage
        cached = u.input_tokens_details.cached_tokens
        note = "  <- cache populated" if i == 1 else f"  <- {cached / u.input_tokens * 100:.0f}% of input cached"
        print(f"{i:>2}  {resp.service_tier:>5}  {u.input_tokens:>6}  {cached:>6}  {u.output_tokens:>6}  {elapsed:>5.1f}s{note}")

    print("\nNote: request #1 is a cache miss (cached=0); later requests reuse the")
    print("shared prefix, so cached_tokens covers most of the input at ~Batch pricing.")


if __name__ == "__main__":
    main()
