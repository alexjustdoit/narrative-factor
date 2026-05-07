"""
Mini validation backfill — scores a curated 36-ticker subset to validate
scoring quality before committing to the full 500-ticker backfill.

Designed for a single RTX 4070 (12GB VRAM) with qwen3:14b (~8.5GB at Q4).
Completes in 2-4 hours depending on how many narratives are currently active.

The ticker set is chosen to include clear ground-truth cases where the expected
narrative direction is obvious (NVDA on AI, XOM on inflation, etc.). Use
validate_mini.py afterward to check whether the model is getting them right.

Setup:
  1. Pull the model:
       ollama pull qwen3:14b
  2. In .env set:
       SCORER_BACKEND=local
       LOCAL_LLM_MODEL=qwen3:14b
       LOCAL_LLM_BASE_URL=http://localhost:11434/v1
       BACKFILL_WORKERS=1
  3. Run:
       venv/bin/python run_mini.py

Then analyze results:
  venv/bin/python validate_mini.py

Note: only narratives that have existing signal files (data/signals/*.csv) will
be scored. Run trends.py + activation.py for the full 28-narrative set first to
maximize coverage, or run as-is to test against the original 14.
"""

import filings as filing_store
import scorer as scorer_mod
from run_weekly import _run_backfill


# 36-ticker curated universe chosen for clear narrative ground-truth cases.
# Covers AI, energy transition, tariffs, recession, banking, consumer, pharma,
# and cybersecurity — sectors where expected narrative direction is unambiguous.
MINI_TICKERS = [
    # AI/GPU beneficiaries — expect +2/+3 on ai_generative, gpu_demand
    "NVDA", "MSFT", "GOOGL", "META", "AMD", "ORCL", "PLTR", "SNOW",

    # Energy traditional — expect -2/-3 on energy_transition; +1/+2 on inflation
    "XOM", "CVX", "COP",

    # Clean energy — expect +2/+3 on energy_transition (once signal file exists)
    "NEE", "ENPH", "CEG",

    # Consumer staples — expect +1/+2 on inflation, +1 on recession (trade-down)
    "PG", "KO", "WMT", "COST",

    # Consumer discretionary — expect -1/-2 on recession
    "RCL", "GM", "F",

    # Tariff-exposed (China/Vietnam manufacturing) — expect -1/-2 on us_tariffs
    "AAPL", "NKE", "AMZN",

    # Tariff beneficiaries (domestic industrial) — expect +1/+2 on us_tariffs
    "CAT", "DE",

    # Banking — expect -1/-2 on banking_crisis and recession narratives
    "JPM", "BAC", "GS",

    # Pharma — expect +1/+2 on drug_pricing narrative (once signal file exists)
    "JNJ", "PFE", "LLY",

    # Cybersecurity — expect +2/+3 on cybersecurity_threat (once signal file exists)
    "PANW", "CRWD", "FTNT",
]


if __name__ == "__main__":
    print(f"Mini backfill: {len(MINI_TICKERS)} tickers")
    print(f"Tickers: {', '.join(MINI_TICKERS)}\n")
    print("Note: only narratives with existing data/signals/*.csv files will be scored.")
    print("Run trends.py + activation.py for the full 28-narrative set first for max coverage.\n")

    filings_conn = filing_store.get_db()
    scores_conn = scorer_mod.get_scores_db()

    try:
        _run_backfill(MINI_TICKERS, scores_conn, filings_conn)
    finally:
        filings_conn.close()
        scores_conn.close()

    print("\nDone. Run validate_mini.py to analyze scoring quality.")
