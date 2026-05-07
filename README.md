# Narrative Factor

A systematic equity factor that scores S&P 500 companies by their exposure to macro narratives gaining prominence in public discourse — replicating the methodology from [*The Narrative Factor* (Reese, 2026)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6685058).

The factor achieved a **1.95x information ratio** (factor-neutralized, industry-neutral) over January 2020 – April 2026 in the original paper, with a max drawdown of 4.01% vs. 21.81% for a comparable momentum strategy.

---

## Important differences from the paper (retail implementation)

The paper's results are based on an institutional long-short strategy with daily rebalancing. This implementation differs in three meaningful ways:

**Long-only instead of long-short**
The paper constructs a market-neutral portfolio — buying high-exposure stocks and shorting low-exposure stocks. This implementation is long-only, holding only the top-decile narrative exposure stocks within each sector. Long-only captures the upside of the signal but retains full market beta: in a broad market drawdown, the portfolio falls with the market rather than being insulated by the short book. Expect higher volatility and deeper drawdowns than the paper reports, and performance that is more correlated with the S&P 500.

**Weekly rebalancing instead of daily**
The paper rebalances daily with a 3% turnover cap. This implementation rebalances weekly. Since the narrative signal is forward-looking and moves on a multi-week timescale, weekly rebalancing should capture most of the signal value while meaningfully reducing transaction costs and tax events. Turnover will be lower than the paper's ~7x annual figure.

**Tax considerations: account type matters significantly**

| Account type | Impact |
|---|---|
| **Tax-advantaged (IRA, 401k, Roth)** | Gains compound tax-free or tax-deferred. This is the natural home for an active factor strategy — turnover has no immediate tax consequence. |
| **Taxable account** | Each rebalance that sells a position generates a taxable event. With weekly rebalancing, most positions are held for weeks to a few months, meaning gains are taxed as **short-term capital gains** (ordinary income rates: up to 37%). This can substantially erode the strategy's excess return. A strategy generating 6-7% annual excess return in a 35% bracket could see that advantage reduced by 2-3 percentage points annually from tax drag alone, before even accounting for state taxes. |

**Practical guidance:** Run this strategy in a tax-advantaged account if possible. In a taxable account, consider extending the rebalance frequency to monthly or quarterly to allow more positions to qualify for long-term capital gains treatment (held > 1 year), at the cost of some signal freshness.

---

## Strategy design

The narrative factor is designed as an **overlay on an established factor-based portfolio** rather than a standalone strategy. By itself, the signal identifies macro narrative tailwinds but does not screen for fundamental quality. Combined with a base factor, narrative provides the "right time" dimension while the base factor provides the "right company" filter.

### Three overlay modes to validate

**Selection layer** — Restrict the base factor's universe to stocks in the top narrative quartile or decile. Clean and interpretable; the base factor picks the stocks, narrative filters for macro timing. Reduces diversification but maximizes signal purity. This is closest to the original paper's methodology (top-decile within sector).

**Position weighting layer** — Keep the base factor's full universe; use the narrative score to tilt position sizes up or down. Overweight high-exposure stocks, underweight low-exposure stocks. More continuous expression of the signal, preserves diversification, and allows tuning the blend ratio between base factor and narrative. The most practically flexible approach.

**Timing layer** — Use the aggregate portfolio-level (or sector-level) narrative score to modulate overall market exposure, or to rotate between base factors depending on the narrative environment (e.g., lean growth when AI/tech narratives dominate, lean value when recession/rates narratives dominate). Highest potential alpha; also the highest risk of overfitting. Test this last — market timing is hard to validate on a 6-year window with an unusual macro regime.

These modes are not mutually exclusive. The backtest grid tests combinations.

### Base strategies to test on

| Base strategy | Fit with narrative | Key consideration |
|---|---|---|
| **Quality** (ROIC, low leverage, stable earnings) | Strong | Natural complement — quality filters for company health, narrative filters for macro tailwind. Signals are largely orthogonal; genuine information diversification. |
| **Momentum** (12-1 month price return) | Most theoretically interesting | Narratives are a plausible leading indicator for price momentum — public discourse precedes buying behavior. Could improve entry timing and reduce crowded-trade exposure. |
| **Growth** (revenue growth, margin expansion) | Correlation risk | Growth stocks cluster in AI, clean energy, etc., which are already high-narrative sectors. Risk of double-counting the same signal rather than diversifying it. |
| **Value** (P/E, P/B, EV/EBITDA) | Interesting tension | Value stocks are often cheap *because* narratives are against them — that's the contrarian thesis. A selection-layer overlay may screen out exactly the stocks value wants. A weighting-layer approach (narrative tilts sizes within the value universe) is more compatible. |

**Recommended test order:** quality-weighting → momentum-selection → growth-weighting → value-weighting → timing experiments.

### Walk-forward validation plan

**Primary window (full 28-narrative set):**
- Train 2020–2022, test 2022–2024
- Train 2020–2024, test 2024–2026

Avoid fitting to the full 2020–2026 period in a single pass — the macro regime (pandemic, zero rates, rate shock, AI boom) is unusual and a single in-sample fit will overstate confidence.

**Extended window (robustness check):**

The narrative data sources impose hard limits on how far back the signal can be constructed:

| Period | Trends | Wikipedia | Active narratives | Usefulness |
|---|---|---|---|---|
| 2020–2026 | ✓ | ✓ | All 28 | Primary window |
| 2015–2020 | ✓ | ✓ | ~10–14 (Shiller perennials + some cyclicals) | Best extended window — Wikipedia available, covers pre-COVID growth regime |
| 2010–2015 | ✓ | ✗ | ~6–10 (perennials only, Trends-only) | Useful stress test — post-GFC recovery, housing/banking/recession narratives active |
| Pre-2010 | ✓ | ✗ | Too few active | Not worth constructing |

The recommended extended test is **2015–2026** as the primary robustness window (11 years, three distinct macro regimes), with an optional **2010–2015 Trends-only sub-test** limited to the Shiller perennial narratives. Note that the 2015–2020 sub-period will look like a different, thinner strategy — fewer active narratives means the signal is constructed from a smaller set. If the overlay still adds value under those conditions, that is strong evidence of generalizability rather than a limitation.

**Survivorship bias:** The signal pipeline scores the current S&P 500 constituent list. The QuantConnect backtest engine uses historical constituent data automatically, so backtest results are survivorship-bias-free at the portfolio level. The signal inputs (10-K scores for delisted companies) are absent — a minor conservative bias in the pre-2020 period.

---

## How it works

1. **Narrative tracking** — 28 macro narratives (AI, inflation, tariffs, geopolitical conflicts, Shiller perennial themes, etc.) are monitored via Google Trends and Wikipedia pageviews. A two-stage activation filter identifies narratives at peak public attention; typically 5–15 are active at any given time.

2. **Exposure scoring** — For each company, an LLM reads its most recent 10-K filing and scores how positively or negatively the company is exposed to each active narrative (-3 to +3), using a perceived-causality framing.

3. **Composite signal** — Active narratives are weighted by their share of total discussion volume. Exposure scores are combined into a single composite, then z-scored within GICS sector groups (industry-neutral).

4. **Backtest** — The composite signal is exported as a parquet file and consumed by a QuantConnect backtest algorithm.

---

## Project structure

```
narrative-factor/
├── narratives.py        # 28 narrative definitions with descriptions
├── trends.py            # Google Trends fetcher (weekly popularity scores)
├── wiki.py              # Wikipedia pageview fetcher (supplementary signal)
├── activation.py        # Two-stage activation filter (optionally blends trends + wiki)
├── universe.py          # S&P 500 constituent list + GICS classification
├── edgar.py             # SEC EDGAR API client (CIK lookup, filing metadata)
├── filings.py           # 10-K section extractor + SQLite cache
├── scorer.py            # LLM exposure scoring pipeline (Anthropic or local)
├── composite.py         # Weighted composite factor construction
├── export_signals.py    # Exports factor scores to parquet for backtesting
├── run_weekly.py        # Weekly pipeline orchestrator
├── reprocess.py         # One-off utility: resample daily trends to weekly
├── qc/
│   ├── algorithm.py     # QuantConnect backtest algorithm
│   └── upload_signals.py
└── data/                # Generated — not committed (~20 GB total)
    ├── trends/          # Google Trends CSVs per narrative
    ├── wikipedia/       # Wikipedia pageview CSVs per narrative
    ├── signals/         # Activation signals + composite_scores.parquet
    ├── universe/        # S&P 500 tickers + GICS classification
    ├── filings.db       # SQLite: 10-K sections per company (~2 GB)
    └── scores.db        # SQLite: LLM exposure scores per (ticker, narrative, filing)
```

---

## Setup

**1. Install Ollama and pull the model** (required for local LLM scoring):
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3.6:35b
```

**2. Clone and install dependencies:**
```bash
git clone https://github.com/alexjustdoit/narrative-factor
cd narrative-factor
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
```

**3. Edit `.env`:**

```env
EDGAR_EMAIL=your-email@example.com

SCORER_BACKEND=local
LOCAL_LLM_MODEL=qwen3.6:35b

# Single machine (both RTX 3090s detected automatically via nvidia-smi):
LOCAL_LLM_BASE_URL=http://localhost:11434/v1

# Multi-node cluster — comma-separate Ollama endpoints, workers assigned round-robin:
# LOCAL_LLM_BASE_URL=http://localhost:11434/v1,http://192.168.1.3:11434/v1

# APU / Strix nodes only (not visible to nvidia-smi — set worker count manually):
# BACKFILL_WORKERS=14

# Only needed when SCORER_BACKEND=anthropic:
# ANTHROPIC_API_KEY=your-key-here
```

If using Strix nodes, also set `OLLAMA_NUM_PARALLEL=6` in the Ollama service config on each node so it accepts concurrent requests.

---

## Running the pipeline

### First-time setup

Steps 1 and 2 below can run in parallel in separate terminals — do that to save ~45 min.

**Step 1 — Fetch narrative popularity data (~45 min)**
```bash
venv/bin/python trends.py       # Google Trends, rate-limited — start this first
venv/bin/python wiki.py         # Wikipedia pageviews (~5 min, run after trends starts)
venv/bin/python reprocess.py    # resample to weekly if any chunks returned daily data
venv/bin/python activation.py   # prints which narratives were active at key dates
```

**Step 2 — Fetch company filings (~90 min, run in a second terminal while Step 1 runs)**
```bash
venv/bin/python filings.py      # fetches 7 10-Ks per ticker (~FY2018–FY2024)
```

**Step 3 — Historical backfill (~9 hrs on full cluster)**
```bash
venv/bin/python run_weekly.py --backfill --skip-trends --skip-wikipedia
```

The backfill auto-detects GPU count via `nvidia-smi` and parallelizes accordingly. If interrupted, it resumes from where it left off — already-cached scores are skipped at startup.

Estimated times with Qwen3.6 35B (~20 GB VRAM, fits on a single RTX 3090):

| Hardware | Workers | Est. time |
|---|---|---|
| 2× RTX 3090 only | 2 | ~61 hrs |
| 2× RTX 3090 + 2 Strix nodes (6 Ollama instances each) | 14 | ~9 hrs |

> **Phase 1 / Phase 2:** The initial backfill scores 10-K filings only (~73,500 calls). After validating the backtest signal, uncomment the 10-Q line in `filings.py __main__`, re-run `filings.py`, then run another backfill pass. Already-cached 10-K scores are never re-scored.

**Step 4 — Export signals for backtesting**
```bash
venv/bin/python export_signals.py
# Output: data/signals/composite_scores.parquet
```

### Weekly maintenance

After the initial backfill, only newly filed 10-Ks are scored — ~50 filings/week across the S&P 500. Cost depends on backend:

- **Local** (`SCORER_BACKEND=local`): negligible electricity, same as backfill
- **Anthropic** (`SCORER_BACKEND=anthropic`): ~$1/week at claude-sonnet-4-6 pricing (28 narratives, ~5–15 active)

```bash
venv/bin/python run_weekly.py

# Skip refresh steps when re-running in the same session:
venv/bin/python run_weekly.py --skip-trends --skip-wikipedia
```

The weekly run now fetches Wikipedia pageviews for all 28 narratives (~5 min, cached for 14 days). Wikipedia data is free, no API key needed, and runs significantly faster than Google Trends.

---

## Mini validation run (RTX 4070 / 12GB VRAM)

qwen3.6:35b requires ~18-20GB VRAM and won't fit in 12GB. Use `qwen3:14b` (~8.5GB at Q4_K_M) — smaller but sufficient for structured scoring. Set `LOCAL_LLM_MODEL=qwen3:14b` and `BACKFILL_WORKERS=1` in `.env`, then:

1. `ollama pull qwen3:14b`
2. `venv/bin/python run_mini.py` — 36 curated tickers, ~2-4 hrs
3. `venv/bin/python validate_mini.py` — sanity checks + go/no-go verdict (≥80% pass → proceed)
4. If NO-GO: switch to a larger model or use `SCORER_BACKEND=anthropic` instead

---

## QuantConnect backtest

1. Upload `data/signals/composite_scores.parquet` to QC Object Store (see `qc/upload_signals.py`)
2. Create a new QC Algorithm project and paste in `qc/algorithm.py`
3. Set backtest dates to `2020-01-01` onward

`qc/algorithm.py` is parametric — the top of the file has a CONFIG block with two variables that define the backtest variant:

```python
BASE_FACTOR  = "quality"    # "quality" | "value" | "momentum" | None
OVERLAY_MODE = "selection"  # "selection" | "weighting" | "narrative_only"
```

| `OVERLAY_MODE` | Behavior |
|---|---|
| `narrative_only` | Baseline — top-decile by narrative score, equal weight |
| `selection` | Base factor pre-filters sector to top 50%; narrative selects the top decile within that |
| `weighting` | Narrative selects holdings; position sizes blend narrative + base factor scores |

Run `narrative_only` first as the baseline, then layer in base factors. The full grid is 4 base factors × 3 overlay modes = 12 core variants, plus sweeps on `TOP_DECILE` and `NARRATIVE_BLEND`.

---

## LLM backends

Both backends work for all pipeline steps — set `SCORER_BACKEND` in `.env` to switch:

| Backend | Cost: initial backfill | Cost: weekly maintenance |
|---|---|---|
| `anthropic` | ~$174 one-time (500 co × 28 narratives × ~6 yrs) | ~$1/week (only new filings × active narratives) |
| `local` | ~$1 electricity / ~6 hrs on full cluster | Negligible — same cache logic applies |

The typical setup is `local` for the initial backfill (saves ~$174), then either backend for weekly maintenance. Weekly cost stays low because only newly filed 10-Ks are scored against currently active narratives (~5–15 of 28 at any time). If you have a GPU machine running anyway, keeping `local` for weekly runs is essentially free.

Scores are cached by `(ticker, narrative_id, accession_number)` — one LLM call per filing covers all weeks that filing is current (~52 weeks per 10-K). This reduces unique calls by ~37x vs. caching by date. The initial backfill is a one-time cost; subsequent weekly runs only score new filings (~50 new filings/week across the S&P 500).

---

## The 28 narratives

The original 14 replicate the paper's methodology. The 14 additions draw from Shiller's *Narrative Economics* (2019) perennial narrative taxonomy — recurring themes that have proven ability to influence economic behavior across cycles. Typically 5–15 are active at any given time; the activation filter decides which.

### Original 14 (from the paper)

| Narrative | Search terms |
|---|---|
| Global Pandemic | pandemic |
| AI / Generative AI | AI |
| Ukraine-Russia Conflict | Ukraine |
| Middle Eastern Conflict | gaza, israel, hamas |
| Iran Military Conflict | iran |
| Inflation | inflation |
| Bitcoin / Cryptocurrency | bitcoin |
| US Immigration Rhetoric | immigration |
| US Tariffs | tariffs, tariff |
| Economic Recession | recession |
| Rise in Unemployment | unemployment |
| US-Venezuela Tensions | venezuela |
| GPU Demand for AI | nvidia, gpus, gpu |
| US-Greenland Tensions | greenland, denmark |

### New 14 (Shiller perennial taxonomy + 2020–2026 extensions)

| Narrative | Search terms | Shiller source |
|---|---|---|
| Banking Crisis / Financial Panic | bank collapse, bank failure, bank run | Ch. 10: Panic vs. Confidence |
| Wage-Price Spiral | wage inflation, labor shortage, worker shortage | Ch. 18: Wage-Price Spiral |
| Housing Boom / Bust | housing bubble, housing crash, home prices | Ch. 15: Real Estate Booms and Busts |
| Corporate Greed / Price Gouging | price gouging, corporate greed, corporate profits | Ch. 17: Boycotts, Profiteers, and Evil Business |
| Labor Strike Wave | labor strike, strike, union organizing | Ch. 18: Evil Labor Unions |
| Government Debt / Fiscal Crisis | debt ceiling, national debt, fiscal crisis | Ch. 8: Seven Propositions |
| Consumer Spending Pullback | consumer spending, consumer pullback, spending cuts | Ch. 11: Frugality vs. Conspicuous Consumption |
| US-China Decoupling | China decoupling, China trade war, made in China | Contemporary extension |
| Energy Transition / Clean Energy | clean energy, renewable energy, net zero | Contemporary extension |
| Interest Rate Shock | rate hike, interest rates, Federal Reserve | Contemporary extension |
| Supply Chain Crisis | supply chain crisis, supply shortage, chip shortage | Contemporary extension |
| AI Regulation / AI Risk | AI regulation, AI safety, AI ban | Ch. 14: Automation and AI |
| Drug Pricing / Pharma Regulation | drug prices, drug pricing, pharmaceutical prices | Contemporary extension |
| Cybersecurity Threat | ransomware, data breach, cyberattack | Contemporary extension |
