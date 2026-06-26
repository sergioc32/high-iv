import unittest
from collections import Counter

from analysis import trade_outcome_review, weekly_report
from analysis.exposure_summary import build_concentration_rows


class SelectorReportingTests(unittest.TestCase):
    def test_build_concentration_rows_splits_theme_tags(self):
        rows = [
            {
                "sector": "Technology",
                "industry": "Semiconductors",
                "risk_theme_tags": "high_iv_rank_70_plus,earnings_exposure",
                "technical_theme_tags": "near_52w_high",
                "theme_tags": "high_iv_rank_70_plus,earnings_exposure,near_52w_high",
                "buying_power_used": "1200",
            },
            {
                "sector": "Healthcare",
                "industry": "Biotech",
                "risk_theme_tags": "high_iv_rank_70_plus",
                "technical_theme_tags": "",
                "theme_tags": "high_iv_rank_70_plus",
                "max_loss": "800",
            },
        ]

        concentration = build_concentration_rows(rows, top_n=10)
        by_dimension_group = {
            (row["dimension"], row["group"]): row for row in concentration
        }

        self.assertEqual(
            by_dimension_group[("sector", "Technology")]["trade_share"],
            "50.0%",
        )
        self.assertEqual(
            by_dimension_group[("risk_theme_tags", "high_iv_rank_70_plus")][
                "trade_share"
            ],
            "100.0%",
        )
        self.assertEqual(
            by_dimension_group[("risk_theme_tags", "high_iv_rank_70_plus")][
                "risk_amount"
            ],
            "2000.00",
        )
        self.assertEqual(
            by_dimension_group[("technical_theme_tags", "near_52w_high")][
                "trade_share"
            ],
            "50.0%",
        )

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
                "review_decision": "accepted",
                "review_decision_reason": "",
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
        self.assertEqual(by_feature["Review Decision"]["populated"], "1")

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
                "review_decision": "accepted",
                "review_decision_reason": "manual_risk_override",
                "sector": "Technology",
                "industry": "Semiconductors",
                "risk_theme_tags": "high_iv_rank_70_plus,earnings_exposure",
                "technical_theme_tags": "near_52w_high",
                "theme_tags": "high_iv_rank_70_plus,earnings_exposure,near_52w_high",
                "max_loss": "1000",
            }
        ]

        open_rows = [
            {
                "sector": "Technology",
                "industry": "Semiconductors",
                "risk_theme_tags": "high_iv_rank_70_plus",
                "technical_theme_tags": "near_52w_high",
                "theme_tags": "high_iv_rank_70_plus,near_52w_high",
                "buying_power_used": "750",
            }
        ]

        metric_rows = trade_outcome_review.build_metrics_rows(
            closed_rows,
            top_n=10,
            open_rows=open_rows,
        )
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
        self.assertIn(
            ("review_decision", "accepted", "trade_count"),
            metric_keys,
        )
        self.assertIn(
            ("review_decision_reason", "manual_risk_override", "trade_count"),
            metric_keys,
        )
        self.assertIn(
            ("Review Decision", "closed_trades", "populated"),
            metric_keys,
        )
        self.assertIn(
            ("open|sector", "Technology", "trade_share"),
            metric_keys,
        )
        self.assertIn(
            ("closed|risk_theme_tags", "earnings_exposure", "trade_share"),
            metric_keys,
        )
        self.assertIn(
            ("open|risk_theme_tags", "high_iv_rank_70_plus", "risk_amount"),
            metric_keys,
        )

    def test_weekly_metrics_export_includes_exposure_concentration(self):
        metric_rows = weekly_report.build_metrics_export_rows(
            overall=weekly_report.MetricSummary(
                trade_count=0,
                win_rate=0.0,
                avg_pnl=0.0,
                median_pnl=0.0,
                total_pnl=0.0,
                max_drawdown_proxy=0.0,
            ),
            selected_rows_count=0,
            selected_selector_coverage_rows=[],
            closed_selector_coverage_rows=[],
            selected_selector_state_counts=Counter(),
            selected_always_review_symbol_counts=Counter(),
            selected_always_review_forced_counts=Counter(),
            selected_always_review_source_counts=Counter(),
            selected_review_decision_counts=Counter(),
            selected_review_reason_counts=Counter(),
            closed_selector_alignment_rows=[],
            exposure_concentration_rows={
                "open": [
                    {
                        "dimension": "risk_theme_tags",
                        "label": "Risk Theme",
                        "group": "high_iv_rank_70_plus",
                        "trade_count": "2",
                        "trade_share": "66.7%",
                        "risk_amount": "1500.00",
                    }
                ],
                "closed": [],
            },
            rolling_window_metrics=[],
            rolling_rejection_trends=[],
            rolling_rejection_reason_trends=[],
            ranking_backtest_results=[],
            sensitivity_analysis_results=[],
            candidate_ranking_impact_results=[],
            segment_rows={},
            trend_rows=[],
            reason_summary_rows=[],
            bucket_summary_rows=[],
            recommendation_lines=[],
            recommendation_impact_rows=[],
            closed_records=[],
            close_reconciliation_summary={"status_rows": [], "source_rows": []},
        )
        metric_keys = {(row[1], row[2], row[3]) for row in metric_rows}

        self.assertIn(
            ("open|risk_theme_tags", "high_iv_rank_70_plus", "trade_share"),
            metric_keys,
        )
        self.assertIn(
            ("open|risk_theme_tags", "high_iv_rank_70_plus", "risk_amount"),
            metric_keys,
        )


if __name__ == "__main__":
    unittest.main()
