"""
Fetches and updates all narrative popularity data and recomputes activation signals.

Runs in order: trends → reprocess → wikipedia → activation.
Safe to re-run — each step skips already-cached data unless --force is passed.

Usage:
    venv/bin/python fetch_narratives.py           # incremental update
    venv/bin/python fetch_narratives.py --force   # re-fetch everything
"""

import argparse
import os
import subprocess
import sys

import pandas as pd

import trends as trends_mod
import wiki as wiki_mod
import activation as activation_mod
from narratives import NARRATIVES, NARRATIVE_MAP
from activation import active_narratives_on
from datetime import date


def step(n, label):
    print(f"\n{'='*60}")
    print(f"  Step {n}: {label}")
    print(f"{'='*60}\n")


def reprocess():
    """Resamples any daily trends CSVs to weekly in-place."""
    TRENDS_DIR = "data/trends"
    if not os.path.exists(TRENDS_DIR):
        return
    resampled = 0
    for fname in os.listdir(TRENDS_DIR):
        if not fname.endswith(".csv"):
            continue
        path = os.path.join(TRENDS_DIR, fname)
        df = pd.read_csv(path, parse_dates=["date"])
        if len(df) < 500:
            continue
        series = df.set_index("date")["score"].resample("W-MON").max().dropna()
        if series.max() > 0:
            series = (series / series.max() * 100).round(2)
        series.reset_index().rename(columns={"score": "score"}).to_csv(path, index=False)
        print(f"  Resampled {fname}: {len(df)} rows → {len(series)} weeks")
        resampled += 1
    if resampled == 0:
        print("  All files already weekly — nothing to resample.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Re-fetch all data even if already cached")
    args = parser.parse_args()

    step(1, "Google Trends (~45 min, rate-limited)")
    trends_mod.fetch_all(force=args.force)

    step(2, "Resample any daily files to weekly")
    reprocess()

    step(3, "Wikipedia pageviews (~5 min)")
    wiki_mod.fetch_all(force=args.force)

    step(4, "Recompute activation signals")
    activation_mod.compute_all()

    # Summary
    today = date.today().isoformat()
    active = active_narratives_on(today)
    signal_files = [f for f in os.listdir("data/signals") if f.endswith(".csv")]

    print(f"\n{'='*60}")
    print(f"  Done")
    print(f"{'='*60}")
    print(f"  Signal files : {len(signal_files)}/28 narratives")
    print(f"  Active today : {len(active)} — {[NARRATIVE_MAP[n]['label'] for n in active]}")
    print(f"\n  Commit new files when ready:")
    print(f"    git add data/trends/ data/signals/ data/wikipedia/")
    print(f"    git commit -m 'Update narrative data'")
