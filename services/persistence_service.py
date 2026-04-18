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
    ) -> str:
        frame = pd.DataFrame(opportunities)
        preferred_order = [
            "symbol",
            "stock_price",
            "short_strike",
            "long_strike",
            "width",
            "premium",
            "max_loss",
            "risk_reward_ratio",
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
        filename = f"opportunities_{time.strftime('%Y%m%d_%H%M%S')}{suffix}.csv"
        self.opportunities_dir.mkdir(parents=True, exist_ok=True)
        filepath = self.opportunities_dir / filename
        frame.to_csv(filepath, index=False)
        return os.fspath(filepath)
