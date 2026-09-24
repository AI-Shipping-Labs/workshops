"""Score an agent eval run with the LLM judge over ordinary Responses API calls.

The OpenAI baseline judge: same three checks as the typed-decision judges
(answer correctness, instruction following, trajectory optimality), but with
written reasoning per check via `responses.parse` structured outputs.

The run prints token totals and the cost, and writes a report next to the
judged file; the Jev judge reads it to compare costs.

Usage:
    uv run python -m evals.synthetic.run_judge --limit 10
    uv run python -m evals.synthetic.run_judge --data evals/synthetic/data/evals_run_sample.json
"""

import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

from evals.synthetic.judge import CHECKS, JUDGE_MODEL
from evals.synthetic.judge_common import DEFAULT_DATA, load_entries
from evals.utils import fmt_time, map_progress

# gpt-5.4-mini, USD per 1M tokens.
# https://developers.openai.com/api/docs/models/gpt-5.4-mini
PRICES = {"standard": {"input": 0.75, "cached": 0.075, "output": 4.50}}


def empty_usage() -> dict:
    return {"input": 0, "cached": 0, "output": 0, "reasoning": 0}


def usage_of(response) -> dict:
    usage = getattr(response, "usage", None)
    if usage is None:
        return empty_usage()
    details = getattr(usage, "input_tokens_details", None)
    output_details = getattr(usage, "output_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) if details is not None else 0
    reasoning = getattr(output_details, "reasoning_tokens", 0) if output_details is not None else 0
    return {
        "input": usage.input_tokens or 0,
        "cached": cached or 0,
        "output": usage.output_tokens or 0,
        "reasoning": reasoning or 0,
    }


def add_usage(total: dict, usage: dict) -> None:
    for key in total:
        total[key] += usage.get(key, 0)


def cost_usd(usage: dict, tier: str) -> float:
    prices = PRICES[tier]
    cached = min(usage["cached"], usage["input"])
    uncached = usage["input"] - cached
    return (
        uncached * prices["input"]
        + cached * prices["cached"]
        + usage["output"] * prices["output"]
    ) / 1_000_000


def costs_usd(usage: dict) -> dict:
    return {tier: cost_usd(usage, tier) for tier in PRICES}


async def judge_indexed(client: AsyncOpenAI, item: tuple[int, dict]) -> tuple[int, dict]:
    index, entry = item
    return index, await judge_entry(client, entry)


async def judge_entry(client: AsyncOpenAI, entry: dict) -> dict:
    judged = dict(entry)
    for check in CHECKS:
        try:
            response = await client.responses.parse(
                model=JUDGE_MODEL,
                instructions=check["instructions"],
                input=check["format"](entry),
                text_format=check["model"],
            )
            parsed = response.output_parsed
            if parsed is None:
                result = {
                    "reasoning": "Judge returned no parsed output.",
                    "score": "bad",
                }
            else:
                result = parsed.model_dump()
            result["usage"] = usage_of(response)
            tier = getattr(response, "service_tier", None)
            if tier:
                result["service_tier"] = tier
            judged[check["result_key"]] = result
        except Exception as exc:
            judged[check["result_key"]] = {
                "reasoning": f"Error: {exc}",
                "score": "bad",
                "usage": empty_usage(),
            }
    return judged


def _check_usage(entry: dict, check: dict) -> dict:
    raw = entry.get(check["result_key"], {}).get("usage") or {}
    usage = empty_usage()
    add_usage(usage, raw)
    return usage


def build_report(entries: list[dict], elapsed: float, data_path: Path, output_path: Path) -> dict:
    total = len(entries)
    overall = empty_usage()
    tiers = sorted({
        entry.get(check["result_key"], {}).get("service_tier")
        for entry in entries
        for check in CHECKS
        if entry.get(check["result_key"], {}).get("service_tier")
    })
    checks = []
    for check in CHECKS:
        usage = empty_usage()
        good = 0
        requests = 0
        for entry in entries:
            result = entry.get(check["result_key"], {})
            if "usage" in result or "score" in result:
                requests += 1
            if result.get("score") == "good":
                good += 1
            add_usage(usage, _check_usage(entry, check))
        add_usage(overall, usage)
        checks.append({
            "name": check["name"],
            "good": good,
            "bad": total - good,
            "requests": requests,
            "tokens": usage,
            "cost_usd": costs_usd(usage),
        })

    return {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": JUDGE_MODEL,
        "service_tier": "standard",
        "observed_service_tiers": tiers,
        "prices_per_1m_usd": PRICES,
        "source": str(data_path),
        "judged_results": str(output_path),
        "entries": total,
        "requests": sum(item["requests"] for item in checks),
        "elapsed_seconds": round(elapsed, 3),
        "tokens": overall,
        "cost_usd": costs_usd(overall),
        "checks": checks,
    }


def _money(value: float) -> str:
    return f"${value:.5f}"


def render_report(report: dict) -> str:
    tokens = report["tokens"]
    uncached = tokens["input"] - min(tokens["cached"], tokens["input"])
    lines = [
        "# Judge report",
        "",
        f"Standard Responses API run of `{report['model']}` on {report['created_at']}.",
        "Cost is what this run spends at the gpt-5.4-mini standard list rates.",
        "",
        "## Run",
        "",
        f"- Source: `{report['source']}`",
        f"- Judged results: `{report['judged_results']}`",
        f"- Entries: {report['entries']}",
        f"- Judge requests: {report['requests']}",
        f"- Elapsed: {fmt_time(report['elapsed_seconds'])}",
        f"- Observed service tier: {', '.join(report['observed_service_tiers']) or 'n/a'}",
        "",
        "## Scores",
        "",
        "| Check | Good | Bad | Good % |",
        "| --- | ---: | ---: | ---: |",
    ]
    for check in report["checks"]:
        pct = (check["good"] / report["entries"] * 100) if report["entries"] else 0
        lines.append(
            f"| {check['name']} | {check['good']} | {check['bad']} | {pct:.0f}% |"
        )
    lines.extend([
        "",
        "## Tokens",
        "",
        "| | Tokens |",
        "| --- | ---: |",
        f"| Input | {tokens['input']:,} |",
        f"| Cached input | {tokens['cached']:,} |",
        f"| Uncached input | {uncached:,} |",
        f"| Output | {tokens['output']:,} |",
        f"| Reasoning (included in output) | {tokens['reasoning']:,} |",
        "",
        "## Cost",
        "",
        "USD, using the gpt-5.4-mini list prices stored in this report.",
        "",
        "| Tier | This run |",
        "| --- | ---: |",
        f"| Standard (actual) | {_money(report['cost_usd']['standard'])} |",
        "",
        "### By check, standard tier",
        "",
        "| Check | Input | Cached | Output | Cost |",
        "| --- | ---: | ---: | ---: | ---: |",
    ])
    for check in report["checks"]:
        usage = check["tokens"]
        lines.append(
            f"| {check['name']} | {usage['input']:,} | {usage['cached']:,} | "
            f"{usage['output']:,} | {_money(check['cost_usd']['standard'])} |"
        )
    lines.append("")
    return "\n".join(lines)


def print_report(report: dict) -> None:
    tokens = report["tokens"]
    uncached = tokens["input"] - min(tokens["cached"], tokens["input"])
    print("\n" + "=" * 55)
    print("  JUDGE CHECK RESULTS")
    print("=" * 55)
    print(f"  Entries             : {report['entries']}")
    print(f"  Judge requests      : {report['requests']}")
    print("-" * 55)
    for check in report["checks"]:
        pct = (check["good"] / report["entries"] * 100) if report["entries"] else 0
        print(
            f"  {check['name']:<22s}  good: {check['good']}  "
            f"bad: {check['bad']}  ({pct:.0f}% good)"
        )
    print("-" * 55)
    print(f"  Input tokens        : {tokens['input']:>12,}")
    print(f"    of which cached   : {tokens['cached']:>12,}")
    print(f"    uncached input    : {uncached:>12,}")
    print(f"  Output tokens       : {tokens['output']:>12,}")
    print(f"    of which reasoning: {tokens['reasoning']:>12,}")
    print("-" * 55)
    print(f"  Cost (standard)     : {_money(report['cost_usd']['standard'])}")
    print("=" * 55)


def write_report(report: dict, output_path: Path) -> tuple[Path, Path]:
    report_json = output_path.with_name(output_path.stem + "_report.json")
    report_md = output_path.with_name(output_path.stem + "_report.md")
    report_json.write_text(json.dumps(report, indent=2) + "\n")
    report_md.write_text(render_report(report))
    return report_json, report_md


async def run(args) -> None:
    data_path = Path(args.data)
    entries = load_entries(data_path, args.limit)
    print(f"Loaded {len(entries)} entries from {data_path}.")
    print(f"Judging with {JUDGE_MODEL} on the standard Responses API "
          f"({len(CHECKS)} checks each, concurrency={args.concurrency}).")

    client = AsyncOpenAI()
    t_start = time.perf_counter()
    indexed = await map_progress(
        list(enumerate(entries)),
        lambda item: judge_indexed(client, item),
        max_concurrency=args.concurrency,
    )
    judged = [entry for _, entry in sorted(indexed, key=lambda pair: pair[0])]
    elapsed = time.perf_counter() - t_start

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = data_path.with_name(data_path.stem + "_judged.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(judged, indent=2, default=str))

    summary = build_report(judged, elapsed, data_path, output_path)
    report_json, report_md = write_report(summary, output_path)
    print(f"\nSaved judged results to {output_path}")
    print(f"Saved report to {report_md}")
    print(f"Saved report data to {report_json}")
    print(f"Total time: {fmt_time(elapsed)}")
    print_report(summary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=str(DEFAULT_DATA),
                        help="Path to an evals_run_*.json file.")
    parser.add_argument("--output", default=None,
                        help="Output JSON path (default: <data>_judged.json).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only judge the first N entries.")
    parser.add_argument("--concurrency", type=int, default=5,
                        help="Parallel entries to judge (default: 5).")
    args = parser.parse_args()

    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set (put it in .env).")

    asyncio.run(run(args))


if __name__ == "__main__":
    main()
