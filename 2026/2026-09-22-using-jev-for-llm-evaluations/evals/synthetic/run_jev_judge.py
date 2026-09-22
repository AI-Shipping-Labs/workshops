"""Judge an agent eval run with Jev through OpenRouter.

Usage:
    uv run python -m evals.synthetic.run_jev_judge --limit 5
    uv run python -m evals.synthetic.run_jev_judge --data path/to/evals_run.json

Jev returns typed decisions and probabilities, not written reasoning. Each
eval entry is one state with the three shared checks from judge_common as
its questions. Independent entries use separate requests, run concurrently.
"""

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from evals.synthetic.judge_common import (
    CHECKS,
    add_common_args,
    base_report,
    build_decision_request,
    default_output,
    load_entries,
    parse_choice_answer,
    print_summary,
    render_checks_report,
    write_outputs,
)
from evals.utils import fmt_time, map_progress

MODEL = "~typesafe/jev-latest"
ENDPOINT = "https://openrouter.ai/api/alpha/decisions"


class EvaluationError(Exception):
    def __init__(self, message: str, attempts: int):
        super().__init__(message)
        self.attempts = attempts


def prepare_jev_request(entry: dict) -> dict:
    """Build the complete JSON body for one eval entry without a network call."""
    return {"model": MODEL, **build_decision_request(entry)}


def send_jev_request(payload: dict, api_key: str) -> tuple[dict, int]:
    """Send a prepared request and return the response plus HTTP attempt count."""
    for attempt in range(3):
        try:
            response = requests.post(
                ENDPOINT,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=90,
            )
            if response.status_code in (429, 502, 503, 504) and attempt < 2:
                time.sleep(2**attempt)
                continue
            if not response.ok:
                hint = (
                    " Retry later." if response.status_code in (429, 502, 503, 504) else ""
                )
                raise EvaluationError(
                    f"OpenRouter HTTP {response.status_code} after {attempt + 1} attempt(s).{hint}",
                    attempt + 1,
                )
            return response.json(), attempt + 1
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt == 2:
                raise EvaluationError(
                    f"OpenRouter connection failed after 3 attempts: {exc}", 3
                ) from exc
            time.sleep(2**attempt)
    raise EvaluationError("OpenRouter request failed after 3 attempts", 3)


async def judge_indexed(
    item: tuple[int, dict], api_key: str
) -> tuple[int, dict, dict]:
    index, entry = item
    judged = dict(entry)
    try:
        payload = prepare_jev_request(entry)
        result, attempts = await asyncio.to_thread(send_jev_request, payload, api_key)
        answers = result["answers"]
        judged.update({
            check["result_key"]: parse_choice_answer(answers[name], name)
            for name, check in CHECKS.items()
        })
        judged["jev_evaluation"] = {"model": result.get("model", MODEL)}
        usage = result.get("usage") or {}
        metadata = {
            "model": result.get("model", MODEL),
            "entries": 1,
            "http_attempts": attempts,
            "usage": {
                "input": usage.get("input_tokens", 0) or 0,
                "output": usage.get("output_tokens", 0) or 0,
            },
            "cost_usd": float(usage["cost"]) if usage.get("cost") is not None else None,
        }
        return index, judged, metadata
    except EvaluationError as exc:
        error = str(exc)
        attempts = exc.attempts
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        error = str(exc)
        attempts = 1
    for check in CHECKS.values():
        judged[check["result_key"]] = {"score": "error", "error": error}
    judged["jev_evaluation"] = {"model": MODEL, "error": error}
    metadata = {"model": MODEL, "entries": 1, "http_attempts": attempts, "error": error}
    return index, judged, metadata


def build_report(
    entries: list[dict], evaluations: list[dict], http_attempts: int,
    elapsed: float, source: Path, output: Path,
) -> dict:
    report = base_report(MODEL, source, output, entries, elapsed)
    costs = [item.get("cost_usd") for item in evaluations if item.get("cost_usd") is not None]
    report.update({
        "requests": len(evaluations),
        "http_attempts": http_attempts,
        "failed_requests": sum("error" in item for item in evaluations),
        # Preserve OpenRouter's usage values verbatim.
        "tokens": {
            "input": sum(item.get("usage", {}).get("input", 0) for item in evaluations),
            "output": sum(item.get("usage", {}).get("output", 0) for item in evaluations),
        },
        "openrouter_cost_usd": (
            round(sum(costs), 10) if len(costs) == len(evaluations) else None
        ),
        "token_usage_note": (
            "Token counts and billed cost are reported by OpenRouter. Jev returns typed "
            "decisions without generated prose; its output token metric is not a "
            "text-generation count. Cost is taken from usage.cost, not calculated here."
        ),
        "evaluations": evaluations,
    })
    return report


def openai_comparison(source, entry_count: int) -> dict | None:
    path = source.with_name(source.stem + "_judged_report.json")
    if not path.exists():
        return None
    report = json.loads(path.read_text())
    if report.get("entries") != entry_count or Path(report.get("source", "")).resolve() != source.resolve():
        return None
    standard_cost = report.get("cost_usd", {}).get("standard")
    if standard_cost is None:
        return None
    return {
        "model": report.get("model"),
        "standard_cost_usd": standard_cost,
        "report": str(path),
    }


def render_report(report: dict) -> str:
    cost = report["openrouter_cost_usd"]
    stat_lines = [
        f"- Entries / requests: {report['entries']} / {report['requests']}",
        f"- HTTP attempts (including retries): {report['http_attempts']}",
        f"- Failed requests: {report['failed_requests']}",
        f"- Elapsed: {fmt_time(report['elapsed_seconds'])}",
        f"- OpenRouter-reported input tokens: {report['tokens']['input']:,}",
        f"- OpenRouter-reported output token metric: {report['tokens']['output']:,}",
        f"- OpenRouter cost (USD): {cost if cost is not None else 'unavailable'}",
        f"- Usage note: {report['token_usage_note']}",
    ]
    sections = []
    if report.get("openai_comparison"):
        comparison = report["openai_comparison"]
        jev_cost = (
            f"${report['openrouter_cost_usd']:.6f}"
            if report["openrouter_cost_usd"] is not None else "unavailable"
        )
        sections.append("\n".join([
            "## Cost comparison",
            "",
            "| Judge | Cost (USD) |",
            "| --- | ---: |",
            f"| Jev (OpenRouter reported) | {jev_cost} |",
            f"| OpenAI `{comparison['model']}` (saved standard-tier report) "
            f"| ${comparison['standard_cost_usd']:.6f} |",
            "",
            f"OpenAI source report: `{comparison['report']}`.",
        ]))
    return render_checks_report(
        "Jev judge report",
        report,
        stat_lines,
        sections=sections,
        closing="Jev returns scores and probabilities without written reasoning.",
    )


async def run(args: argparse.Namespace, api_key: str) -> None:
    source = Path(args.data)
    entries = load_entries(source, args.limit)
    print(
        f"Judging {len(entries)} entries with {MODEL}: 3 questions per request, "
        f"concurrency={args.concurrency}."
    )

    started = time.perf_counter()
    indexed = await map_progress(
        list(enumerate(entries)),
        lambda item: judge_indexed(item, api_key),
        max_concurrency=args.concurrency,
    )
    ordered = sorted(indexed, key=lambda item: item[0])
    judged = [entry for _, entry, _ in ordered]
    evaluations = [metadata for _, _, metadata in ordered]
    http_attempts = sum(item["http_attempts"] for item in evaluations)
    elapsed = time.perf_counter() - started

    output = Path(args.output) if args.output else default_output(source, "jev")
    report = build_report(judged, evaluations, http_attempts, elapsed, source, output)
    report["openai_comparison"] = openai_comparison(source, len(entries))
    report_md_path = write_outputs(judged, report, render_report(report), output)
    print_summary(report, report_md_path)
    print(f"Requests: {report['requests']}; HTTP attempts: {report['http_attempts']}; "
          f"failed: {report['failed_requests']}; time: {fmt_time(elapsed)}")
    cost = report["openrouter_cost_usd"]
    print(f"Jev OpenRouter cost: ${cost:.6f}" if cost is not None else "Jev OpenRouter cost: unavailable")
    if report["openai_comparison"]:
        comparison = report["openai_comparison"]
        print(f"OpenAI {comparison['model']} standard-tier cost (saved report): "
              f"${comparison['standard_cost_usd']:.6f}")
    if report["failed_requests"]:
        raise SystemExit(f"{report['failed_requests']} Jev evaluation request(s) failed; see {output}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    parser.add_argument("--concurrency", type=int, default=5, help="Parallel entries (default: 5).")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be nonnegative")
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")

    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPEN_ROUTER_API_KEY")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY is not set (put it in .env).")
    asyncio.run(run(args, api_key))


if __name__ == "__main__":
    main()
