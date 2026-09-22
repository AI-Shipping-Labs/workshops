"""Judge an eval run locally with the Laya typed-decisions checkpoint.

Usage:
    uv run --extra laya python -m evals.synthetic.run_laya_judge --limit 5

Each entry uses the same state and questions as the Jev judge (see
judge_common), scored locally instead of over the network: one `predict`
call per entry, three good/bad choices, no written reasoning.
"""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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
from evals.utils import fmt_time

MODEL = "convaiinnovations/laya"


def judge_entry(agent, entry: dict) -> tuple[dict, int]:
    """Score one entry locally; returns the per-check results and input tokens."""
    request = build_decision_request(entry)
    # Laya clips state tokens from the right. Reject oversized cases instead
    # of silently judging only the beginning of the state.
    max_len = agent.cfg.get("max_len", 1024)
    head_max_len = agent.cfg.get("head_max_len", 256)
    state_text = json.dumps(request["state"], ensure_ascii=False)
    state_tokens = len(agent.tok(state_text, add_special_tokens=False)["input_ids"])
    if state_tokens > max_len - head_max_len - 3:
        raise ValueError(
            f"input is {state_tokens} tokens; safe state budget is "
            f"{max_len - head_max_len - 3}. Shorten this case before judging."
        )
    result = agent.predict(request["state"], request["questions"])
    parsed = {
        check["result_key"]: parse_choice_answer(result["answers"][name], name)
        for name, check in CHECKS.items()
    }
    return parsed, result.get("usage", {}).get("input_tokens", 0)


def build_report(entries: list[dict], elapsed: float, source: Path, output: Path,
                 input_tokens: int, errors: int) -> dict:
    report = base_report(f"{MODEL}/typed-decisions", source, output, entries, elapsed)
    report.update({
        "checks_run": len(entries) * len(CHECKS),
        "failed_checks": errors,
        "input_tokens": input_tokens,
        "api_cost_usd": 0,
    })
    return report


def render_report(report: dict) -> str:
    stat_lines = [
        f"- Entries / checks: {report['entries']} / {report['checks_run']}",
        f"- Failed checks: {report['failed_checks']}",
        f"- Elapsed: {fmt_time(report['elapsed_seconds'])}",
        f"- Input tokens processed locally: {report['input_tokens']:,}",
        "- API cost: $0 (local compute and downloads still use resources)",
    ]
    return render_checks_report(
        "Laya judge report",
        report,
        stat_lines,
        closing="Laya returns choices and probabilities without written reasoning.",
    )


def run(args: argparse.Namespace) -> None:
    try:
        import laya
        import torch
    except ImportError as exc:
        raise SystemExit("Install the optional dependency with `uv sync --extra laya`.") from exc

    source = Path(args.data)
    entries = load_entries(source, args.limit)
    started = time.perf_counter()
    print(f"Loading local Laya checkpoint {MODEL}/typed-decisions...")
    agent = laya.load(MODEL, subfolder="typed-decisions", device=args.device)
    workers = args.workers or (min(6, max(1, (os.cpu_count() or 2) // 2))
                               if agent.device.type == "cpu" else 1)
    if workers > 1 and agent.device.type == "cpu":
        # The CPU is already saturated by independent inferences. One PyTorch
        # thread per worker avoids multiplying the thread count by six.
        torch.set_num_threads(1)
    print(f"Scoring {len(entries)} entries on {agent.device} with {workers} worker(s).")
    judged = [dict(entry) for entry in entries]
    errors = 0
    input_tokens = 0

    def score_job(index: int):
        try:
            return index, judge_entry(agent, entries[index]), None
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            return index, None, str(exc)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for completed, (index, result, error) in enumerate(pool.map(score_job, range(len(entries))), 1):
            if error is None:
                parsed, tokens = result
                judged[index].update(parsed)
            else:
                for check in CHECKS.values():
                    judged[index][check["result_key"]] = {"score": "error", "error": error}
                tokens = 0
                errors += len(CHECKS)
            input_tokens += tokens
            judged[index]["laya_evaluation"] = {
                "model": f"{MODEL}/typed-decisions",
                **({"error": error} if error else {}),
            }
            print(f"Judged {completed}/{len(entries)}", end="\r", flush=True)
    if entries:
        print()
    elapsed = time.perf_counter() - started

    output = Path(args.output) if args.output else default_output(source, "laya")
    report = build_report(judged, elapsed, source, output, input_tokens, errors)
    report_md_path = write_outputs(judged, report, render_report(report), output)
    print_summary(report, report_md_path)
    if errors:
        raise SystemExit(f"{errors} Laya check(s) failed; see {output}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_args(parser)
    parser.add_argument("--device", choices=("cpu", "cuda", "mps"), help="Laya device (default: auto).")
    parser.add_argument("--workers", type=int, help="Parallel entries (default: up to 6 on CPU, 1 on GPU).")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be nonnegative")
    if args.workers is not None and args.workers < 1:
        parser.error("--workers must be at least 1")
    run(args)


if __name__ == "__main__":
    main()
