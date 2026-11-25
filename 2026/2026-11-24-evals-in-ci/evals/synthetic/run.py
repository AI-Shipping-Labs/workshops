"""Run the FAQ agent on the eval questions and save answers + trajectories.

Each question is a live multi-step loop that calls the `search` tool and
reacts to the results, so questions can't be bundled into offline requests.
We run them concurrently (default concurrency=5) and, for every question,
record the agent's final answer plus its trajectory — the sequence of
tool calls it made (name, arguments, and results) and how many iterations
it took.

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

import agent  # noqa: E402
from agent import run_agent  # noqa: E402
from pricing import request_cost, require_prices  # noqa: E402
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


class UsageTracker:
    """Wraps the OpenAI client and records the token usage and cost of every
    Responses API call the agent makes.

    It works without changes to agent.py (so it also measures the baseline
    version in CI): the agent only sees an object with `.responses.stream`
    and `.responses.create`, everything else passes through.
    """

    def __init__(self, client: AsyncOpenAI):
        self._client = client
        self.calls: list[dict] = []
        self.responses = _TrackedResponses(client.responses, self)

    def __getattr__(self, name):
        return getattr(self._client, name)

    def record(self, model: str, response) -> None:
        usage = getattr(response, "usage", None)
        details = getattr(usage, "input_tokens_details", None)
        u = {
            "input": getattr(usage, "input_tokens", 0) or 0,
            "cached": getattr(details, "cached_tokens", 0) or 0,
            "output": getattr(usage, "output_tokens", 0) or 0,
        }
        # Price by the model name the agent requested (the response may
        # report a dated snapshot name).
        self.calls.append({"model": model, "usage": u, "cost_usd": request_cost(model, u)})

    def summary(self) -> dict:
        total = {"input": 0, "cached": 0, "output": 0}
        for call in self.calls:
            for key in total:
                total[key] += call["usage"][key]
        return {
            "models": sorted({c["model"] for c in self.calls}),
            "requests": len(self.calls),
            "tokens": total,
            "cost_usd": sum(c["cost_usd"] for c in self.calls),
        }


class _TrackedResponses:
    def __init__(self, responses, tracker: UsageTracker):
        self._responses = responses
        self._tracker = tracker

    def __getattr__(self, name):
        return getattr(self._responses, name)

    async def create(self, **kwargs):
        response = await self._responses.create(**kwargs)
        self._tracker.record(kwargs.get("model"), response)
        return response

    def stream(self, **kwargs):
        return _TrackedStream(self._responses.stream(**kwargs), kwargs.get("model"), self._tracker)


class _TrackedStream:
    def __init__(self, manager, model: str, tracker: UsageTracker):
        self._manager = manager
        self._model = model
        self._tracker = tracker
        self._stream = None

    async def __aenter__(self):
        self._stream = await self._manager.__aenter__()
        return self._stream

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._tracker.record(self._model, await self._stream.get_final_response())
        return await self._manager.__aexit__(exc_type, exc, tb)


async def run_agent_on_row(client: AsyncOpenAI, row: dict) -> dict:
    """Run the agent on a single question row and capture answer, trajectory and cost."""
    renderer = TrajectoryRenderer()
    tracker = UsageTracker(client)
    try:
        answer = await run_agent(tracker, row["question"], renderer)
        return {
            "input": row,
            "rag_response": {"answer": answer},
            "tools": renderer.tools,
            "iterations": renderer.iterations,
            "agent_usage": tracker.summary(),
        }
    except Exception as exc:
        return {
            "input": row,
            "rag_response": {"answer": f"Agent error: {exc}"},
            "tools": renderer.tools,
            "iterations": renderer.iterations,
            "agent_usage": tracker.summary(),
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
    print(f"  Agent model         : {agent.MODEL_NAME}")
    print(f"  Agent cost          : ${sum(r['agent_usage']['cost_usd'] for r in results):.5f}")
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
    require_prices(agent.MODEL_NAME)

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
