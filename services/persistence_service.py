"""
Persistence helpers for CSV outputs.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd

from utils.analytics_fields import MARKET_CONTEXT_FIELDS


class PersistenceService:
    def __init__(
        self,
        trades_dir: str = "trades",
        opportunities_dir: str = "opportunities",
        review_queue_dir: str = "opportunities_review",
    ) -> None:
        self.trades_dir = Path(trades_dir)
        self.opportunities_dir = Path(opportunities_dir)
        self.review_queue_dir = Path(review_queue_dir)

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
            "run_id",
            "snapshot_ts",
            "strategy_id",
            "option_side",
            "directional_bias",
            "alignment_score_version",
            "symbol",
            *MARKET_CONTEXT_FIELDS,
            "stock_price",
            "stock_change_pct",
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

    def save_review_queue(
        self,
        opportunities: list[dict[str, object]],
        market_open: bool,
        filename_prefix: str = "review_queue",
    ) -> str:
        """Persist a lightweight post-run decision queue for manual review."""
        frame = pd.DataFrame(opportunities)
        if frame.empty:
            raise ValueError("Cannot save review queue for an empty opportunity set.")

        preferred_order = [
            "run_id",
            "snapshot_ts",
            "strategy_id",
            "option_side",
            "directional_bias",
            "symbol",
            *MARKET_CONTEXT_FIELDS,
            "stock_price",
            "stock_change_pct",
            "short_strike",
            "long_strike",
            "expiration_date",
            "dte",
            "premium",
            "max_loss",
            "risk_reward_ratio",
            "strategy_alignment_score",
            "put_selector_score",
            "call_selector_score",
            "selector_preferred_strategy",
            "selector_confidence",
            "selector_reason",
            "always_review_symbol",
            "always_review_forced_into_analysis",
            "always_review_source",
            "decision",
            "decision_reason",
            "decision_note",
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
        self.review_queue_dir.mkdir(parents=True, exist_ok=True)
        filepath = self.review_queue_dir / filename
        frame.to_csv(filepath, index=False)
        return os.fspath(filepath)
