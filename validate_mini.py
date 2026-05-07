"""
Analyzes scores.db from a mini backfill run to assess whether scoring quality
is sufficient to proceed with the full 500-ticker backfill.

Four checks, in order of importance:

  1. Sanity checks     — obvious cases with a clear expected direction
  2. Distribution      — is the model discriminating or defaulting to 0?
  3. Sector coherence  — do sector averages match expected narrative exposure?
  4. Reasoning samples — human-readable spot-check of explanation quality

Outputs a go/no-go verdict based on how many sanity checks pass.

Usage:
    venv/bin/python validate_mini.py
    venv/bin/python validate_mini.py --samples 20
    venv/bin/python validate_mini.py --db path/to/scores.db
"""

import argparse
import random
import sqlite3
import sys

import pandas as pd


SCORES_DB = "data/scores.db"

# -----------------------------------------------------------------------
# Ground-truth pairs: (ticker, narrative_id, expected_sign, note)
# expected_sign: "+" means score should be > 0, "-" means < 0
#
# Only pairs where the narrative has a signal file AND the model was asked
# to score it will appear in results — others are skipped with a note.
# -----------------------------------------------------------------------
GROUND_TRUTH = [
    # AI / GPU narratives (signal files exist in original 14)
    ("NVDA",  "ai_generative",        "+", "Core AI chip supplier — primary beneficiary"),
    ("NVDA",  "gpu_demand",           "+", "GPUs are their entire business"),
    ("MSFT",  "ai_generative",        "+", "Azure OpenAI, Copilot products"),
    ("GOOGL", "ai_generative",        "+", "Google AI / Gemini"),
    ("META",  "ai_generative",        "+", "Heavy AI infrastructure investment"),
    ("AMD",   "ai_generative",        "+", "Competing AI chip supplier (MI300)"),
    ("XOM",   "ai_generative",        "-", "Fossil fuel — not an AI beneficiary"),

    # Inflation narrative (signal file exists)
    ("XOM",   "inflation",            "+", "Energy price inflation boosts margins directly"),
    ("CVX",   "inflation",            "+", "Same as XOM"),
    ("PG",    "inflation",            "+", "Consumer staples pricing power"),
    ("RCL",   "inflation",            "-", "Cruise lines face cost inflation without full pass-through"),

    # Recession narrative (signal file exists)
    ("WMT",   "recession",            "+", "Consumer trade-down destination in downturns"),
    ("COST",  "recession",            "+", "Same — discount retail benefits from trade-down"),
    ("RCL",   "recession",            "-", "Highly discretionary — first to be cut in recession"),
    ("GM",    "recession",            "-", "Auto demand collapses in recessions"),

    # Tariffs narrative (signal file exists)
    ("AAPL",  "us_tariffs",           "-", "China manufacturing — directly tariff-exposed"),
    ("NKE",   "us_tariffs",           "-", "Vietnam/China manufacturing concentration"),
    ("CAT",   "us_tariffs",           "+", "Domestic industrial — tariff beneficiary on imports"),

    # Energy transition (only testable after Shiller trends + activation run)
    ("XOM",   "energy_transition",    "-", "Fossil fuel core business threatened"),
    ("NEE",   "energy_transition",    "+", "Largest US clean energy utility"),
    ("ENPH",  "energy_transition",    "+", "Solar microinverter pure-play"),

    # Banking crisis (only testable after Shiller trends + activation run)
    ("JPM",   "banking_crisis",       "-", "Banking sector contagion / fear"),
    ("BAC",   "banking_crisis",       "-", "Same"),

    # Cybersecurity (only testable after Shiller trends + activation run)
    ("PANW",  "cybersecurity_threat", "+", "Cybersecurity is their product"),
    ("CRWD",  "cybersecurity_threat", "+", "Endpoint security pure-play"),
]

PASS_THRESHOLD = 0.80   # ≥80% of testable checks → proceed with full backfill
WARN_THRESHOLD = 0.65   # 65-79% → proceed with caution / spot-check more samples


def load_scores(db_path: str) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        "SELECT ticker, narrative_id, score, reasoning, model, filed_date FROM scores",
        conn,
    )
    conn.close()
    return df


def mean_score(df: pd.DataFrame, ticker: str, narrative_id: str) -> float | None:
    rows = df[(df["ticker"] == ticker) & (df["narrative_id"] == narrative_id)]
    if rows.empty:
        return None
    return rows["score"].mean()


def section(title: str):
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"{'═' * 60}")


def run(db_path: str, n_samples: int):
    print(f"\nLoading: {db_path}")
    try:
        df = load_scores(db_path)
    except Exception as e:
        print(f"  Could not load scores.db: {e}")
        sys.exit(1)

    if df.empty:
        print("  scores.db is empty — backfill has not run yet.")
        sys.exit(1)

    scored_tickers    = set(df["ticker"].unique())
    scored_narratives = set(df["narrative_id"].unique())
    models_used       = df["model"].dropna().unique().tolist()

    print(f"  {len(df):,} scores  |  {len(scored_tickers)} tickers  |  "
          f"{len(scored_narratives)} narratives  |  model: {', '.join(models_used)}")

    # -----------------------------------------------------------------------
    # 1. Sanity checks
    # -----------------------------------------------------------------------
    section("1 · Sanity checks (expected direction)")

    passed   = 0
    failed   = 0
    skipped  = 0

    print(f"  {'Ticker':<6}  {'Narrative':<24}  {'Avg':>5}  {'Exp':>4}  {'Result':<8}  Note")
    print(f"  {'-'*6}  {'-'*24}  {'-'*5}  {'-'*4}  {'-'*8}  {'-'*30}")

    for ticker, narrative_id, expected_sign, note in GROUND_TRUTH:
        if ticker not in scored_tickers or narrative_id not in scored_narratives:
            label = "(no data — narrative not yet scored)"
            print(f"  {ticker:<6}  {narrative_id:<24}  {'—':>5}  {expected_sign:>4}  {'SKIP':<8}  {label}")
            skipped += 1
            continue

        avg = mean_score(df, ticker, narrative_id)
        if avg is None:
            print(f"  {ticker:<6}  {narrative_id:<24}  {'—':>5}  {expected_sign:>4}  {'SKIP':<8}  no scores")
            skipped += 1
            continue

        correct = (expected_sign == "+" and avg > 0) or (expected_sign == "-" and avg < 0)
        result  = "PASS" if correct else "FAIL"
        if correct:
            passed += 1
        else:
            failed += 1

        print(f"  {ticker:<6}  {narrative_id:<24}  {avg:>+5.2f}  {expected_sign:>4}  {result:<8}  {note}")

    testable = passed + failed
    if testable == 0:
        print("\n  No testable pairs found — run trends.py + activation.py first,")
        print("  then re-run the mini backfill before validating.")
        sys.exit(1)

    pct = passed / testable
    print(f"\n  Result: {passed}/{testable} testable checks passed ({pct:.0%})  |  {skipped} skipped (missing signal data)")

    # -----------------------------------------------------------------------
    # 2. Score distribution
    # -----------------------------------------------------------------------
    section("2 · Score distribution")

    scores = df["score"]
    std    = scores.std()
    mean   = scores.mean()
    pct_zero = (scores == 0).mean() * 100

    dist = scores.value_counts().sort_index()
    print(f"\n  Mean: {mean:+.3f}   Std: {std:.3f}   Zeros: {pct_zero:.1f}%\n")
    print(f"  {'Score':>6}  {'Count':>7}  {'Share':>7}  Bar")
    print(f"  {'-'*6}  {'-'*7}  {'-'*7}  {'-'*30}")
    for score_val, count in dist.items():
        share = count / len(scores)
        bar   = "█" * int(share * 40)
        print(f"  {score_val:>+6}  {count:>7,}  {share:>6.1%}  {bar}")

    dist_ok = std >= 0.5 and pct_zero < 60
    print(f"\n  Distribution {'OK' if dist_ok else 'POOR'}: "
          f"std={'≥0.5 ✓' if std >= 0.5 else f'{std:.2f} — too low, model may be defaulting to 0'}  |  "
          f"zeros={'<60% ✓' if pct_zero < 60 else f'{pct_zero:.0f}% — too many zeros'}")

    # -----------------------------------------------------------------------
    # 3. Sector coherence (avg score per narrative across key tickers)
    # -----------------------------------------------------------------------
    section("3 · Sector coherence")

    SECTOR_GROUPS = {
        "ai_generative": {
            "high (AI core)":   ["NVDA", "MSFT", "GOOGL", "META", "AMD"],
            "low (non-tech)":   ["XOM",  "CVX",  "WMT",  "JPM",  "PG"],
        },
        "inflation": {
            "high (pricing power)": ["XOM", "CVX", "PG", "KO"],
            "low (cost-exposed)":   ["RCL", "GM",  "F",  "AMZN"],
        },
        "recession": {
            "high (defensive)": ["WMT", "COST", "PG", "KO"],
            "low (cyclical)":   ["RCL", "GM",   "F",  "CAT"],
        },
        "us_tariffs": {
            "high (domestic)":     ["CAT", "DE"],
            "low (china-exposed)": ["AAPL", "NKE", "AMZN"],
        },
    }

    any_coherence_data = False
    for narrative_id, groups in SECTOR_GROUPS.items():
        if narrative_id not in scored_narratives:
            continue
        any_coherence_data = True
        print(f"\n  {narrative_id}")
        for label, tickers in groups.items():
            avgs = [mean_score(df, t, narrative_id) for t in tickers
                    if t in scored_tickers]
            avgs = [a for a in avgs if a is not None]
            if not avgs:
                print(f"    {label:<30} — no data")
                continue
            group_mean = sum(avgs) / len(avgs)
            direction  = "↑" if group_mean > 0.1 else ("↓" if group_mean < -0.1 else "→")
            print(f"    {label:<30} avg={group_mean:+.2f}  {direction}  "
                  f"({', '.join(f'{t}:{v:+.1f}' for t, v in zip(tickers, avgs))})")

    if not any_coherence_data:
        print("  No matching narratives in scores.db yet.")

    # -----------------------------------------------------------------------
    # 4. Reasoning samples
    # -----------------------------------------------------------------------
    section(f"4 · Reasoning samples (n={n_samples})")

    sample_rows = df[df["reasoning"].notna()]
    if len(sample_rows) == 0:
        print("  No reasoning text stored — check scorer output.")
    else:
        samples = sample_rows.sample(min(n_samples, len(sample_rows)), random_state=42)
        for _, row in samples.iterrows():
            print(f"\n  {row['ticker']} × {row['narrative_id']}  score={row['score']:+d}  "
                  f"filed={row['filed_date']}")
            print(f"  {row['reasoning']}")

    # -----------------------------------------------------------------------
    # Verdict
    # -----------------------------------------------------------------------
    section("Verdict")

    if pct >= PASS_THRESHOLD and dist_ok:
        verdict = "GO"
        detail  = "Scoring quality looks solid. Proceed with the full backfill."
    elif pct >= WARN_THRESHOLD:
        verdict = "CAUTION"
        detail  = ("Direction accuracy is marginal. Read the reasoning samples carefully "
                   "before committing to the full run. Consider testing with the Anthropic "
                   "backend on 10 tickers (scorer.py __main__) to compare.")
    else:
        verdict = "NO-GO"
        detail  = ("Too many sanity checks failed. Options: (1) switch to a larger local model "
                   "(qwen3:30b if VRAM allows), (2) use SCORER_BACKEND=anthropic for the full "
                   "backfill — ~$174 one-time but guaranteed quality, (3) wait for the friend's "
                   "35B cluster rather than running 14B locally.")

    print(f"\n  {verdict}: {passed}/{testable} sanity checks ({pct:.0%})  |  "
          f"distribution: {'OK' if dist_ok else 'POOR'}")
    print(f"  {detail}\n")

    return verdict != "NO-GO"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db",      default=SCORES_DB, help="Path to scores.db")
    parser.add_argument("--samples", type=int, default=10,
                        help="Number of reasoning samples to print (default: 10)")
    args = parser.parse_args()
    ok = run(args.db, args.samples)
    sys.exit(0 if ok else 1)
