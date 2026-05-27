"""SEC EDGAR full-text search and filing download."""
from dataclasses import dataclass
from typing import Literal

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import get_settings

EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
SUBMISSIONS_URL = "https://data.sec.gov/submissions"
EDGAR_BASE = "https://www.sec.gov/Archives/edgar/data"
HEADERS = {"User-Agent": get_settings().edgar_user_agent}

FormType = Literal["10-K", "10-Q", "8-K"]


@dataclass
class FilingMeta:
    filing_id: str
    ticker: str
    cik: str
    form_type: str
    filed_date: str
    document_url: str
    title: str


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _get(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    r = await client.get(url, headers=HEADERS, timeout=30, **kwargs)
    r.raise_for_status()
    return r


async def get_cik(ticker: str) -> str:
    """Look up CIK using SEC's official company_tickers.json mapping."""
    async with httpx.AsyncClient() as client:
        r = await _get(client, "https://www.sec.gov/files/company_tickers.json")
        data = r.json()
    ticker_upper = ticker.upper()
    for entry in data.values():
        if entry.get("ticker", "").upper() == ticker_upper:
            return str(entry["cik_str"])
    raise ValueError(f"CIK not found for ticker {ticker!r} — check the ticker is listed on SEC EDGAR")


async def search_filings(
    ticker: str,
    form_type: FormType,
    years: list[int],
) -> list[FilingMeta]:
    cik = await get_cik(ticker)
    cik_padded = cik.zfill(10)

    async with httpx.AsyncClient() as client:
        r = await _get(client, f"{SUBMISSIONS_URL}/CIK{cik_padded}.json")
        data = r.json()

    filings_data = data.get("filings", {}).get("recent", {})
    forms = filings_data.get("form", [])
    dates = filings_data.get("filingDate", [])
    accessions = filings_data.get("accessionNumber", [])
    docs = filings_data.get("primaryDocument", [])

    results: list[FilingMeta] = []
    for form, date, accession, doc in zip(forms, dates, accessions, docs):
        if form != form_type:
            continue
        year = int(date[:4])
        if year not in years:
            continue
        acc_clean = accession.replace("-", "")
        url = f"{EDGAR_BASE}/{cik}/{acc_clean}/{doc}"
        results.append(FilingMeta(
            filing_id=accession,
            ticker=ticker.upper(),
            cik=cik,
            form_type=form,
            filed_date=date,
            document_url=url,
            title=f"{ticker.upper()} {form} {date}",
        ))

    return results


async def download_filing(url: str) -> str:
    async with httpx.AsyncClient() as client:
        r = await _get(client, url)
        return r.text
