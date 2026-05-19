import argparse
import asyncio
import csv
import json
from pathlib import Path

from dotenv import load_dotenv

from evals.manual.judge import create_judge_agent, format_judge_prompt
from evals.manual.utils import DEFAULT_JUDGED_PATH, DEFAULT_RESULTS_PATH, serialize_usage


load_dotenv()


async def judge_entry(judge, entry: dict) -> dict:
    prompt = format_judge_prompt(entry)
    result = await judge.run(prompt)

    return {
        **entry,
        "judge_label": result.output.label,
        "judge_reasoning": result.output.reasoning,
        "judge_usage": serialize_usage(result.usage()),
    }


def write_csv_summary(results: list[dict], path: Path) -> None:
    csv_path = path.with_suffix(".csv")
    fieldnames = [
        "id",
        "group",
        "input",
        "expected_output",
        "expected_tools",
        "actual_tools",
        "judge_label",
        "judge_reasoning",
    ]

    with csv_path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for entry in results:
            writer.writerow(
                {
                    "id": entry["id"],
                    "group": entry["group"],
                    "input": entry["input"],
                    "expected_output": entry["expected_output"],
                    "expected_tools": ",".join(entry["expected_tools"]),
                    "actual_tools": ",".join(tool["name"] for tool in entry["tool_calls"]),
                    "judge_label": entry["judge_label"],
                    "judge_reasoning": entry["judge_reasoning"],
                }
            )

    print(f"Saved CSV summary to {csv_path}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Judge manual investment-agent eval results.")
    parser.add_argument("--data", default=str(DEFAULT_RESULTS_PATH))
    parser.add_argument("--output", default=str(DEFAULT_JUDGED_PATH))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    entries = json.loads(Path(args.data).read_text())
    if args.limit is not None:
        entries = entries[: args.limit]

    judge = create_judge_agent()
    judged = []

    for index, entry in enumerate(entries, start=1):
        print(f"[{index}/{len(entries)}] judging {entry['id']}")

        try:
            judged_entry = await judge_entry(judge, entry)
        except Exception as exc:
            judged_entry = {
                **entry,
                "judge_label": "bad",
                "judge_reasoning": f"Judge error: {exc}",
                "judge_usage": {},
            }

        judged.append(judged_entry)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(judged, indent=2))
    print(f"Saved judged results to {output_path}")
    write_csv_summary(judged, output_path)

    good = 0
    for entry in judged:
        if entry["judge_label"] == "good":
            good += 1

    total = len(judged)
    print(f"Good: {good}/{total}")


if __name__ == "__main__":
    asyncio.run(main())
