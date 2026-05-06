"""
One-off: resamples already-fetched daily CSVs to weekly.
Run this after trends.py finishes if some files were saved before the resample fix.
"""

import os
import pandas as pd

TRENDS_DIR = "data/trends"

for fname in os.listdir(TRENDS_DIR):
    if not fname.endswith(".csv"):
        continue
    path = os.path.join(TRENDS_DIR, fname)
    df = pd.read_csv(path, parse_dates=["date"])

    if len(df) < 500:
        print(f"  {fname}: {len(df)} rows — already weekly, skipping")
        continue

    series = df.set_index("date")["score"]
    series = series.resample("W-MON").max().dropna()
    if series.max() > 0:
        series = (series / series.max() * 100).round(2)

    out = series.reset_index()
    out.columns = ["date", "score"]
    out.to_csv(path, index=False)
    print(f"  {fname}: {len(df)} rows → {len(out)} weeks")
