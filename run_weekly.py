"""
Weekly pipeline runner.

Runs every step in the correct order for a weekly refresh:
  1. Refresh Google Trends for all 14 narratives
  2. Recompute activation signals
  3. Fetch any new 10-K filings filed this week
  4. Score new filings against currently active narratives
  5. Rebuild composite factor scores
  6. Report what changed

Usage:
    venv/bin/python run_weekly.py

For the initial historical backfill (first run only), use:
    venv/bin/python run_weekly.py --backfill
"""

import argparse
import sqlite3
from datetime import date, timedelta

import pandas as pd

import trends as trends_mod
import activation as activation_mod
import edgar
import filings as filing_store
import scorer as scorer_mod
import composite as composite_mod
from narratives import NARRATIVES, NARRATIVE_MAP
from universe import get_tickers, fetch_universe
from activation import active_narratives_on


def step(n: int, label: str):
    print(f"\n{'='*60}")
    print(f"  Step {n}: {label}")
    print(f"{'='*60}")


def run_weekly(backfill: bool = False):
    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=8)).isoformat()

    # ------------------------------------------------------------------
    step(1, "Refresh Google Trends")
    # ------------------------------------------------------------------
    trends_mod.fetch_all(force=False)  # skips already-cached narratives

    # ------------------------------------------------------------------
    step(2, "Recompute activation signals")
    # ------------------------------------------------------------------
    results = activation_mod.compute_all()
    active_today = active_narratives_on(today)
    active_labels = [NARRATIVE_MAP[nid]["label"] for nid in active_today]
    print(f"\nCurrently active ({len(active_today)}): {active_labels}")

    # ------------------------------------------------------------------
    step(3, "Fetch new 10-K filings")
    # ------------------------------------------------------------------
    tickers = get_tickers()
    filings_conn = filing_store.get_db()
    cik_map = edgar.get_cik_map()

    new_filings = 0
    for ticker in tickers:
        cik = cik_map.get(ticker)
        if not cik:
            continue
        try:
            filing_list = edgar.get_filing_list(cik, "10-K")
            # Check if most recent filing is newer than what we have cached
            if filing_list.empty:
                continue
            latest = filing_list.iloc[0]
            latest_date = latest["filed_date"].strftime("%Y-%m-%d")
            cached = filings_conn.execute(
                "SELECT filed_date FROM filings WHERE ticker=? ORDER BY filed_date DESC LIMIT 1",
                (ticker,)
            ).fetchone()
            if cached is None or latest_date > cached[0]:
                filing_store.fetch_and_store(ticker, filings_conn, n_filings=1)
                new_filings += 1
        except Exception:
            continue

    filings_conn.close()
    print(f"\nNew filings fetched: {new_filings}")

    # ------------------------------------------------------------------
    step(4, "Score new filings against active narratives")
    # ------------------------------------------------------------------
    if not active_today:
        print("No active narratives — skipping scoring.")
    else:
        filings_conn = filing_store.get_db()
        scores_conn = scorer_mod.get_scores_db()

        if backfill:
            # Score all tickers × all dates where narratives were active
            print("Backfill mode: scoring full universe × all historical dates...")
            _run_backfill(tickers, active_today, scores_conn, filings_conn)
        else:
            # Only score tickers that have a new filing this week
            print(f"Scoring {len(tickers)} tickers × {len(active_today)} active narratives...")
            print("(Cached scores are returned instantly — only new combinations call the API)")
            for i, ticker in enumerate(tickers):
                for nid in active_today:
                    scorer_mod.score_one(
                        ticker, nid, today,
                        scores_conn=scores_conn,
                        filings_conn=filings_conn,
                    )
                if (i + 1) % 50 == 0:
                    print(f"  {i+1}/{len(tickers)} tickers processed")

        scores_conn.close()
        filings_conn.close()

    # ------------------------------------------------------------------
    step(5, "Rebuild composite factor scores")
    # ------------------------------------------------------------------
    df = composite_mod.build_and_save()

    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print(f"  Done — {today}")
    print(f"{'='*60}")
    print(f"Active narratives:  {len(active_today)}")
    print(f"Factor scores:      {len(df):,} rows")
    if not df.empty:
        print(f"Tickers covered:    {df['ticker'].nunique()}")


def _run_backfill(tickers, active_narrative_ids, scores_conn, filings_conn):
    """
    Scores all tickers against all historically active narratives.
    Iterates weekly dates and only calls the API for uncached combinations.
    """
    # Collect all dates where any narrative was active
    all_dates = set()
    for nid in NARRATIVES:
        path = f"data/signals/{nid['id']}.csv"
        try:
            sig = pd.read_csv(path, parse_dates=["date"])
            active_dates = sig[sig["active"] == 1]["date"].dt.strftime("%Y-%m-%d")
            all_dates.update(active_dates.tolist())
        except FileNotFoundError:
            continue

    all_dates = sorted(all_dates)
    total = len(all_dates) * len(tickers) * len(active_narrative_ids)
    print(f"Backfill scope: {len(all_dates)} dates × {len(tickers)} tickers × "
          f"{len(active_narrative_ids)} narratives = {total:,} combinations")
    print("Cached combinations are free — only uncached ones call the API.\n")

    done = 0
    for scoring_date in all_dates:
        # Get narratives active on this specific date
        day_active = [
            nid for nid in active_narrative_ids
            if _is_active_on(nid, scoring_date)
        ]
        if not day_active:
            continue
        for ticker in tickers:
            for nid in day_active:
                scorer_mod.score_one(
                    ticker, nid, scoring_date,
                    scores_conn=scores_conn,
                    filings_conn=filings_conn,
                )
            done += 1
            if done % 500 == 0:
                print(f"  {done:,} ticker-dates processed")


def _is_active_on(narrative_id: str, date_str: str) -> bool:
    import os
    path = f"data/signals/{narrative_id}.csv"
    if not os.path.exists(path):
        return False
    sig = pd.read_csv(path, parse_dates=["date"])
    target = pd.Timestamp(date_str)
    row = sig[sig["date"] <= target]
    if row.empty:
        return False
    return bool(row.iloc[-1]["active"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Score full historical universe (first run only)",
    )
    args = parser.parse_args()
    run_weekly(backfill=args.backfill)
