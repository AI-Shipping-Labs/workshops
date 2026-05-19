from investment_coach_bot.sec import SecClient


def test_search_company_with_mocked_sec_ticker_dataset(monkeypatch) -> None:
    client = SecClient("test@example.com")

    monkeypatch.setattr(
        client,
        "_get_json",
        lambda url, host: {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
            "1": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
        },
    )

    result = client.search_company("nvidia")

    assert result == [{"cik": "0001045810", "ticker": "NVDA", "title": "NVIDIA CORP"}]


def test_annual_series_prefers_usd_and_annual_10k_rows() -> None:
    client = SecClient("test@example.com")
    us_gaap = {
        "Revenues": {
            "label": "Revenue",
            "units": {
                "USD": [
                    {"fy": 2024, "fp": "FY", "form": "10-K", "val": 100, "filed": "2025-01-01", "end": "2024-12-31"},
                    {"fy": 2024, "fp": "Q1", "form": "10-Q", "val": 20, "filed": "2024-04-01", "end": "2024-03-31"},
                    {"fy": 2023, "fp": "FY", "form": "10-K", "val": 80, "filed": "2024-01-01", "end": "2023-12-31"},
                ]
            },
        }
    }

    result = client._annual_series(us_gaap, ["Revenues"])

    assert result["tag"] == "Revenues"
    assert [row["value"] for row in result["values"]] == [100, 80]


def test_financial_snapshot_uses_contract_revenue_tag(monkeypatch) -> None:
    client = SecClient("test@example.com")
    monkeypatch.setattr(
        client,
        "_company_tickers",
        lambda: [type("Company", (), {"cik": "0001713445", "ticker": "RDDT", "title": "Reddit, Inc."})()],
    )
    monkeypatch.setattr(
        client,
        "_company_facts",
        lambda cik: {
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "label": "Revenue",
                        "units": {
                            "USD": [
                                {
                                    "fy": 2024,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "val": 1300000000,
                                    "filed": "2025-02-12",
                                    "end": "2024-12-31",
                                }
                            ]
                        },
                    }
                }
            }
        },
    )

    result = client.get_financial_snapshot("RDDT")

    assert result["annual_revenue"]["tag"] == "RevenueFromContractWithCustomerExcludingAssessedTax"


def test_extract_filing_snippets_returns_interesting_topics() -> None:
    client = SecClient("test@example.com")
    text = (
        "Our business model is based on a platform for communities. "
        "Revenue increased because advertising revenue and data licensing improved. "
        "We monitor daily active users and engagement. "
        "Risk factors include competition and privacy regulation."
    )

    snippets = client._extract_filing_snippets(text, max_snippets=3)

    assert {snippet["topic"] for snippet in snippets} >= {"business_model", "revenue_drivers"}
