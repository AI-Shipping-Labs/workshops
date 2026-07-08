"""Run the FAQ agent from the command line.

Usage:
    uv run python cli.py "How do I install Kafka?"   # one-shot
    uv run python cli.py                              # interactive REPL

This is the same agent loop used by the FastAPI app (`run_agent` in
`agent.py`), wired up with a terminal-friendly renderer. It is handy for
exercising the agent by hand and for building an evaluation dataset.
"""

import asyncio
import sys

from dotenv import load_dotenv
from openai import AsyncOpenAI

from agent import run_agent
from renderer import BaseRenderer
from search import init_index


class CLIRenderer(BaseRenderer):
    """Streams the agent's output to the terminal."""

    async def handle_status(self, payload):
        print(f"\033[90m[{payload.get('message', '')}]\033[0m", flush=True)

    async def handle_tool_call(self, payload):
        args = payload.get("arguments", {})
        print(f"\n\033[36m→ {payload['name']}({args})\033[0m", flush=True)

    async def handle_tool_result(self, payload):
        result = payload.get("result")
        n = len(result) if isinstance(result, list) else "?"
        print(f"\033[36m  ← {n} results\033[0m\n", flush=True)

    async def handle_token(self, payload):
        print(payload["delta"], end="", flush=True)

    async def handle_done(self, payload):
        print("\n", flush=True)


async def ask(client: AsyncOpenAI, question: str) -> str:
    renderer = CLIRenderer()
    return await run_agent(client, question, renderer)


async def main():
    load_dotenv()
    init_index()
    client = AsyncOpenAI()

    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
        await ask(client, question)
        return

    print("FAQ Agent CLI. Type a question (Ctrl-C or empty line to quit).\n")
    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            break
        await ask(client, question)


if __name__ == "__main__":
    asyncio.run(main())
