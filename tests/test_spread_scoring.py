import unittest

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


if __name__ == "__main__":
    unittest.main()
