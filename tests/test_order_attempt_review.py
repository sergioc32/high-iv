import tempfile
import unittest
from pathlib import Path

from analysis import order_attempt_review


class OrderAttemptReviewTests(unittest.TestCase):
    def test_build_metrics_rows_summarizes_filled_and_expired_attempts(self):
        rows = [
            {
                "attempt_outcome": "filled",
                "strategy_id": "put_credit_spread",
                "underlying_symbol": "AMD",
                "limit_price": "0.47",
            },
            {
                "attempt_outcome": "expired_unfilled",
                "strategy_id": "call_credit_spread",
                "underlying_symbol": "SPY",
                "limit_price": "0.61",
            },
        ]

        metrics = order_attempt_review.build_metrics_rows(rows, top_n=10)

        self.assertIn(
            ["overview", "all", "all", "attempt_count", "2.0"],
            metrics,
        )
        self.assertIn(
            ["overview", "all", "all", "filled_count", "1.0"],
            metrics,
        )
        self.assertIn(
            ["overview", "all", "all", "expired_count", "1.0"],
            metrics,
        )
        self.assertTrue(
            any(
                row[:4]
                == [
                    "group_summary",
                    "strategy_id",
                    "call_credit_spread",
                    "expired_count",
                ]
                and row[4] == "1"
                for row in metrics
            )
        )

    def test_main_writes_markdown_and_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            attempts_path = root / "order_attempts.csv"
            attempts_path.write_text(
                "\n".join(
                    [
                        "attempt_outcome,strategy_id,underlying_symbol,short_strike,long_strike,limit_price,received_at,order_id",
                        "expired_unfilled,call_credit_spread,SPY,771,774,0.61,2026-07-27T15:14:07+00:00,1",
                    ]
                ),
                encoding="utf-8",
            )
            reports_dir = root / "reports"
            _, rows = order_attempt_review.load_csv_rows(attempts_path)

            markdown = order_attempt_review.build_markdown_report(
                rows=rows,
                dataset_path=attempts_path,
                markdown_output_path=reports_dir / "order_attempt_review.md",
                csv_output_path=reports_dir / "order_attempt_review.csv",
                top_n=10,
            )

            self.assertIn("Order Attempt Review", markdown)
            self.assertIn("expired_unfilled", markdown)
            self.assertIn("not analyzer-rejected candidates", markdown)


if __name__ == "__main__":
    unittest.main()
