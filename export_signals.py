"""
Pre-computes narrative composite scores for all historical weekly dates and
exports them as a parquet file for use in the QuantConnect backtest.

Output: data/signals/composite_scores.parquet
        columns: [date, ticker, sector, composite_score, active_narrative_count]

Supports incremental updates — if the output file already exists, only dates
after the last recorded date are computed and appended.

Usage:
    python export_signals.py               # full run or incremental update
    python export_signals.py --from 2024-01-01  # recompute from a specific date
    python export_signals.py --force        # recompute everything from scratch
"""

import argparse
import os
import sys
import traceback
import pandas as pd

from composite import build_composite
from scorer import get_scores_db
import filings as filing_store
from universe import fetch_universe

OUTPUT_FILE = "data/signals/composite_scores.parquet"
START_DATE = "2020-01-01"


def load_existing() -> pd.DataFrame | None:
    if os.path.exists(OUTPUT_FILE):
        return pd.read_parquet(OUTPUT_FILE)
    return None


def last_computed_date(existing: pd.DataFrame | None) -> pd.Timestamp | None:
    if existing is None or existing.empty:
        return None
    return pd.to_datetime(existing["date"]).max()


def build_date_range(from_date: str | None, force: bool) -> list[str]:
    existing = None if force else load_existing()
    last = last_computed_date(existing)

    if from_date:
        start = pd.Timestamp(from_date)
    elif last is not None:
        start = last + pd.Timedelta(weeks=1)
    else:
        start = pd.Timestamp(START_DATE)

    today = pd.Timestamp.today().normalize()
    if start > today:
        return []

    return [d.strftime("%Y-%m-%d") for d in pd.date_range(start=start, end=today, freq="W-MON")]


def run(from_date: str | None = None, force: bool = False) -> None:
    os.makedirs("data/signals", exist_ok=True)

    universe_df = fetch_universe()
    tickers = universe_df["ticker"].tolist()
    sector_map = dict(zip(universe_df["ticker"], universe_df["sector"]))

    dates = build_date_range(from_date, force)
    if not dates:
        print("Nothing to compute — output is already up to date.")
        return

    existing = None if force else load_existing()
    print(f"Universe: {len(tickers)} tickers")
    print(f"Dates to compute: {len(dates)} ({dates[0]} → {dates[-1]})")
    if existing is not None:
        print(f"Appending to {len(existing):,} existing rows")
    print()

    scores_conn = get_scores_db()
    filings_conn = filing_store.get_db()

    new_rows = []
    failed = []

    for i, date_str in enumerate(dates, 1):
        try:
            df = build_composite(date_str, tickers, sector_map, scores_conn, filings_conn)
            if not df.empty:
                df.insert(0, "date", pd.Timestamp(date_str))
                new_rows.append(df)
                active = int(df["active_narrative_count"].iloc[0]) if "active_narrative_count" in df.columns else "?"
                print(f"[{i}/{len(dates)}] {date_str} — {len(df)} tickers scored, {active} active narratives")
            else:
                print(f"[{i}/{len(dates)}] {date_str} — no active narratives, skipped")
        except Exception:
            failed.append(date_str)
            print(f"[{i}/{len(dates)}] {date_str} — ERROR")
            traceback.print_exc()

    scores_conn.close()
    filings_conn.close()

    if not new_rows:
        print("\nNo new rows generated.")
        if failed:
            print(f"Failed dates: {failed}")
        return

    new_df = pd.concat(new_rows, ignore_index=True)

    if existing is not None and not force:
        result = pd.concat([existing, new_df], ignore_index=True)
        result = result.drop_duplicates(subset=["date", "ticker"], keep="last")
        result = result.sort_values(["date", "ticker"]).reset_index(drop=True)
    else:
        result = new_df.sort_values(["date", "ticker"]).reset_index(drop=True)

    result["date"] = pd.to_datetime(result["date"])
    result.to_parquet(OUTPUT_FILE, index=False)

    print(f"\nSaved {len(result):,} total rows → {OUTPUT_FILE}")
    print(f"Date range: {result['date'].min().date()} → {result['date'].max().date()}")
    print(f"Tickers with scores: {result['ticker'].nunique()}")
    if failed:
        print(f"\nWARNING: {len(failed)} dates failed and were skipped: {failed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export narrative composite signals for backtesting")
    parser.add_argument("--from", dest="from_date", metavar="DATE",
                        help="Recompute from this date (YYYY-MM-DD) instead of resuming")
    parser.add_argument("--force", action="store_true",
                        help="Recompute everything from scratch, overwriting existing output")
    args = parser.parse_args()

    run(from_date=args.from_date, force=args.force)
