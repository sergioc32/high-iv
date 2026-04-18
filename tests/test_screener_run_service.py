import tempfile
import unittest
from pathlib import Path

import pandas as pd

import config
from services.screener_run_service import ScreenerRunService


class FakeAPI:
    def __init__(self):
        self.quote_requests: list[list[str]] = []

    def get_watchlist(self, watchlist_name, public=True):
        if watchlist_name == config.WATCHLISTS["sp500"]:
            return ["AAA ", " BBB"]
        if watchlist_name == config.WATCHLISTS["tasty_ivr"]:
            return ["AAA"]
        if watchlist_name == config.WATCHLISTS["nasdaq100"]:
            return []
        if watchlist_name == config.WATCHLISTS["high_options_volume"]:
            return ["BBB"]
        return []

    def batch_request_with_delay(self, symbols, batch_size=100, delay=1.0):
        return {
            "AAA": {"earnings_date": "2099-01-10"},
            "BBB": {"earnings_date": "2099-01-15"},
        }

    def get_quotes_batch(self, symbols):
        return {
            symbol: {
                "last_price": 100.0 if symbol == "AAA" else 110.0,
                "volume": 100000,
                "market_cap": 1_000_000_000,
                "is_trading_halted": False,
            }
            for symbol in symbols
        }

    def get_option_expirations(self, symbol):
        return [{"expiration_date": "2099-01-17"}]

    def get_option_chain(self, symbol, expiration_date):
        return {
            "strikes": {
                "95": {"put_symbol": f"{symbol}_P95"},
                "90": {"put_symbol": f"{symbol}_P90"},
            }
        }

    def get_option_quotes(self, symbols):
        self.quote_requests.append(list(symbols))
        return {
            symbol: {"bid": 1.5, "ask": 1.7, "delta": -0.2, "open_interest": 500}
            for symbol in symbols
        }


class FakeScreener:
    def filter_by_iv_rank(self, metrics_data):
        return pd.DataFrame([{"symbol": "AAA"}])

    def display_screening_results(self, high_iv_df, max_display=20):
        return None

    def get_top_candidates(self, high_iv_df):
        return ["AAA"]


class FakeAnalyzer:
    def __init__(self, run_id=None, snapshot_ts=None):
        self.run_id = run_id
        self.snapshot_ts = snapshot_ts
        self.strategy_rejections_by_symbol = {}

    def find_target_expiration(self, expirations):
        return expirations[0]

    def evaluate_spread(
        self,
        symbol,
        stock_price,
        chain,
        target_exp,
        earnings_within_dte="",
    ):
        return {
            "symbol": symbol,
            "stock_price": stock_price,
            "short_strike": 95.0,
            "long_strike": 90.0,
            "width": 5.0,
            "premium": 1.25,
            "max_loss": 375.0,
            "risk_reward_ratio": 3.0,
            "dte": 30,
            "expiration_date": target_exp["expiration_date"],
            "earnings_within_dte": earnings_within_dte,
            "skew_ratio": 1.1,
            "skew_diff": 0.05,
            "short_iv": 0.4,
            "atm_iv": 0.35,
            "ev_score_chosen": 0.8,
        }

    def filter_opportunities(self, opportunities):
        return opportunities


class ScreenerRunServiceTests(unittest.TestCase):
    def test_fetch_watchlist_symbols_uses_fallback_when_watchlist_missing(self):
        class MissingWatchlistAPI:
            def get_watchlist(self, watchlist_name, public=True):
                raise RuntimeError("missing")

        service = ScreenerRunService(
            print_progress_fn=lambda message: None,
            display_opportunities_fn=lambda opportunities: None,
            scorer=lambda opportunities: opportunities,
        )

        symbols = service.fetch_watchlist_symbols(
            MissingWatchlistAPI(),
            "missing-list",
            fallback=["SPY", "QQQ"],
        )

        self.assertEqual(symbols, ["SPY", "QQQ"])

    def test_run_creates_opportunity_csv_and_returns_summary(self):
        original_auto_save = config.AUTO_SAVE_CSV
        try:
            config.AUTO_SAVE_CSV = True
            with tempfile.TemporaryDirectory() as temp_dir:
                service = ScreenerRunService(
                    screener=FakeScreener(),
                    analyzer_factory=FakeAnalyzer,
                    scorer=lambda opportunities: opportunities,
                    display_opportunities_fn=lambda opportunities: None,
                    print_progress_fn=lambda message: None,
                    opportunities_dir=temp_dir,
                )

                result = service.run(
                    api=FakeAPI(),
                    run_id="run-1",
                    snapshot_ts="2026-04-16T12:00:00",
                    market_open=True,
                )

                self.assertTrue(result.success)
                self.assertEqual(result.all_symbols_count, 2)
                self.assertEqual(result.screened_symbols_count, 1)
                self.assertEqual(result.raw_opportunities_count, 1)
                self.assertEqual(len(result.final_opportunities), 1)
                self.assertIsNotNone(result.saved_csv_path)
                self.assertTrue(Path(result.saved_csv_path).exists())

                saved_frame = pd.read_csv(result.saved_csv_path)
                self.assertEqual(saved_frame.loc[0, "symbol"], "AAA")
        finally:
            config.AUTO_SAVE_CSV = original_auto_save


if __name__ == "__main__":
    unittest.main()
