"""Compare two judged eval runs (baseline vs feature) and write a Markdown verdict.

Used by the PR eval workflow: the same questions are run and judged on the
main branch (baseline) and on the PR branch (feature). This script turns the two
`*_judged.json` files into one table with the pass rate per check and a merge
recommendation.

Usage:
    uv run python -m evals.ci.compare \
        --base base_judged.json --feature feature_judged.json \
        --base-label "main @ abc123" --feature-label "PR @ def456" \
        --output comparison.md
"""

import argparse
import json
import sys
from pathlib import Path

# result_key in the judged entries -> label shown in the table
CHECKS = {
    "judge_answer_correctness": "Answer correctness",
    "judge_instruction_following": "Instruction following",
    "judge_trajectory": "Trajectory",
}

MARKER = "<!-- eval-comparison -->"


def load(path: str) -> list[dict]:
    return json.loads(Path(path).read_text())


def pass_rates(entries: list[dict]) -> dict[str, tuple[int, int]]:
    """Return {result_key: (good, total)}."""
    rates = {}
    for key in CHECKS:
        scores = [e.get(key, {}).get("score") for e in entries]
        rates[key] = (sum(s == "good" for s in scores), len(scores))
    return rates


def pct(good: int, total: int) -> float:
    return 100.0 * good / total if total else 0.0


def agent_errors(entries: list[dict]) -> int:
    return sum(1 for e in entries if "error" in e)


def costs(entries: list[dict]) -> dict:
    """Agent and judge cost of a run. Agent cost is None for runs without usage data."""
    has_usage = bool(entries) and all("agent_usage" in e for e in entries)
    agent = sum(e["agent_usage"]["cost_usd"] for e in entries) if has_usage else None
    judge = sum(
        e.get(key, {}).get("cost_usd", 0.0) for e in entries for key in CHECKS
    )
    models = sorted({m for e in entries for m in e.get("agent_usage", {}).get("models", [])})
    return {"agent": agent, "judge": judge, "models": models, "n": len(entries)}


def cost_change(base: float | None, feature: float | None) -> float | None:
    """Relative change of the agent cost in percent, None if unknown."""
    if base is None or feature is None or base == 0:
        return None
    return 100.0 * (feature - base) / base


def flipped(base: list[dict], feature: list[dict], key: str) -> tuple[list[str], list[str]]:
    """Questions whose score changed between runs: (good->bad, bad->good)."""
    base_by_q = {e["input"]["question"]: e.get(key, {}).get("score") for e in base}
    worse, better = [], []
    for e in feature:
        q = e["input"]["question"]
        before, after = base_by_q.get(q), e.get(key, {}).get("score")
        if before == "good" and after == "bad":
            worse.append(q)
        elif before == "bad" and after == "good":
            better.append(q)
    return worse, better


def compare(base: list[dict], feature: list[dict], tolerance: float,
            cost_tolerance: float = 10.0) -> dict:
    base_rates, feature_rates = pass_rates(base), pass_rates(feature)
    rows = []
    for key, label in CHECKS.items():
        b, f = pct(*base_rates[key]), pct(*feature_rates[key])
        delta = f - b
        if delta < -tolerance:
            status = "regression"
        elif delta > tolerance:
            status = "improvement"
        else:
            status = "no significant change"
        worse, better = flipped(base, feature, key)
        rows.append({
            "key": key, "label": label,
            "base": base_rates[key], "feature": feature_rates[key],
            "base_pct": b, "feature_pct": f, "delta": delta,
            "status": status, "worse": worse, "better": better,
        })

    base_err, feature_err = agent_errors(base), agent_errors(feature)
    regressions = [r for r in rows if r["status"] == "regression"]
    improvements = [r for r in rows if r["status"] == "improvement"]

    base_cost, feature_cost = costs(base), costs(feature)
    delta_cost = cost_change(base_cost["agent"], feature_cost["agent"])
    more_expensive = delta_cost is not None and delta_cost > cost_tolerance
    cheaper = delta_cost is not None and delta_cost < -cost_tolerance

    if regressions or feature_err > base_err:
        verdict = "dont_merge"
    elif improvements and more_expensive:
        verdict = "tradeoff"
    elif improvements:
        verdict = "merge_improvement"
    elif more_expensive:
        verdict = "dont_merge_cost"
    elif cheaper:
        verdict = "merge_cheaper"
    else:
        verdict = "merge_neutral"

    return {
        "rows": rows, "verdict": verdict, "tolerance": tolerance,
        "cost_tolerance": cost_tolerance,
        "base_cost": base_cost, "feature_cost": feature_cost, "cost_delta": delta_cost,
        "base_errors": base_err, "feature_errors": feature_err,
        "regressions": regressions, "improvements": improvements,
    }


STATUS_ICON = {"regression": "🔴", "improvement": "🟢", "no significant change": "⚪"}

VERDICT_TEXT = {
    "dont_merge": "❌ **Don't merge.** The PR makes the agent worse on at least one check.",
    "dont_merge_cost": "❌ **Don't merge.** Same quality, but the agent costs more.",
    "tradeoff": "⚠️ **Your call.** Quality improves, but the agent costs more. "
                "Decide whether the improvement is worth the extra cost.",
    "merge_improvement": "✅ **Merge.** The PR improves the agent, nothing regressed "
                         "and it doesn't cost more.",
    "merge_cheaper": "✅ **Merge.** Same quality, and the agent is cheaper.",
    "merge_neutral": "✅ **OK to merge.** No significant change in quality or cost.",
}
FAILING_VERDICTS = {"dont_merge", "dont_merge_cost"}


def _usd(value: float | None) -> str:
    return "n/a" if value is None else f"${value:.4f}"


def _per_q(cost: dict) -> float | None:
    return None if cost["agent"] is None or not cost["n"] else cost["agent"] / cost["n"]


def render(result: dict, base_label: str, feature_label: str, n: int) -> str:
    tol = result["tolerance"]
    lines = [
        MARKER,
        "## Eval comparison",
        "",
        f"Same {n} questions run and judged on both versions.",
        "",
        f"| Check | Baseline ({base_label}) | Feature ({feature_label}) | Change | |",
        "|---|---|---|---|---|",
    ]
    for r in result["rows"]:
        bg, bt = r["base"]
        fg, ft = r["feature"]
        lines.append(
            f"| {r['label']} | {r['base_pct']:.0f}% ({bg}/{bt}) "
            f"| {r['feature_pct']:.0f}% ({fg}/{ft}) "
            f"| {r['delta']:+.0f} pp | {STATUS_ICON[r['status']]} {r['status']} |"
        )
    lines.append(
        f"| Agent errors | {result['base_errors']} | {result['feature_errors']} "
        f"| {result['feature_errors'] - result['base_errors']:+d} | |"
    )

    bc, fc, dc = result["base_cost"], result["feature_cost"], result["cost_delta"]
    if dc is None:
        cost_change_cell, cost_status = "n/a", ""
    else:
        cost_change_cell = f"{dc:+.0f}%"
        if dc > result["cost_tolerance"]:
            cost_status = "🔴 more expensive"
        elif dc < -result["cost_tolerance"]:
            cost_status = "🟢 cheaper"
        else:
            cost_status = "⚪ no significant change"
    lines += [
        "",
        "### Cost",
        "",
        f"| | Baseline ({base_label}) | Feature ({feature_label}) | Change | |",
        "|---|---|---|---|---|",
        f"| Agent model | {', '.join(bc['models']) or 'n/a'} | {', '.join(fc['models']) or 'n/a'} | | |",
        f"| Agent cost per question | {_usd(_per_q(bc))} | {_usd(_per_q(fc))} | {cost_change_cell} | {cost_status} |",
        f"| Agent cost ({n} questions) | {_usd(bc['agent'])} | {_usd(fc['agent'])} | {cost_change_cell} | |",
        f"| Judge cost (eval only) | {_usd(bc['judge'])} | {_usd(fc['judge'])} | | |",
    ]
    total = sum(c for c in (bc["agent"], fc["agent"]) if c is not None) + bc["judge"] + fc["judge"]
    lines += ["", f"This eval run cost {_usd(total)} in total (agent + judge, both versions)."]

    lines += ["", "### Verdict", "", VERDICT_TEXT[result["verdict"]], ""]
    reasons = []
    for r in result["regressions"]:
        reasons.append(f"- {r['label']} dropped by {-r['delta']:.0f} pp.")
    if result["feature_errors"] > result["base_errors"]:
        reasons.append("- The feature branch has more agent errors than the baseline.")
    for r in result["improvements"]:
        reasons.append(f"- {r['label']} improved by {r['delta']:.0f} pp.")
    if dc is not None and abs(dc) > result["cost_tolerance"]:
        word = "more" if dc > 0 else "less"
        reasons.append(f"- The agent costs {abs(dc):.0f}% {word} per question "
                       f"({_usd(_per_q(bc))} → {_usd(_per_q(fc))}).")
    lines += reasons
    lines += [
        "",
        f"A change counts as significant when it's larger than ±{tol:.0f} percentage "
        f"points (about {max(1, round(tol * n / 100))} of {n} questions). Smaller changes "
        "are within the noise of a non-deterministic agent and judge. "
        f"A cost change counts when it's larger than ±{result['cost_tolerance']:.0f}%.",
    ]

    details = []
    for r in result["rows"]:
        if r["worse"] or r["better"]:
            details.append(f"**{r['label']}**")
            details += [f"- 🔴 good → bad: {q}" for q in r["worse"]]
            details += [f"- 🟢 bad → good: {q}" for q in r["better"]]
            details.append("")
    if details:
        lines += ["", "<details><summary>Questions that changed</summary>", "", *details, "</details>"]

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Judged JSON for the baseline (main).")
    parser.add_argument("--feature", required=True, help="Judged JSON for the feature branch.")
    parser.add_argument("--base-label", default="main")
    parser.add_argument("--feature-label", default="PR")
    parser.add_argument("--tolerance", type=float, default=10.0,
                        help="Change in percentage points that counts as significant (default: 10).")
    parser.add_argument("--cost-tolerance", type=float, default=10.0,
                        help="Agent cost change in percent that counts as significant (default: 10).")
    parser.add_argument("--output", default="comparison.md")
    parser.add_argument("--fail-on-regression", action="store_true",
                        help="Exit with code 1 when the verdict is 'don't merge' (quality or cost).")
    args = parser.parse_args()

    base, feature = load(args.base), load(args.feature)
    result = compare(base, feature, args.tolerance, args.cost_tolerance)
    md = render(result, args.base_label, args.feature_label, len(feature))

    Path(args.output).write_text(md)
    print(md)

    if args.fail_on_regression and result["verdict"] in FAILING_VERDICTS:
        sys.exit(1)


if __name__ == "__main__":
    main()
