"""
Two-stage narrative activation filter (replicates the paper's logic).

Stage 1 — Minimum popularity and growth:
  - Score >= MIN_SCORE (floor on discussion volume)
  - AND score has at least doubled over the prior 3 months OR prior 3 years

Stage 2 — Proximity to trailing high:
  - Score is within PROXIMITY_PCT of its rolling 180-day high
  - Isolates narratives at or near peak attention; filters out fading ones

Output: data/signals/<narrative_id>.csv  with columns [date, score, active]
"""

import os
import pandas as pd
import numpy as np
from narratives import NARRATIVES

SIGNALS_DIR = "data/signals"
TRENDS_DIR = "data/trends"

MIN_SCORE = 10          # minimum absolute popularity floor
GROWTH_THRESHOLD = 1.0  # 100% growth = doubled
LOOKBACK_3M = 13        # ~3 months in weekly data
LOOKBACK_3Y = 156       # ~3 years in weekly data
ROLLING_HIGH_DAYS = 26  # 180 days ≈ 26 weeks
PROXIMITY_PCT = 0.80    # must be within 80% of rolling high


def compute_activation(narrative_id: str) -> pd.DataFrame:
    """
    Load raw Trends scores for a narrative and apply the two-stage filter.
    Returns a DataFrame with columns [date, score, active].
    """
    trends_path = os.path.join(TRENDS_DIR, f"{narrative_id}.csv")
    if not os.path.exists(trends_path):
        raise FileNotFoundError(f"No trends data for {narrative_id}. Run trends.py first.")

    df = pd.read_csv(trends_path, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    scores = df["score"]

    # --- Stage 1: minimum score ---
    meets_floor = scores >= MIN_SCORE

    # --- Stage 1: growth (doubled over 3 months OR 3 years) ---
    score_3m_ago = scores.shift(LOOKBACK_3M)
    score_3y_ago = scores.shift(LOOKBACK_3Y)

    growth_3m = (scores / score_3m_ago.replace(0, np.nan)) - 1
    growth_3y = (scores / score_3y_ago.replace(0, np.nan)) - 1

    # A narrative that rises from below the floor to above it counts as meeting
    # the growth requirement — covers fast spikes from near-zero baselines
    # (e.g. pandemic in March 2020, tariffs in early 2025) where the ratio
    # is undefined because the prior score was effectively zero.
    # fillna(0): treat missing prior data (before series start) as zero baseline.
    emerged_3m = (score_3m_ago.fillna(0) < MIN_SCORE) & meets_floor
    emerged_3y = (score_3y_ago.fillna(0) < MIN_SCORE) & meets_floor

    meets_growth = (
        (growth_3m >= GROWTH_THRESHOLD) | emerged_3m |
        (growth_3y >= GROWTH_THRESHOLD) | emerged_3y
    )

    stage1 = meets_floor & meets_growth

    # --- Stage 2: within 95% of rolling 180-day high ---
    rolling_high = scores.rolling(window=ROLLING_HIGH_DAYS, min_periods=1).max()
    meets_proximity = scores >= (PROXIMITY_PCT * rolling_high)

    # Narrative is active only if it passes both stages
    df["active"] = (stage1 & meets_proximity).astype(int)

    return df[["date", "score", "active"]]


def compute_all() -> dict[str, pd.DataFrame]:
    """Compute activation signals for all narratives and save to CSV."""
    os.makedirs(SIGNALS_DIR, exist_ok=True)
    results = {}
    for narrative in NARRATIVES:
        nid = narrative["id"]
        try:
            df = compute_activation(nid)
            out_path = os.path.join(SIGNALS_DIR, f"{nid}.csv")
            df.to_csv(out_path, index=False)
            active_weeks = df["active"].sum()
            print(f"  {narrative['label']}: {active_weeks} active weeks")
            results[nid] = df
        except FileNotFoundError as e:
            print(f"  Skipping {nid}: {e}")
    return results


def active_narratives_on(date: str) -> list[str]:
    """
    Return list of narrative IDs that are active on a given date (YYYY-MM-DD).
    Useful for inspecting what was active at any point in time.
    """
    target = pd.Timestamp(date)
    active = []
    for narrative in NARRATIVES:
        nid = narrative["id"]
        path = os.path.join(SIGNALS_DIR, f"{nid}.csv")
        if not os.path.exists(path):
            continue
        df = pd.read_csv(path, parse_dates=["date"])
        row = df[df["date"] <= target].iloc[-1] if len(df[df["date"] <= target]) > 0 else None
        if row is not None and row["active"] == 1:
            active.append(nid)
    return active


if __name__ == "__main__":
    results = compute_all()

    # Sanity check: print what was active at key dates
    check_dates = {
        "2020-04-01": "Peak pandemic — expect global_pandemic active",
        "2023-06-01": "AI boom — expect ai_generative active",
        "2022-03-01": "Ukraine invasion — expect ukraine_russia active",
        "2025-04-01": "Tariff cycle — expect us_tariffs active",
    }
    print("\n--- Sanity Checks ---")
    for date, note in check_dates.items():
        active = active_narratives_on(date)
        labels = [n["label"] for n in NARRATIVES if n["id"] in active]
        print(f"\n{date} ({note})")
        print(f"  Active: {labels if labels else 'none'}")
