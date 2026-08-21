"""
Service layer for syncing current option spread positions.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

import config
from services.closed_trade_reconciliation_service import (
    ActualCloseMatch,
    ClosedTradeReconciliationService,
)
from services.persistence_service import PersistenceService
from services.run_models import PositionSyncResult


class PositionSyncService:
    def __init__(
        self,
        trades_file: str = "trades/trades_open.csv",
        closed_file: str = "trades/trades_closed.csv",
        persistence_service: PersistenceService | None = None,
        reconciliation_service: ClosedTradeReconciliationService | None = None,
    ) -> None:
        self.trades_file = Path(trades_file)
        self.closed_file = Path(closed_file)
        self.persistence_service = persistence_service or PersistenceService(
            trades_dir=str(self.trades_file.parent)
        )
        self.reconciliation_service = (
            reconciliation_service or ClosedTradeReconciliationService()
        )

    def sync_positions(self, api) -> PositionSyncResult:
        positions = api.get_account_positions()
        if not positions:
            return PositionSyncResult(
                success=False,
                message="No positions found or failed to fetch",
                trades_file=str(self.trades_file),
            )

        spreads = api.parse_option_spreads(positions)
        if not spreads:
            return PositionSyncResult(
                success=False,
                message="No option spreads found in account",
                trades_file=str(self.trades_file),
            )

        df = pd.DataFrame(spreads)
        self._coerce_numeric_fields(df)
        self._enrich_with_quotes(api, df)
        df["exit_signal"] = df.apply(self._exit_signal, axis=1)
        loss_close_review_df = self._build_loss_close_review_df(api, df)

        prev_df = self._load_existing_open_trades()
        closed_trade_messages: list[str] = []
        if prev_df is not None and len(prev_df) > 0:
            closed_trade_messages = self._log_closed_trades(api, prev_df, df)

        self.trades_file = Path(
            self.persistence_service.save_open_trades(
                df, filename=self.trades_file.name
            )
        )

        return PositionSyncResult(
            success=True,
            spreads_count=len(df),
            positions_df=df,
            display_df=self._build_display_df(df),
            profit_targets_df=df[df["current_pnl_pct"] >= config.TARGET_PROFIT_PCT],
            loss_close_review_df=loss_close_review_df,
            dte_warnings_df=df[df["dte_remaining"] <= 21],
            exit_alerts_df=df[df["exit_signal"] != "HOLD"],
            trades_file=str(self.trades_file),
            closed_trade_messages=closed_trade_messages,
        )

    @staticmethod
    def _coerce_numeric_fields(df: pd.DataFrame) -> None:
        df["current_pnl_pct"] = pd.to_numeric(
            df.get("current_pnl_pct"), errors="coerce"
        )
        df["dte_remaining"] = pd.to_numeric(df.get("dte_remaining"), errors="coerce")
        df["entry_credit"] = pd.to_numeric(df.get("entry_credit"), errors="coerce")
        df["current_mark"] = pd.to_numeric(df.get("current_mark"), errors="coerce")

    @staticmethod
    def _build_display_df(df: pd.DataFrame) -> pd.DataFrame:
        display_cols = [
            "symbol",
            "short_strike",
            "long_strike",
            "entry_credit",
            "current_mark",
            "current_pnl",
            "current_pnl_pct",
            "dte_remaining",
            "days_held",
            "exit_signal",
        ]
        display_df = df[display_cols].copy()
        display_df.columns = [
            "Symbol",
            "Short",
            "Long",
            "Entry $",
            "Mark $",
            "P/L $",
            "P/L %",
            "DTE",
            "Days",
            "Exit Signal",
        ]
        return display_df

    def _enrich_with_quotes(self, api, df: pd.DataFrame) -> None:
        symbols = sorted(set(df["symbol"].dropna().tolist()))
        quotes = api.get_quotes_batch(symbols) if symbols else {}
        df["stock_price"] = df["symbol"].map(
            lambda symbol: (quotes.get(symbol) or {}).get("last_price")
        )
        df["short_strike_breached"] = df.apply(
            self._is_short_strike_breached,
            axis=1,
        )

    def _build_loss_close_review_df(self, api, df: pd.DataFrame) -> pd.DataFrame:
        estimated_candidates = df[
            df["current_pnl_pct"] <= -float(config.LOSS_CLOSE_REVIEW_PCT)
        ].copy()
        if estimated_candidates.empty:
            return estimated_candidates

        required_columns = {"short_option_symbol", "long_option_symbol"}
        if not required_columns.issubset(set(estimated_candidates.columns)):
            return estimated_candidates.iloc[0:0]

        option_symbols = sorted(
            {
                str(symbol)
                for symbol in (
                    list(estimated_candidates["short_option_symbol"])
                    + list(estimated_candidates["long_option_symbol"])
                )
                if str(symbol or "").strip()
            }
        )
        option_quotes = api.get_option_quotes(option_symbols, force_refresh=True)
        review_rows: list[dict[str, object]] = []
        for _, row in estimated_candidates.iterrows():
            live_metrics = self._live_close_metrics(row, option_quotes)
            if live_metrics is None:
                continue
            if live_metrics["live_pnl_pct"] > -float(config.LOSS_CLOSE_REVIEW_PCT):
                continue
            review_row = row.to_dict()
            review_row.update(live_metrics)
            review_row["close_order_payload"] = api.build_close_vertical_order(
                short_option_symbol=str(row["short_option_symbol"]),
                long_option_symbol=str(row["long_option_symbol"]),
                limit_debit=float(live_metrics["close_limit_price"]),
            )
            review_rows.append(review_row)

        return pd.DataFrame(review_rows)

    @staticmethod
    def _quote_mid(quote: dict[str, object]) -> float | None:
        bid = quote.get("bid")
        ask = quote.get("ask")
        try:
            if bid is not None and ask is not None:
                return (float(bid) + float(ask)) / 2
            if bid is not None:
                return float(bid)
            if ask is not None:
                return float(ask)
        except (TypeError, ValueError):
            return None
        return None

    @classmethod
    def _live_close_metrics(
        cls, row: pd.Series, option_quotes: dict[str, dict]
    ) -> dict[str, float] | None:
        short_quote = option_quotes.get(str(row.get("short_option_symbol") or ""))
        long_quote = option_quotes.get(str(row.get("long_option_symbol") or ""))
        if not short_quote or not long_quote:
            return None

        short_ask = short_quote.get("ask")
        long_bid = long_quote.get("bid")
        try:
            natural_debit = (
                float(short_ask) - float(long_bid)
                if short_ask is not None and long_bid is not None
                else None
            )
        except (TypeError, ValueError):
            natural_debit = None

        short_mid = cls._quote_mid(short_quote)
        long_mid = cls._quote_mid(long_quote)
        mid_debit = (
            (short_mid - long_mid)
            if short_mid is not None and long_mid is not None
            else None
        )
        close_debit_per_contract = (
            natural_debit if natural_debit is not None else mid_debit
        )
        if close_debit_per_contract is None:
            return None

        live_mark = max(0.0, close_debit_per_contract * 100)
        entry_credit = float(row.get("entry_credit"))
        if entry_credit <= 0:
            return None

        live_pnl = entry_credit - live_mark
        live_pnl_pct = (live_pnl / entry_credit) * 100
        return {
            "live_mark": round(live_mark, 2),
            "live_pnl": round(live_pnl, 2),
            "live_pnl_pct": round(live_pnl_pct, 1),
            "live_debit_per_contract": round(close_debit_per_contract, 2),
            "close_limit_price": round(close_debit_per_contract, 2),
        }

    @staticmethod
    def _is_short_strike_breached(row: pd.Series) -> bool:
        stock_price = row.get("stock_price")
        short_strike = row.get("short_strike")
        if stock_price is None or short_strike is None:
            return False
        option_side = str(row.get("option_side") or "put").strip().lower()
        if option_side == "call":
            return stock_price >= short_strike
        return stock_price <= short_strike

    @staticmethod
    def _exit_signal(row: pd.Series) -> str:
        try:
            credit = float(row.get("entry_credit"))
            debit = float(row.get("current_mark"))
        except Exception:
            return "HOLD"

        if credit <= 0:
            return "HOLD"

        breached = bool(row.get("short_strike_breached"))
        dte = row.get("dte_remaining")

        if debit >= config.EXIT_HARD_STOP_MULTIPLE * credit:
            return "CLOSE - HARD STOP"
        if breached and debit >= config.EXIT_STRUCTURAL_MULTIPLE * credit:
            return "CLOSE - STRUCTURAL BREAK"
        if breached and dte is not None and dte <= config.EXIT_GAMMA_RISK_DTE:
            return "ALERT - GAMMA RISK"
        return "HOLD"

    def _load_existing_open_trades(self) -> pd.DataFrame | None:
        if not self.trades_file.exists():
            return None
        try:
            return pd.read_csv(self.trades_file)
        except Exception:
            return None

    def _log_closed_trades(
        self, api, prev_df: pd.DataFrame, current_df: pd.DataFrame
    ) -> list[str]:
        prev_ids = (
            set(prev_df["trade_id"].astype(str))
            if "trade_id" in prev_df.columns
            else set()
        )
        curr_ids = (
            set(current_df["trade_id"].astype(str))
            if "trade_id" in current_df.columns
            else set()
        )

        closed_ids = sorted(prev_ids - curr_ids)
        if not closed_ids:
            return []

        recent_orders = api.get_account_orders(statuses=["Filled"])

        self.closed_file.parent.mkdir(parents=True, exist_ok=True)
        existing_closed = self._load_existing_closed_trades()
        existing_ids = (
            set(existing_closed["trade_id"].astype(str))
            if (existing_closed is not None and "trade_id" in existing_closed.columns)
            else set()
        )

        records: list[dict[str, object]] = []
        messages: list[str] = []

        for trade_id in closed_ids:
            row = prev_df[prev_df["trade_id"].astype(str) == trade_id]
            if row.empty:
                continue

            actual_close_match = (
                self.reconciliation_service.find_actual_close_for_trade(
                    row.iloc[0],
                    recent_orders,
                )
            )
            record, record_messages = self._build_closed_trade_record(
                trade_id,
                row.iloc[0],
                actual_close_match=actual_close_match,
            )
            messages.extend(record_messages)
            if record is None:
                continue
            if trade_id not in existing_ids:
                records.append(record)

        if not records:
            return messages

        cols = self._closed_trade_columns()
        new_df = pd.DataFrame(records)
        new_df = new_df.reindex(columns=cols)
        if (
            self.closed_file.exists()
            and existing_closed is not None
            and len(existing_closed) >= 0
        ):
            existing_closed = existing_closed.reindex(columns=cols)
            combined = pd.concat([existing_closed, new_df], ignore_index=True)
            combined = combined.reindex(columns=cols)
            combined.to_csv(self.closed_file, index=False)
        else:
            new_df.to_csv(self.closed_file, index=False)

        messages.append(f"Saved {len(records)} closed trade(s) to {self.closed_file}")
        return messages

    def _load_existing_closed_trades(self) -> pd.DataFrame | None:
        if not self.closed_file.exists():
            return None
        try:
            return pd.read_csv(self.closed_file)
        except Exception:
            return None

    def _build_closed_trade_record(
        self,
        trade_id: str,
        row: pd.Series,
        actual_close_match: ActualCloseMatch | None = None,
    ) -> tuple[dict[str, object] | None, list[str]]:
        messages: list[str] = []

        def _safe_float(value) -> float | None:
            try:
                if pd.isna(value):
                    return None
                return float(value)
            except Exception:
                return None

        def _normalize_contract_value(
            value: float | None, trade_width: float | None, field_name: str
        ) -> float | None:
            if value is None:
                return None

            if trade_width is not None and trade_width > 0:
                width_cap = trade_width * 100
                if value > (width_cap * 1.5) and (value / 100) <= (width_cap * 1.5):
                    corrected = value / 100
                    messages.append(
                        f"Corrected {field_name} for {trade_id}: {value:.2f} -> {corrected:.2f} "
                        "(possible x100 scaling)"
                    )
                    return corrected

                if value > (width_cap * 3):
                    messages.append(
                        f"Suspicious {field_name} for {trade_id}: {value:.2f} "
                        f"exceeds expected cap ${width_cap:.2f}"
                    )

            return value

        entry_credit_per_contract = _safe_float(row.get("entry_credit"))
        width = _safe_float(row.get("width"))
        buying_power_used = _safe_float(row.get("buying_power_used"))
        exit_debit_per_contract = _safe_float(row.get("current_mark"))

        entry_credit = _normalize_contract_value(
            entry_credit_per_contract, width, "entry_credit"
        )
        close_debit_estimated = _normalize_contract_value(
            exit_debit_per_contract, width, "close_debit"
        )
        close_debit_actual = (
            actual_close_match.close_debit_actual
            if actual_close_match is not None
            else None
        )
        close_debit = (
            close_debit_actual
            if close_debit_actual is not None
            else close_debit_estimated
        )
        dte_at_close = (
            int(row["dte_remaining"])
            if "dte_remaining" in row and pd.notna(row["dte_remaining"])
            else None
        )

        profit_loss = (
            (entry_credit - close_debit)
            if (entry_credit is not None and close_debit is not None)
            else None
        )
        profit_loss_pct = (
            (profit_loss / entry_credit * 100)
            if (profit_loss is not None and entry_credit)
            else None
        )
        max_profit = entry_credit if entry_credit is not None else None
        max_loss = (
            ((width * 100) - entry_credit)
            if (width is not None and entry_credit is not None)
            else None
        )
        if max_loss is not None and max_loss < 0:
            messages.append(
                f"Skipping invalid closed trade {trade_id}: computed max_loss={max_loss:.2f}"
            )
            return None, messages

        profit_pct_of_max = (
            (profit_loss / max_profit * 100)
            if (profit_loss is not None and max_profit)
            else None
        )

        try:
            entry_date = (
                pd.to_datetime(row["entry_date"]).date()
                if pd.notna(row["entry_date"])
                else None
            )
        except Exception:
            entry_date = None

        close_date = date.today()
        days_held = (close_date - entry_date).days if entry_date else None

        annualized_return = None
        if (
            buying_power_used
            and profit_loss is not None
            and days_held
            and days_held > 0
        ):
            annualized_return = (
                (profit_loss / buying_power_used) * (365 / days_held) * 100
            )

        record = {
            "trade_id": trade_id,
            "strategy_id": row.get("strategy_id"),
            "strategy_family": row.get("strategy_family"),
            "option_side": row.get("option_side"),
            "directional_bias": row.get("directional_bias"),
            "short_leg_type": row.get("short_leg_type"),
            "long_leg_type": row.get("long_leg_type"),
            "symbol": row.get("symbol"),
            "entry_date": row.get("entry_date"),
            "close_date": close_date.isoformat(),
            "short_strike": row.get("short_strike"),
            "long_strike": row.get("long_strike"),
            "width": width,
            "entry_credit": entry_credit,
            "close_debit": close_debit,
            "close_debit_estimated": close_debit_estimated,
            "close_debit_actual": close_debit_actual,
            "fees_estimated": 2.0,
            "dte_at_close": dte_at_close,
            "days_held": days_held,
            "profit_loss": round(profit_loss, 2) if profit_loss is not None else None,
            "profit_loss_pct": round(profit_loss_pct, 2)
            if profit_loss_pct is not None
            else None,
            "max_profit": max_profit,
            "max_loss": round(max_loss, 2) if max_loss is not None else None,
            "profit_pct_of_max": round(profit_pct_of_max, 2)
            if profit_pct_of_max is not None
            else None,
            "annualized_return": round(annualized_return, 2)
            if annualized_return is not None
            else None,
            "actual_exit_found": actual_close_match is not None,
            "exit_price_source": (
                actual_close_match.exit_price_source
                if actual_close_match is not None
                else "position_mark_estimate"
            ),
            "close_fill_timestamp": (
                actual_close_match.close_fill_timestamp
                if actual_close_match is not None
                else None
            ),
            "close_order_id": (
                actual_close_match.close_order_id
                if actual_close_match is not None
                else None
            ),
            "match_confidence": (
                actual_close_match.match_confidence
                if actual_close_match is not None
                else "no_match"
            ),
            "is_estimated_exit": actual_close_match is None,
            "exit_type": (
                "order_history_match"
                if actual_close_match is not None
                else "api_detection"
            ),
            "exit_notes": "",
        }
        return record, messages

    @staticmethod
    def _closed_trade_columns() -> list[str]:
        return [
            "trade_id",
            "strategy_id",
            "strategy_family",
            "option_side",
            "directional_bias",
            "short_leg_type",
            "long_leg_type",
            "symbol",
            "entry_date",
            "close_date",
            "short_strike",
            "long_strike",
            "width",
            "entry_credit",
            "close_debit",
            "close_debit_estimated",
            "close_debit_actual",
            "fees_estimated",
            "dte_at_close",
            "days_held",
            "profit_loss",
            "profit_loss_pct",
            "max_profit",
            "max_loss",
            "profit_pct_of_max",
            "annualized_return",
            "actual_exit_found",
            "exit_price_source",
            "close_fill_timestamp",
            "close_order_id",
            "match_confidence",
            "is_estimated_exit",
            "exit_type",
            "exit_notes",
        ]
