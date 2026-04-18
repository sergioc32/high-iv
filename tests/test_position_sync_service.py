import tempfile
import unittest
from pathlib import Path

import pandas as pd

from services.position_sync_service import PositionSyncService


class FakeAPI:
    def __init__(self, positions, spreads, quotes):
        self._positions = positions
        self._spreads = spreads
        self._quotes = quotes

    def get_account_positions(self):
        return self._positions

    def parse_option_spreads(self, positions):
        return self._spreads

    def get_quotes_batch(self, symbols):
        return {symbol: self._quotes.get(symbol, {}) for symbol in symbols}


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


if __name__ == "__main__":
    unittest.main()
