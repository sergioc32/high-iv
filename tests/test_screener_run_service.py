import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import config
from screener.iv_screener import IVScreener
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
                "95": {
                    "put_symbol": f"{symbol}_P95",
                    "call_symbol": f"{symbol}_C95",
                },
                "90": {
                    "put_symbol": f"{symbol}_P90",
                    "call_symbol": f"{symbol}_C90",
                },
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


class FakeCallAnalyzer(FakeAnalyzer):
    def evaluate_spread(
        self,
        symbol,
        stock_price,
        chain,
        target_exp,
        earnings_within_dte="",
    ):
        return {
            "strategy_id": "call_credit_spread",
            "option_side": "call",
            "directional_bias": "bearish",
            "symbol": symbol,
            "stock_price": stock_price,
            "short_strike": 90.0,
            "long_strike": 95.0,
            "width": 5.0,
            "premium": 1.10,
            "max_loss": 390.0,
            "risk_reward_ratio": 3.55,
            "dte": 30,
            "expiration_date": target_exp["expiration_date"],
            "earnings_within_dte": earnings_within_dte,
            "skew_ratio": 1.05,
            "skew_diff": 0.03,
            "short_iv": 0.35,
            "atm_iv": 0.33,
            "ev_score_chosen": 0.7,
        }


class ScreenerRunServiceTests(unittest.TestCase):
    def test_intraday_volume_is_projected_for_liquidity_filter(self):
        service = ScreenerRunService(
            print_progress_fn=lambda message: None,
            display_opportunities_fn=lambda opportunities: None,
            scorer=lambda opportunities: opportunities,
        )
        metrics_data = {
            "AAA": {
                "symbol": "AAA",
                "iv_rank": 50,
                "last_price": 100,
                "market_cap": config.MIN_MARKET_CAP,
            }
        }
        quotes_data = {
            "AAA": {
                "last_price": 100,
                "volume": 100_000,
                "market_cap": config.MIN_MARKET_CAP,
                "is_trading_halted": False,
            }
        }

        service._enrich_metrics_with_quotes(
            metrics_data,
            quotes_data,
            snapshot_ts="2026-05-01T08:46:00",
            market_open=True,
        )

        self.assertEqual(metrics_data["AAA"]["volume"], 100_000)
        self.assertGreater(metrics_data["AAA"]["volume_for_filter"], 2_000_000)

    def test_iv_screener_uses_projected_volume_when_available(self):
        screener = IVScreener()
        metrics_data = {
            "AAA": {
                "symbol": "AAA",
                "iv_rank": 50,
                "last_price": 100,
                "volume": 100_000,
                "volume_for_filter": 2_500_000,
                "market_cap": config.MIN_MARKET_CAP,
                "is_trading_halted": False,
            },
            "BBB": {
                "symbol": "BBB",
                "iv_rank": 50,
                "last_price": 100,
                "volume": 100_000,
                "volume_for_filter": 1_500_000,
                "market_cap": config.MIN_MARKET_CAP,
                "is_trading_halted": False,
            },
        }

        with contextlib.redirect_stdout(io.StringIO()):
            result = screener.filter_by_iv_rank(metrics_data)

        self.assertEqual(result["symbol"].tolist(), ["AAA"])

    def test_iv_screener_prefers_tasty_liquidity_rating_over_volume(self):
        screener = IVScreener()
        metrics_data = {
            "AAA": {
                "symbol": "AAA",
                "iv_rank": 50,
                "last_price": 100,
                "volume_for_filter": 100_000,
                "liquidity_rating": config.MIN_TASTY_LIQUIDITY_RATING,
                "market_cap": config.MIN_MARKET_CAP,
                "is_trading_halted": False,
            },
            "BBB": {
                "symbol": "BBB",
                "iv_rank": 50,
                "last_price": 100,
                "volume_for_filter": 10_000_000,
                "liquidity_rating": config.MIN_TASTY_LIQUIDITY_RATING - 1,
                "market_cap": config.MIN_MARKET_CAP,
                "is_trading_halted": False,
            },
        }

        with contextlib.redirect_stdout(io.StringIO()):
            result = screener.filter_by_iv_rank(metrics_data)

        self.assertEqual(result["symbol"].tolist(), ["AAA"])

    def test_iv_screener_treats_zero_market_cap_as_not_applicable(self):
        screener = IVScreener()
        metrics_data = {
            "GLD": {
                "symbol": "GLD",
                "iv_rank": 50,
                "last_price": 100,
                "volume_for_filter": 2_500_000,
                "liquidity_rating": config.MIN_TASTY_LIQUIDITY_RATING,
                "market_cap": 0,
                "is_trading_halted": False,
            },
            "SMALL": {
                "symbol": "SMALL",
                "iv_rank": 50,
                "last_price": 100,
                "volume_for_filter": 2_500_000,
                "liquidity_rating": config.MIN_TASTY_LIQUIDITY_RATING,
                "market_cap": config.MIN_MARKET_CAP - 1,
                "is_trading_halted": False,
            },
        }

        with contextlib.redirect_stdout(io.StringIO()):
            result = screener.filter_by_iv_rank(metrics_data)

        self.assertEqual(result["symbol"].tolist(), ["GLD"])

    def test_select_option_symbols_prunes_by_side_and_expected_move(self):
        service = ScreenerRunService(
            print_progress_fn=lambda message: None,
            display_opportunities_fn=lambda opportunities: None,
            scorer=lambda opportunities: opportunities,
            enabled_option_sides=("put",),
        )
        chain = {
            "strikes": {
                50.0: {"put_symbol": "P50", "call_symbol": "C50"},
                80.0: {"put_symbol": "P80", "call_symbol": "C80"},
                90.0: {"put_symbol": "P90", "call_symbol": "C90"},
                100.0: {"put_symbol": "P100", "call_symbol": "C100"},
                110.0: {"put_symbol": "P110", "call_symbol": "C110"},
            }
        }

        put_symbols, call_symbols, raw_count = service._select_option_symbols(
            chain=chain,
            stock_price=100.0,
            dte=45,
            expiration_iv=0.30,
        )

        self.assertEqual(raw_count, 10)
        self.assertEqual(put_symbols, ["P90", "P100"])
        self.assertEqual(call_symbols, [])

    def test_call_only_run_skips_put_outputs(self):
        original_auto_save = config.AUTO_SAVE_CSV
        try:
            config.AUTO_SAVE_CSV = True
            with tempfile.TemporaryDirectory() as temp_dir:
                service = ScreenerRunService(
                    screener=FakeScreener(),
                    analyzer_factory=FakeAnalyzer,
                    call_analyzer_factory=FakeCallAnalyzer,
                    scorer=lambda opportunities: opportunities,
                    display_opportunities_fn=lambda opportunities: None,
                    display_strategy_opportunities_fn=lambda opportunities, title: None,
                    print_progress_fn=lambda message: None,
                    opportunities_dir=temp_dir,
                    enabled_option_sides=("call",),
                )

                result = service.run(
                    api=FakeAPI(),
                    run_id="run-1",
                    snapshot_ts="2026-04-16T12:00:00",
                    market_open=True,
                )

                self.assertTrue(result.success)
                self.assertEqual(result.raw_opportunities_count, 1)
                self.assertEqual(len(result.put_final_opportunities), 0)
                self.assertEqual(len(result.call_final_opportunities), 1)
                self.assertIsNone(result.put_saved_csv_path)
                self.assertIsNotNone(result.call_saved_csv_path)
        finally:
            config.AUTO_SAVE_CSV = original_auto_save

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

    def test_run_with_call_analyzer_creates_separate_strategy_outputs(self):
        original_auto_save = config.AUTO_SAVE_CSV
        try:
            config.AUTO_SAVE_CSV = True
            with tempfile.TemporaryDirectory() as temp_dir:
                service = ScreenerRunService(
                    screener=FakeScreener(),
                    analyzer_factory=FakeAnalyzer,
                    call_analyzer_factory=FakeCallAnalyzer,
                    scorer=lambda opportunities: opportunities,
                    display_opportunities_fn=lambda opportunities: None,
                    display_strategy_opportunities_fn=lambda opportunities, title: None,
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
                self.assertEqual(result.raw_opportunities_count, 2)
                self.assertEqual(len(result.put_final_opportunities), 1)
                self.assertEqual(len(result.call_final_opportunities), 1)
                self.assertEqual(len(result.final_opportunities), 2)
                self.assertIsNotNone(result.put_saved_csv_path)
                self.assertIsNotNone(result.call_saved_csv_path)
                self.assertTrue(Path(result.put_saved_csv_path).exists())
                self.assertTrue(Path(result.call_saved_csv_path).exists())

                put_frame = pd.read_csv(result.put_saved_csv_path)
                call_frame = pd.read_csv(result.call_saved_csv_path)
                self.assertEqual(put_frame.loc[0, "symbol"], "AAA")
                self.assertEqual(call_frame.loc[0, "symbol"], "AAA")
        finally:
            config.AUTO_SAVE_CSV = original_auto_save


if __name__ == "__main__":
    unittest.main()
