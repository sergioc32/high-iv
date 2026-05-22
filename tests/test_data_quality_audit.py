import unittest

from analysis.data_quality_audit import (
    EXPECTED_CANDIDATE_COLUMNS,
    audit_candidate_duplicates,
    audit_candidate_ranges,
    audit_candidate_schema,
)


class DataQualityAuditTests(unittest.TestCase):
    def test_schema_accepts_strategy_identity_columns(self) -> None:
        issues = audit_candidate_schema(EXPECTED_CANDIDATE_COLUMNS)
        self.assertEqual(issues, [])

    def test_call_candidate_long_strike_direction_is_valid(self) -> None:
        rows = [
            {
                "run_id": "run-1",
                "strategy_id": "call_credit_spread",
                "symbol": "SOXL",
                "expiration_date": "2026-06-19",
                "dte": "30",
                "stock_price": "20",
                "short_strike": "22",
                "long_strike": "24",
                "width": "2",
                "credit_mid": "40",
                "credit_natural": "30",
                "credit_expected": "35",
                "fill_quality": "0.875",
                "avg_width_pct": "0.15",
                "mid_weight": "0.75",
                "premium": "35",
                "premium_per_width": "0.175",
                "max_profit": "35",
                "max_loss": "165",
                "risk_reward_ratio": "4.7143",
                "ev_score": "0.18",
                "short_delta": "0.16",
                "short_iv": "0.35",
                "atm_iv": "0.30",
                "skew_ratio": "1.1667",
                "candidate_status": "selected",
                "selected": "True",
                "rejection_reason_primary": "",
            }
        ]

        issues = audit_candidate_ranges(rows)
        messages = [issue.message for issue in issues]
        self.assertFalse(
            any("long_strike must be" in message for message in messages),
            messages,
        )

    def test_credit_natural_too_low_row_can_have_negative_premium_without_warning(
        self,
    ) -> None:
        rows = [
            {
                "run_id": "run-1",
                "strategy_id": "put_credit_spread",
                "symbol": "TEAM",
                "expiration_date": "2026-06-19",
                "dte": "30",
                "stock_price": "100",
                "short_strike": "50",
                "long_strike": "45",
                "width": "5",
                "credit_mid": "10",
                "credit_natural": "-25",
                "credit_expected": "-25",
                "fill_quality": "-0.5",
                "avg_width_pct": "0.15",
                "mid_weight": "0.75",
                "premium": "-25",
                "premium_per_width": "-0.05",
                "max_profit": "-25",
                "max_loss": "525",
                "risk_reward_ratio": "",
                "ev_score": "-0.041135",
                "short_delta": "0.136172515",
                "short_iv": "0.30",
                "atm_iv": "0.28",
                "skew_ratio": "1.0714",
                "candidate_status": "rejected",
                "selected": "False",
                "rejection_reason_primary": "credit_natural_too_low",
            }
        ]

        issues = audit_candidate_ranges(rows)
        messages = [issue.message for issue in issues]
        self.assertFalse(
            any("ev_score should not be negative" in message for message in messages),
            messages,
        )
        self.assertFalse(
            any("premium_per_width is negative" in message for message in messages),
            messages,
        )
        self.assertFalse(
            any("fill_quality cannot be negative" in message for message in messages),
            messages,
        )

    def test_duplicate_check_is_strategy_aware(self) -> None:
        rows = [
            {
                "run_id": "run-1",
                "strategy_id": "put_credit_spread",
                "symbol": "SOXL",
                "expiration_date": "2026-06-19",
                "short_strike": "18",
                "long_strike": "16",
                "candidate_status": "selected",
            },
            {
                "run_id": "run-1",
                "strategy_id": "call_credit_spread",
                "symbol": "SOXL",
                "expiration_date": "2026-06-19",
                "short_strike": "18",
                "long_strike": "16",
                "candidate_status": "selected",
            },
        ]

        issues = audit_candidate_duplicates(rows)
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
