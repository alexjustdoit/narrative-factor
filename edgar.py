"""
SEC EDGAR API client.

SEC requires a descriptive User-Agent with contact info on all requests.
Set EDGAR_EMAIL in .env or it defaults to a placeholder.
"""

import os
import json
import time
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

EDGAR_EMAIL = os.getenv("EDGAR_EMAIL", "narrative-factor@research.com")
HEADERS = {
    "User-Agent": f"narrative-factor-research {EDGAR_EMAIL}",
    "Accept-Encoding": "gzip, deflate",
}

CIK_CACHE = "data/universe/cik_map.json"
REQUEST_DELAY = 0.15  # SEC rate limit: max ~10 req/sec; stay well under


def _get(url: str) -> requests.Response:
    time.sleep(REQUEST_DELAY)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp


# ---------------------------------------------------------------------------
# CIK lookup
# ---------------------------------------------------------------------------

def get_cik_map(force: bool = False) -> dict[str, str]:
    """
    Returns {ticker: zero-padded-CIK} for all SEC-registered companies.
    Downloaded once from SEC and cached locally.
    """
    os.makedirs("data/universe", exist_ok=True)
    if os.path.exists(CIK_CACHE) and not force:
        with open(CIK_CACHE) as f:
            return json.load(f)

    print("Downloading CIK map from SEC EDGAR...")
    data = _get("https://www.sec.gov/files/company_tickers.json").json()

    cik_map = {}
    for entry in data.values():
        ticker = entry["ticker"].upper().replace(".", "-")
        cik = str(entry["cik_str"]).zfill(10)
        cik_map[ticker] = cik

    with open(CIK_CACHE, "w") as f:
        json.dump(cik_map, f)

    print(f"Cached {len(cik_map)} CIKs → {CIK_CACHE}")
    return cik_map


def ticker_to_cik(ticker: str) -> str | None:
    cik_map = get_cik_map()
    return cik_map.get(ticker.upper())


# ---------------------------------------------------------------------------
# Filing metadata
# ---------------------------------------------------------------------------

def get_filing_list(cik: str, form_type: str = "10-K") -> pd.DataFrame:
    """
    Returns metadata for all filings of a given type for a CIK.
    Columns: accession_number, filed_date, form_type, primary_document
    """
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    data = _get(url).json()

    recent = data["filings"]["recent"]
    df = pd.DataFrame({
        "accession_number": recent["accessionNumber"],
        "filed_date":        pd.to_datetime(recent["filingDate"]),
        "form_type":         recent["form"],
        "primary_document":  recent["primaryDocument"],
    })

    df = df[df["form_type"].str.startswith(form_type)].copy()
    df = df.sort_values("filed_date", ascending=False).reset_index(drop=True)
    return df


def get_filing_as_of(cik: str, as_of_date: str, form_type: str = "10-K") -> dict | None:
    """
    Returns the most recent filing of form_type filed on or before as_of_date.
    Returns None if no filing found.
    """
    target = pd.Timestamp(as_of_date)
    df = get_filing_list(cik, form_type)
    prior = df[df["filed_date"] <= target]
    if prior.empty:
        return None
    row = prior.iloc[0]
    return row.to_dict()


# ---------------------------------------------------------------------------
# Filing document fetch
# ---------------------------------------------------------------------------

def get_filing_html(cik: str, accession_number: str, primary_document: str) -> str:
    """
    Fetches the raw HTML of a filing's primary document.
    """
    acc_nodash = accession_number.replace("-", "")
    cik_int = int(cik)
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{primary_document}"
    return _get(url).text
