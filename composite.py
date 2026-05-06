"""
Composite narrative factor construction.

Combines per-company narrative exposure scores with narrative discussion weights
to produce a single composite factor score per (ticker, date).

Pipeline:
  1. Determine which narratives are active on the given date and their weights
  2. Pull exposure scores for each (ticker, active_narrative) pair
  3. Compute weighted sum: NarrativeComposite(i,t) = Σ_k [Exposure(i,k,t) × Weight(k,t)]
  4. Winsorize at 2.5/97.5 percentile within each industry group
  5. Z-score standardise within each industry group

The factor-neutralised variant (residualising against momentum, value, quality,
leverage, beta) is handled downstream in the backtest layer.

Interface expected by export_signals.py:
  build_composite(date_str, tickers, sector_map, scores_conn, filings_conn)
  → DataFrame(ticker, sector, raw_score, active_narrative_count)
"""

import os
import sqlite3

import numpy as np
import pandas as pd

from narratives import NARRATIVES

TRENDS_DIR   = "data/trends"
SIGNALS_DIR  = "data/signals"
WINSOR_LOW   = 0.025
WINSOR_HIGH  = 0.975
WEIGHT_CAP   = 100   # cap each narrative's popularity before computing share weight


# ---------------------------------------------------------------------------
# Narrative weights for a single date
# ---------------------------------------------------------------------------

def _narrative_weights_on(date_str: str) -> dict[str, float]:
    """
    Returns {narrative_id: weight} for all active narratives on date_str.
    Weight = clipped_popularity / sum(all active clipped popularities).
    Inactive narratives are absent from the dict.
    """
    target = pd.Timestamp(date_str)
    active = {}

    for narrative in NARRATIVES:
        nid        = narrative["id"]
        sig_path   = os.path.join(SIGNALS_DIR, f"{nid}.csv")
        trend_path = os.path.join(TRENDS_DIR,  f"{nid}.csv")

        if not os.path.exists(sig_path) or not os.path.exists(trend_path):
            continue

        sig    = pd.read_csv(sig_path,   parse_dates=["date"])
        trends = pd.read_csv(trend_path, parse_dates=["date"])

        # Most recent row on or before target date
        sig_row   = sig[sig["date"]    <= target]
        trend_row = trends[trends["date"] <= target]

        if sig_row.empty or trend_row.empty:
            continue
        if sig_row.iloc[-1]["active"] != 1:
            continue

        popularity       = float(trend_row.iloc[-1]["score"])
        active[nid]      = min(popularity, WEIGHT_CAP)

    if not active:
        return {}

    total = sum(active.values())
    return {nid: score / total for nid, score in active.items()}


# ---------------------------------------------------------------------------
# Scores lookup
# ---------------------------------------------------------------------------

def _get_scores_for_date(date_str: str, narrative_ids: list[str],
                          scores_conn: sqlite3.Connection,
                          filings_conn: sqlite3.Connection) -> pd.DataFrame:
    """
    For each ticker, finds the accession_number current as of date_str,
    then pulls its cached score for each narrative.
    Returns DataFrame(ticker, narrative_id, score).
    """
    # Get all accession_numbers current as of date_str
    filing_rows = filings_conn.execute("""
        SELECT ticker, accession_number
        FROM (
            SELECT ticker, accession_number,
                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY filed_date DESC) AS rn
            FROM filings
            WHERE filed_date <= ?
        ) WHERE rn = 1
    """, (date_str,)).fetchall()

    if not filing_rows:
        return pd.DataFrame(columns=["ticker", "narrative_id", "score"])

    placeholders = ",".join("?" * len(narrative_ids))
    rows = []
    for ticker, acc in filing_rows:
        score_rows = scores_conn.execute(f"""
            SELECT narrative_id, score
            FROM scores
            WHERE ticker = ? AND accession_number = ?
            AND narrative_id IN ({placeholders})
        """, (ticker, acc, *narrative_ids)).fetchall()
        for nid, score in score_rows:
            rows.append({"ticker": ticker, "narrative_id": nid, "score": score})

    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["ticker", "narrative_id", "score"])


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _winsorise_zscore(series: pd.Series) -> pd.Series:
    """Winsorises then z-scores within a group. Returns NaN for groups < 3."""
    if series.dropna().shape[0] < 3:
        return pd.Series(np.nan, index=series.index)
    low  = series.quantile(WINSOR_LOW)
    high = series.quantile(WINSOR_HIGH)
    clipped = series.clip(lower=low, upper=high)
    std = clipped.std()
    if std == 0:
        return pd.Series(0.0, index=series.index)
    return (clipped - clipped.mean()) / std


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_composite(date_str: str,
                    tickers: list[str],
                    sector_map: dict[str, str],
                    scores_conn: sqlite3.Connection,
                    filings_conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Builds composite factor scores for all tickers on a single date.

    Args:
        date_str:     YYYY-MM-DD scoring date
        tickers:      list of ticker symbols to score
        sector_map:   {ticker: GICS sector} for industry-neutral normalisation
        scores_conn:  open connection to data/scores.db
        filings_conn: open connection to data/filings.db

    Returns:
        DataFrame with columns: ticker, sector, raw_score, active_narrative_count
        Empty DataFrame if no narratives are active on this date.
    """
    weights = _narrative_weights_on(date_str)
    if not weights:
        return pd.DataFrame(columns=["ticker", "sector", "raw_score", "active_narrative_count"])

    active_ids = list(weights.keys())
    scores_df  = _get_scores_for_date(date_str, active_ids, scores_conn, filings_conn)

    if scores_df.empty:
        return pd.DataFrame(columns=["ticker", "sector", "raw_score", "active_narrative_count"])

    # Weighted sum per ticker
    scores_df["weighted"] = scores_df["score"] * scores_df["narrative_id"].map(weights)
    composite = (
        scores_df.groupby("ticker")
        .agg(raw_score=("weighted", "sum"), active_narrative_count=("narrative_id", "nunique"))
        .reset_index()
    )

    # Attach sector
    composite["sector"] = composite["ticker"].map(sector_map)

    # Winsorise + z-score within each sector group
    composite["raw_score"] = (
        composite.groupby("sector")["raw_score"]
        .transform(_winsorise_zscore)
    )

    return composite[["ticker", "sector", "raw_score", "active_narrative_count"]]
