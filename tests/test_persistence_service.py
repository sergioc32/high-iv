import tempfile
import unittest
from pathlib import Path

import pandas as pd

from services.persistence_service import PersistenceService


class PersistenceServiceTests(unittest.TestCase):
    def test_save_open_trades_writes_to_trades_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = PersistenceService(trades_dir=temp_dir)
            frame = pd.DataFrame([{"trade_id": "t1", "symbol": "ABC"}])

            saved_path = service.save_open_trades(frame)

            self.assertTrue(Path(saved_path).exists())
            saved_frame = pd.read_csv(saved_path)
            self.assertEqual(saved_frame.loc[0, "trade_id"], "t1")

    def test_save_opportunities_preserves_preferred_columns_and_suffix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = PersistenceService(opportunities_dir=temp_dir)

            saved_path = service.save_opportunities(
                [
                    {
                        "symbol": "ABC",
                        "stock_price": 120.0,
                        "short_strike": 115.0,
                        "long_strike": 110.0,
                        "premium": 1.3,
                        "ev_score_chosen": 0.9,
                    }
                ],
                market_open=False,
            )

            saved_file = Path(saved_path)
            self.assertTrue(saved_file.exists())
            self.assertIn("_indicative", saved_file.name)

            saved_frame = pd.read_csv(saved_file)
            self.assertEqual(
                list(saved_frame.columns[:6]),
                [
                    "symbol",
                    "stock_price",
                    "short_strike",
                    "long_strike",
                    "width",
                    "premium",
                ],
            )
            self.assertEqual(saved_frame.loc[0, "symbol"], "ABC")


if __name__ == "__main__":
    unittest.main()
