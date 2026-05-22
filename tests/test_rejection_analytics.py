import csv
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import config
from analysis.build_rejected_candidate_dataset import build_rejected_candidate_dataset
from analysis.rejection_diagnostics import (
    is_rejection_counter_column,
    summarize_candidate_level,
    summarize_symbol_level,
)


class RejectionAnalyticsTests(unittest.TestCase):
    def test_rejected_candidate_dataset_groups_by_strategy_and_uses_strategy_target(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidates_path = Path(temp_dir) / "opportunity_candidates.csv"
            output_path = Path(temp_dir) / "rejected_candidate_dataset.csv"
            with candidates_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "run_id",
                        "strategy_id",
                        "symbol",
                        "expiration_date",
                        "candidate_status",
                        "selected",
                        "rejection_reason_primary",
                        "rejection_reason_flags",
                        "stock_price",
                        "short_strike",
                        "width",
                        "premium",
                        "short_delta",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "run_id": "run-1",
                        "strategy_id": "put_credit_spread",
                        "symbol": "SOXL",
                        "expiration_date": "2026-06-19",
                        "candidate_status": "selected",
                        "selected": "True",
                        "rejection_reason_primary": "",
                        "rejection_reason_flags": "",
                        "stock_price": "20",
                        "short_strike": "18",
                        "width": "2",
                        "premium": "45",
                        "short_delta": str(config.PUT_TARGET_DELTA),
                    }
                )
                writer.writerow(
                    {
                        "run_id": "run-1",
                        "strategy_id": "call_credit_spread",
                        "symbol": "SOXL",
                        "expiration_date": "2026-06-19",
                        "candidate_status": "rejected",
                        "selected": "False",
                        "rejection_reason_primary": "short_bid_ask_width",
                        "rejection_reason_flags": "short_bid_ask_width",
                        "stock_price": "20",
                        "short_strike": "22",
                        "width": "2",
                        "premium": "30",
                        "short_delta": str(config.CALL_TARGET_DELTA + 0.02),
                    }
                )

            build_rejected_candidate_dataset(
                candidates_path=candidates_path, output_path=output_path
            )

            with output_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["strategy_id"], "call_credit_spread")
            self.assertEqual(row["same_group_candidate_count"], "1")
            self.assertEqual(row["sibling_selected_exists"], "False")
            self.assertEqual(row["delta_distance_from_target"], "0.02")
            self.assertEqual(row["moneyness_pct"], "0.1")

    def test_symbol_rejection_summary_ignores_strategy_metadata_fields(self) -> None:
        header = [
            "timestamp",
            "run_id",
            "snapshot_ts",
            "strategy_id",
            "strategy_family",
            "option_side",
            "directional_bias",
            "short_leg_type",
            "long_leg_type",
            "symbol",
            "strategy_version",
            "short_bid_ask_width",
            "total_rejections",
        ]
        rows = [
            {
                "timestamp": "2026-05-14T10:00:00",
                "run_id": "run-1",
                "snapshot_ts": "2026-05-14T10:00:00",
                "strategy_id": "call_credit_spread",
                "strategy_family": "credit_spread",
                "option_side": "call",
                "directional_bias": "bearish",
                "short_leg_type": "short_call",
                "long_leg_type": "long_call",
                "symbol": "SOXL",
                "strategy_version": "v1",
                "short_bid_ask_width": "3",
                "total_rejections": "3",
            }
        ]

        summary = summarize_symbol_level(header, rows, top_n=5)

        self.assertEqual(summary["reason_totals"], Counter({"short_bid_ask_width": 3}))
        self.assertTrue(is_rejection_counter_column("short_bid_ask_width"))
        self.assertFalse(is_rejection_counter_column("strategy_id"))
        self.assertFalse(is_rejection_counter_column("run_id"))

    def test_candidate_rejection_summary_tracks_strategy_breakdown(self) -> None:
        rows = [
            {
                "strategy_id": "put_credit_spread",
                "symbol": "AAA",
                "candidate_status": "rejected",
                "rejection_reason_primary": "risk_reward",
            },
            {
                "strategy_id": "call_credit_spread",
                "symbol": "AAA",
                "candidate_status": "rejected",
                "rejection_reason_primary": "short_bid_ask_width",
            },
            {
                "strategy_id": "call_credit_spread",
                "symbol": "BBB",
                "candidate_status": "rejected",
                "rejection_reason_primary": "short_bid_ask_width",
            },
        ]

        summary = summarize_candidate_level(rows, top_n=5)

        self.assertEqual(summary["reason_totals"]["short_bid_ask_width"], 2)
        self.assertEqual(
            summary["strategy_reason_totals"]["call_credit_spread"][
                "short_bid_ask_width"
            ],
            2,
        )
        self.assertEqual(
            summary["strategy_reason_totals"]["put_credit_spread"]["risk_reward"], 1
        )


if __name__ == "__main__":
    unittest.main()
