import unittest

import config
from analysis.ranking_engine import (
    liquidity_score,
    rank_selected_candidates,
    rows_grouped_by_run_symbol_expiration,
    score_opportunities,
)


class RankingEngineTests(unittest.TestCase):
    def test_liquidity_grouping_is_strategy_aware(self) -> None:
        rows = [
            {
                "run_id": "run-1",
                "strategy_id": "put_credit_spread",
                "symbol": "SOXL",
                "expiration_date": "2026-06-19",
                "rejection_reason_primary": "short_bid_ask_width",
            },
            {
                "run_id": "run-1",
                "strategy_id": "call_credit_spread",
                "symbol": "SOXL",
                "expiration_date": "2026-06-19",
                "rejection_reason_primary": "",
            },
        ]

        grouped = rows_grouped_by_run_symbol_expiration(rows)
        score, group_size = liquidity_score(rows[1], grouped)

        self.assertEqual(group_size, 1)
        self.assertEqual(score, 1.0)

    def test_rank_selected_candidates_uses_strategy_specific_calibration_counts(
        self,
    ) -> None:
        rows = [
            {
                "run_id": "run-1",
                "snapshot_ts": "2026-05-14T10:00:00",
                "strategy_id": "put_credit_spread",
                "symbol": "AAA",
                "expiration_date": "2026-06-19",
                "dte": "30",
                "short_strike": "95",
                "long_strike": "90",
                "width": "5",
                "premium": "120",
                "premium_per_width": "0.24",
                "max_loss": "380",
                "risk_reward_ratio": "3.1667",
                "short_delta": "0.16",
                "skew_ratio": "1.1",
                "skew_diff": "0.03",
                "ev_score": "0.265",
                "range_position_52w": "0.35",
                "distance_to_52w_high_pct": "0.18",
                "distance_to_52w_low_pct": "0.05",
                "selected": "true",
                "candidate_status": "selected",
                "earnings_within_dte": "",
            },
            {
                "run_id": "run-1",
                "snapshot_ts": "2026-05-14T10:00:00",
                "strategy_id": "call_credit_spread",
                "symbol": "BBB",
                "expiration_date": "2026-06-19",
                "dte": "30",
                "short_strike": "110",
                "long_strike": "115",
                "width": "5",
                "premium": "105",
                "premium_per_width": "0.21",
                "max_loss": "395",
                "risk_reward_ratio": "3.7619",
                "short_delta": "0.16",
                "skew_ratio": "1.05",
                "skew_diff": "0.02",
                "ev_score": "0.223",
                "range_position_52w": "0.92",
                "distance_to_52w_high_pct": "0.01",
                "distance_to_52w_low_pct": "0.40",
                "selected": "true",
                "candidate_status": "selected",
                "earnings_within_dte": "",
            },
        ]

        ranked = rank_selected_candidates(rows, "run-1")

        self.assertEqual(len(ranked), 2)
        self.assertEqual({row["calibration_selected_count"] for row in ranked}, {1})
        self.assertEqual(
            {row["strategy_id"] for row in ranked},
            {"put_credit_spread", "call_credit_spread"},
        )
        self.assertEqual(
            {row["alignment_score_version"] for row in ranked},
            {config.ALIGNMENT_SCORE_VERSION},
        )

    def test_call_extension_component_rewards_near_52w_high(self) -> None:
        opportunities = [
            {
                "strategy_id": "call_credit_spread",
                "symbol": "HIGH",
                "short_delta": 0.16,
                "skew_ratio": 1.0,
                "skew_diff": 0.02,
                "ev_score_chosen": 0.20,
                "dte": 30,
                "snapshot_ts": "2026-05-14T10:00:00",
                "earnings_within_dte": "",
                "range_position_52w": 0.95,
                "distance_to_52w_high_pct": 0.01,
                "distance_to_52w_low_pct": 0.45,
            },
            {
                "strategy_id": "call_credit_spread",
                "symbol": "MID",
                "short_delta": 0.16,
                "skew_ratio": 1.0,
                "skew_diff": 0.02,
                "ev_score_chosen": 0.20,
                "dte": 30,
                "snapshot_ts": "2026-05-14T10:00:00",
                "earnings_within_dte": "",
                "range_position_52w": 0.45,
                "distance_to_52w_high_pct": 0.30,
                "distance_to_52w_low_pct": 0.20,
            },
        ]

        ranked = score_opportunities(opportunities)

        self.assertEqual(ranked[0]["symbol"], "HIGH")
        self.assertIn("near_52w_high", ranked[0]["alignment_flags"])

    def test_score_opportunities_adds_alignment_version_and_components(self) -> None:
        opportunities = [
            {
                "strategy_id": "put_credit_spread",
                "symbol": "SOXL",
                "short_delta": 0.16,
                "skew_ratio": 1.08,
                "skew_diff": 0.03,
                "ev_score_chosen": 0.22,
                "dte": 30,
                "snapshot_ts": "2026-05-22T10:00:00",
                "earnings_within_dte": "",
                "range_position_52w": 0.62,
                "distance_to_52w_high_pct": 0.08,
                "distance_to_52w_low_pct": 0.14,
            }
        ]

        ranked = score_opportunities(opportunities)

        self.assertEqual(len(ranked), 1)
        scored = ranked[0]
        self.assertEqual(
            scored["alignment_score_version"], config.ALIGNMENT_SCORE_VERSION
        )
        self.assertIn("delta_preference_component", scored)
        self.assertIn("skew_component", scored)
        self.assertIn("ev_component", scored)
        self.assertIn("liquidity_component", scored)
        self.assertIn("extension_component", scored)
        self.assertIn("directional_adjustment", scored)
        self.assertIn("earnings_adjustment", scored)
        self.assertIn("alignment_flags", scored)
        self.assertIn("delta_zone", scored)
        self.assertIn("explanation_summary", scored)
        self.assertEqual(scored["total_rank_score"], scored["strategy_alignment_score"])


if __name__ == "__main__":
    unittest.main()
