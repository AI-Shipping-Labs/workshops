"""OpenAI model prices, standard tier, USD per 1M text tokens.

Source: https://developers.openai.com/api/docs/pricing (checked 2026-11-24).

Every model the agent or the judge uses must be in PRICES: the eval scripts
refuse to start otherwise, and a test checks it on every push. When you switch
to a new model, look up its price on the page above and add it here.

Flagship models have a long-context tier: a request with more than 272K input
tokens is billed at the `long` rates for the whole request. Cost is therefore
computed per request (see `request_cost`), never on summed usage.
"""

PRICING_URL = "https://developers.openai.com/api/docs/pricing"
LONG_CONTEXT_THRESHOLD = 272_000


def _p(input, cached, output, long=None):
    price = {"input": input, "cached": cached, "output": output}
    if long:
        price["long"] = {"input": long[0], "cached": long[1], "output": long[2]}
    return price


# model: input / cached input / output (cached=None: no caching discount listed)
PRICES = {
    # Flagship table: short context (<=272K) and long context (>272K)
    "gpt-6.2-astra": _p(8.00, 0.40, 40.00, long=(16.00, 0.80, 60.00)),
    "gpt-6.2-sol": _p(2.00, 0.10, 10.00, long=(4.00, 0.20, 15.00)),
    "gpt-6.1-sol": _p(2.00, 0.10, 10.00, long=(4.00, 0.20, 15.00)),
    "gpt-6.1-terra": _p(1.00, 0.05, 5.00, long=(2.00, 0.10, 7.50)),
    "gpt-6-astra": _p(10.00, 1.00, 50.00, long=(20.00, 2.00, 75.00)),
    "gpt-6-sol": _p(2.00, 0.20, 10.00, long=(4.00, 0.40, 15.00)),
    "gpt-6-luna": _p(0.10, 0.01, 0.50, long=(0.20, 0.02, 0.75)),
    "gpt-5.6-sol": _p(4.00, 0.40, 20.00, long=(8.00, 0.80, 30.00)),
    "gpt-5.6-terra": _p(2.00, 0.20, 12.00, long=(4.00, 0.40, 18.00)),
    "gpt-5.6-luna": _p(0.20, 0.02, 1.20, long=(0.40, 0.04, 1.80)),
    "gpt-5.5": _p(5.00, 0.50, 30.00, long=(10.00, 1.00, 45.00)),
    "gpt-5.5-pro": _p(30.00, None, 180.00, long=(60.00, None, 270.00)),
    "gpt-5.4": _p(2.50, 0.25, 15.00, long=(5.00, 0.50, 22.50)),
    "gpt-5.4-pro": _p(30.00, None, 180.00, long=(60.00, None, 270.00)),
    # Other standard models (no long-context tier listed)
    "gpt-5.4-mini": _p(0.75, 0.075, 4.50),
    "gpt-5.4-nano": _p(0.20, 0.02, 1.25),
    "gpt-5.2": _p(1.75, 0.175, 14.00),
    "gpt-5.2-pro": _p(21.00, None, 168.00),
    "gpt-5.1": _p(1.25, 0.125, 10.00),
    "gpt-5": _p(1.25, 0.125, 10.00),
    "gpt-5-mini": _p(0.25, 0.025, 2.00),
    "gpt-5-nano": _p(0.05, 0.005, 0.40),
    "gpt-5-pro": _p(15.00, None, 120.00),
    "gpt-4.1": _p(2.00, 0.50, 8.00),
    "gpt-4.1-mini": _p(0.40, 0.10, 1.60),
    "gpt-4o": _p(2.50, 1.25, 10.00),
    "gpt-4o-mini": _p(0.15, 0.075, 0.60),
    "o3": _p(2.00, 0.50, 8.00),
    "o3-pro": _p(20.00, None, 80.00),
}


class UnknownModelError(KeyError):
    def __str__(self) -> str:
        return self.args[0]


def get_price(model: str) -> dict:
    if model not in PRICES:
        raise UnknownModelError(
            f"No price for model '{model}'. Look it up on {PRICING_URL} "
            "and add it to PRICES in pricing.py."
        )
    return PRICES[model]


def require_prices(*models: str) -> None:
    """Exit before spending any money if a model has no known price."""
    for model in models:
        try:
            get_price(model)
        except UnknownModelError as exc:
            raise SystemExit(f"ERROR: {exc}") from None


def request_cost(model: str, usage: dict) -> float:
    """USD cost of ONE API request. usage: {"input", "cached", "output"} tokens."""
    price = get_price(model)
    if usage.get("input", 0) > LONG_CONTEXT_THRESHOLD and "long" in price:
        price = price["long"]
    cached = min(usage.get("cached", 0), usage.get("input", 0))
    uncached = usage.get("input", 0) - cached
    cached_rate = price["cached"] if price["cached"] is not None else price["input"]
    return (
        uncached * price["input"]
        + cached * cached_rate
        + usage.get("output", 0) * price["output"]
    ) / 1_000_000
