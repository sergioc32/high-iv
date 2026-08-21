import csv
import tempfile
import unittest
from pathlib import Path

from ml import build_training_dataset as training_builder
from ml import model_score_baseline_report as baseline_report


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class TrainingDatasetTests(unittest.TestCase):
    def test_build_training_dataset_filters_rows_and_computes_return_on_risk(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            executed_path = root / "executed_trade_dataset.csv"
            output_path = root / "training_dataset.csv"
            rows = [
                {
                    "trade_id": "put_ok",
                    "symbol": "AAA",
                    "entry_date": "2026-05-01",
                    "close_date": "2026-05-10",
                    "trade_status": "closed",
                    "match_status": "exact_match",
                    "reviewed_setup_found": "True",
                    "profit_loss": "50",
                    "max_loss": "250",
                    "actual_exit_found": "True",
                    "feature_provenance": "candidate_log_exact",
                    "option_side": "put",
                    "strategy_alignment_score": "78.2",
                },
                {
                    "trade_id": "call_ok",
                    "symbol": "BBB",
                    "entry_date": "2026-05-02",
                    "close_date": "2026-05-11",
                    "trade_status": "closed",
                    "match_status": "adjusted_match",
                    "reviewed_setup_found": "True",
                    "profit_loss": "-20",
                    "max_loss": "100",
                    "actual_exit_found": "False",
                    "feature_provenance": "candidate_log_adjusted",
                    "directional_bias": "bearish",
                    "selector_preferred_strategy": "call",
                },
                {
                    "trade_id": "trade_only_excluded",
                    "symbol": "CCC",
                    "entry_date": "2026-05-03",
                    "close_date": "2026-05-12",
                    "trade_status": "closed",
                    "match_status": "trade_only",
                    "reviewed_setup_found": "True",
                    "profit_loss": "15",
                    "max_loss": "120",
                },
                {
                    "trade_id": "not_reviewed_excluded",
                    "symbol": "DDD",
                    "entry_date": "2026-05-04",
                    "close_date": "2026-05-13",
                    "trade_status": "closed",
                    "match_status": "exact_match",
                    "reviewed_setup_found": "False",
                    "profit_loss": "30",
                    "max_loss": "110",
                },
                {
                    "trade_id": "open_excluded",
                    "symbol": "EEE",
                    "entry_date": "2026-05-05",
                    "close_date": "",
                    "trade_status": "open",
                    "match_status": "exact_match",
                    "reviewed_setup_found": "True",
                    "profit_loss": "",
                    "max_loss": "200",
                },
            ]
            headers = sorted({key for row in rows for key in row})
            write_csv(executed_path, headers, rows)

            training_builder.build_training_dataset(executed_path, output_path)

            with open(output_path, newline="", encoding="utf-8") as handle:
                built_rows = list(csv.DictReader(handle))

            self.assertEqual(2, len(built_rows))
            self.assertEqual(
                ["put_ok", "call_ok"], [row["trade_id"] for row in built_rows]
            )

            put_row = built_rows[0]
            call_row = built_rows[1]

            self.assertEqual("put_credit_spread", put_row["strategy_id"])
            self.assertEqual("0.200000", put_row["realized_return_on_risk"])
            self.assertEqual("1", put_row["win_flag"])
            self.assertEqual("train", put_row["time_split_group"])
            self.assertEqual("1", put_row["is_train"])

            self.assertEqual("call_credit_spread", call_row["strategy_id"])
            self.assertEqual("-0.200000", call_row["realized_return_on_risk"])
            self.assertEqual("0", call_row["win_flag"])
            self.assertEqual("test", call_row["time_split_group"])
            self.assertEqual("1", call_row["is_test"])
            self.assertEqual("0.64", call_row["sample_weight"])

    def test_strategy_inference_uses_strike_geometry_when_metadata_is_blank(self):
        put_row = {"short_strike": "95", "long_strike": "90"}
        call_row = {"short_strike": "225", "long_strike": "230"}
        unknown_row = {"short_strike": "", "long_strike": ""}

        self.assertEqual(
            "put_credit_spread", training_builder.canonical_strategy_id(put_row)
        )
        self.assertEqual("put", training_builder.canonical_option_side(put_row))
        self.assertEqual(
            "call_credit_spread", training_builder.canonical_strategy_id(call_row)
        )
        self.assertEqual("call", training_builder.canonical_option_side(call_row))
        self.assertEqual(
            "unknown_strategy", training_builder.canonical_strategy_id(unknown_row)
        )

    def test_render_baseline_report_includes_call_readiness_note_when_needed(
        self,
    ) -> None:
        rows = [
            {
                "strategy_id": "put_credit_spread",
                "selector_version": "",
                "realized_return_on_risk": "0.20",
                "annualized_return": "0.31",
                "days_held": "8",
                "win_flag": "1",
                "feature_provenance": "candidate_log_exact",
                "strategy_alignment_score": "78.0",
                "selector_preferred_strategy": "put",
            },
            {
                "strategy_id": "put_credit_spread",
                "selector_version": "v1",
                "realized_return_on_risk": "-0.10",
                "annualized_return": "-0.08",
                "days_held": "19",
                "win_flag": "0",
                "feature_provenance": "candidate_log_adjusted",
                "strategy_alignment_score": "63.0",
                "selector_preferred_strategy": "both",
            },
        ]

        markdown = baseline_report.render_markdown_report(
            Path("ml/training_dataset.csv"),
            rows,
        )
        csv_rows = baseline_report.build_csv_rows(rows)

        self.assertIn("No call-credit-spread rows are present", markdown)
        self.assertIn("## By Strategy", markdown)
        self.assertTrue(
            any(
                row[:3] == ["segmentation", "strategy_id", "put_credit_spread"]
                for row in csv_rows
            )
        )


if __name__ == "__main__":
    unittest.main()
