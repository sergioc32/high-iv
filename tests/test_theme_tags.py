import unittest

from screener.theme_tags import build_theme_fields, build_theme_tags


class ThemeTagsTests(unittest.TestCase):
    def test_builds_categorized_fields_and_combined_tags_in_stable_order(self):
        fields = build_theme_fields(
            iv_rank=85,
            market_cap=5_000_000_000,
            range_position_52w=0.95,
        )

        self.assertEqual(
            fields,
            {
                "risk_theme_tags": (
                    "high_iv_rank_70_plus,small_cap,speculative_small_cap_high_iv"
                ),
                "technical_theme_tags": "near_52w_high,near_52w_high_extended",
                "theme_tags": (
                    "high_iv_rank_70_plus,small_cap,speculative_small_cap_high_iv,"
                    "near_52w_high,near_52w_high_extended"
                ),
                "theme_taxonomy_version": "v1",
            },
        )

    def test_risk_themes_include_extreme_iv_and_earnings_exposure(self):
        fields = build_theme_fields(
            iv_rank=90,
            earnings_within_dte="2026-07-10",
        )

        self.assertEqual(
            fields["risk_theme_tags"],
            "high_iv_rank_70_plus,extreme_iv_rank_90_plus,earnings_exposure",
        )

    def test_risk_themes_include_execution_quality_and_delta_tags(self):
        fields = build_theme_fields(
            avg_width_pct=0.25,
            credit_expected=0.32,
            width=3,
            min_credit_per_width=0.10,
            short_delta=0.19,
            target_delta=0.16,
            short_open_interest=40,
            long_open_interest=100,
            min_short_open_interest=25,
            min_long_open_interest=5,
        )

        self.assertEqual(
            fields["risk_theme_tags"],
            (
                "wide_bid_ask_spread,low_credit_quality,"
                "delta_stretched,low_open_interest"
            ),
        )

        near_target_fields = build_theme_fields(
            short_delta=0.17,
            target_delta=0.16,
        )

        self.assertEqual(
            near_target_fields["risk_theme_tags"],
            "delta_near_target",
        )

    def test_technical_themes_include_low_range_and_real_90_day_momentum(self):
        fields = build_theme_fields(
            range_position_52w=0.05,
            price_change_90d=-0.80,
        )

        self.assertEqual(
            fields["technical_theme_tags"],
            "near_52w_low,near_52w_low_distressed,extreme_momentum",
        )

    def test_combined_compatibility_helper_returns_theme_tags(self):
        self.assertEqual(build_theme_tags(iv_rank=70), "high_iv_rank_70_plus")

    def test_blank_and_false_earnings_values_do_not_create_exposure(self):
        self.assertEqual(build_theme_fields()["risk_theme_tags"], "")
        self.assertEqual(
            build_theme_fields(earnings_within_dte="False")["risk_theme_tags"],
            "",
        )


if __name__ == "__main__":
    unittest.main()
