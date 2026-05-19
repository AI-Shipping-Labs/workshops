import re

import pytest
from pydantic_ai.exceptions import UsageLimitExceeded

from investment_coach_bot.agent import (
    AgentCouldNotAnswer,
    InvestmentAgentConfig,
    create_agent,
    run_agent,
)
from investment_coach_bot.config import get_settings
from investment_coach_bot.tools import InvestmentResearchTools
from tests.utils import FakeSecClient, collect_tools


def create_test_agent():
    settings = get_settings()
    tools = InvestmentResearchTools(FakeSecClient())
    return create_agent(InvestmentAgentConfig(model=settings.openai_model), tools)


def find_terms(text: str, terms: list[str]) -> list[str]:
    found_terms = []

    for term in terms:
        pattern = rf"\b{re.escape(term)}\b"
        if re.search(pattern, text, flags=re.IGNORECASE):
            found_terms.append(term)

    return found_terms


@pytest.mark.asyncio
async def test_agent_uses_sec_tools() -> None:
    agent = create_test_agent()

    result = await agent.run("what can you tell me about reddit")

    tool_calls = collect_tools(result.new_messages())
    tool_names = [tool.name for tool in tool_calls]

    assert result.output.answer
    assert "search_company" in tool_names
    assert "get_financial_snapshot" in tool_names
    assert "get_filing_digest" in tool_names


@pytest.mark.asyncio
async def test_agent_avoids_forbidden_terminology() -> None:
    agent = create_test_agent()

    user_prompt = "what can you tell me about reddit"
    
    result = await agent.run(user_prompt)
    answer = result.output

    forbidden_terms = [
        "bull case",
        "base case",
        "bear case",
        "alpha",
        "moat",
        "rerating",
        "re-rating",
        "multiple expansion",
        "thesis break",
        "breaks thesis",
    ]

    assert len(find_terms(answer.answer, forbidden_terms)) == 0


@pytest.mark.asyncio
async def test_run_agent_stops_when_tool_limit_is_exceeded() -> None:
    class LoopingAgent:
        name = "looping-agent"

        async def run(self, *args, **kwargs):
            raise UsageLimitExceeded("tool call limit exceeded")

    with pytest.raises(AgentCouldNotAnswer) as exc_info:
        await run_agent(LoopingAgent(), "tell me about bydents")

    assert "could not resolve this confidently" in str(exc_info.value).lower()
