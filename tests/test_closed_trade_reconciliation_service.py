import tempfile
import unittest
from pathlib import Path

import pandas as pd

from services.closed_trade_reconciliation_service import (
    ClosedTradeReconciliationService,
)
from services.position_sync_service import PositionSyncService


class FakeSyncAPI:
    def __init__(self, positions, spreads, quotes=None, orders=None):
        self._positions = positions
        self._spreads = spreads
        self._quotes = quotes or {}
        self._orders = orders or []

    def get_account_positions(self):
        return self._positions

    def parse_option_spreads(self, positions):
        return self._spreads

    def get_quotes_batch(self, symbols):
        return {symbol: self._quotes.get(symbol, {}) for symbol in symbols}

    def get_account_orders(
        self, account_number=None, lookback_days=None, statuses=None
    ):
        return self._orders


class ClosedTradeReconciliationServiceTests(unittest.TestCase):
    def test_exact_leg_match_returns_actual_close(self):
        service = ClosedTradeReconciliationService()
        trade_row = {
            "symbol": "AAOI",
            "short_option_symbol": "AAOI  260515P00070000",
            "long_option_symbol": "AAOI  260515P00065000",
        }
        recent_orders = [
            {
                "id": 452604504,
                "status": "Filled",
                "underlying-symbol": "AAOI",
                "price": "0.50",
                "price-effect": "Debit",
                "received-at": "2026-04-10T15:07:00+00:00",
                "terminal-at": "2026-04-10T15:07:01+00:00",
                "legs": [
                    {
                        "action": "Buy to Close",
                        "symbol": "AAOI  260515P00070000",
                        "fills": [
                            {
                                "filled-at": "2026-04-10T15:07:01+00:00",
                                "fill-price": "1.00",
                            }
                        ],
                    },
                    {
                        "action": "Sell to Close",
                        "symbol": "AAOI  260515P00065000",
                        "fills": [
                            {
                                "filled-at": "2026-04-10T15:07:01+00:00",
                                "fill-price": "0.50",
                            }
                        ],
                    },
                ],
            }
        ]

        match = service.find_actual_close_for_trade(trade_row, recent_orders)

        self.assertIsNotNone(match)
        self.assertEqual(match.close_debit_actual, 50.0)
        self.assertEqual(match.close_order_id, 452604504)
        self.assertEqual(match.match_confidence, "exact_legs")
        self.assertEqual(match.close_fill_timestamp, "2026-04-10T15:07:01+00:00")

    def test_position_sync_falls_back_to_estimate_when_no_matching_order_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            trades_file = Path(temp_dir) / "trades_open.csv"
            closed_file = Path(temp_dir) / "trades_closed.csv"
            pd.DataFrame(
                [
                    {
                        "trade_id": "2026-03-25_AAOI_2026-05-15_70_5",
                        "symbol": "AAOI",
                        "entry_date": "2026-03-25",
                        "short_strike": 70.0,
                        "long_strike": 65.0,
                        "width": 5.0,
                        "entry_credit": 100.0,
                        "current_mark": 88.0,
                        "current_pnl": 12.0,
                        "current_pnl_pct": 12.0,
                        "dte_remaining": 36,
                        "days_held": 16,
                        "buying_power_used": 400.0,
                        "short_option_symbol": "AAOI  260515P00070000",
                        "long_option_symbol": "AAOI  260515P00065000",
                    }
                ]
            ).to_csv(trades_file, index=False)

            api = FakeSyncAPI(
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
                        "short_option_symbol": "NEW   260618P00100000",
                        "long_option_symbol": "NEW   260618P00095000",
                    }
                ],
                quotes={"NEW": {"last_price": 130.0}},
                orders=[],
            )

            result = PositionSyncService(
                trades_file=str(trades_file),
                closed_file=str(closed_file),
            ).sync_positions(api)

            self.assertTrue(result.success)
            closed_df = pd.read_csv(closed_file)
            self.assertEqual(len(closed_df), 1)
            self.assertEqual(closed_df.loc[0, "close_debit"], 88.0)
            self.assertEqual(closed_df.loc[0, "close_debit_estimated"], 88.0)
            self.assertTrue(pd.isna(closed_df.loc[0, "close_debit_actual"]))
            self.assertFalse(bool(closed_df.loc[0, "actual_exit_found"]))
            self.assertEqual(closed_df.loc[0, "exit_type"], "api_detection")

    def test_closed_trade_schema_migrates_legacy_file_when_appending_new_row(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            trades_file = Path(temp_dir) / "trades_open.csv"
            closed_file = Path(temp_dir) / "trades_closed.csv"

            legacy_closed_row = {
                "trade_id": "legacy-trade",
                "symbol": "OLD",
                "entry_date": "2026-03-01",
                "close_date": "2026-03-10",
                "short_strike": 100.0,
                "long_strike": 95.0,
                "width": 5.0,
                "entry_credit": 110.0,
                "close_debit": 55.0,
                "fees_estimated": 2.0,
                "dte_at_close": 10,
                "days_held": 9,
                "profit_loss": 55.0,
                "profit_loss_pct": 50.0,
                "max_profit": 110.0,
                "max_loss": 390.0,
                "profit_pct_of_max": 50.0,
                "annualized_return": 57.0,
                "is_estimated_exit": True,
                "exit_type": "api_detection",
                "exit_notes": "",
            }
            pd.DataFrame([legacy_closed_row]).to_csv(closed_file, index=False)

            pd.DataFrame(
                [
                    {
                        "trade_id": "2026-03-25_AAOI_2026-05-15_70_5",
                        "symbol": "AAOI",
                        "entry_date": "2026-03-25",
                        "short_strike": 70.0,
                        "long_strike": 65.0,
                        "width": 5.0,
                        "entry_credit": 100.0,
                        "current_mark": 88.0,
                        "current_pnl": 12.0,
                        "current_pnl_pct": 12.0,
                        "dte_remaining": 36,
                        "days_held": 16,
                        "buying_power_used": 400.0,
                        "short_option_symbol": "AAOI  260515P00070000",
                        "long_option_symbol": "AAOI  260515P00065000",
                    }
                ]
            ).to_csv(trades_file, index=False)

            matching_orders = [
                {
                    "id": 452604504,
                    "status": "Filled",
                    "underlying-symbol": "AAOI",
                    "price": "0.50",
                    "price-effect": "Debit",
                    "received-at": "2026-04-10T15:07:00+00:00",
                    "terminal-at": "2026-04-10T15:07:01+00:00",
                    "legs": [
                        {
                            "action": "Buy to Close",
                            "symbol": "AAOI  260515P00070000",
                            "fills": [
                                {
                                    "filled-at": "2026-04-10T15:07:01+00:00",
                                    "fill-price": "1.00",
                                }
                            ],
                        },
                        {
                            "action": "Sell to Close",
                            "symbol": "AAOI  260515P00065000",
                            "fills": [
                                {
                                    "filled-at": "2026-04-10T15:07:01+00:00",
                                    "fill-price": "0.50",
                                }
                            ],
                        },
                    ],
                }
            ]

            api = FakeSyncAPI(
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
                        "short_option_symbol": "NEW   260618P00100000",
                        "long_option_symbol": "NEW   260618P00095000",
                    }
                ],
                quotes={"NEW": {"last_price": 130.0}},
                orders=matching_orders,
            )

            result = PositionSyncService(
                trades_file=str(trades_file),
                closed_file=str(closed_file),
            ).sync_positions(api)

            self.assertTrue(result.success)
            closed_df = pd.read_csv(closed_file)
            self.assertEqual(len(closed_df), 2)
            self.assertIn("close_debit_estimated", closed_df.columns)
            self.assertIn("close_debit_actual", closed_df.columns)
            self.assertIn("actual_exit_found", closed_df.columns)
            self.assertEqual(closed_df.loc[0, "trade_id"], "legacy-trade")
            appended = closed_df[
                closed_df["trade_id"] == "2026-03-25_AAOI_2026-05-15_70_5"
            ].iloc[0]
            self.assertEqual(appended["close_debit"], 50.0)
            self.assertEqual(appended["close_debit_estimated"], 88.0)
            self.assertEqual(appended["close_debit_actual"], 50.0)
            self.assertTrue(bool(appended["actual_exit_found"]))
            self.assertEqual(appended["exit_type"], "order_history_match")


if __name__ == "__main__":
    unittest.main()
