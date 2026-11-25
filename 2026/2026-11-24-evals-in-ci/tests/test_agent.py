import re

QUESTION = "What exact ssh command should I use for Jupyter on port 8888?"


def test_agent_uses_search(ask):
    answer, tools = ask(QUESTION)

    assert answer
    assert len(tools) >= 1
    assert all(t["name"] == "search" for t in tools)


def test_answer_has_sources_section(ask):
    answer, _ = ask(QUESTION)

    assert "Sources" in answer
    assert re.search(r"^- \[[0-9a-f]+\]", answer, flags=re.MULTILINE)


def test_sources_come_from_search_results(ask):
    answer, tools = ask(QUESTION)

    cited = set(re.findall(r"^- \[([0-9a-f]+)\]", answer, flags=re.MULTILINE))
    found = {doc["id"] for t in tools for doc in t["result"]}

    assert cited
    assert cited <= found, f"cited ids not in search results: {cited - found}"
