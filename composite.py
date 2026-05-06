"""
Composite narrative factor construction.

Combines per-company narrative exposure scores with narrative discussion weights
to produce a single composite factor score per (ticker, date).

Pipeline:
  1. For each date, determine which narratives are active and their weights
  2. Pull exposure scores for each (ticker, active_narrative) pair
  3. Compute weighted sum: NarrativeComposite(i,t) = Σ_k [Exposure(i,k,t) × Weight(k,t)]
  4. Winsorize at 2.5/97.5 percentile within each industry group
  5. Z-score standardise within each industry group

Output: data/factor_scores.csv
Columns: date, ticker, sector, raw_score

The factor-neutralised variant (residualising against momentum, value, quality,
leverage, beta) is handled in the backtest layer, which already has price and
financial data. This module produces the raw signal only.
"""

import os
import sqlite3
import warnings

import numpy as np
import pandas as pd
from scipy import stats

from activation import compute_activation
from narratives import NARRATIVES
from universe import fetch_universe

SCORES_DB = "data/scores.db"
TRENDS_DIR = "data/trends"
OUTPUT_FILE = "data/factor_scores.csv"

WINSOR_LOW = 0.025
WINSOR_HIGH = 0.975
NARRATIVE_WEIGHT_CAP = 100  # matches paper: cap each narrative score at 100 before weighting


# ---------------------------------------------------------------------------
# Narrative weights
# ---------------------------------------------------------------------------

def build_weight_series() -> pd.DataFrame:
    """
    Returns a DataFrame indexed by (date, narrative_id) with columns:
      - popularity: raw popularity score
      - active:     1/0 activation flag
      - weight:     discussion-share weight (only nonzero when active)

    Weight = clipped_popularity / sum(clipped_popularity across active narratives)
    """
    frames = []
    for narrative in NARRATIVES:
        nid = narrative["id"]
        trends_path = os.path.join(TRENDS_DIR, f"{nid}.csv")
        signals_path = os.path.join("data/signals", f"{nid}.csv")

        if not os.path.exists(trends_path) or not os.path.exists(signals_path):
            continue

        trends = pd.read_csv(trends_path, parse_dates=["date"])
        signals = pd.read_csv(signals_path, parse_dates=["date"])

        merged = trends.merge(signals[["date", "active"]], on="date", how="inner")
        merged["narrative_id"] = nid
        merged = merged.rename(columns={"score": "popularity"})
        frames.append(merged[["date", "narrative_id", "popularity", "active"]])

    if not frames:
        raise RuntimeError("No trends/signals data found. Run trends.py and activation.py first.")

    df = pd.concat(frames, ignore_index=True)

    # Cap popularity before weighting
    df["clipped"] = df["popularity"].clip(upper=NARRATIVE_WEIGHT_CAP)
    df["clipped"] = df["clipped"] * df["active"]  # zero out inactive

    # Compute weight as share of total active discussion on each date
    total = df.groupby("date")["clipped"].transform("sum")
    df["weight"] = df["clipped"] / total.replace(0, np.nan)
    df["weight"] = df["weight"].fillna(0)

    return df[["date", "narrative_id", "popularity", "active", "weight"]]


# ---------------------------------------------------------------------------
# Exposure scores
# ---------------------------------------------------------------------------

def load_scores(conn: sqlite3.Connection) -> pd.DataFrame:
    """Loads all cached exposure scores from scores.db."""
    return pd.read_sql("""
        SELECT ticker, narrative_id, as_of_date AS date, score
        FROM scores
    """, conn, parse_dates=["date"])


# ---------------------------------------------------------------------------
# Composite construction
# ---------------------------------------------------------------------------

def _winsorise_zscore(series: pd.Series) -> pd.Series:
    """Winsorises then z-scores a series. Returns NaN for groups with < 3 stocks."""
    if series.dropna().shape[0] < 3:
        return pd.Series(np.nan, index=series.index)
    low = series.quantile(WINSOR_LOW)
    high = series.quantile(WINSOR_HIGH)
    clipped = series.clip(lower=low, upper=high)
    std = clipped.std()
    if std == 0:
        return pd.Series(0.0, index=series.index)
    return (clipped - clipped.mean()) / std


def build_composite(dates: list[str] | None = None) -> pd.DataFrame:
    """
    Builds the composite factor score for every (date, ticker) pair where
    at least one active narrative has a cached exposure score.

    Args:
        dates: optional list of YYYY-MM-DD strings to restrict computation.
               If None, uses all dates present in signals data.

    Returns:
        DataFrame with columns: date, ticker, sector, raw_score
    """
    weights = build_weight_series()

    conn = sqlite3.connect(SCORES_DB)
    scores = load_scores(conn)
    conn.close()

    if scores.empty:
        raise RuntimeError("No scores in scores.db. Run scorer.py first.")

    universe = fetch_universe()[["ticker", "sector", "sub_industry"]]

    if dates:
        weights = weights[weights["date"].isin(pd.to_datetime(dates))]

    # Only keep active narratives with nonzero weight
    active_weights = weights[weights["weight"] > 0]

    # Merge scores with weights
    merged = scores.merge(
        active_weights[["date", "narrative_id", "weight"]],
        on=["date", "narrative_id"],
        how="inner",
    )

    if merged.empty:
        raise RuntimeError(
            "No overlap between score dates and active narrative dates. "
            "Check that scorer was run for dates when narratives were active."
        )

    # Weighted sum per (ticker, date)
    merged["weighted_score"] = merged["score"] * merged["weight"]
    composite = (
        merged.groupby(["date", "ticker"])["weighted_score"]
        .sum()
        .reset_index()
        .rename(columns={"weighted_score": "raw_score"})
    )

    # Attach sector for industry-neutral normalisation
    composite = composite.merge(universe[["ticker", "sector"]], on="ticker", how="left")

    # Winsorise + z-score within each (date, sector) group
    composite["raw_score"] = (
        composite.groupby(["date", "sector"])["raw_score"]
        .transform(_winsorise_zscore)
    )

    composite = composite.sort_values(["date", "ticker"]).reset_index(drop=True)
    return composite


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_and_save(dates: list[str] | None = None, verbose: bool = True) -> pd.DataFrame:
    """Builds composite scores and saves to OUTPUT_FILE."""
    if verbose:
        print("Building composite factor scores...")

    df = build_composite(dates)

    os.makedirs("data", exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False)

    if verbose:
        print(f"Saved {len(df):,} rows → {OUTPUT_FILE}")
        print(f"Date range: {df['date'].min().date()} – {df['date'].max().date()}")
        print(f"Tickers: {df['ticker'].nunique()}")
        print(f"\nScore distribution:")
        print(df["raw_score"].describe().round(3).to_string())

    return df


if __name__ == "__main__":
    df = build_and_save()
