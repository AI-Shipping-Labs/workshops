"""Shared plumbing for the typed-decision judges (Jev and Laya).

Both judges run the same three good/bad checks over an eval run — answer
correctness, instruction following, and trajectory optimality — and produce
the same outputs: `<input>_<judge>_judged.json` plus a JSON and Markdown
report. This module holds what they share: the check definitions, answer
parsing, report building and rendering, and CLI/output helpers.

The OpenAI baseline judge (run_judge.py) answers the same three checks but
returns written reasoning, so it keeps its own prompts in judge.py; the check
names and result keys still match.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from evals.utils import fmt_time

# Import the agent's real system prompt so the instruction check sees exactly
# what the agent was told to do.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agent import INSTRUCTIONS as AGENT_INSTRUCTIONS  # noqa: E402

DATA_DIR = Path(__file__).parent / "data"
DEFAULT_DATA = DATA_DIR / "evals_run_sample.json"

# The three checks every judge runs, with the canonical wording. Jev sends
# `instructions` and `criteria` as one choice question per check; Laya sends
# the same fields to its local pipeline. `result_key` is the field added to
# each judged entry.
CHECKS = {
    "correctness": {
        "result_key": "judge_answer_correctness",
        "instructions": (
            "Compare agent_answer with reference_answer for user_question. "
            "Judge meaning, not wording. Extra correct detail is fine, but all "
            "key facts in the reference answer must be covered."
        ),
        "criteria": {
            "good": "The answer conveys all key facts in the reference answer.",
            "bad": "The answer misses a key fact, contradicts the reference, or is wrong.",
        },
    },
    "instruction": {
        "result_key": "judge_instruction_following",
        "instructions": (
            "Check agent_answer and tool_calls against agent_instructions. The "
            "agent must call search and end with a Sources section containing "
            "lines like '- [id] section > question'. If the answer correctly "
            "says the FAQ has no answer, sources may be absent. Do not require "
            "search results; they may be omitted from the state."
        ),
        "criteria": {
            "good": "The visible answer and tool calls follow the agent instructions.",
            "bad": "A concrete instruction is violated, such as no search or missing Sources.",
        },
    },
    "trajectory": {
        "result_key": "judge_trajectory",
        "instructions": (
            "Judge only whether tool_calls searched the FAQ for user_question. "
            "One to three distinct relevant searches is normal. Do not judge "
            "the final answer or unseen search results."
        ),
        "criteria": {
            "good": "Relevant searches without exact duplicates; no clear waste or omission.",
            "bad": "No searches, exact duplicate queries, more than four searches, or unrelated queries.",
        },
    },
}


def build_decision_request(entry: dict) -> dict:
    """Build the shared request body that both decision judges evaluate.

    `state` contains the facts to examine; `questions` are the three shared
    checks, one choice question each. Jev wraps this in one OpenRouter request
    per entry; Laya scores the same body with a local `predict` call. Keep the
    large search results out of `state` — the checks don't need them and they
    would blow up the token bill.
    """
    state = {
        "user_question": entry["input"]["question"],
        "reference_answer": entry["input"]["reference_answer"],
        "agent_answer": entry["rag_response"]["answer"],
        "agent_instructions": AGENT_INSTRUCTIONS,
        "tool_calls": [
            {"name": tool["name"], "args": tool.get("args", {})}
            for tool in entry.get("tools", [])
        ],
    }
    questions = {
        name: {
            "type": "choice",
            "instructions": check["instructions"],
            "criteria": check["criteria"],
        }
        for name, check in CHECKS.items()
    }
    return {"state": state, "questions": questions}


def load_entries(data_path: Path, limit: int | None) -> list[dict]:
    """Read an evals_run_*.json file, optionally keeping only the first N."""
    entries = json.loads(data_path.read_text())
    return entries[:limit] if limit is not None else entries


def default_output(source: Path, judge: str) -> Path:
    return source.with_name(source.stem + f"_{judge}_judged.json")


def parse_choice_answer(answer: dict, check_name: str) -> dict:
    """Validate one good/bad answer and normalize it to a result dict."""
    if not isinstance(answer, dict) or answer.get("choice") not in CHECKS[check_name]["criteria"]:
        raise ValueError(f"Unexpected {check_name} choice answer: {answer!r}")
    return {
        "score": answer["choice"],
        "probabilities": answer.get("probabilities", {}),
    }


def count_scores(entries: list[dict]) -> list[dict]:
    """Per-check good/bad/error counts over the judged entries."""
    return [
        {
            "name": name,
            **{
                score: sum(entry[spec["result_key"]].get("score") == score for entry in entries)
                for score in ("good", "bad", "error")
            },
        }
        for name, spec in CHECKS.items()
    ]


def base_report(
    model: str, source: Path, output: Path, entries: list[dict], elapsed: float
) -> dict:
    """Report skeleton common to both decision judges."""
    return {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model,
        "source": str(source),
        "judged_results": str(output),
        "entries": len(entries),
        "elapsed_seconds": round(elapsed, 3),
        "checks": count_scores(entries),
    }


def render_checks_report(
    title: str,
    report: dict,
    stat_lines: list[str],
    sections: list[str] | None = None,
    closing: str = "",
) -> str:
    """Markdown report: header, judge-specific stats, score table, sections."""
    lines = [
        f"# {title}",
        "",
        f"Model: `{report['model']}`",
        "",
        f"- Source: `{report['source']}`",
        f"- Judged results: `{report['judged_results']}`",
        *stat_lines,
        "",
        "| Check | Good | Bad | Error |",
        "| --- | ---: | ---: | ---: |",
    ]
    for check in report["checks"]:
        lines.append(
            f"| {check['name']} | {check['good']} | {check['bad']} | {check['error']} |"
        )
    for section in sections or []:
        lines.extend(["", section])
    if closing:
        lines.extend(["", closing])
    return "\n".join(lines) + "\n"


def write_outputs(judged: list[dict], report: dict, report_md: str, output: Path) -> Path:
    """Write the judged entries plus the JSON and Markdown report twins."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(judged, indent=2, default=str) + "\n")
    output.with_name(output.stem + "_report.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    report_md_path = output.with_name(output.stem + "_report.md")
    report_md_path.write_text(report_md)
    return report_md_path


def print_summary(report: dict, report_md_path: Path) -> None:
    print(f"Saved results to {report['judged_results']}")
    print(f"Saved report to {report_md_path} and {report_md_path.with_suffix('.json')}")
    for check in report["checks"]:
        print(
            f"  {check['name']}: good={check['good']} bad={check['bad']} "
            f"error={check['error']}"
        )


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--data", default=str(DEFAULT_DATA), help="Path to an evals_run_*.json file."
    )
    parser.add_argument(
        "--output", help="Output JSON path (default: <data>_<judge>_judged.json)."
    )
    parser.add_argument("--limit", type=int, help="Only judge the first N entries.")
