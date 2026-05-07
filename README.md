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

1. **Narrative tracking** — 14 macro narratives (AI, inflation, tariffs, geopolitical conflicts, etc.) are monitored via Google Trends. A two-stage activation filter identifies narratives at peak public attention.

2. **Exposure scoring** — For each company, an LLM reads its most recent 10-K filing and scores how positively or negatively the company is exposed to each active narrative (-3 to +3), using a perceived-causality framing.

3. **Composite signal** — Active narratives are weighted by their share of total discussion volume. Exposure scores are combined into a single composite, then z-scored within GICS sector groups (industry-neutral).

4. **Backtest** — The composite signal is exported as a parquet file and consumed by a QuantConnect backtest algorithm.

---

## Project structure

```
narrative-factor/
├── narratives.py        # 14 narrative definitions with descriptions
├── trends.py            # Google Trends fetcher (weekly popularity scores)
├── activation.py        # Two-stage activation filter
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

**Step 1 — Fetch narrative popularity data (~45 min)**
```bash
venv/bin/python trends.py
venv/bin/python reprocess.py    # resample to weekly if any chunks returned daily data
venv/bin/python activation.py   # sanity check: prints which narratives were active at key dates
```

**Step 2 — Fetch company filings (~45 min)**
```bash
venv/bin/python filings.py
```

Steps 1 and 2 can run in parallel in separate terminals.

**Step 3 — Historical backfill (score all companies × all narratives)**

Run on a local GPU machine to avoid API rate limits and cost.

```bash
# On the GPU machine — install Ollama and pull the model first
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3.6:35b

# Copy data files from the fetch machine
scp user@fetch-machine:narrative-factor/data/filings.db data/
scp -r user@fetch-machine:narrative-factor/data/trends data/
scp -r user@fetch-machine:narrative-factor/data/signals data/

# Run the backfill
venv/bin/python run_weekly.py --backfill

# Skip the Google Trends refresh when re-running in the same session
# (trends data won't have changed, saves ~4 min of API calls)
venv/bin/python run_weekly.py --backfill --skip-trends
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

Estimated backfill times with Qwen3.6 35B (Q4, ~18 GB VRAM — fits on a single RTX 3090):

| Hardware | Workers | Est. time |
|---|---|---|
| 2× RTX 3090 only | 2 | ~9.7 hrs |
| 2× RTX 3090 + 2 Strix nodes (6 Ollama instances each) | 14 | ~3 hrs |
| Previous baseline (Qwen2.5 72B, both 3090s PCIe-bridged) | 1 effective | ~45 hrs |

Qwen3.6 35B fits on a single RTX 3090 (vs. Qwen2.5 72B needing both GPUs shared over PCIe), so each 3090 runs its own independent instance — that's the main reason for the 4.5× speedup on the same hardware.

If the backfill is interrupted it resumes from where it left off — already-cached scores are skipped at startup.

**Step 4 — Export signals for backtesting**
```bash
venv/bin/python export_signals.py
# Output: data/signals/composite_scores.parquet
```

### Weekly maintenance

After the initial backfill, only newly filed 10-Ks are scored — ~50 filings/week across the S&P 500. Cost depends on backend:

- **Local** (`SCORER_BACKEND=local`): negligible electricity, same as backfill
- **Anthropic** (`SCORER_BACKEND=anthropic`): ~$0.50/week at claude-sonnet-4-6 pricing

```bash
venv/bin/python run_weekly.py
```

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
| `anthropic` | ~$87 one-time (500 co × 14 narratives × ~6 yrs) | ~$0.50/week (only new filings scored) |
| `local` | ~$0.50 electricity / ~3 hrs on full cluster | Negligible — same cache logic applies |

The typical setup is `local` for the initial backfill (saves ~$87), then either backend for weekly maintenance. If you have a GPU machine running anyway, keeping `local` for weekly runs is essentially free.

Scores are cached by `(ticker, narrative_id, accession_number)` — one LLM call per filing covers all weeks that filing is current (~52 weeks per 10-K). This reduces unique calls by ~37x vs. caching by date. The initial backfill is a one-time cost; subsequent weekly runs only score new filings (~50 new filings/week across the S&P 500).

---

## The 14 narratives

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
