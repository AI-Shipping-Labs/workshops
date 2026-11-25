import pytest

import agent
from evals.synthetic.judge import JUDGE_MODEL
from pricing import UnknownModelError, get_price, request_cost


def test_agent_model_has_a_price():
    get_price(agent.MODEL_NAME)


def test_judge_model_has_a_price():
    get_price(JUDGE_MODEL)


def test_unknown_model_fails():
    with pytest.raises(UnknownModelError, match="pricing.py"):
        get_price("gpt-does-not-exist")


def test_request_cost():
    # gpt-5.4-mini: $0.75 input, $0.075 cached, $4.50 output per 1M tokens
    usage = {"input": 1_000_000, "cached": 200_000, "output": 100_000}
    expected = 0.8 * 0.75 + 0.2 * 0.075 + 0.1 * 4.50
    assert request_cost("gpt-5.4-mini", usage) == pytest.approx(expected)


def test_long_context_request_uses_long_rates():
    # gpt-6-luna over 272K input: $0.20 input, $0.75 output
    usage = {"input": 300_000, "cached": 0, "output": 10_000}
    expected = 0.3 * 0.20 + 0.01 * 0.75
    assert request_cost("gpt-6-luna", usage) == pytest.approx(expected)
