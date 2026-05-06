"""
Fetches, parses, and caches 10-K filing sections for the S&P 500 universe.

For each company we store:
  - Item 1  (Business Description) — what the company does
  - Item 7  (MD&A)                 — management's view of trends and risks

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


# ---------------------------------------------------------------------------
# Fetch and store
# ---------------------------------------------------------------------------

def fetch_and_store(ticker: str, conn: sqlite3.Connection, n_filings: int = 3):
    """
    Fetches the most recent n_filings 10-K filings for a ticker and stores
    extracted sections in the database. Skips filings already in DB.
    """
    cik = edgar.ticker_to_cik(ticker)
    if not cik:
        print(f"  {ticker}: no CIK found, skipping")
        return

    try:
        filings = edgar.get_filing_list(cik, form_type="10-K")
    except Exception as e:
        print(f"  {ticker}: failed to get filing list — {e}")
        return

    filings = filings.head(n_filings)

    for _, row in filings.iterrows():
        acc = row["accession_number"]

        # Skip if already in DB
        exists = conn.execute(
            "SELECT 1 FROM filings WHERE accession_number = ?", (acc,)
        ).fetchone()
        if exists:
            continue

        try:
            html = edgar.get_filing_html(cik, acc, row["primary_document"])
            text = _html_to_text(html)
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
    print("This will take ~30-45 minutes. Already-cached filings are skipped.\n")

    for i, ticker in enumerate(tickers):
        print(f"[{i+1}/{len(tickers)}] {ticker}")
        fetch_and_store(ticker, conn, n_filings=3)

    total = conn.execute("SELECT COUNT(*) FROM filings").fetchone()[0]
    print(f"\nDone. {total} filings stored in {DB_PATH}")
    conn.close()
