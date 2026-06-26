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
                        "run_id": "run-1",
                        "snapshot_ts": "2026-05-22T12:00:00",
                        "symbol": "ABC",
                        "stock_price": 120.0,
                        "stock_change_pct": 3.3,
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
                    "run_id",
                    "snapshot_ts",
                    "strategy_id",
                    "option_side",
                    "directional_bias",
                    "alignment_score_version",
                ],
            )
            self.assertEqual(saved_frame.loc[0, "run_id"], "run-1")
            self.assertEqual(saved_frame.loc[0, "snapshot_ts"], "2026-05-22T12:00:00")
            self.assertEqual(saved_frame.loc[0, "stock_change_pct"], 3.3)
            self.assertEqual(saved_frame.loc[0, "symbol"], "ABC")

    def test_save_review_queue_writes_blank_decision_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_dir = Path(temp_dir) / "review"
            service = PersistenceService(
                opportunities_dir=temp_dir,
                review_queue_dir=str(review_dir),
            )

            saved_path = service.save_review_queue(
                [
                    {
                        "run_id": "run-1",
                        "snapshot_ts": "2026-05-22T12:00:00",
                        "strategy_id": "put_credit_spread",
                        "symbol": "ABC",
                        "stock_price": 120.0,
                        "short_strike": 115.0,
                        "long_strike": 110.0,
                        "strategy_alignment_score": 78.2,
                    }
                ],
                market_open=True,
            )

            saved_file = Path(saved_path)
            self.assertTrue(saved_file.exists())
            self.assertEqual(saved_file.parent, review_dir)

            saved_frame = pd.read_csv(saved_file)
            self.assertIn("decision", saved_frame.columns)
            self.assertIn("decision_reason", saved_frame.columns)
            self.assertIn("decision_note", saved_frame.columns)
            self.assertEqual(saved_frame.loc[0, "run_id"], "run-1")


if __name__ == "__main__":
    unittest.main()
