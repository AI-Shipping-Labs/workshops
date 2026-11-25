from search import search


def test_search_returns_results():
    results = search("How do I install Kafka?")

    assert 0 < len(results) <= 5
    for doc in results:
        assert doc["question"]
        assert doc["answer"]


def test_search_respects_limit():
    assert len(search("docker", limit=2)) == 2


def test_search_finds_known_entry():
    results = search("curl: Could not resolve host: output.csv")

    ids = [doc["id"] for doc in results]
    assert "48cae101d6" in ids
