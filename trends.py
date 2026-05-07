"""
Fetches weekly Google Trends popularity scores for each narrative.

Google Trends returns a relative interest score (0-100) over the requested window.
Because scores are relative to the window, we fetch in overlapping 6-month chunks
and stitch them together using an overlap period to normalise across chunks.

Output: data/trends/<narrative_id>.csv  with columns [date, score]
"""

import time
import os
import random
import pandas as pd
from pytrends.request import TrendReq
from pytrends.exceptions import TooManyRequestsError
from narratives import NARRATIVES

TRENDS_DIR = "data/trends"
START_DATE = "2020-01-01"

# Delay between chunks within a narrative (seconds)
CHUNK_DELAY = 10
# Delay between narratives (seconds)
NARRATIVE_DELAY = 15
# Exponential backoff on 429: base * 2^attempt, plus jitter
BACKOFF_BASE = 30
MAX_RETRIES = 4


def _fetch_chunk(pytrends: TrendReq, terms: list[str], start: str, end: str) -> pd.Series:
    """Fetch a single time chunk with exponential backoff on 429."""
    for attempt in range(MAX_RETRIES):
        try:
            pytrends.build_payload(
                kw_list=terms[:5],
                timeframe=f"{start} {end}",
                geo="US",
            )
            df = pytrends.interest_over_time()
            if df.empty:
                return pd.Series(dtype=float)
            df = df.drop(columns=["isPartial"], errors="ignore")
            return df.max(axis=1)
        except TooManyRequestsError:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 5)
            print(f"    429 rate limit — waiting {wait:.0f}s before retry {attempt + 1}/{MAX_RETRIES - 1}")
            time.sleep(wait)
        except Exception:
            raise


def _stitch_chunks(chunks: list[pd.Series]) -> pd.Series:
    """
    Normalise and concatenate overlapping chunks into a single continuous series.
    Uses the overlap window to compute a scale factor between adjacent chunks.
    """
    if not chunks:
        return pd.Series(dtype=float)
    result = chunks[0].copy().astype(float)
    for chunk in chunks[1:]:
        overlap = result.index.intersection(chunk.index)
        if len(overlap) < 2:
            result = pd.concat([result, chunk])
            continue
        base_mean = result.loc[overlap].mean()
        chunk_mean = chunk.loc[overlap].mean()
        if chunk_mean == 0:
            continue
        scale = base_mean / chunk_mean
        non_overlap = chunk.index.difference(result.index)
        result = pd.concat([result, chunk.loc[non_overlap] * scale])
    return result.sort_index()


def fetch_narrative(narrative: dict, force: bool = False) -> pd.DataFrame:
    """
    Fetch and cache weekly Trends scores for a single narrative.
    Returns a DataFrame with columns [date, score].
    """
    out_path = os.path.join(TRENDS_DIR, f"{narrative['id']}.csv")
    if os.path.exists(out_path) and not force:
        return pd.read_csv(out_path, parse_dates=["date"])

    pytrends = TrendReq(hl="en-US", tz=0)
    terms = narrative["terms"]
    today = pd.Timestamp.today().strftime("%Y-%m-%d")

    # Build 6-month chunks with 1-month overlap to allow stitching
    periods = pd.date_range(start=START_DATE, end=today, freq="6MS")
    chunks = []
    for i, period_start in enumerate(periods):
        period_end = min(period_start + pd.DateOffset(months=7), pd.Timestamp(today))
        start_str = period_start.strftime("%Y-%m-%d")
        end_str = period_end.strftime("%Y-%m-%d")
        try:
            chunk = _fetch_chunk(pytrends, terms, start_str, end_str)
            if not chunk.empty:
                chunks.append(chunk)
                print(f"    chunk {start_str}–{end_str}: {len(chunk)} rows")
        except Exception as e:
            print(f"  Warning: chunk {start_str}–{end_str} failed: {e}")
        time.sleep(CHUNK_DELAY)

    series = _stitch_chunks(chunks)

    # Resample to weekly (Monday) regardless of input granularity.
    # Google Trends returns daily data for sub-9-month windows, weekly for longer.
    # Standardising here keeps activation.py parameters consistent.
    series.index = pd.to_datetime(series.index)
    series = series.resample("W-MON").max().dropna()

    # Rescale so the all-time max = 100
    if series.max() > 0:
        series = (series / series.max() * 100).round(2)

    df = series.reset_index()
    df.columns = ["date", "score"]
    os.makedirs(TRENDS_DIR, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"  Saved {len(df)} weeks → {out_path}")
    return df


def fetch_all(force: bool = False):
    """Fetch Trends data for all narratives."""
    n_total = len(NARRATIVES)
    for i, narrative in enumerate(NARRATIVES):
        print(f"\n[{i+1}/{n_total}] Fetching: {narrative['label']}")
        fetch_narrative(narrative, force=force)
        if i < len(NARRATIVES) - 1:
            print(f"  Waiting {NARRATIVE_DELAY}s before next narrative...")
            time.sleep(NARRATIVE_DELAY)


if __name__ == "__main__":
    fetch_all()
