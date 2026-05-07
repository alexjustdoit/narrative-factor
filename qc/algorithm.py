"""
Narrative Factor — Parametric QuantConnect Backtest Algorithm

Supports three overlay modes and three base factor options. Change the CONFIG
block to run different variants — the full backtest grid is BASE_FACTOR ×
OVERLAY_MODE (12 core variants) plus parameter sweeps on TOP_DECILE and
NARRATIVE_BLEND.

Overlay modes:
  narrative_only  —  baseline: top-decile by narrative score, equal weight
  selection       —  base factor filters universe; narrative selects within it
  weighting       —  narrative selects holdings; base + narrative blend sizes them

Base factors:
  quality   —  ROE + ROA composite (higher = better)
  value     —  earnings yield + book yield (higher = cheaper)
  momentum  —  12-1 month price return (skips last month to avoid reversal)
  None      —  no base factor (same as narrative_only for selection; equal base weight for weighting)

Setup:
  1. Upload data/signals/composite_scores.parquet to QC Object Store
  2. Paste this file into a new QC Algorithm project
  3. Set backtest dates to match your signal file range
"""

from AlgorithmImports import *
import io
import numpy as np
import pandas as pd


# ============================================================
# CONFIG — change these to define a backtest variant
# ============================================================

BASE_FACTOR        = "quality"    # "quality" | "value" | "momentum" | None
OVERLAY_MODE       = "selection"  # "selection" | "weighting" | "narrative_only"

TOP_DECILE         = 0.10         # top-N fraction by narrative score (all modes)
BASE_UNIVERSE_PCTL = 0.50         # selection mode: base factor top-N cutoff before narrative filter
NARRATIVE_BLEND    = 0.50         # weighting mode: narrative weight (0.0 = all base, 1.0 = all narrative)

MAX_POSITION_SIZE  = 0.05
MIN_SECTOR_STOCKS  = 5
SIGNAL_KEY         = "narrative/composite_scores.parquet"


class NarrativeFactorAlgorithm(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 6)
        self.set_end_date(2026, 4, 13)
        self.set_cash(100_000)
        self.set_benchmark("SPY")
        self.set_brokerage_model(
            BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.CASH
        )

        self.add_equity("SPY", Resolution.DAILY)

        self._signals: pd.DataFrame = pd.DataFrame()
        self._symbol_map: dict[str, Symbol] = {}

        self._load_signals()
        self._add_universe_equities()

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self._rebalance,
        )

        self.log(
            f"Config: BASE_FACTOR={BASE_FACTOR}  OVERLAY_MODE={OVERLAY_MODE}  "
            f"TOP_DECILE={TOP_DECILE}  BASE_UNIVERSE_PCTL={BASE_UNIVERSE_PCTL}  "
            f"NARRATIVE_BLEND={NARRATIVE_BLEND}"
        )

    # ------------------------------------------------------------------
    # Signal loading
    # ------------------------------------------------------------------

    def _load_signals(self) -> None:
        raw = self.object_store.read_bytes(SIGNAL_KEY)
        self._signals = pd.read_parquet(io.BytesIO(raw))
        self._signals["date"] = pd.to_datetime(self._signals["date"])
        self.log(
            f"Signals loaded: {len(self._signals):,} rows, "
            f"{self._signals['ticker'].nunique()} tickers, "
            f"{self._signals['date'].min().date()} → {self._signals['date'].max().date()}"
        )

    def _add_universe_equities(self) -> None:
        for ticker in self._signals["ticker"].unique():
            try:
                symbol = self.add_equity(ticker, Resolution.DAILY).symbol
                self._symbol_map[ticker] = symbol
            except Exception:
                pass
        self.log(
            f"Added {len(self._symbol_map)}/{self._signals['ticker'].nunique()} tickers"
        )

    # ------------------------------------------------------------------
    # Rebalancing
    # ------------------------------------------------------------------

    def _rebalance(self) -> None:
        today = self.time.date()
        targets = self._get_targets(today)

        if not targets:
            if self.portfolio.invested:
                self.liquidate()
                self.log(f"{today}: no active signal — liquidated to cash")
            return

        for holding in self.portfolio.values:
            if holding.invested and holding.symbol not in targets:
                self.liquidate(holding.symbol)

        for symbol, weight in targets.items():
            if self.securities[symbol].is_tradable:
                self.set_holdings(symbol, weight)

        self.log(
            f"{today}: {len(targets)} positions, "
            f"avg weight {sum(targets.values()) / len(targets):.2%}"
        )

    # ------------------------------------------------------------------
    # Target construction
    # ------------------------------------------------------------------

    def _get_targets(self, today) -> dict[Symbol, float]:
        past = self._signals[self._signals["date"].dt.date <= today]
        if past.empty:
            return {}

        snap = past[past["date"] == past["date"].max()].copy()
        if snap["composite_score"].isna().all():
            return {}

        # Batch-fetch base scores for all tracked symbols
        tracked = [self._symbol_map[t] for t in snap["ticker"] if t in self._symbol_map]
        base_scores = self._get_base_scores(tracked) if BASE_FACTOR else {}

        sector_weights: dict[Symbol, float] = {}

        for sector, group in snap.groupby("sector"):
            group = (
                group[group["ticker"].isin(self._symbol_map)]
                .dropna(subset=["composite_score"])
            )
            if len(group) < MIN_SECTOR_STOCKS:
                continue

            sector_base = {
                self._symbol_map[t]: base_scores[self._symbol_map[t]]
                for t in group["ticker"]
                if self._symbol_map.get(t) in base_scores
            }

            sector_weights.update(self._apply_overlay(group, sector_base))

        if not sector_weights:
            return {}

        # Normalize globally then cap; remainder sits in cash
        total = sum(sector_weights.values())
        if total == 0:
            return {}
        return {
            sym: min(w / total, MAX_POSITION_SIZE)
            for sym, w in sector_weights.items()
        }

    def _apply_overlay(
        self, group: pd.DataFrame, base_scores: dict[Symbol, float]
    ) -> dict[Symbol, float]:
        """Returns {Symbol: unnormalized_weight} for one sector."""

        if OVERLAY_MODE == "narrative_only" or BASE_FACTOR is None:
            return self._select_top_equal(group)

        if OVERLAY_MODE == "selection":
            filtered = self._filter_by_base(group, base_scores)
            return self._select_top_equal(filtered)

        if OVERLAY_MODE == "weighting":
            holdings = self._select_top_df(group)
            if holdings.empty:
                return {}
            return self._blend_weights(holdings, base_scores)

        return {}

    def _select_top_equal(self, group: pd.DataFrame) -> dict[Symbol, float]:
        """Top-N by narrative score, equal weight."""
        top = self._select_top_df(group)
        return {
            self._symbol_map[t]: 1.0
            for t in top["ticker"]
            if t in self._symbol_map
        }

    def _select_top_df(self, group: pd.DataFrame) -> pd.DataFrame:
        """Returns top TOP_DECILE rows by composite_score."""
        n = max(1, round(len(group) * TOP_DECILE))
        return group.nlargest(n, "composite_score")

    def _filter_by_base(
        self, group: pd.DataFrame, base_scores: dict[Symbol, float]
    ) -> pd.DataFrame:
        """Keeps top BASE_UNIVERSE_PCTL of sector by base factor score."""
        group = group.copy()
        group["_base"] = group["ticker"].map(
            {t: base_scores.get(self._symbol_map.get(t)) for t in group["ticker"]}
        )
        has_base = group.dropna(subset=["_base"])
        if len(has_base) < 3:
            return group  # sparse base data — fall back to full sector
        n = max(1, round(len(has_base) * BASE_UNIVERSE_PCTL))
        return has_base.nlargest(n, "_base")

    def _blend_weights(
        self, holdings: pd.DataFrame, base_scores: dict[Symbol, float]
    ) -> dict[Symbol, float]:
        """
        Sizes positions by NARRATIVE_BLEND * z(narrative) + (1-NARRATIVE_BLEND) * z(base).
        Falls back to equal weight when base data is unavailable.
        """
        tickers = [t for t in holdings["ticker"] if t in self._symbol_map]
        if not tickers:
            return {}

        narr_raw = dict(zip(holdings["ticker"], holdings["composite_score"]))
        base_raw = {t: base_scores.get(self._symbol_map[t]) for t in tickers}

        narr_z = _zscore({t: narr_raw[t] for t in tickers if t in narr_raw})
        base_z = _zscore({t: v for t, v in base_raw.items() if v is not None})

        weights: dict[Symbol, float] = {}
        for t in tickers:
            n_score = narr_z.get(t, 0.0)
            b_score = base_z.get(t, 0.0)
            blend   = NARRATIVE_BLEND if t in base_z else 1.0
            combined = blend * n_score + (1.0 - blend) * b_score
            weights[self._symbol_map[t]] = max(combined, 0.0)

        # All non-positive scores (e.g., bear market) → fall back to equal weight
        if sum(weights.values()) == 0:
            return {sym: 1.0 for sym in weights}

        return weights

    # ------------------------------------------------------------------
    # Base factor scoring
    # ------------------------------------------------------------------

    def _get_base_scores(self, symbols: list[Symbol]) -> dict[Symbol, float]:
        if BASE_FACTOR == "quality":
            return self._quality_scores(symbols)
        if BASE_FACTOR == "value":
            return self._value_scores(symbols)
        if BASE_FACTOR == "momentum":
            return self._momentum_scores(symbols)
        return {}

    def _quality_scores(self, symbols: list[Symbol]) -> dict[Symbol, float]:
        """ROE + ROA composite. Higher = better quality."""
        out = {}
        for sym in symbols:
            try:
                f = self.securities[sym].fundamentals
                if f is None:
                    continue
                roe = f.operation_ratios.roe.value
                roa = f.operation_ratios.roa.value
                vals = [v for v in (roe, roa) if v is not None and np.isfinite(v)]
                if vals:
                    out[sym] = sum(vals) / len(vals)
            except Exception:
                pass
        return out

    def _value_scores(self, symbols: list[Symbol]) -> dict[Symbol, float]:
        """Earnings yield (1/PE) + book yield (1/PB). Higher = cheaper."""
        out = {}
        for sym in symbols:
            try:
                f = self.securities[sym].fundamentals
                if f is None:
                    continue
                pe = f.valuation_ratios.pe_ratio
                pb = f.valuation_ratios.pb_ratio
                ey = (1.0 / pe) if pe and pe > 0 and np.isfinite(pe) else None
                by = (1.0 / pb) if pb and pb > 0 and np.isfinite(pb) else None
                vals = [v for v in (ey, by) if v is not None]
                if vals:
                    out[sym] = sum(vals) / len(vals)
            except Exception:
                pass
        return out

    def _momentum_scores(self, symbols: list[Symbol]) -> dict[Symbol, float]:
        """12-1 month price return (batched). Skips last month to avoid reversal."""
        if not symbols:
            return {}
        try:
            hist = self.history(symbols, 252, Resolution.DAILY)
            if hist.empty:
                return {}
            out = {}
            for sym in symbols:
                try:
                    prices = hist.loc[sym]["close"]
                    if len(prices) < 22:
                        continue
                    out[sym] = float(prices.iloc[-21] / prices.iloc[0]) - 1.0
                except Exception:
                    pass
            return out
        except Exception:
            return {}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _zscore(scores: dict) -> dict:
    """Z-scores a {key: float} dict in-place. Returns {} if fewer than 2 values."""
    if len(scores) < 2:
        return dict(scores)
    vals = np.array(list(scores.values()), dtype=float)
    mean, std = vals.mean(), vals.std()
    if std == 0:
        return {k: 0.0 for k in scores}
    return {k: float((v - mean) / std) for k, v in scores.items()}
