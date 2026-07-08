"""Run the FAQ agent on the synthetic questions and save answers + trajectories.

This can't use the Batch API: the agent is a multi-step loop that calls the
`search` tool and reacts to results, so each question needs live back-and-forth
requests. We run them concurrently (default concurrency=5) and, for every
question, record the agent's final answer plus its trajectory — the sequence of
tool calls it made (name, arguments, and results) and how many iterations it took.

Output is a dated JSON file, e.g.:
    evals/synthetic/data/evals_run_2026_07_02_143000_synthetic.json

Usage:
    uv run python -m evals.synthetic.run
    uv run python -m evals.synthetic.run --limit 5 --concurrency 3

Adapted from:
    https://github.com/alexeygrigorev/ai-engineering-buildcamp-code/blob/main/documentation-agent/evals/synthetic/run.py
"""

import argparse
import asyncio
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Make project-root modules importable whether run as a module or a script.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from agent import run_agent  # noqa: E402
from renderer import BaseRenderer  # noqa: E402
from search import init_index  # noqa: E402

from evals.utils import fmt_time, map_progress  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"


class TrajectoryRenderer(BaseRenderer):
    """Collects the agent's answer and its full tool-call trajectory."""

    def __init__(self):
        self.answer_parts: list[str] = []
        self.tools: list[dict] = []
        self.iterations = 0

    async def handle_token(self, payload):
        self.answer_parts.append(payload["delta"])

    async def handle_iteration(self, payload):
        self.iterations = payload["n"]

    async def handle_tool_call(self, payload):
        self.tools.append({
            "name": payload["name"],
            "args": payload["arguments"],
            "result": None,
        })

    async def handle_tool_result(self, payload):
        if self.tools:
            self.tools[-1]["result"] = payload["result"]

    @property
    def answer(self) -> str:
        return "".join(self.answer_parts)


async def run_agent_on_row(client: AsyncOpenAI, row: dict) -> dict:
    """Run the agent on a single question row and capture answer + trajectory."""
    renderer = TrajectoryRenderer()
    try:
        answer = await run_agent(client, row["question"], renderer)
        return {
            "input": row,
            "rag_response": {"answer": answer},
            "tools": renderer.tools,
            "iterations": renderer.iterations,
        }
    except Exception as exc:
        return {
            "input": row,
            "rag_response": {"answer": f"Agent error: {exc}"},
            "tools": renderer.tools,
            "iterations": renderer.iterations,
            "error": str(exc),
        }


def report(results: list[dict], elapsed: float) -> None:
    total = len(results)
    errors = sum(1 for r in results if "error" in r)
    total_tools = sum(len(r["tools"]) for r in results)
    no_tools = sum(1 for r in results if not r["tools"])

    print("\n" + "=" * 55)
    print("  AGENT RUN RESULTS")
    print("=" * 55)
    print(f"  Total questions     : {total}")
    print(f"  Agent errors        : {errors}")
    print(f"  Questions w/o tools : {no_tools}")
    print(f"  Total tool calls    : {total_tools}")
    print(f"  Avg tool calls/q    : {total_tools / total:.2f}" if total else "")
    print(f"  Total time          : {fmt_time(elapsed)}")
    print("=" * 55)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run the FAQ agent on synthetic questions.")
    parser.add_argument("--questions", default=str(DATA_DIR / "questions_sample.csv"),
                        help="Path to the generated questions CSV.")
    parser.add_argument("--output", default=None,
                        help="Output JSON path (default: data/evals_run_<timestamp>_synthetic.json).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Run on a random subset of N questions.")
    parser.add_argument("--concurrency", type=int, default=5,
                        help="Number of parallel agent calls (default: 5).")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed used when --limit samples a subset.")
    args = parser.parse_args()

    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set (put it in .env).")

    print(f"Loading questions from {args.questions}...")
    df = pd.read_csv(args.questions)
    df = df.where(pd.notna(df), None)  # NaN -> None for clean JSON
    rows = df.to_dict(orient="records")
    print(f"  -> {len(rows)} questions loaded.")

    if args.limit is not None:
        k = min(args.limit, len(rows))
        rows = random.Random(args.seed).sample(rows, k)
        print(f"  -> Sampling {k} random questions (--limit {args.limit}, seed {args.seed}).")

    print("Initializing search index...")
    init_index()
    client = AsyncOpenAI()

    print(f"\nRunning {len(rows)} questions with concurrency={args.concurrency}...")
    t_start = time.perf_counter()
    results = await map_progress(
        rows,
        lambda row: run_agent_on_row(client, row),
        max_concurrency=args.concurrency,
    )
    elapsed = time.perf_counter() - t_start

    if args.output:
        output_path = Path(args.output)
    else:
        stamp = datetime.now().strftime("%Y_%m_%d_%H%M%S")
        output_path = DATA_DIR / f"evals_run_{stamp}_synthetic.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    import json
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {output_path}")

    report(results, elapsed)


if __name__ == "__main__":
    asyncio.run(main())
