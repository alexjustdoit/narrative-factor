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

```bash
git clone https://github.com/alexjustdoit/narrative-factor
cd narrative-factor
python3 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```env
EDGAR_EMAIL=your-email@example.com

# Backend: "anthropic" or "local" — works for all steps including weekly maintenance
SCORER_BACKEND=local
LOCAL_LLM_BASE_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=qwen3.6:35b

# Only needed when SCORER_BACKEND=anthropic
ANTHROPIC_API_KEY=your-key-here
```

---

## Running the pipeline

### First-time setup

**Step 1 — Fetch narrative popularity data (~45–60 min)**
```bash
venv/bin/python trends.py       # Google Trends — rate-limited, takes ~45 min for 28 narratives
venv/bin/python wiki.py         # Wikipedia pageviews — fast, no auth required (~5 min)
venv/bin/python reprocess.py    # resample to weekly if any chunks returned daily data
venv/bin/python activation.py   # sanity check: prints which narratives were active at key dates

# Optional: enable Wikipedia blending in .env, then rerun activation
# USE_WIKIPEDIA=true
# venv/bin/python activation.py --use-wikipedia
```

**Step 2 — Fetch company filings (~90 min)**
```bash
venv/bin/python filings.py   # fetches 7 10-Ks per ticker (~FY2018–FY2024)
```

Steps 1 and 2 can run in parallel in separate terminals.

> **Phase 1 / Phase 2:** The initial backfill scores 10-K filings only. After validating the backtest signal, uncomment the 10-Q line in `filings.py __main__` and run a second backfill pass for quarterly updates. The cache ensures already-scored 10-Ks are never re-scored.

**Step 3 — Historical backfill (score all companies × all narratives)**

Run on a local GPU machine to avoid API rate limits and cost.

```bash
# On the GPU machine — install Ollama and pull the model first
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3.6:35b

# Run the full pipeline — fetches, activation, then backfill in one shot
venv/bin/python trends.py
venv/bin/python wiki.py
venv/bin/python reprocess.py
venv/bin/python activation.py
venv/bin/python filings.py
venv/bin/python run_weekly.py --backfill --skip-trends --skip-wikipedia

# If interrupted and re-running in the same session:
venv/bin/python run_weekly.py --backfill --skip-trends --skip-wikipedia
```

The backfill parallelizes automatically:

- **NVIDIA discrete GPUs** — detected via `nvidia-smi`, one worker per GPU; no configuration needed
- **APU / Strix nodes** — set `BACKFILL_WORKERS=N` in `.env` (APUs aren't visible to nvidia-smi)
- **Multi-node cluster** — set `LOCAL_LLM_BASE_URL` to a comma-separated list of Ollama endpoints; workers are assigned round-robin across endpoints

Example `.env` for a 14-worker setup (2× RTX 3090 + 2 Strix nodes with 6 Ollama instances each):

```env
SCORER_BACKEND=local
LOCAL_LLM_MODEL=qwen3.6:35b
BACKFILL_WORKERS=14
LOCAL_LLM_BASE_URL=http://localhost:11434/v1,http://192.168.1.3:11434/v1
```

Also set `OLLAMA_NUM_PARALLEL=6` in the Ollama service config on each Strix node so it accepts concurrent requests.

Estimated backfill times with Qwen3.6 35B (Q4, ~20 GB VRAM — fits on a single RTX 3090).
Assumes ~73,500 calls (500 tickers × 7 10-Ks × ~21 ever-active narratives, Phase 1 / 10-K only):

| Hardware | Workers | Est. time |
|---|---|---|
| 2× RTX 3090 only | 2 | ~61 hrs |
| 2× RTX 3090 + 2 Strix nodes (6 Ollama instances each) | 14 | ~9 hrs |

Qwen3.6 35B fits on a single RTX 3090, so each GPU runs its own independent Ollama instance — two workers from the two 3090s alone, plus however many the Strix nodes add.

Phase 2 (adding 10-Qs after backtest validation) adds ~126,000 more calls. Only new filings are scored — already-cached 10-Ks are skipped.

If the backfill is interrupted it resumes from where it left off — already-cached scores are skipped at startup.

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

## QuantConnect backtest

1. Upload `data/signals/composite_scores.parquet` to QC Object Store (see `qc/upload_signals.py`)
2. Create a new QC Algorithm project and paste in `qc/algorithm.py`
3. Set backtest dates to `2020-01-01` onward

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
