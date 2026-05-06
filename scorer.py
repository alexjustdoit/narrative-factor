"""
LLM exposure scoring pipeline.

Scores are cached by (ticker, narrative_id, accession_number) — the specific
filing, not the date. This means a company scored against a narrative for any
week covered by the same 10-K returns the cached result instantly, with no
API call. A 10-K covers ~52 weeks, so this reduces backfill calls by ~37x.

Supports two backends, selected via SCORER_BACKEND env var:
  anthropic (default) — Claude API via Anthropic SDK
  local               — OpenAI-compatible local endpoint (Ollama / vLLM)

Required env vars:
  ANTHROPIC_API_KEY           — for anthropic backend
  LOCAL_LLM_BASE_URL          — for local backend (e.g. http://192.168.1.x:11434/v1)
  LOCAL_LLM_MODEL             — model name for local backend (e.g. qwen2.5:72b)
"""

import json
import os
import sqlite3
from datetime import datetime, UTC

from dotenv import load_dotenv

import filings as filing_store
from narratives import NARRATIVE_MAP

load_dotenv()

SCORES_DB   = "data/scores.db"
BACKEND     = os.getenv("SCORER_BACKEND", "anthropic")
MODEL       = os.getenv("SCORER_MODEL", "claude-sonnet-4-6")
LOCAL_URL   = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
LOCAL_MODEL = os.getenv("LOCAL_LLM_MODEL", "qwen2.5:72b")

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a systematic equity analyst scoring company exposures to macro narratives.

Your task is to assess how a specific macro narrative causally impacts a company's
business — through revenue, costs, demand, regulation, or competitive position.

Key principles:
- Focus on CAUSAL mechanisms, not sentiment or recent stock performance.
- A narrative can be active and impactful regardless of whether the surrounding
  discussion is positive or negative. What matters is the intensity of attention
  and its differential impact across companies.
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

    # Cache key is (ticker, narrative_id, accession_number) — the specific filing,
    # not the date. One LLM call per filing covers all weeks that filing is current.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker           TEXT NOT NULL,
            narrative_id     TEXT NOT NULL,
            accession_number TEXT NOT NULL,
            filed_date       TEXT NOT NULL,
            score            INTEGER NOT NULL,
            reasoning        TEXT,
            model            TEXT,
            scored_at        TEXT NOT NULL,
            UNIQUE(ticker, narrative_id, accession_number)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_scores_lookup
        ON scores (ticker, narrative_id, accession_number)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_scores_ticker_date
        ON scores (ticker, filed_date)
    """)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# LLM backends
# ---------------------------------------------------------------------------

def _parse_response(raw: str) -> dict:
    """Parses LLM JSON output, stripping markdown fences if present."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    result = json.loads(raw.strip())
    if not isinstance(result.get("score"), int) or result["score"] not in range(-3, 4):
        raise ValueError(f"Invalid score: {result.get('score')}")
    return result


def _build_prompt(ticker: str, narrative_id: str, as_of_date: str,
                  item1: str, item7: str) -> str:
    narrative = NARRATIVE_MAP[narrative_id]
    return SCORE_PROMPT.format(
        label=narrative["label"],
        description=narrative["description"],
        ticker=ticker,
        as_of_date=as_of_date,
        item1_text=item1 or "(not available)",
        item7_text=item7 or "(not available)",
    )


def _call_anthropic(prompt: str) -> dict:
    import anthropic
    client = anthropic.Anthropic()
    message = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_response(message.content[0].text)


def _call_local(prompt: str) -> dict:
    from openai import OpenAI
    client = OpenAI(base_url=LOCAL_URL, api_key="local")
    response = client.chat.completions.create(
        model=LOCAL_MODEL,
        max_tokens=300,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
    )
    return _parse_response(response.choices[0].message.content)


def _call_llm(ticker: str, narrative_id: str, as_of_date: str,
              item1: str, item7: str) -> dict:
    prompt = _build_prompt(ticker, narrative_id, as_of_date, item1, item7)
    if BACKEND == "local":
        return _call_local(prompt)
    return _call_anthropic(prompt)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_one(ticker: str, narrative_id: str, as_of_date: str,
              scores_conn: sqlite3.Connection | None = None,
              filings_conn: sqlite3.Connection | None = None) -> dict | None:
    """
    Scores a single (ticker, narrative, date) combination.

    Cache is keyed by accession_number — if the same filing is current for
    multiple weeks, the cached score is returned with no API call.

    Returns {score, reasoning, cached} or None if no filing context available.
    """
    own_scores  = scores_conn is None
    own_filings = filings_conn is None
    if own_scores:
        scores_conn = get_scores_db()
    if own_filings:
        filings_conn = filing_store.get_db()

    try:
        context = filing_store.get_context(ticker, as_of_date, filings_conn)
        if not context:
            return None

        acc = context["accession_number"]

        # Cache hit — same filing already scored for this narrative
        cached = scores_conn.execute("""
            SELECT score, reasoning FROM scores
            WHERE ticker = ? AND narrative_id = ? AND accession_number = ?
        """, (ticker, narrative_id, acc)).fetchone()

        if cached:
            return {"score": cached[0], "reasoning": cached[1], "cached": True}

        # Cache miss — call LLM
        result = _call_llm(
            ticker, narrative_id, as_of_date,
            context["item1_text"], context["item7_text"],
        )

        active_model = LOCAL_MODEL if BACKEND == "local" else MODEL
        scores_conn.execute("""
            INSERT OR IGNORE INTO scores
                (ticker, narrative_id, accession_number, filed_date,
                 score, reasoning, model, scored_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticker, narrative_id, acc, context["filed_date"],
            result["score"], result["reasoning"],
            active_model, datetime.now(UTC).isoformat(),
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
    Returns {ticker: {narrative_id: {score, reasoning}}}
    """
    scores_conn  = get_scores_db()
    filings_conn = filing_store.get_db()
    results      = {}
    total        = len(tickers) * len(narrative_ids)
    done         = 0

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
                if verbose and done % 100 == 0:
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

    filings_conn = fs.get_db()
    for ticker in ["NVDA", "NEE", "XOM"]:
        print(f"Ensuring {ticker} filings cached...")
        fs.fetch_and_store(ticker, filings_conn, n_filings=4)
    filings_conn.close()

    print(f"\n--- Scoring (backend: {BACKEND}) ---\n")
    as_of = "2024-06-01"
    tests = [
        ("NVDA", "ai_generative"),   # expect +3
        ("NVDA", "us_tariffs"),      # expect -1 or -2
        ("NEE",  "ai_generative"),   # expect 0 or +1
        ("XOM",  "inflation"),       # expect +2 or +3
    ]

    for ticker, narrative_id in tests:
        label  = NARRATIVE_MAP[narrative_id]["label"]
        result = score_one(ticker, narrative_id, as_of)
        if result:
            cached = " (cached)" if result.get("cached") else ""
            print(f"{ticker} × {label}: {result['score']:+d}{cached}")
            print(f"  {result['reasoning']}")
        else:
            print(f"{ticker} × {label}: no filing context")
        print()
