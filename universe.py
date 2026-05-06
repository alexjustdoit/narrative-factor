"""
Builds and caches the investable universe from the S&P 500 constituent list.

Uses Wikipedia as the source for current constituents + GICS classification.
GICS Sector (12 groups) and GICS Sub-Industry (31+ groups) are used for
industry-neutral signal construction in the composite factor.

Output: data/universe/tickers.csv
"""

import io
import os
import requests
import pandas as pd

UNIVERSE_DIR = "data/universe"
UNIVERSE_FILE = os.path.join(UNIVERSE_DIR, "tickers.csv")
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}


def fetch_universe(force: bool = False) -> pd.DataFrame:
    """
    Fetches S&P 500 constituents from Wikipedia.
    Returns DataFrame with columns: ticker, name, sector, sub_industry
    """
    if os.path.exists(UNIVERSE_FILE) and not force:
        return pd.read_csv(UNIVERSE_FILE)

    os.makedirs(UNIVERSE_DIR, exist_ok=True)
    print("Fetching S&P 500 constituent list from Wikipedia...")

    resp = requests.get(WIKI_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text), header=0)
    df = tables[0]

    df = df.rename(columns={
        "Symbol": "ticker",
        "Security": "name",
        "GICS Sector": "sector",
        "GICS Sub-Industry": "sub_industry",
    })

    # yfinance uses BRK-B not BRK.B
    df["ticker"] = df["ticker"].str.replace(".", "-", regex=False)
    df = df[["ticker", "name", "sector", "sub_industry"]].copy()

    df.to_csv(UNIVERSE_FILE, index=False)
    print(f"Saved {len(df)} tickers → {UNIVERSE_FILE}")
    return df


def get_tickers() -> list[str]:
    return fetch_universe()["ticker"].tolist()


def get_sector_map() -> dict[str, str]:
    """Returns {ticker: GICS sector} for industry-neutral construction."""
    df = fetch_universe()
    return dict(zip(df["ticker"], df["sector"]))


def get_subindustry_map() -> dict[str, str]:
    """Returns {ticker: GICS sub-industry} for subindustry-neutral construction."""
    df = fetch_universe()
    return dict(zip(df["ticker"], df["sub_industry"]))


if __name__ == "__main__":
    df = fetch_universe(force=True)
    print(f"\n{len(df)} tickers loaded")
    print(f"Sectors ({df['sector'].nunique()}): ")
    print(df["sector"].value_counts().to_string())
    print(f"\nSub-industries: {df['sub_industry'].nunique()}")
