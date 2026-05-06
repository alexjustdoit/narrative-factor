"""
LLM exposure scoring pipeline.

For each (ticker, narrative_id, as_of_date), scores how positively or negatively
the company is exposed to the narrative on a -3 to +3 integer scale.

Uses a structured chain-of-thought prompt anchored to point-in-time SEC filing
context to avoid look-ahead bias. Results are cached in data/scores.db so
already-scored combinations are never re-queried.

Usage:
    # Score a single company
    score = score_one("NVDA", "ai_generative", "2024-01-15")

    # Score all active narratives for all tickers on a given date
    score_batch(tickers, active_narrative_ids, as_of_date="2024-01-15")
"""

import json
import os
import sqlite3
from datetime import datetime, UTC

import anthropic
from dotenv import load_dotenv

import filings as filing_store
from narratives import NARRATIVE_MAP

load_dotenv()

SCORES_DB = "data/scores.db"
MODEL = os.getenv("SCORER_MODEL", "claude-sonnet-4-6")

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a systematic equity analyst scoring company exposures to macro narratives.

Your task is to assess how a specific macro narrative causally impacts a company's
business — through revenue, costs, demand, regulation, or competitive position.

Key principles:
- Focus on CAUSAL mechanisms, not sentiment or recent stock performance.
- A narrative can be active and impactful even if the surrounding discussion is negative.
  What matters is the intensity of attention and its differential impact across companies.
- Score relative to the cross-section: if NVIDIA is +3 on GPU Demand for AI,
  score other companies relative to that anchor.
- Use only the filing context provided. Do not use knowledge of events that
  occurred after the as-of date."""

SCORE_PROMPT = """## Narrative
**{label}**

{description}

## Company
**Ticker:** {ticker}
**Filing context as of:** {as_of_date}

### Business Description (Item 1)
{item1_text}

### Management Discussion & Analysis (Item 7)
{item7_text}

## Scoring Task
Score this company's exposure to the narrative above on this scale:
  +3 = Core business is a primary beneficiary — directly and substantially benefits
  +2 = Significant revenue or demand tailwind
  +1 = Some positive exposure but not a primary driver
   0 = No meaningful exposure either way
  -1 = Some headwind but manageable
  -2 = Significant cost, demand, or competitive pressure
  -3 = Core business faces direct and substantial threat

## Instructions
Think through this step by step:
1. What types of companies benefit or suffer from this narrative, and why?
2. What specific business mechanisms apply here (revenue streams, cost structure, customer base)?
3. What does this company's filing context reveal about their actual exposure?
4. What is the net directional score, weighted by magnitude?

Respond with valid JSON only — no markdown, no explanation outside the JSON:
{{
  "reasoning": "<2-3 sentences on the specific causal mechanism for this company>",
  "score": <integer from -3 to +3>
}}"""


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_scores_db() -> sqlite3.Connection:
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(SCORES_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker       TEXT NOT NULL,
            narrative_id TEXT NOT NULL,
            as_of_date   TEXT NOT NULL,
            score        INTEGER NOT NULL,
            reasoning    TEXT,
            model        TEXT,
            scored_at    TEXT NOT NULL,
            UNIQUE(ticker, narrative_id, as_of_date)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_scores_lookup
        ON scores (ticker, narrative_id, as_of_date)
    """)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _call_llm(ticker: str, narrative_id: str, as_of_date: str,
               item1: str, item7: str) -> dict:
    """Calls the Claude API and returns {score, reasoning}."""
    narrative = NARRATIVE_MAP[narrative_id]

    prompt = SCORE_PROMPT.format(
        label=narrative["label"],
        description=narrative["description"],
        ticker=ticker,
        as_of_date=as_of_date,
        item1_text=item1 or "(not available)",
        item7_text=item7 or "(not available)",
    )

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if model wraps output despite instructions
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    result = json.loads(raw)

    if not isinstance(result.get("score"), int) or result["score"] not in range(-3, 4):
        raise ValueError(f"Invalid score value: {result.get('score')}")

    return result


def score_one(ticker: str, narrative_id: str, as_of_date: str,
               scores_conn: sqlite3.Connection | None = None,
               filings_conn: sqlite3.Connection | None = None) -> dict | None:
    """
    Scores a single (ticker, narrative, date) combination.
    Returns {score, reasoning} dict, or None if filing context unavailable.
    Skips and returns cached result if already scored.
    """
    own_scores = scores_conn is None
    own_filings = filings_conn is None
    if own_scores:
        scores_conn = get_scores_db()
    if own_filings:
        filings_conn = filing_store.get_db()

    try:
        # Return cached result if exists
        cached = scores_conn.execute("""
            SELECT score, reasoning FROM scores
            WHERE ticker = ? AND narrative_id = ? AND as_of_date = ?
        """, (ticker, narrative_id, as_of_date)).fetchone()

        if cached:
            return {"score": cached[0], "reasoning": cached[1], "cached": True}

        # Get filing context
        context = filing_store.get_context(ticker, as_of_date, filings_conn)
        if not context:
            return None

        result = _call_llm(
            ticker, narrative_id, as_of_date,
            context["item1_text"], context["item7_text"],
        )

        scores_conn.execute("""
            INSERT OR IGNORE INTO scores
                (ticker, narrative_id, as_of_date, score, reasoning, model, scored_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            ticker, narrative_id, as_of_date,
            result["score"], result["reasoning"],
            MODEL, datetime.now(UTC).isoformat(),
        ))
        scores_conn.commit()
        return result

    finally:
        if own_scores:
            scores_conn.close()
        if own_filings:
            filings_conn.close()


def score_batch(tickers: list[str], narrative_ids: list[str], as_of_date: str,
                verbose: bool = True) -> dict:
    """
    Scores all (ticker, narrative) combinations for a given date.
    Already-cached scores are returned instantly without an API call.
    Returns {ticker: {narrative_id: {score, reasoning}}}
    """
    scores_conn = get_scores_db()
    filings_conn = filing_store.get_db()
    results = {}
    total = len(tickers) * len(narrative_ids)
    done = 0

    try:
        for ticker in tickers:
            results[ticker] = {}
            for nid in narrative_ids:
                result = score_one(
                    ticker, nid, as_of_date,
                    scores_conn=scores_conn,
                    filings_conn=filings_conn,
                )
                if result:
                    results[ticker][nid] = result
                done += 1
                if verbose and done % 50 == 0:
                    print(f"  {done}/{total} scored")
    finally:
        scores_conn.close()
        filings_conn.close()

    return results


# ---------------------------------------------------------------------------
# Manual test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import edgar
    import filings as fs

    # Pre-fetch NVDA and NEE filings if not already cached
    test_tickers = {
        "NVDA": "ai_generative",   # should be +3
        "NEE":  "ai_generative",   # utility — should be ~0
        "NVDA": "us_tariffs",      # NVDA sources from TSMC — should be negative
        "XOM":  "inflation",       # energy in inflation — should be positive
    }

    filings_conn = fs.get_db()
    cik_map = edgar.get_cik_map()

    for ticker in set(test_tickers.keys()):
        cik = cik_map.get(ticker)
        if cik:
            print(f"Pre-fetching {ticker} filings...")
            fs.fetch_and_store(ticker, filings_conn, n_filings=2)

    filings_conn.close()

    print("\n--- Scoring ---\n")
    as_of = "2024-06-01"

    for ticker, narrative_id in test_tickers.items():
        narrative_label = NARRATIVE_MAP[narrative_id]["label"]
        print(f"{ticker} × {narrative_label}")
        result = score_one(ticker, narrative_id, as_of)
        if result:
            print(f"  Score: {result['score']:+d}")
            print(f"  Reasoning: {result['reasoning']}")
        else:
            print("  No filing context available")
        print()
