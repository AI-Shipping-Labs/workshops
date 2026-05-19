import argparse
import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from investment_coach_bot.agent import InvestmentAgentConfig, create_agent, run_agent
from investment_coach_bot.config import get_settings
from investment_coach_bot.sec import SecClient
from investment_coach_bot.tools import InvestmentResearchTools
from evals.manual.utils import (
    DEFAULT_RESULTS_PATH,
    DEFAULT_SCENARIOS_PATH,
    collect_tools,
    read_scenarios,
    serialize_usage,
    split_expected_tools,
)


load_dotenv()


def create_investment_agent():
    settings = get_settings()
    sec = SecClient(settings.sec_user_agent, settings.http_timeout_seconds)
    tools = InvestmentResearchTools(sec)
    return create_agent(InvestmentAgentConfig(model=settings.openai_model), tools)


async def run_scenario(agent, scenario: dict[str, str]) -> dict:
    result = await run_agent(agent, scenario["input"])

    return {
        "id": scenario["id"],
        "group": scenario["group"],
        "input": scenario["input"],
        "expected_output": scenario["expected_output"],
        "expected_tools": split_expected_tools(scenario["expected_tools"]),
        "actual_output": result.output.answer,
        "needs_clarification": result.output.needs_clarification,
        "used_tools_from_output": result.output.used_tools,
        "tool_calls": collect_tools(result.new_messages()),
        "usage": serialize_usage(result.usage()),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run investment agent on manual eval scenarios.")
    parser.add_argument("--scenarios", default=str(DEFAULT_SCENARIOS_PATH))
    parser.add_argument("--output", default=str(DEFAULT_RESULTS_PATH))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    scenarios = read_scenarios(Path(args.scenarios))
    if args.limit is not None:
        scenarios = scenarios[: args.limit]

    agent = create_investment_agent()
    results = []

    for index, scenario in enumerate(scenarios, start=1):
        print(f"[{index}/{len(scenarios)}] {scenario['id']}: {scenario['input']}")

        try:
            result = await run_scenario(agent, scenario)
        except Exception as exc:
            result = {
                "id": scenario["id"],
                "group": scenario["group"],
                "input": scenario["input"],
                "expected_output": scenario["expected_output"],
                "expected_tools": split_expected_tools(scenario["expected_tools"]),
                "actual_output": f"Agent error: {exc}",
                "needs_clarification": False,
                "used_tools_from_output": [],
                "tool_calls": [],
                "usage": {},
            }

        results.append(result)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2))
    print(f"Saved {len(results)} results to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
