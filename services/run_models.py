"""
Typed result models shared across service modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass(slots=True)
class PositionSyncResult:
    success: bool
    message: str = ""
    spreads_count: int = 0
    positions_df: pd.DataFrame | None = None
    display_df: pd.DataFrame | None = None
    profit_targets_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    dte_warnings_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    exit_alerts_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    trades_file: str = "trades/trades_open.csv"
    closed_trade_messages: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ScreenerRunResult:
    success: bool
    message: str = ""
    all_symbols_count: int = 0
    screened_symbols_count: int = 0
    raw_opportunities_count: int = 0
    final_opportunities: list[dict[str, object]] = field(default_factory=list)
    diagnostics: dict[str, int] = field(default_factory=dict)
    saved_csv_path: str | None = None
