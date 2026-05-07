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
import os
import sqlite3
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def run_weekly(backfill: bool = False, skip_trends: bool = False):
    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=8)).isoformat()

    # ------------------------------------------------------------------
    step(1, "Refresh Google Trends")
    # ------------------------------------------------------------------
    if skip_trends:
        print("  Skipped (--skip-trends)")
    else:
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
        for form_type in ("10-K", "10-Q"):
            try:
                filing_list = edgar.get_filing_list(cik, form_type)
                if filing_list.empty:
                    continue
                latest = filing_list.iloc[0]
                latest_date = latest["filed_date"].strftime("%Y-%m-%d")
                cached = filings_conn.execute(
                    "SELECT filed_date FROM filings WHERE ticker=? AND form_type=? "
                    "ORDER BY filed_date DESC LIMIT 1",
                    (ticker, form_type)
                ).fetchone()
                if cached is None or latest_date > cached[0]:
                    filing_store.fetch_and_store(ticker, filings_conn, n_filings=1,
                                                 form_type=form_type)
                    new_filings += 1
            except Exception:
                continue

    filings_conn.close()
    print(f"\nNew filings fetched: {new_filings}")

    # ------------------------------------------------------------------
    step(4, "Score new filings against active narratives")
    # ------------------------------------------------------------------
    if not active_today and not backfill:
        print("No active narratives — skipping scoring.")
    else:
        filings_conn = filing_store.get_db()
        scores_conn = scorer_mod.get_scores_db()

        if backfill:
            print("Backfill mode: scoring full universe × all historical narratives...")
            _run_backfill(tickers, scores_conn, filings_conn)
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


def _detect_workers() -> tuple[int, list[str]]:
    """
    Returns (n_workers, [endpoint_urls]).

    Detection order:
      1. BACKFILL_WORKERS env var — use this for Strix APU nodes (not visible to nvidia-smi)
      2. nvidia-smi — counts discrete NVIDIA GPUs automatically
      3. Default 4

    LOCAL_LLM_BASE_URL can be comma-separated for multi-node setups:
      LOCAL_LLM_BASE_URL=http://192.168.1.2:11434/v1,http://192.168.1.3:11434/v1
    Workers are assigned URLs round-robin across endpoints.
    """
    raw_url = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
    urls = [u.strip() for u in raw_url.split(",") if u.strip()]

    env_workers = os.getenv("BACKFILL_WORKERS")
    if env_workers:
        n = int(env_workers)
        print(f"  Workers: {n} (from BACKFILL_WORKERS env var)")
        return n, urls

    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            gpus = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
            if gpus:
                print(f"  Detected {len(gpus)} GPU(s) via nvidia-smi:")
                for g in gpus:
                    print(f"    • {g}")
                return len(gpus), urls
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    print("  nvidia-smi not found — defaulting to 4 workers")
    print("  (Set BACKFILL_WORKERS=N to override, e.g. BACKFILL_WORKERS=14 for full cluster)")
    return 4, urls


def _run_backfill(tickers: list[str], scores_conn: sqlite3.Connection,
                  filings_conn: sqlite3.Connection):
    """
    Parallel backfill: enumerates all unique (ticker, narrative_id, accession_number)
    combos, pre-filters already-cached ones, then dispatches uncached items to a
    thread pool. Each thread opens its own DB connections and LLM client.

    Fixes a bug in the old sequential version: the old code only scored narratives
    active TODAY, missing narratives that were active historically but not now
    (e.g. pandemic in 2020, Ukraine in 2022). This version discovers all narratives
    that were ever active from the signal files.
    """
    # ---- Detect parallelism ----
    n_workers, urls = _detect_workers()
    print(f"  Endpoints: {urls}")

    # ---- Discover all ever-active narrative IDs ----
    ever_active_ids = set()
    for narrative in NARRATIVES:
        path = f"data/signals/{narrative['id']}.csv"
        try:
            sig = pd.read_csv(path, parse_dates=["date"])
            if (sig["active"] == 1).any():
                ever_active_ids.add(narrative["id"])
        except FileNotFoundError:
            continue

    if not ever_active_ids:
        print("No active narrative signal files found. Run activation.py first.")
        return
    print(f"  Narratives ever active: {len(ever_active_ids)}")

    # ---- Load all filings (read-only from the caller's connection) ----
    ticker_set = set(tickers)
    filing_rows = filings_conn.execute(
        "SELECT ticker, accession_number, filed_date FROM filings ORDER BY ticker, filed_date"
    ).fetchall()
    filing_rows = [(t, a, d) for t, a, d in filing_rows if t in ticker_set]

    # ---- Pre-filter: which combos are already cached? ----
    cached_rows = scores_conn.execute(
        "SELECT ticker, narrative_id, accession_number FROM scores"
    ).fetchall()
    cached_set = set(cached_rows)

    # ---- Build uncached work queue ----
    work_items = []
    for ticker, accession_number, filed_date in filing_rows:
        for nid in ever_active_ids:
            if (ticker, nid, accession_number) not in cached_set:
                work_items.append((ticker, nid, accession_number, filed_date))

    total_possible = len(filing_rows) * len(ever_active_ids)
    already_cached = total_possible - len(work_items)
    print(f"\n  Total unique combos : {total_possible:,}")
    print(f"  Already cached      : {already_cached:,}")
    print(f"  To score now        : {len(work_items):,}")

    if not work_items:
        print("\n  Nothing to score — backfill already complete.")
        return

    est_secs = len(work_items) / n_workers * 6   # ~6s per call per worker
    est_hrs  = est_secs / 3600
    print(f"  Estimated time      : ~{est_hrs:.1f} hrs at {n_workers} workers")
    print(f"\nStarting parallel backfill with {n_workers} workers...\n")

    # ---- Worker function (runs in thread pool) ----
    counter = {"done": 0, "errors": 0, "cached": 0}
    lock    = threading.Lock()

    def _worker(item: tuple, endpoint_url: str):
        ticker, nid, accession_number, filed_date = item
        try:
            # Each thread opens its own connections — never share across threads
            local_filings = filing_store.get_db()
            try:
                row = local_filings.execute(
                    "SELECT item1_text, item7_text FROM filings WHERE accession_number = ?",
                    (accession_number,),
                ).fetchone()
            finally:
                local_filings.close()

            if not row:
                return

            result = scorer_mod.score_direct(
                ticker, nid, accession_number, filed_date,
                row[0], row[1],
                endpoint_url=endpoint_url,
            )

            with lock:
                if result and result.get("cached"):
                    counter["cached"] += 1
                else:
                    counter["done"] += 1
                n = counter["done"] + counter["cached"]
                if n % 200 == 0 or n == len(work_items):
                    pct = n / len(work_items) * 100
                    print(f"  {n:,}/{len(work_items):,}  ({pct:.1f}%)  "
                          f"[scored: {counter['done']:,}  cached: {counter['cached']:,}  "
                          f"errors: {counter['errors']:,}]", flush=True)
        except Exception as e:
            with lock:
                counter["errors"] += 1
                if counter["errors"] <= 5:
                    print(f"  ERROR {ticker}×{nid}: {e}", flush=True)

    # ---- Dispatch ----
    with ThreadPoolExecutor(max_workers=n_workers) as executor:
        futures = [
            executor.submit(_worker, item, urls[i % len(urls)])
            for i, item in enumerate(work_items)
        ]
        for _ in as_completed(futures):
            pass

    print(f"\n  Backfill complete:")
    print(f"    Scored  : {counter['done']:,}")
    print(f"    Cached  : {counter['cached']:,}")
    print(f"    Errors  : {counter['errors']:,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Score full historical universe (first run only)",
    )
    parser.add_argument(
        "--skip-trends",
        action="store_true",
        help="Skip Google Trends refresh (useful when re-running backfill in the same session)",
    )
    args = parser.parse_args()
    run_weekly(backfill=args.backfill, skip_trends=args.skip_trends)
