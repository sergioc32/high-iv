import csv
import tempfile
import unittest
from pathlib import Path

from screener.spread_logging import CandidateLogWriter, RejectionLogWriter


class SpreadLoggingTests(unittest.TestCase):
    def test_candidate_log_migration_infers_strategy_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "opportunity_candidates.csv"
            path.write_text(
                "\n".join(
                    [
                        "run_id,snapshot_ts,symbol,expiration_date,dte,stock_price,short_strike,long_strike,width,premium,premium_per_width,max_profit,max_loss,risk_reward_ratio,ev_score,short_delta,short_iv,atm_iv,skew_ratio,skew_diff,earnings_within_dte,candidate_status,selected,rejection_reason_primary,rejection_reason_flags",
                        "old_run,2026-04-01T10:00:00,ABC,2026-05-15,30,100,95,90,5,100,0.2,100,400,4,0.2,0.16,0.3,0.25,1.2,0.05,,selected,True,,",
                    ]
                ),
                encoding="utf-8",
            )

            writer = CandidateLogWriter(
                path,
                strategy_version="v2_dynamic",
                legacy_strategy_version="v1_conservative",
                cutoff_date_text="2026-04-09",
            )
            writer.append_row(
                {
                    "run_id": "new_run",
                    "snapshot_ts": "2026-04-15T10:00:00",
                    "strategy_version": "v2_dynamic",
                    "symbol": "XYZ",
                    "expiration_date": "2026-05-15",
                    "dte": 30,
                    "stock_price": 120,
                    "short_strike": 100,
                    "long_strike": 95,
                    "width": 5,
                    "credit_mid": 110,
                    "credit_natural": 100,
                    "credit_expected": 108,
                    "fill_quality": 0.98,
                    "avg_width_pct": 0.08,
                    "mid_weight": 0.85,
                    "premium": 108,
                    "premium_per_width": 0.216,
                    "max_profit": 108,
                    "max_loss": 392,
                    "risk_reward_ratio": 3.6296,
                    "ev_score": 0.23,
                    "short_delta": 0.16,
                    "short_iv": 0.30,
                    "atm_iv": 0.25,
                    "skew_ratio": 1.2,
                    "skew_diff": 0.05,
                    "earnings_within_dte": "",
                    "candidate_status": "selected",
                    "selected": True,
                    "rejection_reason_primary": "",
                    "rejection_reason_flags": "",
                }
            )

            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(rows[0]["strategy_version"], "v1_conservative")
            self.assertEqual(rows[1]["strategy_version"], "v2_dynamic")

    def test_rejection_log_migration_infers_strategy_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rejections_tracking.csv"
            path.write_text(
                "\n".join(
                    [
                        "timestamp,symbol,delta_bounds,delta_bounds_min,delta_bounds_max,delta_bounds_missing,open_interest,short_bid_ask_width,long_bid_ask_width,credit_conservative,premium_zero_or_negative,risk_reward,no_long_strike,total_rejections",
                        "2026-04-01T10:00:00,ABC,1,0,1,0,0,0,0,1,0,0,0,1",
                    ]
                ),
                encoding="utf-8",
            )

            writer = RejectionLogWriter(
                path,
                strategy_version="v2_dynamic",
                legacy_strategy_version="v1_conservative",
                cutoff_date_text="2026-04-09",
            )
            writer.log(
                "XYZ",
                {
                    "delta_bounds": 1,
                    "delta_bounds_min": 0,
                    "delta_bounds_max": 1,
                    "delta_bounds_missing": 0,
                    "itm_or_atm": 0,
                    "long_strike_unavailable": 0,
                    "short_leg_missing_quote": 0,
                    "long_leg_missing_quote": 0,
                    "open_interest": 0,
                    "short_bid_ask_width": 0,
                    "long_bid_ask_width": 0,
                    "credit_natural_too_low": 0,
                    "credit_expected_too_low": 0,
                    "premium_zero_or_negative": 0,
                    "risk_reward": 0,
                    "no_long_strike": 0,
                },
            )

            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(rows[0]["strategy_version"], "v1_conservative")
            self.assertEqual(rows[1]["strategy_version"], "v2_dynamic")


if __name__ == "__main__":
    unittest.main()
