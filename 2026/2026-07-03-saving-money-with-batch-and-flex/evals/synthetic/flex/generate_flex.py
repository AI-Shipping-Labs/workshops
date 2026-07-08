"""Generate synthetic questions in parallel over the Flex tier, with token + cost tracking.

Same generation as `evals/synthetic/generate.py` (5 questions per sampled FAQ doc),
but every request goes through `service_tier="flex"` (Batch-level pricing, real time)
and runs concurrently. For each request we record input / cached / output tokens, and
at the end we sum them up and compute how much the whole run cost.

Caching note: across DIFFERENT documents the only shared prompt prefix is the
instructions (~370 tokens), which is below the ~1024-token prompt-cache minimum, so
`cached_tokens` will usually be 0 here. The cached column is still tracked and priced
correctly — it just won't light up unless the shared prefix is large.

Run (debug on 10 docs -> 50 questions, then scale up):
    uv run python -m evals.synthetic.flex.generate_flex --num-docs 10
    uv run python -m evals.synthetic.flex.generate_flex --num-docs 100 --concurrency 10

Docs: https://developers.openai.com/api/docs/guides/flex-processing
"""

import argparse
import asyncio
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import AsyncOpenAI, RateLimitError

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from evals.synthetic.generate import (  # noqa: E402
    DEFAULT_NUM_DOCS,
    INSTRUCTIONS,
    MODEL_NAME,
    QUESTIONS_PER_DOC,
    QuestionsResponse,
    create_user_prompt,
    load_documents,
    sample_documents,
)
from evals.utils import map_progress  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"
FLEX_TIMEOUT = 900.0
MAX_FLEX_RETRIES = 4

# gpt-5.4-mini prices per 1M tokens (source: OpenAI pricing page).
# Flex bills at Batch rates (50% of standard); cached input is a further discount.
PRICES = {
    "flex":     {"input": 0.375, "cached": 0.0375, "output": 2.25},
    "standard": {"input": 0.75,  "cached": 0.075,  "output": 4.50},
}


async def parse_with_flex(client: AsyncOpenAI, **kwargs):
    """responses.parse with service_tier='flex', retrying 429s then falling back to auto."""
    for attempt in range(MAX_FLEX_RETRIES):
        try:
            return await client.responses.parse(service_tier="flex", **kwargs)
        except RateLimitError:
            await asyncio.sleep(2 ** attempt)
    return await client.responses.parse(service_tier="auto", **kwargs)


async def generate_for_document(client, doc, num_questions):
    prompt = create_user_prompt(doc, num_questions)
    resp = await parse_with_flex(
        client,
        model=MODEL_NAME,
        instructions=INSTRUCTIONS,
        input=prompt,
        text_format=QuestionsResponse,
    )
    u = resp.usage
    usage = {
        "input": u.input_tokens,
        "cached": u.input_tokens_details.cached_tokens,
        "output": u.output_tokens,
    }

    parsed = resp.output_parsed
    rows = []
    for q in (parsed.questions if parsed else []):
        rows.append({
            "question": q.user_question,
            "reference_answer": q.reference_answer,
            "line_number_start": q.line_number_start,
            "line_number_end": q.line_number_end,
            "question_type": q.question_type,
            "doc_id": doc.get("id"),
            "section": doc.get("section"),
            "source_question": doc.get("question"),
        })
    return rows, usage


def cost(totals: dict, tier: str) -> float:
    p = PRICES[tier]
    uncached = totals["input"] - totals["cached"]
    return (uncached / 1e6) * p["input"] + (totals["cached"] / 1e6) * p["cached"] + (totals["output"] / 1e6) * p["output"]


def report(totals: dict, n_requests: int, n_cached_hits: int, n_questions: int):
    flex_cost = cost(totals, "flex")
    std_cost = cost(totals, "standard")

    print("\n" + "=" * 55)
    print("  FLEX GENERATION — TOKENS & COST")
    print("=" * 55)
    print(f"  Requests            : {n_requests}")
    print(f"  Questions generated : {n_questions}")
    print(f"  Requests w/ cache   : {n_cached_hits}")
    print("-" * 55)
    print(f"  Input tokens        : {totals['input']:>12,}")
    print(f"    of which cached   : {totals['cached']:>12,}")
    print(f"    uncached input    : {totals['input'] - totals['cached']:>12,}")
    print(f"  Output tokens       : {totals['output']:>12,}")
    print(f"  Total tokens        : {totals['input'] + totals['output']:>12,}")
    print("-" * 55)
    print(f"  Cost (flex tier)    : ${flex_cost:.5f}")
    print(f"  Would be (standard) : ${std_cost:.5f}   (flex saves ${std_cost - flex_cost:.5f})")
    print("=" * 55)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--num-docs", type=int, default=DEFAULT_NUM_DOCS)
    parser.add_argument("--num-questions", type=int, default=QUESTIONS_PER_DOC)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--output", type=str, default="questions_flex")
    args = parser.parse_args()

    load_dotenv()

    documents = load_documents()
    sample = sample_documents(documents, args.num_docs, args.seed)
    print(f"Loaded {len(documents)} FAQ docs; sampled {len(sample)} (seed={args.seed}).")
    print(f"Generating with concurrency={args.concurrency} over the flex tier...\n")

    client = AsyncOpenAI(timeout=FLEX_TIMEOUT)
    results = await map_progress(
        sample,
        lambda doc: generate_for_document(client, doc, args.num_questions),
        max_concurrency=args.concurrency,
    )

    all_rows = []
    totals = {"input": 0, "cached": 0, "output": 0}
    n_cached_hits = 0
    for rows, usage in results:
        all_rows.extend(rows)
        for k in totals:
            totals[k] += usage[k]
        if usage["cached"] > 0:
            n_cached_hits += 1

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(all_rows)
    csv_path = DATA_DIR / f"{args.output}.csv"
    json_path = DATA_DIR / f"{args.output}.json"
    df.to_csv(csv_path, index=False)
    df.to_json(json_path, orient="records", indent=2)
    print(f"\nSaved {len(df)} questions to {csv_path} and {json_path}")

    report(totals, n_requests=len(results), n_cached_hits=n_cached_hits, n_questions=len(all_rows))


if __name__ == "__main__":
    asyncio.run(main())
