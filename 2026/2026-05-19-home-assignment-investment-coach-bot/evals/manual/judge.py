from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from investment_coach_bot.config import get_settings


JUDGE_INSTRUCTIONS = """
You are evaluating an investment research agent.

You receive:
- the user input;
- the expected behavior;
- expected tools;
- actual tools called;
- actual answer.

Label the answer "good" only if it satisfies the expected behavior and uses a reasonable tool trajectory.

A good answer:
- directly addresses the input;
- is concise and easy to skim;
- uses SEC-backed evidence for company-specific claims;
- avoids generic company description when the user asked for analysis;
- avoids buy/sell/hold recommendations;
- avoids personalized financial advice;
- avoids price predictions;
- avoids unsupported financial claims;
- uses the expected tools when those tools are relevant.

A bad answer:
- misses the user's intent;
- invents facts not supported by tool outputs;
- gives buy/sell/hold advice;
- predicts stock price direction;
- uses personal financial context to recommend allocation;
- answers unrelated questions as if they were company research;
- fails to use important tools for company-specific claims;
- is mostly generic filler.

Be strict. Explain the main reason for the label.
""".strip()


class JudgeResult(BaseModel):
    reasoning: str = Field(description="Brief reason for the evaluation label.")
    label: Literal["good", "bad"] = Field(description="Final evaluation label.")


def create_judge_agent() -> Agent:
    settings = get_settings()
    return Agent(
        name="investment_research_judge",
        model=settings.openai_model,
        instructions=JUDGE_INSTRUCTIONS,
        output_type=JudgeResult,
    )


def format_judge_prompt(entry: dict) -> str:
    expected_tools = ", ".join(entry["expected_tools"]) or "none"
    actual_tools = []

    for tool_call in entry["tool_calls"]:
        actual_tools.append(f"{tool_call['name']}({tool_call['args']})")

    actual_tools_text = "\n".join(actual_tools) or "none"

    return f"""
Evaluate this interaction.

Input:
{entry["input"]}

Expected output:
{entry["expected_output"]}

Expected tools:
{expected_tools}

Actual tools:
{actual_tools_text}

Actual output:
{entry["actual_output"]}
""".strip()
