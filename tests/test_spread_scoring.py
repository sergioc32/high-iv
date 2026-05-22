import unittest

from screener.chain_access import (
    compute_option_skew_metrics,
    find_strike_by_delta,
    get_call_by_strike,
)
from screener.spread_scoring import (
    abs_delta,
    calculate_credit_components,
    normalize_iv,
    to_float,
)


class SpreadScoringTests(unittest.TestCase):
    def test_numeric_coercion_and_iv_normalization(self) -> None:
        self.assertIsNone(to_float(None))
        self.assertIsNone(to_float("abc"))
        self.assertEqual(to_float("1.25"), 1.25)
        self.assertEqual(abs_delta("-0.16"), 0.16)
        self.assertEqual(normalize_iv("25"), 0.25)
        self.assertEqual(normalize_iv(0.42), 0.42)
        self.assertIsNone(normalize_iv("bad"))

    def test_credit_components_shift_toward_natural_in_wider_markets(self) -> None:
        tight = calculate_credit_components(
            2.0,
            2.1,
            1.0,
            1.1,
            credit_width_pct_tight=0.10,
            credit_width_pct_ok=0.20,
            credit_width_pct_wide=0.35,
            credit_mid_weight_tight=0.85,
            credit_mid_weight_ok=0.75,
            credit_mid_weight_moderate=0.65,
            credit_mid_weight_very_wide=0.55,
        )
        wide = calculate_credit_components(
            2.0,
            3.0,
            1.0,
            2.0,
            credit_width_pct_tight=0.10,
            credit_width_pct_ok=0.20,
            credit_width_pct_wide=0.35,
            credit_mid_weight_tight=0.85,
            credit_mid_weight_ok=0.75,
            credit_mid_weight_moderate=0.65,
            credit_mid_weight_very_wide=0.55,
        )

        self.assertGreater(tight.mid_weight, wide.mid_weight)
        self.assertGreaterEqual(tight.credit_expected, tight.credit_natural)
        self.assertLessEqual(tight.credit_expected, tight.credit_mid)
        self.assertGreaterEqual(wide.credit_expected, wide.credit_natural)
        self.assertLessEqual(wide.credit_expected, wide.credit_mid)

    def test_generic_option_helpers_support_call_side(self) -> None:
        chain = {
            "strikes": {
                90.0: {
                    "call": {
                        "delta": 0.16,
                        "implied_volatility": 0.30,
                    }
                },
                95.0: {
                    "call": {
                        "delta": 0.50,
                        "implied_volatility": 0.28,
                    }
                },
            }
        }

        call_data = get_call_by_strike(chain, 90.0)
        self.assertEqual(call_data.get("delta"), 0.16)

        strike = find_strike_by_delta(chain, 0.16, option_type="call", tolerance=0.05)
        self.assertEqual(strike, 90.0)

        skew_metrics = compute_option_skew_metrics(
            chain, 92.0, 90.0, option_type="call"
        )
        self.assertEqual(skew_metrics["short_iv"], 0.3)
        self.assertEqual(skew_metrics["atm_iv"], 0.28)
        self.assertGreater(skew_metrics["skew_ratio"], 1.0)

    def test_option_lookup_matches_exact_numeric_strike_across_key_types(self) -> None:
        chain = {
            "strikes": {
                "90.0": {
                    "call": {
                        "delta": 0.16,
                        "implied_volatility": 0.30,
                    }
                }
            }
        }

        call_data = get_call_by_strike(chain, 90.0)
        self.assertEqual(call_data.get("delta"), 0.16)

    def test_option_lookup_does_not_fall_back_to_nearest_strike(self) -> None:
        chain = {
            "strikes": {
                90.0: {
                    "call": {
                        "delta": 0.16,
                        "implied_volatility": 0.30,
                    }
                },
                95.0: {},
            }
        }

        call_data = get_call_by_strike(chain, 95.0)
        self.assertEqual(call_data, {})


if __name__ == "__main__":
    unittest.main()
