import asyncio
import os

import pytest
from dotenv import load_dotenv
from openai import AsyncOpenAI

from agent import run_agent
from evals.synthetic.run import TrajectoryRenderer
from search import init_index

load_dotenv()


@pytest.fixture(scope="session", autouse=True)
def index():
    # Downloads the FAQ once for the whole test session.
    return init_index()


@pytest.fixture(scope="session")
def ask():
    """Run the agent on a question, return (answer, tool calls).

    Results are cached per question, so several tests can check the same
    answer while paying for a single agent run.
    """
    if not os.getenv("OPENAI_API_KEY"):
        # GitHub Actions sets CI=true: a missing secret must fail, not skip.
        if os.getenv("CI"):
            pytest.fail("OPENAI_API_KEY is not set in CI (add it as a repo secret)")
        pytest.skip("OPENAI_API_KEY is not set")

    cache = {}

    async def _run(question):
        renderer = TrajectoryRenderer()
        async with AsyncOpenAI() as client:
            answer = await run_agent(client, question, renderer)
        return answer, renderer.tools

    def _ask(question: str):
        if question not in cache:
            cache[question] = asyncio.run(_run(question))
        return cache[question]

    return _ask
