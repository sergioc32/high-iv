"""
Persistence helpers for CSV outputs.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd


class PersistenceService:
    def __init__(
        self,
        trades_dir: str = "trades",
        opportunities_dir: str = "opportunities",
    ) -> None:
        self.trades_dir = Path(trades_dir)
        self.opportunities_dir = Path(opportunities_dir)

    def save_open_trades(
        self,
        frame: pd.DataFrame,
        filename: str = "trades_open.csv",
    ) -> str:
        self.trades_dir.mkdir(parents=True, exist_ok=True)
        filepath = self.trades_dir / filename
        frame.to_csv(filepath, index=False)
        return os.fspath(filepath)

    def save_opportunities(
        self,
        opportunities: list[dict[str, object]],
        market_open: bool,
        filename_prefix: str = "opportunities",
    ) -> str:
        frame = pd.DataFrame(opportunities)
        preferred_order = [
            "strategy_id",
            "option_side",
            "directional_bias",
            "alignment_score_version",
            "symbol",
            "stock_price",
            "short_strike",
            "long_strike",
            "width",
            "premium",
            "max_loss",
            "risk_reward_ratio",
            "strategy_alignment_score",
            "total_rank_score",
            "selector_version",
            "market_regime_spy",
            "market_regime_qqq",
            "market_regime_summary",
            "symbol_extension_bucket",
            "put_selector_score",
            "call_selector_score",
            "selector_preferred_strategy",
            "selector_confidence",
            "selector_reason",
            "always_review_symbol",
            "always_review_forced_into_analysis",
            "always_review_source",
            "delta_preference_component",
            "skew_component",
            "ev_component",
            "liquidity_component",
            "extension_component",
            "directional_adjustment",
            "earnings_adjustment",
            "alignment_flags",
            "delta_zone",
            "explanation_summary",
            "dte",
            "expiration_date",
            "earnings_within_dte",
            "skew_ratio",
            "skew_diff",
            "short_iv",
            "atm_iv",
        ]
        for column in preferred_order:
            if column not in frame.columns:
                frame[column] = ""
        remaining_cols = [
            column for column in frame.columns if column not in preferred_order
        ]
        frame = frame[preferred_order + remaining_cols]

        suffix = "_indicative" if not market_open else ""
        filename = f"{filename_prefix}_{time.strftime('%Y%m%d_%H%M%S')}{suffix}.csv"
        self.opportunities_dir.mkdir(parents=True, exist_ok=True)
        filepath = self.opportunities_dir / filename
        frame.to_csv(filepath, index=False)
        return os.fspath(filepath)
