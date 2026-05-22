import unittest

from analysis import trade_outcome_review, weekly_report


class SelectorReportingTests(unittest.TestCase):
    def test_weekly_report_selector_alignment_group(self):
        self.assertEqual(
            weekly_report.selector_alignment_group(
                {
                    "selector_preferred_strategy": "put",
                    "strategy_id": "put_credit_spread",
                }
            ),
            "preferred_match",
        )
        self.assertEqual(
            weekly_report.selector_alignment_group(
                {
                    "selector_preferred_strategy": "call",
                    "strategy_id": "put_credit_spread",
                }
            ),
            "preferred_mismatch",
        )
        self.assertEqual(
            weekly_report.selector_alignment_group(
                {
                    "selector_preferred_strategy": "both",
                    "strategy_id": "call_credit_spread",
                }
            ),
            "both",
        )

    def test_weekly_report_build_field_coverage_rows(self):
        rows = [
            {
                "selector_version": "v1",
                "call_selector_score": "72",
                "always_review_symbol": "True",
                "always_review_forced_into_analysis": "False",
                "always_review_source": "configured_always_review",
            },
            {"selector_version": "", "call_selector_score": ""},
        ]
        coverage = weekly_report.build_field_coverage_rows(
            rows,
            cohort_name="selected_rows",
        )
        by_feature = {row["feature"]: row for row in coverage}
        self.assertEqual(by_feature["Selector Version"]["populated"], "1")
        self.assertEqual(by_feature["Selector Version"]["share"], "50.0%")
        self.assertEqual(by_feature["Call Selector Score"]["populated"], "1")
        self.assertEqual(by_feature["Always Review Symbol"]["populated"], "1")
        self.assertEqual(
            by_feature["Always Review Forced Into Analysis"]["populated"],
            "1",
        )
        self.assertEqual(by_feature["Always Review Source"]["populated"], "1")

    def test_trade_outcome_metrics_include_selector_dimensions(self):
        closed_rows = [
            {
                "trade_status": "closed",
                "profit_loss": "55.0",
                "match_status": "exact_match",
                "actual_exit_found": "True",
                "exit_price_source": "actual_fill",
                "strategy_version": "v2_dynamic",
                "alignment_score_version": "v1",
                "selector_version": "v1",
                "selector_preferred_strategy": "call",
                "selector_confidence": "medium",
                "market_regime_summary": "bullish",
                "symbol_extension_bucket": "upper_range",
                "strategy_id": "call_credit_spread",
                "short_delta": "0.16",
                "dte": "28",
                "fill_quality_score": "0.82",
                "put_selector_score": "58",
                "call_selector_score": "72",
                "range_position_52w": "0.89",
                "distance_to_52w_high_pct": "0.04",
                "fill_edge": "0.03",
                "mid_capture_pct": "0.65",
                "anchor_vs_shift_status": "anchor",
                "shift_steps_from_anchor": "0",
                "always_review_symbol": "True",
                "always_review_forced_into_analysis": "True",
                "always_review_source": "configured_always_review",
            }
        ]

        metric_rows = trade_outcome_review.build_metrics_rows(closed_rows, top_n=10)
        metric_keys = {(row[1], row[2], row[3]) for row in metric_rows}

        self.assertIn(
            ("selector_preferred_strategy", "call", "trade_count"),
            metric_keys,
        )
        self.assertIn(
            ("selector_alignment", "preferred_match", "trade_count"),
            metric_keys,
        )
        self.assertIn(
            ("alignment_score_version", "v1", "trade_count"),
            metric_keys,
        )
        self.assertIn(
            ("Selector Version", "closed_trades", "populated"),
            metric_keys,
        )
        self.assertIn(
            ("always_review_symbol", "true", "trade_count"),
            metric_keys,
        )
        self.assertIn(
            ("always_review_forced_into_analysis", "true", "trade_count"),
            metric_keys,
        )
        self.assertIn(
            ("always_review_source", "configured_always_review", "trade_count"),
            metric_keys,
        )
        self.assertIn(
            ("Always Review Symbol", "closed_trades", "populated"),
            metric_keys,
        )


if __name__ == "__main__":
    unittest.main()
