import tempfile
import unittest
from pathlib import Path

import pandas as pd

from services.position_sync_service import PositionSyncService


class FakeAPI:
    def __init__(self, positions, spreads, quotes, orders=None):
        self._positions = positions
        self._spreads = spreads
        self._quotes = quotes
        self._orders = orders or []
        self.option_quote_force_refresh = None

    def get_account_positions(self):
        return self._positions

    def parse_option_spreads(self, positions):
        return self._spreads

    def get_quotes_batch(self, symbols):
        return {symbol: self._quotes.get(symbol, {}) for symbol in symbols}

    def get_account_orders(self, statuses=None):
        return self._orders

    def get_option_quotes(self, symbols, batch_size=50, force_refresh=False):
        self.option_quote_force_refresh = force_refresh
        return {symbol: self._quotes.get(symbol, {}) for symbol in symbols}

    def build_close_vertical_order(
        self,
        *,
        short_option_symbol,
        long_option_symbol,
        limit_debit,
        quantity=1,
        time_in_force="Day",
    ):
        return {
            "time-in-force": time_in_force,
            "order-type": "Limit",
            "price": round(float(limit_debit), 2),
            "price-effect": "Debit",
            "legs": [
                {
                    "instrument-type": "Equity Option",
                    "symbol": short_option_symbol,
                    "quantity": int(quantity),
                    "action": "Buy to Close",
                },
                {
                    "instrument-type": "Equity Option",
                    "symbol": long_option_symbol,
                    "quantity": int(quantity),
                    "action": "Sell to Close",
                },
            ],
        }


class PositionSyncServiceTests(unittest.TestCase):
    def test_sync_positions_builds_result_and_writes_open_trades(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            trades_file = Path(temp_dir) / "trades_open.csv"
            closed_file = Path(temp_dir) / "trades_closed.csv"
            service = PositionSyncService(
                trades_file=str(trades_file),
                closed_file=str(closed_file),
            )
            api = FakeAPI(
                positions=[{"symbol": "ABC"}],
                spreads=[
                    {
                        "trade_id": "trade-1",
                        "symbol": "ABC",
                        "short_strike": 95.0,
                        "long_strike": 90.0,
                        "entry_credit": 100.0,
                        "current_mark": 40.0,
                        "current_pnl": 60.0,
                        "current_pnl_pct": 60.0,
                        "dte_remaining": 18,
                        "days_held": 5,
                        "buying_power_used": 400.0,
                        "entry_date": "2026-04-10",
                        "width": 5.0,
                    }
                ],
                quotes={"ABC": {"last_price": 120.0}},
            )

            result = service.sync_positions(api)

            self.assertTrue(result.success)
            self.assertEqual(result.spreads_count, 1)
            self.assertTrue(trades_file.exists())
            self.assertEqual(
                list(result.display_df.columns),
                [
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
                ],
            )
            self.assertEqual(len(result.profit_targets_df), 1)
            self.assertEqual(len(result.dte_warnings_df), 1)
            self.assertEqual(len(result.exit_alerts_df), 0)

    def test_sync_positions_uses_call_breach_direction(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            trades_file = Path(temp_dir) / "trades_open.csv"
            closed_file = Path(temp_dir) / "trades_closed.csv"
            service = PositionSyncService(
                trades_file=str(trades_file),
                closed_file=str(closed_file),
            )
            api = FakeAPI(
                positions=[{"symbol": "IWM"}],
                spreads=[
                    {
                        "trade_id": "call-trade",
                        "strategy_id": "call_credit_spread",
                        "option_side": "call",
                        "symbol": "IWM",
                        "short_strike": 225.0,
                        "long_strike": 230.0,
                        "entry_credit": 70.0,
                        "current_mark": 40.0,
                        "current_pnl": 30.0,
                        "current_pnl_pct": 42.9,
                        "dte_remaining": 18,
                        "days_held": 1,
                        "buying_power_used": 430.0,
                        "entry_date": "2026-08-07",
                        "width": 5.0,
                    }
                ],
                quotes={"IWM": {"last_price": 226.0}},
            )

            result = service.sync_positions(api)

            self.assertTrue(result.success)
            self.assertTrue(bool(result.positions_df.loc[0, "short_strike_breached"]))

    def test_sync_positions_logs_closed_trade_when_previous_trade_disappears(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            trades_file = Path(temp_dir) / "trades_open.csv"
            closed_file = Path(temp_dir) / "trades_closed.csv"
            pd.DataFrame(
                [
                    {
                        "trade_id": "old-trade",
                        "symbol": "OLD",
                        "short_strike": 80.0,
                        "long_strike": 75.0,
                        "entry_credit": 90.0,
                        "current_mark": 20.0,
                        "current_pnl": 70.0,
                        "current_pnl_pct": 77.7,
                        "dte_remaining": 10,
                        "days_held": 7,
                        "buying_power_used": 410.0,
                        "entry_date": "2026-04-01",
                        "width": 5.0,
                    }
                ]
            ).to_csv(trades_file, index=False)

            service = PositionSyncService(
                trades_file=str(trades_file),
                closed_file=str(closed_file),
            )
            api = FakeAPI(
                positions=[{"symbol": "NEW"}],
                spreads=[
                    {
                        "trade_id": "new-trade",
                        "symbol": "NEW",
                        "short_strike": 100.0,
                        "long_strike": 95.0,
                        "entry_credit": 100.0,
                        "current_mark": 80.0,
                        "current_pnl": 20.0,
                        "current_pnl_pct": 20.0,
                        "dte_remaining": 30,
                        "days_held": 2,
                        "buying_power_used": 400.0,
                        "entry_date": "2026-04-14",
                        "width": 5.0,
                    }
                ],
                quotes={"NEW": {"last_price": 130.0}},
            )

            result = service.sync_positions(api)

            self.assertTrue(result.success)
            self.assertTrue(closed_file.exists())
            self.assertTrue(
                any(
                    "Saved 1 closed trade(s)" in message
                    for message in result.closed_trade_messages
                )
            )
            closed_df = pd.read_csv(closed_file)
            self.assertEqual(len(closed_df), 1)
            self.assertEqual(closed_df.loc[0, "trade_id"], "old-trade")

    def test_sync_positions_confirms_loss_close_review_with_live_quotes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            trades_file = Path(temp_dir) / "trades_open.csv"
            closed_file = Path(temp_dir) / "trades_closed.csv"
            service = PositionSyncService(
                trades_file=str(trades_file),
                closed_file=str(closed_file),
            )
            api = FakeAPI(
                positions=[{"symbol": "ABC"}],
                spreads=[
                    {
                        "trade_id": "loss-trade",
                        "strategy_id": "put_credit_spread",
                        "option_side": "put",
                        "symbol": "ABC",
                        "short_strike": 95.0,
                        "long_strike": 90.0,
                        "entry_credit": 100.0,
                        "current_mark": 198.0,
                        "current_pnl": -98.0,
                        "current_pnl_pct": -98.0,
                        "dte_remaining": 18,
                        "days_held": 5,
                        "buying_power_used": 400.0,
                        "entry_date": "2026-04-10",
                        "width": 5.0,
                        "short_option_symbol": "ABC   260918P00095000",
                        "long_option_symbol": "ABC   260918P00090000",
                    }
                ],
                quotes={
                    "ABC": {"last_price": 94.0},
                    "ABC   260918P00095000": {"bid": 2.05, "ask": 2.15},
                    "ABC   260918P00090000": {"bid": 0.10, "ask": 0.20},
                },
            )

            result = service.sync_positions(api)

            self.assertTrue(result.success)
            self.assertTrue(api.option_quote_force_refresh)
            self.assertEqual(len(result.loss_close_review_df), 1)
            candidate = result.loss_close_review_df.iloc[0]
            self.assertEqual(candidate["symbol"], "ABC")
            self.assertEqual(candidate["live_mark"], 205.0)
            self.assertEqual(candidate["live_pnl"], -105.0)
            self.assertEqual(candidate["live_pnl_pct"], -105.0)
            self.assertEqual(candidate["close_limit_price"], 2.05)
            self.assertEqual(
                candidate["close_order_payload"]["legs"][0]["action"],
                "Buy to Close",
            )

    def test_sync_positions_skips_loss_close_review_when_live_quotes_recover(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            trades_file = Path(temp_dir) / "trades_open.csv"
            closed_file = Path(temp_dir) / "trades_closed.csv"
            service = PositionSyncService(
                trades_file=str(trades_file),
                closed_file=str(closed_file),
            )
            api = FakeAPI(
                positions=[{"symbol": "ABC"}],
                spreads=[
                    {
                        "trade_id": "loss-trade",
                        "strategy_id": "put_credit_spread",
                        "option_side": "put",
                        "symbol": "ABC",
                        "short_strike": 95.0,
                        "long_strike": 90.0,
                        "entry_credit": 100.0,
                        "current_mark": 198.0,
                        "current_pnl": -98.0,
                        "current_pnl_pct": -98.0,
                        "dte_remaining": 18,
                        "days_held": 5,
                        "buying_power_used": 400.0,
                        "entry_date": "2026-04-10",
                        "width": 5.0,
                        "short_option_symbol": "ABC   260918P00095000",
                        "long_option_symbol": "ABC   260918P00090000",
                    }
                ],
                quotes={
                    "ABC": {"last_price": 94.0},
                    "ABC   260918P00095000": {"bid": 1.85, "ask": 1.90},
                    "ABC   260918P00090000": {"bid": 0.05, "ask": 0.10},
                },
            )

            result = service.sync_positions(api)

            self.assertTrue(result.success)
            self.assertEqual(len(result.loss_close_review_df), 0)


if __name__ == "__main__":
    unittest.main()
