import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from services.snapshot_service import SnapshotService


class SnapshotServiceTests(unittest.TestCase):
    def test_create_weekly_snapshot_filters_records_to_requested_week(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot_dir = root / "snapshots"
            open_file = root / "trades_open.csv"
            closed_file = root / "trades_closed.csv"

            pd.DataFrame(
                [
                    {
                        "trade_id": "open-in",
                        "entry_date": "2026-04-07",
                        "symbol": "AAA",
                    },
                    {
                        "trade_id": "open-out",
                        "entry_date": "2026-04-14",
                        "symbol": "BBB",
                    },
                ]
            ).to_csv(open_file, index=False)
            pd.DataFrame(
                [
                    {
                        "trade_id": "closed-in",
                        "close_date": "2026-04-10",
                        "symbol": "CCC",
                    },
                    {
                        "trade_id": "closed-out",
                        "close_date": "2026-04-15",
                        "symbol": "DDD",
                    },
                ]
            ).to_csv(closed_file, index=False)

            service = SnapshotService(
                snapshot_dir=str(snapshot_dir),
                trades_open_file=str(open_file),
                trades_closed_file=str(closed_file),
            )

            created = service.create_weekly_snapshot(
                week_start=date(2026, 4, 6),
                week_end=date(2026, 4, 12),
            )

            self.assertTrue(created)
            snapshot_file = snapshot_dir / "snapshot_2026-04-06_2026-04-12.json"
            self.assertTrue(snapshot_file.exists())

            snapshot_data = json.loads(snapshot_file.read_text(encoding="utf-8"))
            self.assertEqual(snapshot_data["summary"]["total_open"], 1)
            self.assertEqual(snapshot_data["summary"]["total_closed"], 1)
            self.assertEqual(snapshot_data["summary"]["total_trades"], 2)
            self.assertEqual(snapshot_data["trades_open"][0]["trade_id"], "open-in")
            self.assertEqual(snapshot_data["trades_closed"][0]["trade_id"], "closed-in")
            self.assertIn("TARGET_DTE", snapshot_data["config"])

    def test_maybe_backfill_weekly_snapshots_creates_missing_completed_weeks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            snapshot_dir = root / "snapshots"
            open_file = root / "trades_open.csv"
            closed_file = root / "trades_closed.csv"

            pd.DataFrame(
                [
                    {
                        "trade_id": "week-one",
                        "entry_date": "2026-03-31",
                        "symbol": "AAA",
                    },
                    {
                        "trade_id": "week-two",
                        "entry_date": "2026-04-08",
                        "symbol": "BBB",
                    },
                ]
            ).to_csv(open_file, index=False)
            pd.DataFrame(columns=["trade_id", "close_date", "symbol"]).to_csv(
                closed_file,
                index=False,
            )

            service = SnapshotService(
                snapshot_dir=str(snapshot_dir),
                trades_open_file=str(open_file),
                trades_closed_file=str(closed_file),
            )

            created = service.maybe_backfill_weekly_snapshots(today=date(2026, 4, 16))

            self.assertEqual(created, 2)
            self.assertTrue(
                (snapshot_dir / "snapshot_2026-03-30_2026-04-05.json").exists()
            )
            self.assertTrue(
                (snapshot_dir / "snapshot_2026-04-06_2026-04-12.json").exists()
            )


if __name__ == "__main__":
    unittest.main()
