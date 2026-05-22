import csv
import tempfile
import unittest
from pathlib import Path

from ml import fit_put_baseline_model as put_baseline


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class PutBaselineFitTests(unittest.TestCase):
    def test_run_put_baseline_fit_writes_reports_and_predictions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            dataset_path = root / "training_dataset.csv"
            reports_dir = root / "reports"
            rows = [
                {
                    "trade_id": "t1",
                    "symbol": "AAA",
                    "strategy_id": "put_credit_spread",
                    "time_split_group": "train",
                    "entry_date": "2026-01-01",
                    "close_date": "2026-01-08",
                    "dte": "30",
                    "width": "5",
                    "premium_per_width": "0.20",
                    "max_loss": "400",
                    "risk_reward_ratio": "4.0",
                    "short_delta": "-0.16",
                    "moneyness_pct": "0.10",
                    "distance_to_short_strike_pct": "0.10",
                    "width_pct_of_stock": "0.02",
                    "premium_pct_of_width": "0.20",
                    "delta_distance_from_target": "0.01",
                    "strategy_alignment_score": "72",
                    "realized_return_on_risk": "0.12",
                },
                {
                    "trade_id": "t2",
                    "symbol": "BBB",
                    "strategy_id": "put_credit_spread",
                    "time_split_group": "train",
                    "entry_date": "2026-01-02",
                    "close_date": "2026-01-10",
                    "dte": "28",
                    "width": "5",
                    "premium_per_width": "0.22",
                    "max_loss": "390",
                    "risk_reward_ratio": "3.7",
                    "short_delta": "-0.15",
                    "moneyness_pct": "0.11",
                    "distance_to_short_strike_pct": "0.11",
                    "width_pct_of_stock": "0.02",
                    "premium_pct_of_width": "0.22",
                    "delta_distance_from_target": "0.00",
                    "strategy_alignment_score": "76",
                    "realized_return_on_risk": "0.18",
                },
                {
                    "trade_id": "t3",
                    "symbol": "CCC",
                    "strategy_id": "put_credit_spread",
                    "time_split_group": "train",
                    "entry_date": "2026-01-03",
                    "close_date": "2026-01-11",
                    "dte": "26",
                    "width": "5",
                    "premium_per_width": "0.18",
                    "max_loss": "410",
                    "risk_reward_ratio": "4.5",
                    "short_delta": "-0.17",
                    "moneyness_pct": "0.09",
                    "distance_to_short_strike_pct": "0.09",
                    "width_pct_of_stock": "0.02",
                    "premium_pct_of_width": "0.18",
                    "delta_distance_from_target": "0.01",
                    "strategy_alignment_score": "68",
                    "realized_return_on_risk": "-0.05",
                },
                {
                    "trade_id": "t4",
                    "symbol": "DDD",
                    "strategy_id": "put_credit_spread",
                    "time_split_group": "validation",
                    "entry_date": "2026-01-04",
                    "close_date": "2026-01-12",
                    "dte": "29",
                    "width": "5",
                    "premium_per_width": "0.21",
                    "max_loss": "395",
                    "risk_reward_ratio": "3.9",
                    "short_delta": "-0.16",
                    "moneyness_pct": "0.10",
                    "distance_to_short_strike_pct": "0.10",
                    "width_pct_of_stock": "0.02",
                    "premium_pct_of_width": "0.21",
                    "delta_distance_from_target": "0.00",
                    "strategy_alignment_score": "74",
                    "realized_return_on_risk": "0.15",
                },
                {
                    "trade_id": "t5",
                    "symbol": "EEE",
                    "strategy_id": "put_credit_spread",
                    "time_split_group": "test",
                    "entry_date": "2026-01-05",
                    "close_date": "2026-01-13",
                    "dte": "27",
                    "width": "5",
                    "premium_per_width": "0.19",
                    "max_loss": "405",
                    "risk_reward_ratio": "4.1",
                    "short_delta": "-0.17",
                    "moneyness_pct": "0.09",
                    "distance_to_short_strike_pct": "0.09",
                    "width_pct_of_stock": "0.02",
                    "premium_pct_of_width": "0.19",
                    "delta_distance_from_target": "0.01",
                    "strategy_alignment_score": "70",
                    "realized_return_on_risk": "0.05",
                },
                {
                    "trade_id": "call_skip",
                    "symbol": "FFF",
                    "strategy_id": "call_credit_spread",
                    "time_split_group": "train",
                    "entry_date": "2026-01-06",
                    "close_date": "2026-01-14",
                    "dte": "25",
                    "width": "5",
                    "premium_per_width": "0.18",
                    "max_loss": "410",
                    "risk_reward_ratio": "4.5",
                    "short_delta": "0.16",
                    "moneyness_pct": "-0.09",
                    "distance_to_short_strike_pct": "-0.09",
                    "width_pct_of_stock": "0.02",
                    "premium_pct_of_width": "0.18",
                    "delta_distance_from_target": "0.01",
                    "strategy_alignment_score": "65",
                    "realized_return_on_risk": "0.02",
                },
            ]
            fieldnames = sorted({key for row in rows for key in row})
            write_csv(dataset_path, fieldnames, rows)

            outputs = put_baseline.run_put_baseline_fit(dataset_path, reports_dir)

            self.assertTrue(outputs["markdown_path"].exists())
            self.assertTrue(outputs["metrics_path"].exists())
            self.assertTrue(outputs["predictions_path"].exists())

            markdown = outputs["markdown_path"].read_text(encoding="utf-8")
            self.assertIn("Put Baseline Model Fit", markdown)
            self.assertIn("put_knn", markdown)

            with open(
                outputs["predictions_path"], newline="", encoding="utf-8"
            ) as handle:
                prediction_rows = list(csv.DictReader(handle))

            self.assertEqual(2, len(prediction_rows))
            self.assertEqual(
                {"validation", "test"},
                {row["time_split_group"] for row in prediction_rows},
            )
            self.assertTrue(
                all(
                    row["model_score_version"].startswith(
                        (
                            "put_knn_ror_v1_",
                            "put_linear_core_ror_v1_",
                            "put_linear_plus_alignment_ror_v1_",
                        )
                    )
                    for row in prediction_rows
                )
            )


if __name__ == "__main__":
    unittest.main()
