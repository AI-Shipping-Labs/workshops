from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any]


class FakeSecClient:
    def search_company(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        return [{"cik": "0001713445", "ticker": "RDDT", "title": "Reddit, Inc."}]

    def get_financial_snapshot(self, ticker_or_cik: str) -> dict[str, Any]:
        return {
            "company": {"cik": "0001713445", "ticker": "RDDT", "title": "Reddit, Inc."},
            "annual_revenue": {"values": [{"fy": 2025, "value": 2_202_506_000}]},
        }

    def get_latest_filings(
        self,
        ticker_or_cik: str,
        limit: int = 5,
        form_type: str | None = None,
    ) -> dict[str, Any]:
        return {
            "filings": [
                {
                    "form": "10-K",
                    "filing_date": "2026-02-06",
                    "url": "https://www.sec.gov/example",
                }
            ]
        }

    def get_filing_digest(
        self,
        ticker_or_cik: str,
        form_type: str = "10-K",
        max_snippets: int = 8,
    ) -> dict[str, Any]:
        return {
            "snippets": [
                {
                    "topic": "revenue_drivers",
                    "text": "Advertising revenue and content licensing are key revenue drivers.",
                }
            ]
        }


def collect_tools(messages) -> list[ToolCall]:
    tool_calls = []

    for message in messages:
        for part in message.parts:
            if part.part_kind != "tool-call":
                continue
            if part.tool_name == "final_result":
                continue
            tool_calls.append(ToolCall(part.tool_name, part.args))

    return tool_calls
