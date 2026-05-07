"""
Narrative Factor — QuantConnect Backtest Algorithm

Long-only implementation of the narrative factor strategy.
Rebalances weekly, holding the top-decile narrative composite score
within each GICS sector (industry-neutral).

When no narratives are active the strategy holds cash — matching the paper's
design where the factor goes flat during inactive windows.

Setup:
  1. Upload data/signals/composite_scores.parquet to QC Object Store
     via the QC Research terminal:
         qb.object_store.save_bytes("narrative/composite_scores.parquet",
                                    open("composite_scores.parquet","rb").read())
  2. Paste this file into a new QC Algorithm project.
  3. Set backtest dates to match your signal file range (2020-01-01 onward).
"""

from AlgorithmImports import *
import io
import pandas as pd


SIGNAL_KEY        = "narrative/composite_scores.parquet"
TOP_DECILE        = 0.10    # fraction of each sector to go long
MIN_SECTOR_STOCKS = 5       # skip sector if fewer stocks have scores
MAX_POSITION_SIZE = 0.05    # single-stock weight cap


class NarrativeFactorAlgorithm(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 6)   # first Monday in signal range
        self.set_end_date(2026, 4, 13)    # match paper period; update as signals extend
        self.set_cash(100_000)

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE,
                                 AccountType.CASH)

        # SPY is needed as the schedule anchor
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

    # ------------------------------------------------------------------
    # Signal loading
    # ------------------------------------------------------------------

    def _load_signals(self) -> None:
        raw = self.object_store.read_bytes(SIGNAL_KEY)
        self._signals = pd.read_parquet(io.BytesIO(raw))
        self._signals["date"] = pd.to_datetime(self._signals["date"])
        self.log(f"Signals loaded: {len(self._signals):,} rows, "
                 f"{self._signals['ticker'].nunique()} tickers, "
                 f"{self._signals['date'].min().date()} → {self._signals['date'].max().date()}")

    def _add_universe_equities(self) -> None:
        for ticker in self._signals["ticker"].unique():
            try:
                symbol = self.add_equity(ticker, Resolution.DAILY).symbol
                self._symbol_map[ticker] = symbol
            except Exception:
                pass  # ticker may not be in QC data (delisted, name change, etc.)
        self.log(f"Added {len(self._symbol_map)} of {self._signals['ticker'].nunique()} "
                 f"signal tickers to QC universe")

    # ------------------------------------------------------------------
    # Rebalancing
    # ------------------------------------------------------------------

    def _rebalance(self) -> None:
        today = self.Time.date()
        targets = self._get_targets(today)

        if not targets:
            # No active narratives — go flat (matches paper's design)
            if self.portfolio.invested:
                self.liquidate()
                self.log(f"{today}: no active narrative — liquidated to cash")
            return

        # Liquidate positions no longer in target set
        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in targets:
                self.liquidate(holding.symbol)

        # Set target weights for tradeable securities
        for symbol, weight in targets.items():
            if self.securities[symbol].is_tradable:
                self.set_holdings(symbol, weight)

        self.log(f"{today}: {len(targets)} positions, "
                 f"avg weight {sum(targets.values())/len(targets):.2%}")

    def _get_targets(self, today) -> dict[Symbol, float]:
        """
        Select top-decile tickers within each sector on the most recent
        signal date <= today. Returns {Symbol: weight} or empty dict.
        """
        past = self._signals[self._signals["date"].dt.date <= today]
        if past.empty:
            return {}

        latest_date = past["date"].max()
        snap = past[past["date"] == latest_date].copy()

        # Empty composite_score rows indicate inactive period in the signal file
        if snap["composite_score"].isna().all():
            return {}

        selected_tickers = []
        for sector, group in snap.groupby("sector"):
            group = group[group["ticker"].isin(self._symbol_map)].dropna(subset=["composite_score"])
            if len(group) < MIN_SECTOR_STOCKS:
                continue
            n_long = max(1, round(len(group) * TOP_DECILE))
            top = group.nlargest(n_long, "composite_score")["ticker"].tolist()
            selected_tickers.extend(top)

        if not selected_tickers:
            return {}

        raw_weight = 1.0 / len(selected_tickers)
        weight = min(raw_weight, MAX_POSITION_SIZE)

        return {
            self._symbol_map[t]: weight
            for t in selected_tickers
            if t in self._symbol_map
        }
