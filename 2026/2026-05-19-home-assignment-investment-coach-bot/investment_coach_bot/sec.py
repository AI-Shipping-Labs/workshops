from dataclasses import dataclass
from html import unescape
import re
from typing import Any

from bs4 import BeautifulSoup
import httpx


COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


@dataclass(frozen=True)
class CompanyMatch:
    cik: str
    ticker: str
    title: str


class SecClient:
    def __init__(self, user_agent: str, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds
        self.headers = {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": "",
        }

    def search_company(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        query_normalized = query.strip().lower()
        companies = self._company_tickers()

        matches = []
        for company in companies:
            ticker = company.ticker.lower()
            title = company.title.lower()
            if query_normalized in {ticker, company.cik} or query_normalized in title:
                matches.append(company)

        if not matches:
            matches = [
                company
                for company in companies
                if query_normalized in company.ticker.lower()
                or query_normalized in company.title.lower()
            ]

        return [
            {"cik": company.cik, "ticker": company.ticker, "title": company.title}
            for company in matches[:limit]
        ]

    def get_financial_snapshot(self, ticker_or_cik: str) -> dict[str, Any]:
        company = self._resolve_company(ticker_or_cik)
        if not company:
            return {"error": "Company not found in SEC company tickers", "query": ticker_or_cik}

        facts = self._company_facts(company.cik)
        us_gaap = facts.get("facts", {}).get("us-gaap", {})

        return {
            "company": {
                "cik": company.cik,
                "ticker": company.ticker,
                "title": company.title,
            },
            "annual_revenue": self._annual_series(
                us_gaap,
                [
                    "Revenues",
                    "RevenueFromContractWithCustomerExcludingAssessedTax",
                    "SalesRevenueNet",
                ],
            ),
            "annual_net_income": self._annual_series(us_gaap, ["NetIncomeLoss"]),
            "annual_operating_income": self._annual_series(us_gaap, ["OperatingIncomeLoss"]),
            "annual_assets": self._annual_series(us_gaap, ["Assets"]),
            "annual_liabilities": self._annual_series(us_gaap, ["Liabilities"]),
            "annual_cash": self._annual_series(
                us_gaap,
                ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
            ),
            "notes": [
                "Data source: SEC EDGAR companyfacts XBRL API.",
                "Values are selected from annual 10-K facts when available.",
                "Revenue tags vary by filer; the tool tries common revenue tags used in SEC XBRL facts.",
            ],
        }

    def get_latest_filings(
        self,
        ticker_or_cik: str,
        limit: int = 5,
        form_type: str | None = None,
    ) -> dict[str, Any]:
        company = self._resolve_company(ticker_or_cik)
        if not company:
            return {"error": "Company not found in SEC company tickers", "query": ticker_or_cik}

        submissions = self._submissions(company.cik)
        recent = submissions.get("filings", {}).get("recent", {})
        filings = []
        forms = recent.get("form", [])
        for idx, form in enumerate(forms):
            if form_type and form != form_type:
                continue
            accession = recent.get("accessionNumber", [None])[idx]
            primary_doc = recent.get("primaryDocument", [None])[idx]
            filing_date = recent.get("filingDate", [None])[idx]
            report_date = recent.get("reportDate", [None])[idx]
            filing_url = None
            if accession and primary_doc:
                accession_clean = accession.replace("-", "")
                filing_url = (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{int(company.cik)}/{accession_clean}/{primary_doc}"
                )
            filings.append(
                {
                    "form": form,
                    "filing_date": filing_date,
                    "report_date": report_date,
                    "accession_number": accession,
                    "url": filing_url,
                }
            )
            if len(filings) >= limit:
                break

        return {
            "company": {
                "cik": company.cik,
                "ticker": company.ticker,
                "title": company.title,
            },
            "filings": filings,
            "source": "SEC submissions API",
        }

    def get_filing_digest(
        self,
        ticker_or_cik: str,
        form_type: str = "10-K",
        max_snippets: int = 8,
    ) -> dict[str, Any]:
        filings_response = self.get_latest_filings(ticker_or_cik, limit=1, form_type=form_type)
        filings = filings_response.get("filings", [])
        if not filings:
            return {
                "error": f"No recent {form_type} filing found",
                "query": ticker_or_cik,
                "source": "SEC submissions API",
            }

        filing = filings[0]
        url = filing.get("url")
        if not url:
            return {"error": "Filing URL unavailable", "filing": filing}

        text = self._get_filing_text(url)
        snippets = self._extract_filing_snippets(text, max_snippets)
        return {
            "company": filings_response.get("company"),
            "filing": filing,
            "snippets": snippets,
            "source": "SEC filing HTML text",
            "note": (
                "Snippets are extracted from the filing text around business, revenue, "
                "MD&A, risk, user, advertising, and cash-flow keywords."
            ),
        }

    def _resolve_company(self, ticker_or_cik: str) -> CompanyMatch | None:
        query = ticker_or_cik.strip().lower()
        for company in self._company_tickers():
            if query in {company.ticker.lower(), company.cik.lower()}:
                return company
        matches = self.search_company(ticker_or_cik, limit=1)
        if not matches:
            return None
        match = matches[0]
        return CompanyMatch(match["cik"], match["ticker"], match["title"])

    def _company_tickers(self) -> list[CompanyMatch]:
        data = self._get_json(COMPANY_TICKERS_URL, host="www.sec.gov")
        return [
            CompanyMatch(
                cik=str(row["cik_str"]).zfill(10),
                ticker=row["ticker"],
                title=row["title"],
            )
            for row in data.values()
        ]

    def _company_facts(self, cik: str) -> dict[str, Any]:
        return self._get_json(COMPANY_FACTS_URL.format(cik=cik), host="data.sec.gov")

    def _submissions(self, cik: str) -> dict[str, Any]:
        return self._get_json(SUBMISSIONS_URL.format(cik=cik), host="data.sec.gov")

    def _get_json(self, url: str, host: str) -> dict[str, Any]:
        headers = {**self.headers, "Host": host}
        with httpx.Client(timeout=self.timeout_seconds, headers=headers) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.json()

    def _get_filing_text(self, url: str) -> str:
        headers = {**self.headers, "Host": "www.sec.gov"}
        with httpx.Client(timeout=self.timeout_seconds, headers=headers, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            html = response.text

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "ix:hidden"]):
            tag.decompose()
        text = soup.get_text(" ")
        text = unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    def _extract_filing_snippets(self, text: str, max_snippets: int) -> list[dict[str, str]]:
        topics = {
            "business_model": ["business model", "our business", "platform"],
            "revenue_drivers": ["advertising revenue", "data licensing", "revenue growth", "revenue"],
            "users_and_engagement": ["daily active", "weekly active", "user", "engagement"],
            "profitability": ["net income", "operating income", "profitability", "loss"],
            "cash_flow": ["cash flow", "operating activities", "free cash flow"],
            "risks": ["risk factors", "competition", "regulation", "privacy"],
            "management_discussion": ["management's discussion", "results of operations"],
        }

        sentences = re.split(r"(?<=[.!?])\s+", text)
        lowered_sentences = [sentence.lower() for sentence in sentences]
        snippets = []
        used_indexes: set[int] = set()
        for topic, keywords in topics.items():
            for keyword in keywords:
                sentence_index = self._find_best_sentence(
                    lowered_sentences,
                    keyword,
                    used_indexes,
                )
                if sentence_index is None:
                    continue
                start = max(0, sentence_index - 1)
                end = min(len(sentences), sentence_index + 3)
                used_indexes.add(sentence_index)
                snippet_text = " ".join(sentences[start:end])
                snippets.append(
                    {
                        "topic": topic,
                        "keyword": keyword,
                        "text": snippet_text[:1400].strip(),
                    }
                )
                break
            if len(snippets) >= max_snippets:
                break
        return snippets

    def _find_best_sentence(
        self,
        lowered_sentences: list[str],
        keyword: str,
        used_indexes: set[int],
    ) -> int | None:
        keyword = keyword.lower()
        for idx, sentence in enumerate(lowered_sentences):
            if idx in used_indexes or keyword not in sentence:
                continue
            if _looks_like_xbrl_noise(sentence):
                continue
            return idx
        return None

    def _annual_series(
        self, us_gaap: dict[str, Any], tags: list[str], limit: int = 5
    ) -> dict[str, Any]:
        for tag in tags:
            fact = us_gaap.get(tag)
            if not fact:
                continue
            units = fact.get("units", {})
            unit_name, rows = self._first_unit(units)
            annual_rows = [
                row
                for row in rows
                if row.get("form") == "10-K"
                and row.get("fp") == "FY"
                and row.get("fy") is not None
                and row.get("val") is not None
            ]
            annual_rows.sort(key=lambda row: row.get("end") or "", reverse=True)
            unique_rows = []
            seen_period_ends = set()
            for row in annual_rows:
                period_end = row.get("end")
                if period_end in seen_period_ends:
                    continue
                seen_period_ends.add(period_end)
                unique_rows.append(row)
            return {
                "tag": tag,
                "label": fact.get("label"),
                "unit": unit_name,
                "values": [
                    {
                        "fy": row.get("fy"),
                        "filed": row.get("filed"),
                        "end": row.get("end"),
                        "value": row.get("val"),
                        "form": row.get("form"),
                    }
                    for row in unique_rows[:limit]
                ],
            }

        return {"error": "No matching SEC fact tag found", "tried_tags": tags, "values": []}

    def _first_unit(self, units: dict[str, list[dict[str, Any]]]) -> tuple[str, list[dict[str, Any]]]:
        if "USD" in units:
            return "USD", units["USD"]
        if "shares" in units:
            return "shares", units["shares"]
        if not units:
            return "unknown", []
        unit_name = next(iter(units))
        return unit_name, units[unit_name]


def _looks_like_xbrl_noise(sentence: str) -> bool:
    noise_markers = ["us-gaap:", "srt:", "dei:", "iso4217:", "xbrli:"]
    return sum(marker in sentence for marker in noise_markers) >= 2
