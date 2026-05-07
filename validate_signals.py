"""
Validates composite_scores.parquet before uploading to QuantConnect.

Checks:
  - Schema and types
  - Date range and continuity
  - Ticker coverage per date
  - Score distribution
  - Active narrative periods
  - Inactive (no-signal) periods

Usage:
    python validate_signals.py
    python validate_signals.py --file path/to/composite_scores.parquet
"""

import argparse
import sys
import numpy as np
import pandas as pd

DEFAULT_FILE = "data/signals/composite_scores.parquet"
EXPECTED_COLS = {"date", "ticker", "sector", "composite_score", "active_narrative_count"}


def check(label: str, passed: bool, detail: str = "") -> bool:
    status = "PASS" if passed else "FAIL"
    line = f"  [{status}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    return passed


def run(filepath: str) -> bool:
    print(f"\nValidating: {filepath}\n")
    all_passed = True

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------
    try:
        df = pd.read_parquet(filepath)
    except FileNotFoundError:
        print(f"  [FAIL] File not found: {filepath}")
        print("\n  Run export_signals.py first to generate the signal file.")
        return False
    except Exception as e:
        print(f"  [FAIL] Could not load parquet: {e}")
        return False

    print(f"  Loaded {len(df):,} rows\n")

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    print("Schema")
    missing_cols = EXPECTED_COLS - set(df.columns)
    all_passed &= check("Required columns present", not missing_cols,
                        f"missing: {missing_cols}" if missing_cols else "")
    all_passed &= check("date is datetime", pd.api.types.is_datetime64_any_dtype(df["date"]))
    all_passed &= check("composite_score is numeric",
                        pd.api.types.is_numeric_dtype(df["composite_score"]))
    all_passed &= check("No null tickers", df["ticker"].isna().sum() == 0)
    all_passed &= check("No null scores",  df["composite_score"].isna().sum() == 0)

    # ------------------------------------------------------------------
    # Date range
    # ------------------------------------------------------------------
    print("\nDate range")
    df["date"] = pd.to_datetime(df["date"])
    dates = sorted(df["date"].unique())
    start, end = dates[0], dates[-1]
    n_dates = len(dates)

    all_passed &= check("Starts 2020 or later", start.year >= 2020, str(start.date()))
    all_passed &= check("Ends recently (within 60 days)",
                        (pd.Timestamp.today() - end).days <= 60,
                        f"last date: {end.date()}")

    expected_mondays = pd.date_range(start=start, end=end, freq="W-MON")
    missing_mondays = set(expected_mondays) - set(pd.DatetimeIndex(dates))
    pct_missing = len(missing_mondays) / len(expected_mondays) * 100
    all_passed &= check("Date continuity (weekly Mondays)",
                        pct_missing < 5,
                        f"{len(missing_mondays)} of {len(expected_mondays)} Mondays missing ({pct_missing:.1f}%)")

    print(f"         Range : {start.date()} → {end.date()} ({n_dates} dates)")

    # ------------------------------------------------------------------
    # Coverage
    # ------------------------------------------------------------------
    print("\nTicker coverage")
    coverage = df.groupby("date")["ticker"].count()
    median_cov = int(coverage.median())
    min_cov    = int(coverage.min())
    low_dates  = coverage[coverage < 50]

    all_passed &= check("Median coverage ≥ 100 tickers/date", median_cov >= 100,
                        f"median={median_cov}")
    all_passed &= check("No dates with < 50 tickers", len(low_dates) == 0,
                        f"{len(low_dates)} dates below threshold" if len(low_dates) else "")

    total_tickers = df["ticker"].nunique()
    print(f"         Tickers total : {total_tickers}")
    print(f"         Per date      : median={median_cov}, min={min_cov}")

    # ------------------------------------------------------------------
    # Score distribution
    # ------------------------------------------------------------------
    print("\nScore distribution")
    scores = df["composite_score"]
    mean_s = scores.mean()
    std_s  = scores.std()
    pct_zero = (scores == 0).mean() * 100

    all_passed &= check("Mean score near 0 (industry-neutral)",
                        abs(mean_s) < 0.1, f"mean={mean_s:.4f}")
    all_passed &= check("Std dev reasonable (0.5 – 2.0)",
                        0.5 <= std_s <= 2.0, f"std={std_s:.4f}")
    all_passed &= check("Not degenerate (< 50% zeros)", pct_zero < 50,
                        f"{pct_zero:.1f}% zeros")

    print(f"         Mean={mean_s:.4f}  Std={std_s:.4f}  "
          f"Min={scores.min():.2f}  Max={scores.max():.2f}")

    # ------------------------------------------------------------------
    # Narrative activity
    # ------------------------------------------------------------------
    print("\nNarrative activity")
    if "active_narrative_count" in df.columns:
        by_date = df.drop_duplicates("date").set_index("date")["active_narrative_count"]
        inactive_dates = (by_date == 0).sum()
        max_active = int(by_date.max())
        avg_active = by_date[by_date > 0].mean()

        all_passed &= check("At least some active periods",
                            (by_date > 0).sum() > 0,
                            f"{(by_date > 0).sum()} of {len(by_date)} dates active")
        check("Inactive periods present (expected by design)",
              inactive_dates > 0,
              f"{inactive_dates} inactive dates")
        print(f"         Max active narratives : {max_active}")
        print(f"         Avg when active        : {avg_active:.1f}")
    else:
        print("         active_narrative_count column not present — skipping")

    # ------------------------------------------------------------------
    # Sector breakdown
    # ------------------------------------------------------------------
    print("\nSector breakdown")
    if "sector" in df.columns:
        sector_counts = df["ticker"].groupby(df["sector"]).nunique().sort_values(ascending=False)
        all_passed &= check("At least 5 sectors represented", len(sector_counts) >= 5,
                            f"{len(sector_counts)} sectors")
        for sector, n in sector_counts.items():
            print(f"         {sector:<45} {n:>4} tickers")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(f"\n{'─'*50}")
    if all_passed:
        print("  All checks passed — safe to upload to QuantConnect.\n")
    else:
        print("  Some checks FAILED — review issues above before uploading.\n")

    return all_passed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=DEFAULT_FILE,
                        help="Path to composite_scores.parquet")
    args = parser.parse_args()
    ok = run(args.file)
    sys.exit(0 if ok else 1)
