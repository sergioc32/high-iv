import csv
import tempfile
import unittest
from pathlib import Path

from analysis import build_analysis_dataset as analysis_builder
from analysis import build_executed_trade_dataset as executed_builder
from screener.spread_logging import CANDIDATE_FIELDNAMES


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class AnalyticsDatasetTests(unittest.TestCase):
    def _build_fixture(self, root: Path) -> tuple[Path, Path, Path]:
        opportunities_dir = root / "opportunities"
        review_dir = root / "opportunities_review"
        trades_dir = root / "trades"
        analysis_dir = root / "analysis"

        candidate_row = {field: "" for field in CANDIDATE_FIELDNAMES}
        candidate_row.update(
            {
                "run_id": "20260522_120000",
                "snapshot_ts": "2026-05-22T12:00:00",
                "strategy_version": "v2_dynamic",
                "strategy_id": "call_credit_spread",
                "strategy_family": "credit_spread",
                "option_side": "call",
                "directional_bias": "bearish",
                "short_leg_type": "short_call",
                "long_leg_type": "long_call",
                "symbol": "XYZ",
                "sector": "Technology",
                "industry": "Semiconductors",
                "risk_theme_tags": (
                    "high_iv_rank_70_plus,small_cap,speculative_small_cap_high_iv"
                ),
                "technical_theme_tags": "near_52w_high,near_52w_high_extended",
                "theme_tags": (
                    "high_iv_rank_70_plus,small_cap,speculative_small_cap_high_iv,"
                    "near_52w_high,near_52w_high_extended"
                ),
                "theme_taxonomy_version": "v1",
                "expiration_date": "2026-06-19",
                "dte": "28",
                "stock_price": "120.0",
                "year_high_price": "125.0",
                "year_low_price": "80.0",
                "range_position_52w": "0.89",
                "distance_to_52w_high_pct": "0.0400",
                "distance_to_52w_low_pct": "0.5000",
                "short_strike": "130.0",
                "long_strike": "135.0",
                "width": "5.0",
                "credit_mid": "1.15",
                "credit_natural": "1.00",
                "credit_expected": "1.08",
                "fill_quality": "good",
                "avg_width_pct": "0.09",
                "mid_weight": "0.65",
                "premium": "1.08",
                "premium_per_width": "0.2160",
                "max_profit": "108.0",
                "max_loss": "392.0",
                "risk_reward_ratio": "3.63",
                "ev_score": "0.18",
                "short_delta": "0.16",
                "short_iv": "0.34",
                "atm_iv": "0.31",
                "skew_ratio": "1.05",
                "skew_diff": "0.03",
                "earnings_within_dte": "False",
                "anchor_vs_shift_status": "anchor",
                "shift_steps_from_anchor": "0",
                "short_strike_shift": "0.0",
                "long_strike_shift": "0.0",
                "shift_direction": "none",
                "candidate_status": "reviewed_context",
                "selected": "True",
                "rejection_reason_primary": "",
                "rejection_reason_flags": "",
            }
        )
        write_csv(
            opportunities_dir / "opportunity_candidates.csv",
            list(CANDIDATE_FIELDNAMES),
            [candidate_row],
        )

        write_csv(
            trades_dir / "trades_open.csv",
            [
                "trade_id",
                "symbol",
                "expiration",
                "short_strike",
                "long_strike",
                "width",
                "entry_date",
            ],
            [],
        )
        write_csv(
            trades_dir / "trades_closed.csv",
            [
                "trade_id",
                "symbol",
                "expiration",
                "short_strike",
                "long_strike",
                "width",
                "entry_date",
                "close_date",
                "profit_loss",
                "actual_exit_found",
            ],
            [
                {
                    "trade_id": "XYZ_2026-05-22_2026-06-19_130_135",
                    "symbol": "XYZ",
                    "expiration": "2026-06-19",
                    "short_strike": "130.0",
                    "long_strike": "135.0",
                    "width": "5.0",
                    "entry_date": "2026-05-22",
                    "close_date": "2026-05-29",
                    "profit_loss": "55.0",
                    "actual_exit_found": "True",
                }
            ],
        )

        write_csv(
            opportunities_dir / "call_spread_opportunities_20260522_120000.csv",
            [
                "strategy_version",
                "strategy_id",
                "option_side",
                "directional_bias",
                "symbol",
                "expiration_date",
                "short_strike",
                "long_strike",
                "width",
                "alignment_score_version",
                "strategy_alignment_score",
                "total_rank_score",
                "delta_preference_component",
                "skew_component",
                "ev_component",
                "liquidity_component",
                "extension_component",
                "directional_adjustment",
                "earnings_adjustment",
                "alignment_flags",
                "delta_zone",
                "explanation_summary",
                "selector_version",
                "market_regime_spy",
                "market_regime_qqq",
                "market_regime_summary",
                "symbol_extension_bucket",
                "put_selector_score",
                "call_selector_score",
                "put_selector_band",
                "call_selector_band",
                "selector_preferred_strategy",
                "selector_confidence",
                "selector_reason",
                "selector_earnings_stage",
                "selector_earnings_penalty",
                "always_review_symbol",
                "always_review_forced_into_analysis",
                "always_review_source",
            ],
            [
                {
                    "strategy_version": "v2_dynamic",
                    "strategy_id": "call_credit_spread",
                    "option_side": "call",
                    "directional_bias": "bearish",
                    "symbol": "XYZ",
                    "expiration_date": "2026-06-19",
                    "short_strike": "130.0",
                    "long_strike": "135.0",
                    "width": "5.0",
                    "alignment_score_version": "v1",
                    "strategy_alignment_score": "78.40",
                    "total_rank_score": "78.40",
                    "delta_preference_component": "0.24",
                    "skew_component": "0.11",
                    "ev_component": "0.20",
                    "liquidity_component": "0.14",
                    "extension_component": "0.26",
                    "directional_adjustment": "0.00",
                    "earnings_adjustment": "0.00",
                    "alignment_flags": "near_52w_high",
                    "delta_zone": "target",
                    "explanation_summary": "align=78.4 ev=0.18 call near highs",
                    "selector_version": "v1",
                    "market_regime_spy": "bullish",
                    "market_regime_qqq": "extended_bullish",
                    "market_regime_summary": "bullish",
                    "symbol_extension_bucket": "upper_range",
                    "put_selector_score": "58",
                    "call_selector_score": "72",
                    "put_selector_band": "viable",
                    "call_selector_band": "strong",
                    "selector_preferred_strategy": "call",
                    "selector_confidence": "medium",
                    "selector_reason": "Extended tape with upper-range symbol favors call fades.",
                    "selector_earnings_stage": "post_cycle",
                    "selector_earnings_penalty": "0",
                    "always_review_symbol": "True",
                    "always_review_forced_into_analysis": "True",
                    "always_review_source": "configured_always_review",
                }
            ],
        )

        write_csv(
            review_dir / "review_queue_20260522_120100.csv",
            [
                "run_id",
                "snapshot_ts",
                "strategy_id",
                "symbol",
                "expiration_date",
                "short_strike",
                "long_strike",
                "decision",
                "decision_reason",
                "decision_note",
            ],
            [
                {
                    "run_id": "20260522_120000",
                    "snapshot_ts": "2026-05-22T12:00:00",
                    "strategy_id": "call_credit_spread",
                    "symbol": "XYZ",
                    "expiration_date": "2026-06-19",
                    "short_strike": "130.0",
                    "long_strike": "135.0",
                    "decision": "accepted",
                    "decision_reason": "",
                    "decision_note": "Comfortable with the setup.",
                }
            ],
        )

        return opportunities_dir, trades_dir, analysis_dir

    def test_build_analysis_dataset_propagates_call_selector_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            opportunities_dir, trades_dir, analysis_dir = self._build_fixture(root)

            original_candidates_path = analysis_builder.CANDIDATES_PATH
            original_open_path = analysis_builder.TRADES_OPEN_PATH
            original_closed_path = analysis_builder.TRADES_CLOSED_PATH
            original_output_path = analysis_builder.OUTPUT_PATH
            original_daily_globs = analysis_builder.DAILY_OPPORTUNITIES_GLOBS
            original_review_queue_glob = analysis_builder.REVIEW_QUEUE_GLOB
            try:
                analysis_builder.CANDIDATES_PATH = (
                    opportunities_dir / "opportunity_candidates.csv"
                )
                analysis_builder.TRADES_OPEN_PATH = trades_dir / "trades_open.csv"
                analysis_builder.TRADES_CLOSED_PATH = trades_dir / "trades_closed.csv"
                analysis_builder.OUTPUT_PATH = analysis_dir / "analysis_dataset.csv"
                analysis_builder.DAILY_OPPORTUNITIES_GLOBS = (
                    str(opportunities_dir / "call_spread_opportunities_*.csv"),
                )
                analysis_builder.REVIEW_QUEUE_GLOB = str(
                    root / "opportunities_review" / "review_queue_*.csv"
                )

                analysis_builder.build_analysis_dataset()

                with open(
                    analysis_builder.OUTPUT_PATH,
                    newline="",
                    encoding="utf-8",
                ) as handle:
                    rows = list(csv.DictReader(handle))
            finally:
                analysis_builder.CANDIDATES_PATH = original_candidates_path
                analysis_builder.TRADES_OPEN_PATH = original_open_path
                analysis_builder.TRADES_CLOSED_PATH = original_closed_path
                analysis_builder.OUTPUT_PATH = original_output_path
                analysis_builder.DAILY_OPPORTUNITIES_GLOBS = original_daily_globs
                analysis_builder.REVIEW_QUEUE_GLOB = original_review_queue_glob

            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["strategy_id"], "call_credit_spread")
            self.assertEqual(row["option_side"], "call")
            self.assertEqual(row["sector"], "Technology")
            self.assertEqual(row["industry"], "Semiconductors")
            self.assertEqual(
                row["risk_theme_tags"],
                "high_iv_rank_70_plus,small_cap,speculative_small_cap_high_iv",
            )
            self.assertEqual(
                row["technical_theme_tags"],
                "near_52w_high,near_52w_high_extended",
            )
            self.assertEqual(
                row["theme_tags"],
                "high_iv_rank_70_plus,small_cap,speculative_small_cap_high_iv,"
                "near_52w_high,near_52w_high_extended",
            )
            self.assertEqual(row["theme_taxonomy_version"], "v1")
            self.assertEqual(row["alignment_score_version"], "v1")
            self.assertEqual(row["strategy_alignment_score"], "78.40")
            self.assertEqual(row["selector_version"], "v1")
            self.assertEqual(row["put_selector_score"], "58")
            self.assertEqual(row["call_selector_score"], "72")
            self.assertEqual(row["selector_preferred_strategy"], "call")
            self.assertEqual(row["always_review_symbol"], "True")
            self.assertEqual(row["always_review_forced_into_analysis"], "True")
            self.assertEqual(row["always_review_source"], "configured_always_review")
            self.assertEqual(row["review_decision"], "accepted")
            self.assertEqual(row["review_decision_reason"], "")
            self.assertEqual(row["review_decision_note"], "Comfortable with the setup.")
            self.assertEqual(
                row["review_queue_file"], "review_queue_20260522_120100.csv"
            )
            self.assertEqual(
                row["daily_opportunity_file"],
                "call_spread_opportunities_20260522_120000.csv",
            )

    def test_build_analysis_dataset_enriches_selected_missing_match_from_daily_file(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            opportunities_dir = root / "opportunities"
            trades_dir = root / "trades"
            analysis_dir = root / "analysis"

            candidate_row = {field: "" for field in CANDIDATE_FIELDNAMES}
            candidate_row.update(
                {
                    "run_id": "20260522_130000",
                    "snapshot_ts": "2026-05-22T13:00:00",
                    "strategy_version": "v2_dynamic",
                    "strategy_id": "put_credit_spread",
                    "strategy_family": "credit_spread",
                    "option_side": "put",
                    "directional_bias": "bullish",
                    "short_leg_type": "short_put",
                    "long_leg_type": "long_put",
                    "symbol": "ABC",
                    "expiration_date": "2026-06-19",
                    "dte": "28",
                    "stock_price": "210.0",
                    "short_strike": "195.0",
                    "long_strike": "190.0",
                    "width": "5.0",
                    "premium": "1.22",
                    "premium_per_width": "0.2440",
                    "max_profit": "122.0",
                    "max_loss": "378.0",
                    "risk_reward_ratio": "3.10",
                    "ev_score": "0.22",
                    "short_delta": "0.17",
                    "short_iv": "0.31",
                    "atm_iv": "0.28",
                    "skew_ratio": "1.07",
                    "skew_diff": "0.04",
                    "candidate_status": "selected",
                    "selected": "True",
                }
            )
            write_csv(
                opportunities_dir / "opportunity_candidates.csv",
                list(CANDIDATE_FIELDNAMES),
                [candidate_row],
            )
            write_csv(
                trades_dir / "trades_open.csv",
                [
                    "trade_id",
                    "symbol",
                    "expiration",
                    "short_strike",
                    "long_strike",
                    "width",
                    "entry_date",
                ],
                [],
            )
            write_csv(
                trades_dir / "trades_closed.csv",
                [
                    "trade_id",
                    "symbol",
                    "expiration",
                    "short_strike",
                    "long_strike",
                    "width",
                    "entry_date",
                ],
                [],
            )
            write_csv(
                opportunities_dir / "put_spread_opportunities_20260522_130000.csv",
                [
                    "strategy_version",
                    "strategy_id",
                    "option_side",
                    "directional_bias",
                    "symbol",
                    "expiration_date",
                    "short_strike",
                    "long_strike",
                    "width",
                    "alignment_score_version",
                    "strategy_alignment_score",
                    "selector_version",
                    "put_selector_score",
                    "call_selector_score",
                    "selector_preferred_strategy",
                    "market_regime_summary",
                    "symbol_extension_bucket",
                    "always_review_symbol",
                    "always_review_forced_into_analysis",
                    "always_review_source",
                ],
                [
                    {
                        "strategy_version": "v2_dynamic",
                        "strategy_id": "put_credit_spread",
                        "option_side": "put",
                        "directional_bias": "bullish",
                        "symbol": "ABC",
                        "expiration_date": "2026-06-19",
                        "short_strike": "195.0",
                        "long_strike": "190.0",
                        "width": "5.0",
                        "alignment_score_version": "v1",
                        "strategy_alignment_score": "74.20",
                        "selector_version": "v1",
                        "put_selector_score": "67",
                        "call_selector_score": "41",
                        "selector_preferred_strategy": "put",
                        "market_regime_summary": "bullish",
                        "symbol_extension_bucket": "mid_range",
                        "always_review_symbol": "True",
                        "always_review_forced_into_analysis": "False",
                        "always_review_source": "configured_always_review",
                    }
                ],
            )

            original_candidates_path = analysis_builder.CANDIDATES_PATH
            original_open_path = analysis_builder.TRADES_OPEN_PATH
            original_closed_path = analysis_builder.TRADES_CLOSED_PATH
            original_output_path = analysis_builder.OUTPUT_PATH
            original_daily_globs = analysis_builder.DAILY_OPPORTUNITIES_GLOBS
            try:
                analysis_builder.CANDIDATES_PATH = (
                    opportunities_dir / "opportunity_candidates.csv"
                )
                analysis_builder.TRADES_OPEN_PATH = trades_dir / "trades_open.csv"
                analysis_builder.TRADES_CLOSED_PATH = trades_dir / "trades_closed.csv"
                analysis_builder.OUTPUT_PATH = analysis_dir / "analysis_dataset.csv"
                analysis_builder.DAILY_OPPORTUNITIES_GLOBS = (
                    str(opportunities_dir / "put_spread_opportunities_*.csv"),
                )

                analysis_builder.build_analysis_dataset()

                with open(
                    analysis_builder.OUTPUT_PATH,
                    newline="",
                    encoding="utf-8",
                ) as handle:
                    rows = list(csv.DictReader(handle))
            finally:
                analysis_builder.CANDIDATES_PATH = original_candidates_path
                analysis_builder.TRADES_OPEN_PATH = original_open_path
                analysis_builder.TRADES_CLOSED_PATH = original_closed_path
                analysis_builder.OUTPUT_PATH = original_output_path
                analysis_builder.DAILY_OPPORTUNITIES_GLOBS = original_daily_globs

            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["match_status"], "missing_match")
            self.assertEqual(row["was_in_daily_opportunities_file"], "True")
            self.assertEqual(row["alignment_score_version"], "v1")
            self.assertEqual(row["selector_version"], "v1")
            self.assertEqual(row["put_selector_score"], "67")
            self.assertEqual(row["call_selector_score"], "41")
            self.assertEqual(row["selector_preferred_strategy"], "put")
            self.assertEqual(row["always_review_symbol"], "True")
            self.assertEqual(row["always_review_forced_into_analysis"], "False")
            self.assertEqual(row["always_review_source"], "configured_always_review")

    def test_build_analysis_dataset_prefers_same_run_daily_file_for_same_day_match(
        self,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            opportunities_dir = root / "opportunities"
            trades_dir = root / "trades"
            analysis_dir = root / "analysis"

            candidate_row = {field: "" for field in CANDIDATE_FIELDNAMES}
            candidate_row.update(
                {
                    "run_id": "20260522_111518",
                    "snapshot_ts": "2026-05-22T11:15:18.758369",
                    "strategy_version": "v2_dynamic",
                    "strategy_id": "put_credit_spread",
                    "strategy_family": "credit_spread",
                    "option_side": "put",
                    "directional_bias": "bullish",
                    "short_leg_type": "short_put",
                    "long_leg_type": "long_put",
                    "symbol": "FANG",
                    "expiration_date": "2026-06-19",
                    "dte": "28",
                    "stock_price": "190.0",
                    "short_strike": "180.0",
                    "long_strike": "175.0",
                    "width": "5.0",
                    "premium": "1.15",
                    "premium_per_width": "0.2300",
                    "max_profit": "115.0",
                    "max_loss": "385.0",
                    "risk_reward_ratio": "3.35",
                    "ev_score": "0.19",
                    "short_delta": "0.16",
                    "short_iv": "0.29",
                    "atm_iv": "0.26",
                    "skew_ratio": "1.04",
                    "skew_diff": "0.03",
                    "candidate_status": "selected",
                    "selected": "True",
                }
            )
            write_csv(
                opportunities_dir / "opportunity_candidates.csv",
                list(CANDIDATE_FIELDNAMES),
                [candidate_row],
            )
            write_csv(
                trades_dir / "trades_open.csv",
                [
                    "trade_id",
                    "symbol",
                    "expiration",
                    "short_strike",
                    "long_strike",
                    "width",
                    "entry_date",
                ],
                [],
            )
            write_csv(
                trades_dir / "trades_closed.csv",
                [
                    "trade_id",
                    "symbol",
                    "expiration",
                    "short_strike",
                    "long_strike",
                    "width",
                    "entry_date",
                ],
                [],
            )
            daily_fieldnames = [
                "strategy_version",
                "strategy_id",
                "option_side",
                "directional_bias",
                "symbol",
                "expiration_date",
                "short_strike",
                "long_strike",
                "width",
                "alignment_score_version",
                "selector_version",
                "put_selector_score",
                "call_selector_score",
                "selector_preferred_strategy",
                "always_review_symbol",
                "always_review_forced_into_analysis",
                "always_review_source",
            ]
            write_csv(
                opportunities_dir / "put_spread_opportunities_20260522_105335.csv",
                daily_fieldnames,
                [
                    {
                        "strategy_version": "v2_dynamic",
                        "strategy_id": "put_credit_spread",
                        "option_side": "put",
                        "directional_bias": "bullish",
                        "symbol": "FANG",
                        "expiration_date": "2026-06-19",
                        "short_strike": "180.0",
                        "long_strike": "175.0",
                        "width": "5.0",
                        "alignment_score_version": "",
                        "selector_version": "",
                        "put_selector_score": "",
                        "call_selector_score": "",
                        "selector_preferred_strategy": "",
                        "always_review_symbol": "",
                        "always_review_forced_into_analysis": "",
                        "always_review_source": "",
                    }
                ],
            )
            write_csv(
                opportunities_dir / "put_spread_opportunities_20260522_111918.csv",
                daily_fieldnames,
                [
                    {
                        "strategy_version": "v2_dynamic",
                        "strategy_id": "put_credit_spread",
                        "option_side": "put",
                        "directional_bias": "bullish",
                        "symbol": "FANG",
                        "expiration_date": "2026-06-19",
                        "short_strike": "180.0",
                        "long_strike": "175.0",
                        "width": "5.0",
                        "alignment_score_version": "v1",
                        "selector_version": "v1",
                        "put_selector_score": "61",
                        "call_selector_score": "44",
                        "selector_preferred_strategy": "put",
                        "always_review_symbol": "True",
                        "always_review_forced_into_analysis": "True",
                        "always_review_source": "configured_always_review",
                    }
                ],
            )

            original_candidates_path = analysis_builder.CANDIDATES_PATH
            original_open_path = analysis_builder.TRADES_OPEN_PATH
            original_closed_path = analysis_builder.TRADES_CLOSED_PATH
            original_output_path = analysis_builder.OUTPUT_PATH
            original_daily_globs = analysis_builder.DAILY_OPPORTUNITIES_GLOBS
            try:
                analysis_builder.CANDIDATES_PATH = (
                    opportunities_dir / "opportunity_candidates.csv"
                )
                analysis_builder.TRADES_OPEN_PATH = trades_dir / "trades_open.csv"
                analysis_builder.TRADES_CLOSED_PATH = trades_dir / "trades_closed.csv"
                analysis_builder.OUTPUT_PATH = analysis_dir / "analysis_dataset.csv"
                analysis_builder.DAILY_OPPORTUNITIES_GLOBS = (
                    str(opportunities_dir / "put_spread_opportunities_*.csv"),
                )

                analysis_builder.build_analysis_dataset()

                with open(
                    analysis_builder.OUTPUT_PATH,
                    newline="",
                    encoding="utf-8",
                ) as handle:
                    rows = list(csv.DictReader(handle))
            finally:
                analysis_builder.CANDIDATES_PATH = original_candidates_path
                analysis_builder.TRADES_OPEN_PATH = original_open_path
                analysis_builder.TRADES_CLOSED_PATH = original_closed_path
                analysis_builder.OUTPUT_PATH = original_output_path
                analysis_builder.DAILY_OPPORTUNITIES_GLOBS = original_daily_globs

            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(
                row["daily_opportunity_file"],
                "put_spread_opportunities_20260522_111918.csv",
            )
            self.assertEqual(row["alignment_score_version"], "v1")
            self.assertEqual(row["selector_version"], "v1")
            self.assertEqual(row["selector_preferred_strategy"], "put")
            self.assertEqual(row["always_review_symbol"], "True")
            self.assertEqual(row["always_review_forced_into_analysis"], "True")
            self.assertEqual(row["always_review_source"], "configured_always_review")

    def test_build_executed_trade_dataset_carries_selector_metadata_forward(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            opportunities_dir, trades_dir, analysis_dir = self._build_fixture(root)
            analysis_dataset_path = analysis_dir / "analysis_dataset.csv"
            executed_dataset_path = analysis_dir / "executed_trade_dataset.csv"

            original_candidates_path = analysis_builder.CANDIDATES_PATH
            original_open_path = analysis_builder.TRADES_OPEN_PATH
            original_closed_path = analysis_builder.TRADES_CLOSED_PATH
            original_output_path = analysis_builder.OUTPUT_PATH
            original_daily_globs = analysis_builder.DAILY_OPPORTUNITIES_GLOBS
            original_review_queue_glob = analysis_builder.REVIEW_QUEUE_GLOB
            try:
                analysis_builder.CANDIDATES_PATH = (
                    opportunities_dir / "opportunity_candidates.csv"
                )
                analysis_builder.TRADES_OPEN_PATH = trades_dir / "trades_open.csv"
                analysis_builder.TRADES_CLOSED_PATH = trades_dir / "trades_closed.csv"
                analysis_builder.OUTPUT_PATH = analysis_dataset_path
                analysis_builder.DAILY_OPPORTUNITIES_GLOBS = (
                    str(opportunities_dir / "call_spread_opportunities_*.csv"),
                )
                analysis_builder.REVIEW_QUEUE_GLOB = str(
                    root / "opportunities_review" / "review_queue_*.csv"
                )

                analysis_builder.build_analysis_dataset()
            finally:
                analysis_builder.CANDIDATES_PATH = original_candidates_path
                analysis_builder.TRADES_OPEN_PATH = original_open_path
                analysis_builder.TRADES_CLOSED_PATH = original_closed_path
                analysis_builder.OUTPUT_PATH = original_output_path
                analysis_builder.DAILY_OPPORTUNITIES_GLOBS = original_daily_globs
                analysis_builder.REVIEW_QUEUE_GLOB = original_review_queue_glob

            executed_builder.build_executed_trade_dataset(
                analysis_dataset_path=analysis_dataset_path,
                candidates_path=opportunities_dir / "opportunity_candidates.csv",
                output_path=executed_dataset_path,
                daily_opportunities_dir=opportunities_dir,
            )

            with open(
                executed_dataset_path,
                newline="",
                encoding="utf-8",
            ) as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["strategy_id"], "call_credit_spread")
            self.assertEqual(row["sector"], "Technology")
            self.assertEqual(row["industry"], "Semiconductors")
            self.assertEqual(
                row["risk_theme_tags"],
                "high_iv_rank_70_plus,small_cap,speculative_small_cap_high_iv",
            )
            self.assertEqual(
                row["technical_theme_tags"],
                "near_52w_high,near_52w_high_extended",
            )
            self.assertEqual(
                row["theme_tags"],
                "high_iv_rank_70_plus,small_cap,speculative_small_cap_high_iv,"
                "near_52w_high,near_52w_high_extended",
            )
            self.assertEqual(row["theme_taxonomy_version"], "v1")
            self.assertEqual(row["alignment_score_version"], "v1")
            self.assertEqual(row["selector_version"], "v1")
            self.assertEqual(row["selector_preferred_strategy"], "call")
            self.assertEqual(row["call_selector_band"], "strong")
            self.assertEqual(row["always_review_symbol"], "True")
            self.assertEqual(row["always_review_forced_into_analysis"], "True")
            self.assertEqual(row["always_review_source"], "configured_always_review")
            self.assertEqual(row["review_decision"], "accepted")
            self.assertEqual(row["review_decision_note"], "Comfortable with the setup.")
            self.assertEqual(
                row["review_queue_file"], "review_queue_20260522_120100.csv"
            )
            self.assertEqual(row["feature_provenance"], "candidate_log_exact")


if __name__ == "__main__":
    unittest.main()
