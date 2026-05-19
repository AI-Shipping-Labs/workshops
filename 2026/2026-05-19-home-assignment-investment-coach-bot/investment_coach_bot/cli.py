import asyncio

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from investment_coach_bot.agent import (
    AgentCouldNotAnswer,
    InvestmentAgentConfig,
    create_agent,
    run_agent,
)
from investment_coach_bot.config import get_settings
from investment_coach_bot.sec import SecClient
from investment_coach_bot.tools import InvestmentResearchTools

import dotenv
import logfire


def main() -> None:
    configure_monitoring()
    asyncio.run(run_cli())


def configure_monitoring() -> None:
    dotenv.load_dotenv()
    logfire.configure()
    logfire.instrument_pydantic_ai()


async def run_cli() -> None:
    console = Console()
    settings = get_settings()

    sec = SecClient(settings.sec_user_agent, settings.http_timeout_seconds)
    tools = InvestmentResearchTools(sec)
    agent = create_agent(InvestmentAgentConfig(model=settings.openai_model), tools)
    message_history = []

    console.print(
        Panel.fit(
            "Investment Coach CLI\n\n"
            "PydanticAI agent with free SEC EDGAR tools. Educational research only: "
            "no personalized financial advice, price forecasts, or buy/sell/hold recommendations.\n\n"
            "Try: 'Analyze NVDA fundamentals' or 'Should I buy Tesla now?'.\n"
            "Type 'stop' to exit.",
            title="Investment Coach",
        )
    )

    if not settings.openai_api_key:
        console.print(
            "[yellow]OPENAI_API_KEY is not set. Add it to .env before asking questions.[/yellow]"
        )
    if settings.sec_user_agent.endswith("contact@example.com"):
        console.print(
            "[yellow]Set SEC_USER_AGENT in .env to your app/contact email for SEC API requests.[/yellow]"
        )

    while True:
        user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]").strip()
        if user_input.lower() in {"stop", "exit", "quit", "/stop", "/exit", "/quit"}:
            console.print("Goodbye.")
            return
        if not user_input:
            continue

        try:
            result = await run_agent(agent, user_input, message_history, show_trace=True)
            message_history.extend(result.new_messages())
            response = result.output.answer
        except AgentCouldNotAnswer as exc:
            response = str(exc)
        except Exception as exc:
            response = f"I hit an agent error while preparing the response: {exc}"

        console.print(Panel(response, title="Coach", border_style="green"))
