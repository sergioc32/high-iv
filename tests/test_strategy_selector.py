import unittest

import config
from services.strategy_selector import StrategySelector


class StrategySelectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.selector = StrategySelector()

    def test_build_market_context_combines_proxy_regimes(self) -> None:
        context = self.selector.build_market_context(
            {
                "SPY": {
                    "range_position_52w": 0.98,
                    "distance_to_52w_high_pct": 0.01,
                    "distance_to_52w_low_pct": 0.45,
                },
                "QQQ": {
                    "range_position_52w": 0.80,
                    "distance_to_52w_high_pct": 0.05,
                    "distance_to_52w_low_pct": 0.30,
                },
            }
        )

        self.assertEqual(context.market_regime_spy, "extended_bullish")
        self.assertEqual(context.market_regime_qqq, "bullish")
        self.assertEqual(context.market_regime_summary, "extended_bullish")
        self.assertEqual(context.selector_version, config.SELECTOR_VERSION)

    def test_annotate_opportunities_prefers_put_in_constructive_mid_range_context(
        self,
    ) -> None:
        opportunities = [
            {
                "symbol": "SOXL",
                "snapshot_ts": "2026-05-22T10:00:00",
                "expiration_date": "2026-07-03",
                "earnings_within_dte": "",
                "range_position_52w": 0.62,
                "distance_to_52w_high_pct": 0.08,
                "distance_to_52w_low_pct": 0.14,
            }
        ]
        context = self.selector.build_market_context(
            {
                "SPY": {
                    "range_position_52w": 0.80,
                    "distance_to_52w_high_pct": 0.05,
                    "distance_to_52w_low_pct": 0.30,
                },
                "QQQ": {
                    "range_position_52w": 0.78,
                    "distance_to_52w_high_pct": 0.07,
                    "distance_to_52w_low_pct": 0.28,
                },
            }
        )

        annotated = self.selector.annotate_opportunities(
            opportunities, market_context=context
        )

        self.assertEqual(len(annotated), 1)
        row = annotated[0]
        self.assertEqual(row["symbol_extension_bucket"], "mid_range")
        self.assertEqual(row["selector_preferred_strategy"], "put")
        self.assertGreater(row["put_selector_score"], row["call_selector_score"])
        self.assertEqual(row["put_selector_band"], "strong")

    def test_annotate_opportunities_returns_none_when_both_scores_are_weak(
        self,
    ) -> None:
        opportunities = [
            {
                "symbol": "WEAK",
                "snapshot_ts": "2026-05-22T10:00:00",
                "expiration_date": "2026-06-19",
                "earnings_within_dte": "",
                "range_position_52w": 0.10,
                "distance_to_52w_high_pct": 0.60,
                "distance_to_52w_low_pct": 0.02,
            }
        ]
        context = self.selector.build_market_context(
            {
                "SPY": {
                    "range_position_52w": 0.18,
                    "distance_to_52w_high_pct": 0.40,
                    "distance_to_52w_low_pct": 0.03,
                },
                "QQQ": {
                    "range_position_52w": 0.22,
                    "distance_to_52w_high_pct": 0.35,
                    "distance_to_52w_low_pct": 0.04,
                },
            }
        )

        annotated = self.selector.annotate_opportunities(
            opportunities, market_context=context
        )

        self.assertEqual(annotated[0]["selector_preferred_strategy"], "none")
        self.assertLess(
            annotated[0]["put_selector_score"], config.SELECTOR_VIABLE_FLOOR
        )
        self.assertLess(
            annotated[0]["call_selector_score"], config.SELECTOR_VIABLE_FLOOR
        )

    def test_earnings_stage_uses_late_cycle_penalty_when_earnings_is_near_expiration(
        self,
    ) -> None:
        opportunities = [
            {
                "symbol": "LATE",
                "snapshot_ts": "2026-05-22T10:00:00",
                "expiration_date": "2026-07-17",
                "earnings_within_dte": "2026-07-10",
                "range_position_52w": 0.80,
                "distance_to_52w_high_pct": 0.05,
                "distance_to_52w_low_pct": 0.25,
            }
        ]
        context = self.selector.build_market_context(
            {
                "SPY": {
                    "range_position_52w": 0.80,
                    "distance_to_52w_high_pct": 0.05,
                    "distance_to_52w_low_pct": 0.30,
                },
                "QQQ": {
                    "range_position_52w": 0.78,
                    "distance_to_52w_high_pct": 0.07,
                    "distance_to_52w_low_pct": 0.28,
                },
            }
        )

        annotated = self.selector.annotate_opportunities(
            opportunities, market_context=context
        )

        self.assertEqual(annotated[0]["selector_earnings_stage"], "late_cycle")
        self.assertEqual(
            annotated[0]["selector_earnings_penalty"],
            config.SELECTOR_EARNINGS_LATE_CYCLE_PENALTY,
        )


if __name__ == "__main__":
    unittest.main()
