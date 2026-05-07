"""
Wikipedia pageview data pipeline.

Fetches weekly pageview counts for Wikipedia articles associated with each
narrative. Used as a supplementary activation signal alongside Google Trends.

Wikipedia pageviews are a cleaner signal than search volume in some respects:
less gameable, broader demographic (readers not just searchers), and more
directly tied to information-seeking behavior. The two sources are complementary.

Source: Wikimedia Pageviews REST API (free, no authentication required)
  https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{project}/{access}/{agent}/{article}/{granularity}/{start}/{end}

Output: data/wikipedia/{narrative_id}.csv  with columns [date, views, score]
  - views: raw weekly pageview total summed across all articles for the narrative
  - score: normalized 0–100 (100 = peak in full history) — same scale as trends.py

Usage:
    venv/bin/python wiki.py               # fetch all narratives
    venv/bin/python wiki.py --force       # re-fetch even if cached
    venv/bin/python wiki.py --narrative banking_crisis  # single narrative

Integration with activation.py:
    Set USE_WIKIPEDIA=true in .env — activation.py will blend trends + wiki
    scores before applying the two-stage activation filter.
"""

import os
import time
import argparse
import requests
import pandas as pd
from datetime import date, timedelta
from dotenv import load_dotenv

from narratives import NARRATIVES, NARRATIVE_MAP

load_dotenv()

WIKI_DIR    = "data/wikipedia"
BASE_URL    = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
HEADERS     = {
    "User-Agent": (
        "narrative-factor-research/1.0 "
        "(systematic equity factor; https://github.com/alexjustdoit/narrative-factor)"
    )
}

HISTORY_START = "2018-01-01"   # earlier than trends to give a pre-pandemic baseline
ARTICLE_DELAY = 0.35           # seconds between article API calls (polite rate-limiting)


# ---------------------------------------------------------------------------
# Narrative → Wikipedia article mapping
#
# Use canonical, stable article titles (spaces → underscores).
# The API returns 404 for missing/misspelled articles — fetch_article_views()
# handles that gracefully. Update titles if articles are renamed.
# ---------------------------------------------------------------------------

NARRATIVE_ARTICLES: dict[str, list[str]] = {
    "global_pandemic": [
        "COVID-19_pandemic",
        "Pandemic",
    ],
    "ai_generative": [
        "Generative_artificial_intelligence",
        "Large_language_model",
        "ChatGPT",
    ],
    "ukraine_russia": [
        "Russian_invasion_of_Ukraine",
        "Russo-Ukrainian_War",
    ],
    "middle_east": [
        "Hamas",
        "Israeli–Palestinian_conflict",
        "Gaza_Strip",
    ],
    "iran_conflict": [
        "Iran–United_States_relations",
        "Nuclear_program_of_Iran",
    ],
    "inflation": [
        "Inflation",
        "Consumer_price_index",
    ],
    "bitcoin": [
        "Bitcoin",
        "Cryptocurrency",
    ],
    "immigration": [
        "Immigration_to_the_United_States",
        "Illegal_immigration_to_the_United_States",
    ],
    "us_tariffs": [
        "Tariff",
        "Trump_tariffs_(2025)",
    ],
    "recession": [
        "Recession",
        "Economic_recession",
    ],
    "unemployment": [
        "Unemployment",
        "Unemployment_in_the_United_States",
    ],
    "venezuela": [
        "Venezuela",
        "Venezuela–United_States_relations",
    ],
    "gpu_demand": [
        "Graphics_processing_unit",
        "Nvidia",
    ],
    "greenland": [
        "Greenland",
        "Denmark",
    ],
    "banking_crisis": [
        "Bank_run",
        "Financial_crisis",
        "Silicon_Valley_Bank",
        "Bank_failure",
    ],
    "wage_price_spiral": [
        "Wage–price_spiral",
        "Cost-push_inflation",
    ],
    "housing_bust": [
        "Housing_bubble",
        "United_States_housing_market_correction",
    ],
    "corporate_greed": [
        "Price_gouging",
        "Corporate_greed",
    ],
    "labor_strikes": [
        "Strike_action",
        "2023_United_Auto_Workers_strike",
    ],
    "government_debt": [
        "United_States_debt_ceiling",
        "National_debt_of_the_United_States",
    ],
    "consumer_pullback": [
        "Consumer_confidence_index",
        "Consumer_spending",
    ],
    "china_decoupling": [
        "China–United_States_trade_war",
        "Decoupling_(macroeconomics)",
    ],
    "energy_transition": [
        "Energy_transition",
        "Renewable_energy",
    ],
    "interest_rate_shock": [
        "Federal_funds_rate",
        "Federal_Reserve",
    ],
    "supply_chain_crisis": [
        "2021–2023_global_supply_chain_crisis",
        "Supply_chain_disruption",
    ],
    "ai_regulation": [
        "Regulation_of_artificial_intelligence_by_jurisdiction",
        "AI_safety",
    ],
    "drug_pricing": [
        "Prescription_drug_prices_in_the_United_States",
        "Pharmaceutical_industry",
    ],
    "cybersecurity": [
        "Ransomware",
        "Cyberattack",
    ],
}


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _date_chunks(start: str, end: str) -> list[tuple[str, str]]:
    """Split a date range into 1-year chunks (YYYYMMDD format)."""
    chunks = []
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    while s < e:
        chunk_end = min(s + pd.DateOffset(years=1) - pd.Timedelta(days=1), e)
        chunks.append((s.strftime("%Y%m%d"), chunk_end.strftime("%Y%m%d")))
        s = chunk_end + pd.Timedelta(days=1)
    return chunks


def fetch_article_views(article: str) -> pd.Series:
    """
    Fetch daily pageviews for a single Wikipedia article from HISTORY_START to today.
    Returns a pd.Series indexed by Timestamp (daily granularity).
    Returns empty Series on 404 (article doesn't exist) or persistent errors.
    """
    end   = date.today().strftime("%Y%m%d")
    start = HISTORY_START.replace("-", "")

    all_items: list[dict] = []
    found = True
    for chunk_start, chunk_end in _date_chunks(start, end):
        url = (
            f"{BASE_URL}/en.wikipedia/all-access/user"
            f"/{article}/daily/{chunk_start}/{chunk_end}"
        )
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 404:
                found = False
                break
            r.raise_for_status()
            all_items.extend(r.json().get("items", []))
        except Exception as e:
            print(f"      Warning [{article}] chunk {chunk_start}: {e}")
        time.sleep(ARTICLE_DELAY)

    if not found:
        print(f"      404 — article not found: {article}")
        return pd.Series(dtype=float, name=article)

    if not all_items:
        return pd.Series(dtype=float, name=article)

    data = {pd.Timestamp(item["timestamp"][:8]): item["views"] for item in all_items}
    return pd.Series(data, name=article, dtype=float)


# ---------------------------------------------------------------------------
# Per-narrative fetch + normalise
# ---------------------------------------------------------------------------

def fetch_narrative(narrative: dict, force: bool = False) -> pd.DataFrame:
    """
    Fetch and aggregate Wikipedia pageviews for a single narrative.

    Saves data/wikipedia/{id}.csv with columns [date, views, score].
    Skips fetch if cache is < 14 days old (unless force=True).
    Returns the saved DataFrame (may be empty if all articles 404'd).
    """
    nid      = narrative["id"]
    articles = NARRATIVE_ARTICLES.get(nid, [])
    out_path = os.path.join(WIKI_DIR, f"{nid}.csv")

    if not force and os.path.exists(out_path):
        cached = pd.read_csv(out_path, parse_dates=["date"])
        if not cached.empty:
            age_cutoff = pd.Timestamp(date.today() - timedelta(days=14))
            if cached["date"].max() >= age_cutoff:
                print(f"  Cached ({len(cached)} weeks, last: {cached['date'].max().date()})")
                return cached

    if not articles:
        print(f"  No articles configured for {nid} — skipping")
        return pd.DataFrame(columns=["date", "views", "score"])

    print(f"  Fetching {len(articles)} article(s):")
    series_list: list[pd.Series] = []
    for article in articles:
        print(f"    {article}")
        s = fetch_article_views(article)
        if not s.empty:
            series_list.append(s)

    if not series_list:
        print(f"  No usable data returned for {nid}")
        return pd.DataFrame(columns=["date", "views", "score"])

    # Sum across articles and resample to weekly (Monday-anchored, same as trends.py)
    combined = pd.concat(series_list, axis=1).fillna(0).sum(axis=1)
    combined.index = pd.DatetimeIndex(combined.index)
    weekly = combined.resample("W-MON").sum()
    weekly = weekly[weekly > 0].dropna()

    df = pd.DataFrame({
        "date":  weekly.index,
        "views": weekly.values.astype(int),
    })

    # Normalize to 0–100 (100 = all-time peak), identical to trends.py approach
    max_views = df["views"].max()
    df["score"] = (df["views"] / max_views * 100).round(2) if max_views > 0 else 0.0

    os.makedirs(WIKI_DIR, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"  Saved {len(df)} weeks → {out_path}")
    return df


def fetch_all(force: bool = False):
    """Fetch Wikipedia pageview data for all narratives."""
    n_total = len(NARRATIVES)
    for i, narrative in enumerate(NARRATIVES):
        print(f"\n[{i+1}/{n_total}] {narrative['label']}")
        fetch_narrative(narrative, force=force)


# ---------------------------------------------------------------------------
# Score accessor (used by activation.py)
# ---------------------------------------------------------------------------

def get_score_series(narrative_id: str) -> pd.Series | None:
    """
    Load the normalized Wikipedia score series for a narrative.
    Returns a pd.Series indexed by Timestamp, or None if no file exists.
    """
    path = os.path.join(WIKI_DIR, f"{narrative_id}.csv")
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, parse_dates=["date"])
    if df.empty:
        return None
    return df.set_index("date")["score"].astype(float)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Wikipedia pageview data for narratives")
    parser.add_argument("--force",     action="store_true", help="Re-fetch even if cached")
    parser.add_argument("--narrative", metavar="ID",        help="Fetch a single narrative by ID")
    args = parser.parse_args()

    if args.narrative:
        n = NARRATIVE_MAP.get(args.narrative)
        if not n:
            print(f"Unknown narrative ID: {args.narrative}")
            print(f"Valid IDs: {list(NARRATIVE_MAP.keys())}")
        else:
            print(f"\nFetching: {n['label']}")
            fetch_narrative(n, force=args.force)
    else:
        fetch_all(force=args.force)
