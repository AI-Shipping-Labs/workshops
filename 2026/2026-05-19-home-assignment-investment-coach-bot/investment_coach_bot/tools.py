from typing import Any

from investment_coach_bot.sec import SecClient


class InvestmentResearchTools:
    def __init__(self, sec: SecClient):
        self.sec = sec

    def search_company(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        """Search the SEC company ticker dataset by ticker, company name, or CIK."""
        return self.sec.search_company(query, limit)

    def get_financial_snapshot(self, ticker_or_cik: str) -> dict[str, Any]:
        """Fetch an SEC EDGAR companyfacts snapshot with recent annual revenue, profit, balance sheet, and cash facts."""
        return self.sec.get_financial_snapshot(ticker_or_cik)

    def get_latest_filings(
        self,
        ticker_or_cik: str,
        limit: int = 5,
        form_type: str | None = None,
    ) -> dict[str, Any]:
        """Fetch recent SEC filing metadata and URLs for a public company."""
        return self.sec.get_latest_filings(ticker_or_cik, limit, form_type)

    def get_filing_digest(
        self,
        ticker_or_cik: str,
        form_type: str = "10-K",
        max_snippets: int = 8,
    ) -> dict[str, Any]:
        """Fetch the latest 10-K or 10-Q filing text and extract relevant business, revenue, risk, and MD&A snippets."""
        return self.sec.get_filing_digest(ticker_or_cik, form_type, max_snippets)

    def as_tool_list(self):
        return [
            self.search_company,
            self.get_financial_snapshot,
            self.get_latest_filings,
            self.get_filing_digest,
        ]
