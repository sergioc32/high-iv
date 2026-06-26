import csv
import tempfile
import unittest
from pathlib import Path

import config
from screener.put_spread_analyzer import PutSpreadAnalyzer
from screener.spread_analyzer import SpreadAnalyzer


def build_valid_chain() -> dict:
    return {
        "symbol": "XYZ",
        "underlying_quote": {
            "sector": "Technology",
            "industry": "Semiconductors",
            "iv_rank": 85,
            "market_cap": 5_000_000_000,
            "year_high_price": 122.0,
            "year_low_price": 80.0,
        },
        "strikes": {
            100.0: {
                "put": {
                    "delta": -0.16,
                    "bid": 3.0,
                    "ask": 3.1,
                    "open_interest": 100,
                    "implied_volatility": 0.30,
                }
            },
            95.0: {
                "put": {
                    "delta": -0.10,
                    "bid": 2.0,
                    "ask": 2.1,
                    "open_interest": 100,
                    "implied_volatility": 0.28,
                }
            },
            90.0: {
                "put": {
                    "delta": -0.05,
                    "bid": 0.95,
                    "ask": 1.05,
                    "open_interest": 100,
                    "implied_volatility": 0.26,
                }
            },
        },
    }


class SpreadAnalyzerTests(unittest.TestCase):
    def make_analyzer(self, temp_dir: str) -> SpreadAnalyzer:
        analyzer = SpreadAnalyzer(run_id="test_run", snapshot_ts="2026-04-15T10:00:00")
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

    def test_analyzer_prefers_put_specific_config_values(self) -> None:
        original_values = {
            "PUT_TARGET_DELTA": config.PUT_TARGET_DELTA,
            "PUT_MIN_DELTA": config.PUT_MIN_DELTA,
            "PUT_MAX_DELTA": config.PUT_MAX_DELTA,
            "PUT_LONG_DELTA": config.PUT_LONG_DELTA,
            "TARGET_DELTA": config.TARGET_DELTA,
            "MIN_DELTA": config.MIN_DELTA,
            "MAX_DELTA": config.MAX_DELTA,
            "LONG_PUT_DELTA": config.LONG_PUT_DELTA,
        }
        try:
            config.PUT_TARGET_DELTA = 0.17
            config.PUT_MIN_DELTA = 0.14
            config.PUT_MAX_DELTA = 0.22
            config.PUT_LONG_DELTA = 0.11
            config.TARGET_DELTA = 0.01
            config.MIN_DELTA = 0.02
            config.MAX_DELTA = 0.03
            config.LONG_PUT_DELTA = 0.04

            analyzer = SpreadAnalyzer(
                run_id="test_run", snapshot_ts="2026-04-15T10:00:00"
            )

            self.assertEqual(analyzer.target_delta, 0.17)
            self.assertEqual(analyzer.min_delta, 0.14)
            self.assertEqual(analyzer.max_delta, 0.22)
            self.assertEqual(analyzer.long_delta, 0.11)
        finally:
            for name, value in original_values.items():
                setattr(config, name, value)

    def test_put_spread_analyzer_matches_legacy_spread_analyzer(self) -> None:
        legacy = SpreadAnalyzer(run_id="test_run", snapshot_ts="2026-04-15T10:00:00")
        put_specific = PutSpreadAnalyzer(
            run_id="test_run", snapshot_ts="2026-04-15T10:00:00"
        )

        self.assertEqual(type(legacy), PutSpreadAnalyzer)
        self.assertEqual(legacy.target_delta, put_specific.target_delta)
        self.assertEqual(legacy.min_delta, put_specific.min_delta)
        self.assertEqual(legacy.max_delta, put_specific.max_delta)
        self.assertEqual(legacy.long_delta, put_specific.long_delta)

    def test_anchor_retained_when_shift_improvement_is_too_small(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analyzer = self.make_analyzer(temp_dir)
            analyzer.min_score_improvement = 20.0

            result = analyzer.find_spread_strikes(
                build_valid_chain(),
                stock_price=120.0,
                expiration_info={
                    "expiration_date": "2026-05-15",
                    "days_to_expiration": 30,
                },
                debug_symbol="XYZ",
            )

            self.assertIsNotNone(result)
            self.assertEqual(result["short_strike"], 100.0)

    def test_shift_candidate_wins_when_improvement_clears_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analyzer = self.make_analyzer(temp_dir)
            analyzer.min_score_improvement = 10.0

            result = analyzer.find_spread_strikes(
                build_valid_chain(),
                stock_price=120.0,
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
                120.0,
                build_valid_chain(),
                {"expiration_date": "2026-05-15", "days_to_expiration": 30},
            )

            self.assertIsNotNone(opportunity)
            expected_keys = {
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
            self.assertEqual(opportunity["sector"], "Technology")
            self.assertEqual(opportunity["industry"], "Semiconductors")
            self.assertEqual(
                opportunity["risk_theme_tags"],
                "high_iv_rank_70_plus,small_cap,speculative_small_cap_high_iv",
            )
            self.assertEqual(
                opportunity["technical_theme_tags"],
                "near_52w_high,near_52w_high_extended",
            )
            self.assertEqual(
                opportunity["theme_tags"],
                "high_iv_rank_70_plus,small_cap,speculative_small_cap_high_iv,"
                "near_52w_high,near_52w_high_extended",
            )
            self.assertEqual(opportunity["theme_taxonomy_version"], "v1")

            with analyzer.candidate_logger.path.open(
                newline="", encoding="utf-8"
            ) as handle:
                candidate = list(csv.DictReader(handle))[-1]
            self.assertEqual(candidate["sector"], "Technology")
            self.assertEqual(candidate["industry"], "Semiconductors")
            self.assertEqual(
                candidate["risk_theme_tags"],
                "high_iv_rank_70_plus,small_cap,speculative_small_cap_high_iv",
            )
            self.assertEqual(
                candidate["technical_theme_tags"],
                "near_52w_high,near_52w_high_extended",
            )
            self.assertEqual(
                candidate["theme_tags"],
                "high_iv_rank_70_plus,small_cap,speculative_small_cap_high_iv,"
                "near_52w_high,near_52w_high_extended",
            )
            self.assertEqual(candidate["theme_taxonomy_version"], "v1")

    def test_invalid_candidate_logs_rejection_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analyzer = self.make_analyzer(temp_dir)
            chain = {
                "symbol": "XYZ",
                "strikes": {
                    100.0: {
                        "put": {
                            "delta": -0.16,
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
                stock_price=120.0,
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
            self.assertEqual(
                rows[0]["rejection_reason_primary"], "long_strike_unavailable"
            )

    def test_filter_opportunities_keeps_best_ev_and_drops_over_max_delta(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            analyzer = self.make_analyzer(temp_dir)
            analyzer.max_delta = 0.20

            filtered = analyzer.filter_opportunities(
                [
                    {"symbol": "A", "chosen_delta": 0.18, "ev_score_chosen": 0.30},
                    {"symbol": "B", "chosen_delta": 0.25, "ev_score_chosen": 0.90},
                    {"symbol": "C", "chosen_delta": 0.15, "ev_score_chosen": 0.40},
                ],
                max_results=2,
            )

            self.assertEqual([row["symbol"] for row in filtered], ["C", "A"])


if __name__ == "__main__":
    unittest.main()
