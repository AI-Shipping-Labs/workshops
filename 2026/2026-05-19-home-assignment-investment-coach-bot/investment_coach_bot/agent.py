from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_ai import Agent, AgentRunResult
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import FunctionToolCallEvent
from pydantic_ai.usage import UsageLimits

from investment_coach_bot.tools import InvestmentResearchTools


class ResearchResponse(BaseModel):
    answer: str = Field(
        description=(
            "Concise, skim-friendly educational answer. Use short sections: Verdict, Thesis, "
            "Watch, Warning Signs, Evidence. Do not start with raw API data or generic company description."
        )
    )
    used_tools: list[str] = Field(default_factory=list)
    needs_clarification: bool = False


DEFAULT_INSTRUCTIONS = """
You are an investment research agent for educational use only.

Use the SEC EDGAR tools for company-specific analysis. Do not rely on memory for
financial numbers when tools are available.

Safety rules:
- Do not provide personalized financial advice.
- Do not recommend buying, selling, holding, shorting, or position sizing.
- Do not predict that a stock will go up or down.
- If the user asks a buy/sell question, transform it into an educational research brief.
- If the user gives personal financial context, do not use that context. Offer general company research instead.

Tool rules:
- If the company/ticker is unclear, call search_company first or ask a clarification question.
- For company analysis, call get_financial_snapshot.
- For filing context or source links, call get_latest_filings.
- For interesting qualitative analysis, call get_filing_digest for the latest 10-K. If the user asks about recent performance, also call it for the latest 10-Q.
- Do not paste raw tool JSON into the answer.

Answer style:
- Optimize for decision support, not generic company description.
- Assume the user already knows what the company does at a high level. Avoid obvious statements like "Reddit is a social media platform" unless needed for a specific insight.
- Be concise and easy to skim. Target 250-450 words unless the user asks for depth.
- Use short bullet points, not paragraphs.
- Use this exact structure:
  1. "Verdict" - 3 bullets max, one line each. No recommendation, only research takeaway.
  2. "Thesis" - use plain labels: "What could go well", "What seems most likely", and "What could go wrong".
  3. "Watch" - 4 metrics or events max.
  4. "Warning Signs" - 3 disconfirming signals max.
  5. "Evidence" - 4 compact source-backed facts max.
- Each bullet should be one sentence. Avoid multi-sentence bullets.
- Do not add a closing offer like "If you want, I can...".
- Avoid specialized finance jargon unless the user uses those terms first.
- Prefer practical language: "watch", "verify", "the key question is", "this matters because".
- Keep generic background to one sentence maximum.
- Make the safety boundary explicit when the user asked for advice.
""".strip()


DEFAULT_USAGE_LIMITS = UsageLimits(
    request_limit=20,
    tool_calls_limit=8,
)

TOOL_LIMIT_RESPONSE = (
    "I could not resolve this confidently with the available SEC tools. "
    "The query may be misspelled, ambiguous, or outside public-company SEC coverage. "
    "Please try a clearer company name or ticker."
)


class AgentCouldNotAnswer(RuntimeError):
    pass


@dataclass
class InvestmentAgentConfig:
    model: str = "openai:gpt-5.4-mini"
    name: str = "investment-research-agent"
    instructions: str = DEFAULT_INSTRUCTIONS


def create_agent(config: InvestmentAgentConfig, tools: InvestmentResearchTools) -> Agent:
    return Agent(
        name=config.name,
        model=config.model,
        instructions=config.instructions,
        tools=tools.as_tool_list(),
        output_type=ResearchResponse,
    )


class ToolCallPrinter:
    def __init__(self, agent_name: str):
        self.agent_name = agent_name

    async def __call__(self, ctx, event) -> None:
        await self._print_event(event)

    async def _print_event(self, event) -> None:
        if hasattr(event, "__aiter__"):
            async for sub_event in event:
                await self._print_event(sub_event)
            return
        if not isinstance(event, FunctionToolCallEvent):
            return
        print(f"TOOL CALL ({self.agent_name}): {event.part.tool_name}({event.part.args})")


async def run_agent(
    agent: Agent,
    user_prompt: str,
    message_history=None,
    show_trace: bool = False,
) -> AgentRunResult:
    if message_history is None:
        message_history = []

    event_stream_handler = None
    if show_trace:
        print(f"USER PROMPT ({agent.name}): {user_prompt}")
        event_stream_handler = ToolCallPrinter(agent.name or "agent")

    try:
        return await agent.run(
            user_prompt,
            message_history=message_history,
            event_stream_handler=event_stream_handler,
            usage_limits=DEFAULT_USAGE_LIMITS,
        )
    except UsageLimitExceeded as exc:
        raise AgentCouldNotAnswer(TOOL_LIMIT_RESPONSE) from exc
