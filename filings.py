"""
Fetches, parses, and caches 10-K and 10-Q filing sections for the S&P 500 universe.

For each filing we store two sections mapped to common column names:

  10-K  →  item1_text: Item 1  (Business Description)
            item7_text: Item 7  (MD&A)

  10-Q  →  item1_text: Item 1A (Risk Factors — updated risks only; may be empty)
            item7_text: Item 2  (MD&A — quarterly management discussion)

Using the same columns for both form types means get_context() and the scorer
work unchanged. Since get_context() returns the most recent filing before any
given date, a Q3 10-Q (filed November) will automatically be preferred over
the prior year's 10-K for scoring dates in November–January.

Text is truncated to MAX_CHARS per section to keep LLM prompt sizes manageable.
Stored in SQLite at data/filings.db keyed by (ticker, accession_number).

Run this script once to pre-populate the cache; incremental updates add new
filings without re-fetching existing ones.
"""

import os
import re
import sqlite3
import time
from datetime import datetime, UTC

import warnings
import pandas as pd
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

import edgar
from universe import get_tickers

DB_PATH = "data/filings.db"
MAX_CHARS = 4000   # per section — enough context for LLM scoring without bloat
FETCH_DELAY = 0.5  # extra delay between full filing fetches (on top of edgar._get delay)

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS filings (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker           TEXT NOT NULL,
            form_type        TEXT NOT NULL,
            filed_date       TEXT NOT NULL,
            cik              TEXT NOT NULL,
            accession_number TEXT UNIQUE NOT NULL,
            item1_text       TEXT,
            item7_text       TEXT,
            fetched_at       TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ticker_date ON filings (ticker, filed_date)")
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Section extraction
# ---------------------------------------------------------------------------

def _html_to_text(html: str) -> str:
    """Strips HTML tags and normalises whitespace."""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_section(text: str, start_pattern: str, end_pattern: str) -> str:
    """
    Extracts text between the last occurrence of start_pattern and the next
    occurrence of end_pattern. Using the last occurrence skips the TOC entry.
    """
    starts = [m.start() for m in re.finditer(start_pattern, text, re.IGNORECASE)]
    if not starts:
        return ""
    # Use the last match to skip table-of-contents references
    start_pos = starts[-1]

    end_match = re.search(end_pattern, text[start_pos + 50:], re.IGNORECASE)
    end_pos = start_pos + 50 + end_match.start() if end_match else start_pos + MAX_CHARS * 2

    section = text[start_pos:end_pos].strip()
    return section[:MAX_CHARS]


def extract_item1(text: str) -> str:
    return _extract_section(
        text,
        start_pattern=r"item\s+1[\.\s]+business",
        end_pattern=r"item\s+1a[\.\s]|item\s+2[\.\s]",
    )


def extract_item7(text: str) -> str:
    return _extract_section(
        text,
        start_pattern=r"item\s+7[\.\s]+management",
        end_pattern=r"item\s+7a[\.\s]|item\s+8[\.\s]",
    )


def extract_item1a(text: str) -> str:
    """10-Q Item 1A — Risk Factors (updated risks only; often short or empty)."""
    return _extract_section(
        text,
        start_pattern=r"item\s+1a[\.\s]+risk",
        end_pattern=r"item\s+1b[\.\s]|item\s+2[\.\s]",
    )


def extract_item2_10q(text: str) -> str:
    """10-Q Item 2 — Management's Discussion and Analysis."""
    return _extract_section(
        text,
        start_pattern=r"item\s+2[\.\s]+management",
        end_pattern=r"item\s+3[\.\s]|item\s+4[\.\s]",
    )


# ---------------------------------------------------------------------------
# Fetch and store
# ---------------------------------------------------------------------------

def fetch_and_store(ticker: str, conn: sqlite3.Connection,
                    n_filings: int = 3, form_type: str = "10-K"):
    """
    Fetches the most recent n_filings filings of form_type for a ticker and
    stores extracted sections in the database. Skips filings already in DB.

    For 10-K: extracts Item 1 → item1_text, Item 7 → item7_text.
    For 10-Q: extracts Item 1A → item1_text, Item 2 → item7_text.
    """
    cik = edgar.ticker_to_cik(ticker)
    if not cik:
        print(f"  {ticker}: no CIK found, skipping")
        return

    try:
        filings = edgar.get_filing_list(cik, form_type=form_type)
    except Exception as e:
        print(f"  {ticker}: failed to get filing list — {e}")
        return

    filings = filings.head(n_filings)

    for _, row in filings.iterrows():
        acc = row["accession_number"]

        exists = conn.execute(
            "SELECT 1 FROM filings WHERE accession_number = ?", (acc,)
        ).fetchone()
        if exists:
            continue

        try:
            html = edgar.get_filing_html(cik, acc, row["primary_document"])
            text = _html_to_text(html)

            if form_type == "10-Q":
                item1 = extract_item1a(text)
                item7 = extract_item2_10q(text)
            else:
                item1 = extract_item1(text)
                item7 = extract_item7(text)

            conn.execute("""
                INSERT OR IGNORE INTO filings
                    (ticker, form_type, filed_date, cik, accession_number,
                     item1_text, item7_text, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ticker,
                row["form_type"],
                row["filed_date"].strftime("%Y-%m-%d"),
                cik,
                acc,
                item1 or None,
                item7 or None,
                datetime.now(UTC).isoformat(),
            ))
            conn.commit()
            time.sleep(FETCH_DELAY)

        except Exception as e:
            print(f"  {ticker} {acc}: fetch failed — {e}")


# ---------------------------------------------------------------------------
# Point-in-time query
# ---------------------------------------------------------------------------

def get_context(ticker: str, as_of_date: str, conn: sqlite3.Connection) -> dict | None:
    """
    Returns the most recent filing context available before as_of_date.
    Returns dict with item1_text, item7_text, filed_date, accession_number
    — or None if not found.
    """
    row = conn.execute("""
        SELECT item1_text, item7_text, filed_date, accession_number
        FROM filings
        WHERE ticker = ? AND filed_date <= ?
        ORDER BY filed_date DESC
        LIMIT 1
    """, (ticker, as_of_date)).fetchone()

    if not row:
        return None
    return {
        "item1_text":       row[0] or "",
        "item7_text":       row[1] or "",
        "filed_date":       row[2],
        "accession_number": row[3],
    }


# ---------------------------------------------------------------------------
# Main: populate cache for full universe
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tickers = get_tickers()
    conn = get_db()

    print(f"Fetching 10-K filings for {len(tickers)} tickers...")
    print("10-K: 11 per ticker (~FY2014–FY2024, covers 2015–2026 extended backtest window)")
    print("Phase 2 (10-Qs) is commented out — run after validating 10-K backtest.")
    print("This will take ~90 min. Already-cached filings are skipped.\n")

    for i, ticker in enumerate(tickers):
        print(f"[{i+1}/{len(tickers)}] {ticker}")
        fetch_and_store(ticker, conn, n_filings=11, form_type="10-K")  # covers FY2014–FY2024 (2015–2026 extended window)
        # Phase 2 — uncomment after validating 10-K-only backtest:
        # fetch_and_store(ticker, conn, n_filings=12, form_type="10-Q")

    total = conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0]
    print(f"\nDone. {total} filings stored in {DB_PATH}")
    conn.close()
