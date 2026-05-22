import csv
import tempfile
import unittest
from pathlib import Path

import config
from screener.call_spread_analyzer import CallSpreadAnalyzer


def build_valid_call_chain() -> dict:
    return {
        "symbol": "XYZ",
        "strikes": {
            90.0: {
                "call": {
                    "delta": 0.16,
                    "bid": 3.0,
                    "ask": 3.1,
                    "open_interest": 100,
                    "implied_volatility": 0.30,
                }
            },
            95.0: {
                "call": {
                    "delta": 0.10,
                    "bid": 2.0,
                    "ask": 2.1,
                    "open_interest": 100,
                    "implied_volatility": 0.28,
                }
            },
            100.0: {
                "call": {
                    "delta": 0.05,
                    "bid": 0.95,
                    "ask": 1.05,
                    "open_interest": 100,
                    "implied_volatility": 0.26,
                }
            },
        },
    }


class CallSpreadAnalyzerTests(unittest.TestCase):
    def make_analyzer(self, temp_dir: str) -> CallSpreadAnalyzer:
        analyzer = CallSpreadAnalyzer(
            run_id="test_run", snapshot_ts="2026-04-15T10:00:00"
        )
        analyzer.candidate_logger.path = Path(temp_dir) / "opportunity_candidates.csv"
        analyzer.rejection_logger.path = Path(temp_dir) / "rejections_tracking.csv"
        analyzer.enable_oi_filter = False
        analyzer.preferred_width = 5
        analyzer.fallback_width = 5
        analyzer.max_strike_increment = 5
        analyzer.max_risk_reward = 10.0
        analyzer.min_credit_per_width = 0.0
        analyzer.max_delta = 0.30
        analyzer.target_delta = 0.16
        analyzer.skew_window_otm = 1
        analyzer.skew_window_itm = 0
        analyzer.credit_width_pct_tight = 0.10
        analyzer.credit_width_pct_ok = 0.20
        analyzer.credit_width_pct_wide = 0.35
        analyzer.credit_mid_weight_tight = 0.85
        analyzer.credit_mid_weight_ok = 0.75
        analyzer.credit_mid_weight_moderate = 0.65
        analyzer.credit_mid_weight_very_wide = 0.55
        return analyzer

    def test_analyzer_prefers_call_specific_config_values(self) -> None:
        original_values = {
            "CALL_TARGET_DELTA": config.CALL_TARGET_DELTA,
            "CALL_MIN_DELTA": config.CALL_MIN_DELTA,
            "CALL_MAX_DELTA": config.CALL_MAX_DELTA,
            "LONG_CALL_DELTA": config.LONG_CALL_DELTA,
            "CALL_MAX_RISK_REWARD_RATIO": config.CALL_MAX_RISK_REWARD_RATIO,
            "CALL_MIN_CREDIT_PER_WIDTH": config.CALL_MIN_CREDIT_PER_WIDTH,
            "CALL_MIN_NATURAL_CREDIT_PCT": config.CALL_MIN_NATURAL_CREDIT_PCT,
        }
        try:
            config.CALL_TARGET_DELTA = 0.17
            config.CALL_MIN_DELTA = 0.14
            config.CALL_MAX_DELTA = 0.22
            config.LONG_CALL_DELTA = 0.09
            config.CALL_MAX_RISK_REWARD_RATIO = 5.5
            config.CALL_MIN_CREDIT_PER_WIDTH = 0.06
            config.CALL_MIN_NATURAL_CREDIT_PCT = 0.07

            analyzer = CallSpreadAnalyzer(
                run_id="test_run", snapshot_ts="2026-04-15T10:00:00"
            )

            self.assertEqual(analyzer.target_delta, 0.17)
            self.assertEqual(analyzer.min_delta, 0.14)
            self.assertEqual(analyzer.max_delta, 0.22)
            self.assertEqual(analyzer.long_delta, 0.09)
            self.assertEqual(analyzer.max_risk_reward, 5.5)
            self.assertEqual(analyzer.min_credit_per_width, 0.06)
            self.assertEqual(analyzer.min_natural_credit_pct, 0.07)
        finally:
            for name, value in original_values.items():
                setattr(config, name, value)

    def test_anchor_retained_when_shift_improvement_is_too_small(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analyzer = self.make_analyzer(temp_dir)
            analyzer.min_score_improvement = 20.0

            result = analyzer.find_spread_strikes(
                build_valid_call_chain(),
                stock_price=80.0,
                expiration_info={
                    "expiration_date": "2026-05-15",
                    "days_to_expiration": 30,
                },
                debug_symbol="XYZ",
            )

            self.assertIsNotNone(result)
            self.assertEqual(result["short_strike"], 90.0)

    def test_shift_candidate_wins_when_improvement_clears_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analyzer = self.make_analyzer(temp_dir)
            analyzer.min_score_improvement = 10.0

            result = analyzer.find_spread_strikes(
                build_valid_call_chain(),
                stock_price=80.0,
                expiration_info={
                    "expiration_date": "2026-05-15",
                    "days_to_expiration": 30,
                },
                debug_symbol="XYZ",
            )

            self.assertIsNotNone(result)
            self.assertEqual(result["short_strike"], 95.0)

    def test_evaluate_spread_returns_expected_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analyzer = self.make_analyzer(temp_dir)
            analyzer.min_score_improvement = 10.0

            opportunity = analyzer.evaluate_spread(
                "XYZ",
                80.0,
                build_valid_call_chain(),
                {"expiration_date": "2026-05-15", "days_to_expiration": 30},
            )

            self.assertIsNotNone(opportunity)
            expected_keys = {
                "strategy_id",
                "option_side",
                "directional_bias",
                "symbol",
                "stock_price",
                "expiration_date",
                "dte",
                "anchor_strike",
                "chosen_strike",
                "skew_steps_from_anchor",
                "anchor_delta",
                "chosen_delta",
                "ratio_anchor",
                "ratio_chosen",
                "ev_score_anchor",
                "ev_score_chosen",
                "earnings_within_dte",
                "premium",
                "max_loss",
                "max_profit",
                "risk_reward_ratio",
                "short_strike",
                "long_strike",
                "width",
                "short_delta",
                "short_bid",
                "short_ask",
                "long_bid",
                "long_ask",
                "credit_mid",
                "credit_natural",
                "credit_expected",
                "fill_quality",
                "avg_width_pct",
                "mid_weight",
                "short_iv",
                "atm_iv",
                "skew_ratio",
                "skew_diff",
            }
            self.assertTrue(expected_keys.issubset(opportunity.keys()))
            self.assertEqual(opportunity["strategy_id"], "call_credit_spread")
            self.assertEqual(opportunity["option_side"], "call")

    def test_invalid_candidate_logs_rejection_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analyzer = self.make_analyzer(temp_dir)
            chain = {
                "symbol": "XYZ",
                "strikes": {
                    90.0: {
                        "call": {
                            "delta": 0.16,
                            "bid": 3.0,
                            "ask": 3.1,
                            "open_interest": 100,
                            "implied_volatility": 0.30,
                        }
                    },
                    95.0: {},
                },
            }

            result = analyzer.find_spread_strikes(
                chain,
                stock_price=80.0,
                expiration_info={
                    "expiration_date": "2026-05-15",
                    "days_to_expiration": 30,
                },
                debug_symbol="XYZ",
            )

            self.assertIsNone(result)
            with analyzer.candidate_logger.path.open(
                newline="", encoding="utf-8"
            ) as handle:
                rows = list(csv.DictReader(handle))
            rejection_reasons = {row["rejection_reason_primary"] for row in rows}
            self.assertIn("long_leg_missing_quote", rejection_reasons)

    def test_no_valid_width_logs_no_long_strike(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analyzer = self.make_analyzer(temp_dir)
            analyzer.preferred_width = 7
            analyzer.fallback_width = 7
            analyzer.max_strike_increment = 7

            result = analyzer.find_spread_strikes(
                build_valid_call_chain(),
                stock_price=80.0,
                expiration_info={
                    "expiration_date": "2026-05-15",
                    "days_to_expiration": 30,
                },
                debug_symbol="XYZ",
            )

            self.assertIsNone(result)
            with analyzer.candidate_logger.path.open(
                newline="", encoding="utf-8"
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["rejection_reason_primary"], "no_long_strike")

    def test_delta_above_max_is_logged_as_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analyzer = self.make_analyzer(temp_dir)
            analyzer.max_delta = 0.09

            result = analyzer.find_spread_strikes(
                build_valid_call_chain(),
                stock_price=80.0,
                expiration_info={
                    "expiration_date": "2026-05-15",
                    "days_to_expiration": 30,
                },
                debug_symbol="XYZ",
            )

            self.assertIsNone(result)
            with analyzer.candidate_logger.path.open(
                newline="", encoding="utf-8"
            ) as handle:
                rows = list(csv.DictReader(handle))
            rejection_reasons = {row["rejection_reason_primary"] for row in rows}
            self.assertIn("delta_bounds_max", rejection_reasons)

    def test_wide_long_market_is_logged_as_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analyzer = self.make_analyzer(temp_dir)
            chain = build_valid_call_chain()
            chain["strikes"][95.0]["call"]["bid"] = 0.1
            chain["strikes"][95.0]["call"]["ask"] = 4.5

            result = analyzer.find_spread_strikes(
                chain,
                stock_price=80.0,
                expiration_info={
                    "expiration_date": "2026-05-15",
                    "days_to_expiration": 30,
                },
                debug_symbol="XYZ",
            )

            self.assertIsNone(result)
            with analyzer.candidate_logger.path.open(
                newline="", encoding="utf-8"
            ) as handle:
                rows = list(csv.DictReader(handle))
            rejection_reasons = {row["rejection_reason_primary"] for row in rows}
            self.assertIn("long_bid_ask_width", rejection_reasons)


if __name__ == "__main__":
    unittest.main()
