import csv
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIOS_PATH = PROJECT_ROOT / "evals" / "manual" / "data" / "scenarios.csv"
DEFAULT_RESULTS_PATH = PROJECT_ROOT / "evals" / "manual" / "data" / "results.json"
DEFAULT_JUDGED_PATH = PROJECT_ROOT / "evals" / "manual" / "data" / "judged_results.json"


def read_scenarios(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as file:
        reader = csv.DictReader(file)
        return list(reader)


def collect_tools(messages) -> list[dict[str, Any]]:
    tool_calls = []

    for message in messages:
        for part in message.parts:
            if part.part_kind != "tool-call":
                continue
            if part.tool_name == "final_result":
                continue
            tool_calls.append({"name": part.tool_name, "args": part.args})

    return tool_calls


def split_expected_tools(value: str) -> list[str]:
    tools = []

    for item in value.split(","):
        tool = item.strip()
        if tool:
            tools.append(tool)

    return tools


def serialize_usage(usage) -> dict:
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
        "requests": usage.requests,
        "tool_calls": usage.tool_calls,
        "details": usage.details,
    }
