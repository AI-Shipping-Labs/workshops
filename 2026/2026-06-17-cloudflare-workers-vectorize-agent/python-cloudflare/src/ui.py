from functools import cache
from pathlib import Path


@cache
def render_home() -> str:
    """Renders the compact browser UI used to test the Worker locally."""

    return Path(__file__).with_name("index.html").read_text(encoding="utf-8")
