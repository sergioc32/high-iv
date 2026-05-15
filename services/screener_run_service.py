"""
Application service for the end-to-end spread screening pipeline.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from datetime import date, datetime
from datetime import time as datetime_time

import config
from analysis.ranking_engine import score_opportunities
from api.tastytrade import SP500_FALLBACK
from screener.iv_screener import IVScreener
from screener.put_spread_analyzer import PutSpreadAnalyzer
from services.persistence_service import PersistenceService
from services.run_models import ScreenerRunResult
from utils.display import (
    display_opportunities,
    display_strategy_opportunities,
    print_progress,
)


class ScreenerRunService:
    def __init__(
        self,
        screener: IVScreener | None = None,
        analyzer_factory: Callable[..., object] = PutSpreadAnalyzer,
        call_analyzer_factory: Callable[..., object] | None = None,
        scorer: Callable[
            [list[dict[str, object]]], list[dict[str, object]]
        ] = score_opportunities,
        display_opportunities_fn: Callable[
            [list[dict[str, object]]], None
        ] = display_opportunities,
        display_strategy_opportunities_fn: Callable[
            [list[dict[str, object]], str], None
        ] = display_strategy_opportunities,
        print_progress_fn: Callable[[str], None] = print_progress,
        opportunities_dir: str = "opportunities",
        persistence_service: PersistenceService | None = None,
        enabled_option_sides: tuple[str, ...] = ("put", "call"),
    ) -> None:
        enabled_sides = tuple(dict.fromkeys(enabled_option_sides))
        invalid_sides = set(enabled_sides) - {"put", "call"}
        if invalid_sides:
            raise ValueError(f"Unsupported option side(s): {sorted(invalid_sides)}")
        if not enabled_sides:
            raise ValueError("At least one option side must be enabled")
        self.screener = screener or IVScreener()
        self.analyzer_factory = analyzer_factory
        self.call_analyzer_factory = call_analyzer_factory
        self.enabled_option_sides = enabled_sides
        self.scorer = scorer
        self.display_opportunities = display_opportunities_fn
        self.display_strategy_opportunities = display_strategy_opportunities_fn
        self.print_progress = print_progress_fn
        self.persistence_service = persistence_service or PersistenceService(
            opportunities_dir=opportunities_dir
        )

    def run(
        self,
        api,
        run_id: str,
        snapshot_ts: str,
        market_open: bool,
    ) -> ScreenerRunResult:
        self.print_progress(
            "Fetching watchlist symbols for (SPY,IVR,NAS100,High Options Volume)"
        )
        all_symbols = self._collect_watchlist_symbols(api)
        print(
            f"Retrieved {len(all_symbols)} symbols from watchlists before de-duplication"
        )
        all_symbols = list(set(all_symbols))
        print(f"Total symbols to screen: {len(all_symbols)}")

        if not all_symbols:
            print("No symbols found in watchlists")
            return ScreenerRunResult(
                success=False, message="No symbols found in watchlists"
            )

        self.print_progress("Fetching market metrics (IV Rank, IV Percentile)")
        metrics_data = api.batch_request_with_delay(
            all_symbols, batch_size=100, delay=1.0
        )
        if not metrics_data:
            print("Failed to retrieve market metrics")
            return ScreenerRunResult(
                success=False,
                message="Failed to retrieve market metrics",
                all_symbols_count=len(all_symbols),
            )

        self.print_progress("Fetching quotes for liquidity filters")
        quotes_data = api.get_quotes_batch(all_symbols)
        self._enrich_metrics_with_quotes(
            metrics_data,
            quotes_data,
            snapshot_ts=snapshot_ts,
            market_open=market_open,
        )

        self.print_progress("Screening by IV Rank")
        high_iv_df = self.screener.filter_by_iv_rank(metrics_data)
        if len(high_iv_df) == 0:
            print("No stocks found after IV Rank and liquidity filters")
            return ScreenerRunResult(
                success=False,
                message="No stocks found after IV Rank and liquidity filters",
                all_symbols_count=len(all_symbols),
            )

        self.screener.display_screening_results(high_iv_df, max_display=20)
        top_candidates = self.screener.get_top_candidates(high_iv_df)

        print(f"\nAnalyzing options chains for top {len(top_candidates)} candidates...")
        print("   (This may take a few minutes)\n")

        put_enabled = "put" in self.enabled_option_sides
        call_enabled = "call" in self.enabled_option_sides
        put_analyzer = (
            self.analyzer_factory(run_id=run_id, snapshot_ts=snapshot_ts)
            if put_enabled
            else None
        )
        call_analyzer = (
            self.call_analyzer_factory(run_id=run_id, snapshot_ts=snapshot_ts)
            if call_enabled and self.call_analyzer_factory is not None
            else None
        )
        expiration_analyzer = put_analyzer or call_analyzer

        put_opportunities: list[dict[str, object]] = []
        call_opportunities: list[dict[str, object]] = []

        self.print_progress("Fetching quotes for top candidates")
        candidate_quotes = api.get_quotes_batch(top_candidates)

        print(f"Analyzing options chains for {len(top_candidates)} candidates...\n")

        diagnostics = self._initialize_diagnostics()

        self.print_progress("Phase 1: Fetching option chains for all candidates")
        candidate_data, all_option_symbols = self._collect_candidate_option_data(
            api=api,
            analyzer=expiration_analyzer,
            top_candidates=top_candidates,
            candidate_quotes=candidate_quotes,
            metrics_data=metrics_data,
            diagnostics=diagnostics,
        )

        print(f"\nFetched chains for {len(candidate_data)} symbols")
        print(
            f"Found {len(all_option_symbols)} total option symbols to quote (before de-dupe)"
        )

        if not all_option_symbols:
            print("No option symbols found across all candidates")
        else:
            unique_option_symbols = sorted(set(all_option_symbols))
            print(
                f"De-duplicated to {len(unique_option_symbols)} unique option symbols"
            )

            all_option_quotes = self._fetch_option_quotes(api, unique_option_symbols)
            if put_analyzer is not None:
                self._evaluate_candidates(
                    analyzer=put_analyzer,
                    candidate_data=candidate_data,
                    all_option_quotes=all_option_quotes,
                    metrics_data=metrics_data,
                    diagnostics=diagnostics,
                    opportunities=put_opportunities,
                    option_side="put",
                )
            if call_analyzer is not None:
                self._evaluate_candidates(
                    analyzer=call_analyzer,
                    candidate_data=candidate_data,
                    all_option_quotes=all_option_quotes,
                    metrics_data=metrics_data,
                    diagnostics=diagnostics,
                    opportunities=call_opportunities,
                    option_side="call",
                )

        print("\nCompleted options analysis")
        self._print_diagnostics(diagnostics)
        if put_analyzer is not None:
            self._print_strategy_diagnostics(
                "Put Credit Spread", put_analyzer, diagnostics["put_reached_evaluation"]
            )
        if call_analyzer is not None:
            self._print_strategy_diagnostics(
                "Call Credit Spread",
                call_analyzer,
                diagnostics["call_reached_evaluation"],
            )
        self._print_dte_warning(diagnostics)
        print()

        final_put_opportunities: list[dict[str, object]] = []
        final_call_opportunities: list[dict[str, object]] = []
        put_saved_csv_path: str | None = None
        call_saved_csv_path: str | None = None

        if put_analyzer is not None and put_opportunities:
            self.print_progress("Filtering and ranking put spread opportunities")
            final_put_opportunities = put_analyzer.filter_opportunities(
                put_opportunities
            )
            final_put_opportunities = self.scorer(final_put_opportunities)
            self.display_strategy_opportunities(
                final_put_opportunities,
                f"Top {len(final_put_opportunities)} Put Spread Opportunities",
            )

            if config.AUTO_SAVE_CSV:
                put_saved_csv_path = self.persistence_service.save_opportunities(
                    final_put_opportunities,
                    market_open=market_open,
                    filename_prefix="put_spread_opportunities",
                )
                print(f"Saved put spread opportunities to {put_saved_csv_path}")
        elif put_analyzer is not None:
            print("\nNo put spread opportunities found matching all criteria")

        if call_analyzer is not None:
            if call_opportunities:
                self.print_progress("Filtering and ranking call spread opportunities")
                final_call_opportunities = call_analyzer.filter_opportunities(
                    call_opportunities
                )
                final_call_opportunities = self.scorer(final_call_opportunities)
                self.display_strategy_opportunities(
                    final_call_opportunities,
                    f"Top {len(final_call_opportunities)} Call Spread Opportunities",
                )

                if config.AUTO_SAVE_CSV:
                    call_saved_csv_path = self.persistence_service.save_opportunities(
                        final_call_opportunities,
                        market_open=market_open,
                        filename_prefix="call_spread_opportunities",
                    )
                    print(f"Saved call spread opportunities to {call_saved_csv_path}")
            else:
                print("\nNo call spread opportunities found matching all criteria")

        final_opportunities = final_put_opportunities + final_call_opportunities
        saved_csv_path = put_saved_csv_path or call_saved_csv_path
        raw_opportunities_count = len(put_opportunities) + len(call_opportunities)

        return ScreenerRunResult(
            success=True,
            all_symbols_count=len(all_symbols),
            screened_symbols_count=len(high_iv_df),
            raw_opportunities_count=raw_opportunities_count,
            final_opportunities=final_opportunities,
            put_final_opportunities=final_put_opportunities,
            call_final_opportunities=final_call_opportunities,
            diagnostics=diagnostics,
            saved_csv_path=saved_csv_path,
            put_saved_csv_path=put_saved_csv_path,
            call_saved_csv_path=call_saved_csv_path,
        )

    def fetch_watchlist_symbols(
        self,
        api,
        watchlist_name: str,
        fallback: list[str] | None = None,
        public: bool = True,
    ) -> list[str]:
        try:
            symbols = api.get_watchlist(watchlist_name, public=public)
        except Exception as error:
            print(f"Failed to fetch watchlist '{watchlist_name}': {error}")
            symbols = []

        if not symbols:
            if fallback:
                print(
                    f"'{watchlist_name}' watchlist not found, using fallback list of {len(fallback)} symbols"
                )
                return fallback
            print(f"'{watchlist_name}' watchlist not found, skipping")
            return []

        if not isinstance(symbols, list):
            print(
                f"'{watchlist_name}' returned unexpected type ({type(symbols).__name__}); skipping"
            )
            return fallback if fallback else []

        return [
            symbol.strip()
            for symbol in symbols
            if isinstance(symbol, str) and symbol.strip()
        ]

    def get_earnings_within_dte(
        self,
        earnings_date: str | None,
        expiration_date: str,
        today: date | None = None,
    ) -> str:
        if not earnings_date:
            return ""

        try:
            earnings_dt = datetime.strptime(earnings_date, "%Y-%m-%d").date()
            expiration_dt = datetime.strptime(expiration_date, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return ""

        resolved_today = today or date.today()
        return earnings_date if resolved_today <= earnings_dt <= expiration_dt else ""

    def _collect_watchlist_symbols(self, api) -> list[str]:
        all_symbols: list[str] = []
        all_symbols.extend(
            self.fetch_watchlist_symbols(
                api,
                config.WATCHLISTS["sp500"],
                fallback=SP500_FALLBACK,
                public=True,
            )
        )
        all_symbols.extend(
            self.fetch_watchlist_symbols(
                api, config.WATCHLISTS["tasty_ivr"], public=True
            )
        )
        all_symbols.extend(
            self.fetch_watchlist_symbols(
                api, config.WATCHLISTS["nasdaq100"], public=True
            )
        )
        all_symbols.extend(
            self.fetch_watchlist_symbols(
                api,
                config.WATCHLISTS["high_options_volume"],
                public=True,
            )
        )
        return all_symbols

    def _enrich_metrics_with_quotes(
        self,
        metrics_data: dict[str, dict[str, object]],
        quotes_data: dict[str, dict[str, object]],
        snapshot_ts: str | None = None,
        market_open: bool = False,
    ) -> None:
        for symbol, quote in quotes_data.items():
            if symbol in metrics_data and quote:
                if quote.get("last_price") is not None:
                    metrics_data[symbol]["last_price"] = quote.get("last_price")
                if quote.get("volume") is not None:
                    metrics_data[symbol]["volume"] = quote.get("volume")
                    volume_for_filter = self._estimate_full_day_volume(
                        quote.get("volume"),
                        snapshot_ts=snapshot_ts,
                        market_open=market_open,
                    )
                    if volume_for_filter is not None:
                        metrics_data[symbol]["volume_for_filter"] = volume_for_filter
                if quote.get("market_cap") is not None:
                    metrics_data[symbol]["market_cap"] = quote.get("market_cap")
                if quote.get("year_high_price") is not None:
                    metrics_data[symbol]["year_high_price"] = quote.get(
                        "year_high_price"
                    )
                if quote.get("year_low_price") is not None:
                    metrics_data[symbol]["year_low_price"] = quote.get("year_low_price")
                metrics_data[symbol]["is_trading_halted"] = quote.get(
                    "is_trading_halted",
                    False,
                )

    @staticmethod
    def _estimate_full_day_volume(
        volume: object,
        snapshot_ts: str | None,
        market_open: bool,
    ) -> float | None:
        try:
            raw_volume = float(volume)
        except (TypeError, ValueError):
            return None

        if not market_open or not snapshot_ts:
            return raw_volume

        try:
            snapshot_dt = datetime.fromisoformat(snapshot_ts)
        except ValueError:
            return raw_volume

        market_open_time = datetime_time(8, 30)
        market_close_time = datetime_time(15, 0)
        snapshot_time = snapshot_dt.time()

        if snapshot_time <= market_open_time or snapshot_time >= market_close_time:
            return raw_volume

        elapsed_minutes = (
            datetime.combine(snapshot_dt.date(), snapshot_time)
            - datetime.combine(snapshot_dt.date(), market_open_time)
        ).total_seconds() / 60
        regular_session_minutes = 390
        if elapsed_minutes <= 0:
            return raw_volume

        return raw_volume * (regular_session_minutes / elapsed_minutes)

    def _initialize_diagnostics(self) -> dict[str, int]:
        return {
            "total_analyzed": 0,
            "no_quote": 0,
            "no_expirations": 0,
            "no_target_exp": 0,
            "no_chain": 0,
            "no_put_symbols": 0,
            "no_call_symbols": 0,
            "no_option_symbols": 0,
            "no_option_quotes": 0,
            "exceptions": 0,
            "put_reached_evaluation": 0,
            "call_reached_evaluation": 0,
        }

    def _collect_candidate_option_data(
        self,
        api,
        analyzer,
        top_candidates: list[str],
        candidate_quotes: dict[str, dict[str, object]],
        metrics_data: dict[str, dict[str, object]],
        diagnostics: dict[str, int],
    ) -> tuple[dict[str, dict[str, object]], list[str]]:
        candidate_data: dict[str, dict[str, object]] = {}
        all_option_symbols: list[str] = []
        raw_option_symbol_count = 0

        for index, symbol in enumerate(top_candidates, 1):
            print(
                f"   [{index}/{len(top_candidates)}] Fetching chain for {symbol}...",
                end="\r",
            )
            diagnostics["total_analyzed"] += 1

            try:
                quote = candidate_quotes.get(symbol)
                if not quote or not quote["last_price"]:
                    diagnostics["no_quote"] += 1
                    continue

                stock_price = quote["last_price"]
                expirations = api.get_option_expirations(symbol)
                if not expirations:
                    diagnostics["no_expirations"] += 1
                    continue

                target_exp = analyzer.find_target_expiration(expirations)
                if not target_exp:
                    diagnostics["no_target_exp"] += 1
                    continue

                chain = api.get_option_chain(symbol, target_exp["expiration_date"])
                if not chain or not chain.get("strikes"):
                    diagnostics["no_chain"] += 1
                    continue

                symbol_metrics = metrics_data.get(symbol, {})
                expiration_iv = self._get_expiration_iv(
                    symbol_metrics,
                    target_exp["expiration_date"],
                )
                put_symbols, call_symbols, raw_count = self._select_option_symbols(
                    chain=chain,
                    stock_price=stock_price,
                    dte=target_exp.get("days_to_expiration"),
                    expiration_iv=expiration_iv,
                )
                raw_option_symbol_count += raw_count
                if "put" in self.enabled_option_sides and not put_symbols:
                    diagnostics["no_put_symbols"] += 1
                if "call" in self.enabled_option_sides and not call_symbols:
                    diagnostics["no_call_symbols"] += 1
                if not put_symbols and not call_symbols:
                    diagnostics["no_option_symbols"] += 1
                    continue

                candidate_data[symbol] = {
                    "stock_price": stock_price,
                    "target_exp": target_exp,
                    "chain": chain,
                    "put_symbols": put_symbols,
                    "call_symbols": call_symbols,
                    "quote_context": quote,
                }
                all_option_symbols.extend(put_symbols)
                all_option_symbols.extend(call_symbols)

                if config.CHAIN_FETCH_DELAY > 0:
                    time.sleep(config.CHAIN_FETCH_DELAY)

            except Exception as error:
                diagnostics["exceptions"] += 1
                print(f"\n   Error fetching chain for {symbol}: {error}")

        if raw_option_symbol_count > len(all_option_symbols):
            print(
                f"\nPruned option quote universe: {raw_option_symbol_count} -> "
                f"{len(all_option_symbols)} symbols by side and strike range"
            )

        return candidate_data, all_option_symbols

    def _select_option_symbols(
        self,
        chain: dict[str, object],
        stock_price: float,
        dte: object,
        expiration_iv: float | None,
    ) -> tuple[list[str], list[str], int]:
        put_symbols: list[str] = []
        call_symbols: list[str] = []
        raw_count = 0

        put_low, put_high = self._quote_strike_range(
            stock_price=stock_price,
            dte=dte,
            expiration_iv=expiration_iv,
            option_side="put",
        )
        call_low, call_high = self._quote_strike_range(
            stock_price=stock_price,
            dte=dte,
            expiration_iv=expiration_iv,
            option_side="call",
        )

        for strike, strike_data in chain["strikes"].items():
            strike_price = self._to_float(strike)
            if strike_price is None or not isinstance(strike_data, dict):
                continue

            put_symbol = strike_data.get("put_symbol")
            if put_symbol:
                raw_count += 1
                if (
                    "put" in self.enabled_option_sides
                    and put_low <= strike_price <= put_high
                ):
                    put_symbols.append(put_symbol)

            call_symbol = strike_data.get("call_symbol")
            if call_symbol:
                raw_count += 1
                if (
                    "call" in self.enabled_option_sides
                    and call_low <= strike_price <= call_high
                ):
                    call_symbols.append(call_symbol)

        return put_symbols, call_symbols, raw_count

    @staticmethod
    def _get_expiration_iv(
        symbol_metrics: dict[str, object], expiration_date: str
    ) -> float | None:
        expiration_ivs = symbol_metrics.get("option_expiration_ivs")
        if not isinstance(expiration_ivs, dict):
            return None
        return ScreenerRunService._to_float(expiration_ivs.get(expiration_date))

    @staticmethod
    def _quote_strike_range(
        stock_price: float,
        dte: object,
        expiration_iv: float | None,
        option_side: str,
    ) -> tuple[float, float]:
        stock_price_float = float(stock_price)
        if option_side == "put":
            rail_low = stock_price_float * config.PUT_QUOTE_MIN_MONEYNESS
            rail_high = stock_price_float * config.PUT_QUOTE_MAX_MONEYNESS
        else:
            rail_low = stock_price_float * config.CALL_QUOTE_MIN_MONEYNESS
            rail_high = stock_price_float * config.CALL_QUOTE_MAX_MONEYNESS

        dte_float = ScreenerRunService._to_float(dte)
        if expiration_iv is None or dte_float is None or dte_float <= 0:
            return rail_low, rail_high

        expected_move = stock_price_float * expiration_iv * math.sqrt(dte_float / 365)
        if expected_move <= 0:
            return rail_low, rail_high

        otm_move = config.OPTION_QUOTE_EXPECTED_MOVE_MULTIPLIER * expected_move
        atm_buffer = config.OPTION_QUOTE_ATM_BUFFER_EXPECTED_MOVE * expected_move
        if option_side == "put":
            return max(rail_low, stock_price_float - otm_move), min(
                rail_high, stock_price_float + atm_buffer
            )
        return max(rail_low, stock_price_float - atm_buffer), min(
            rail_high, stock_price_float + otm_move
        )

    @staticmethod
    def _to_float(value: object) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _fetch_option_quotes(
        self, api, unique_option_symbols: list[str]
    ) -> dict[str, object]:
        self.print_progress(
            f"Phase 2: Fetching quotes in chunks of {config.OPTION_QUOTE_BATCH_SIZE}"
        )
        all_option_quotes: dict[str, object] = {}
        chunk_size = config.OPTION_QUOTE_BATCH_SIZE
        total_chunks = (len(unique_option_symbols) + chunk_size - 1) // chunk_size

        for chunk_idx in range(total_chunks):
            start_idx = chunk_idx * chunk_size
            end_idx = min(start_idx + chunk_size, len(unique_option_symbols))
            chunk = unique_option_symbols[start_idx:end_idx]

            print(
                f"   Fetching chunk {chunk_idx + 1}/{total_chunks} ({len(chunk)} symbols)...",
                end="\r",
            )

            max_retries = 2
            for attempt in range(max_retries):
                try:
                    chunk_quotes = api.get_option_quotes(chunk)
                    all_option_quotes.update(chunk_quotes)
                    break
                except Exception as error:
                    if attempt < max_retries - 1:
                        print(
                            f"\n   Chunk {chunk_idx + 1} failed (attempt {attempt + 1}/{max_retries}), retrying..."
                        )
                        time.sleep(1.0)
                    else:
                        print(
                            f"\n   Chunk {chunk_idx + 1} failed after {max_retries} attempts: {error}"
                        )

            if chunk_idx < total_chunks - 1 and config.CHAIN_FETCH_DELAY > 0:
                time.sleep(config.CHAIN_FETCH_DELAY)

        print(
            f"\nRetrieved {len(all_option_quotes)} option quotes across {total_chunks} chunk(s)"
        )
        return all_option_quotes

    def _attach_option_quotes(
        self, chain: dict[str, object], all_option_quotes: dict[str, object]
    ) -> None:
        for strike_data in chain["strikes"].values():
            put_symbol = strike_data.get("put_symbol")
            call_symbol = strike_data.get("call_symbol")
            if put_symbol and put_symbol in all_option_quotes:
                strike_data["put"] = all_option_quotes[put_symbol]
            if call_symbol and call_symbol in all_option_quotes:
                strike_data["call"] = all_option_quotes[call_symbol]

    def _evaluate_candidates(
        self,
        analyzer,
        candidate_data: dict[str, dict[str, object]],
        all_option_quotes: dict[str, object],
        metrics_data: dict[str, dict[str, object]],
        diagnostics: dict[str, int],
        opportunities: list[dict[str, object]],
        *,
        option_side: str,
    ) -> None:
        self.print_progress(f"Phase 3: Evaluating {option_side} spread opportunities")

        for index, (symbol, data) in enumerate(candidate_data.items(), 1):
            print(
                f"   [{index}/{len(candidate_data)}] Evaluating {symbol} ({option_side})...",
                end="\r",
            )

            try:
                chain = data["chain"]
                chain["underlying_quote"] = data.get("quote_context") or {}
                self._attach_option_quotes(chain, all_option_quotes)

                has_quotes = any(
                    option_side in strike_data
                    for strike_data in chain["strikes"].values()
                )
                if not has_quotes:
                    diagnostics["no_option_quotes"] += 1
                    continue

                reached_key = f"{option_side}_reached_evaluation"
                diagnostics[reached_key] += 1
                symbol_metrics = metrics_data.get(symbol, {})
                earnings_within_dte = self.get_earnings_within_dte(
                    symbol_metrics.get("earnings_date"),
                    data["target_exp"]["expiration_date"],
                )
                opportunity = analyzer.evaluate_spread(
                    symbol,
                    data["stock_price"],
                    chain,
                    data["target_exp"],
                    earnings_within_dte=earnings_within_dte,
                )
                if opportunity:
                    opportunities.append(opportunity)

            except Exception as error:
                diagnostics["exceptions"] += 1
                print(f"\n   Error evaluating {symbol} ({option_side}): {error}")

    def _print_diagnostics(self, diagnostics: dict[str, int]) -> None:
        print()
        print("=" * 80)
        print("PIPELINE DIAGNOSTICS")
        print("=" * 80)
        print(f"Total symbols analyzed:        {diagnostics['total_analyzed']}")
        print(f"  No quote data:               {diagnostics['no_quote']}")
        print(f"  No expirations:              {diagnostics['no_expirations']}")
        print(f"  No target DTE match:         {diagnostics['no_target_exp']}")
        print(f"  No option chain:             {diagnostics['no_chain']}")
        print(f"  No put symbols:              {diagnostics['no_put_symbols']}")
        print(f"  No call symbols:             {diagnostics['no_call_symbols']}")
        print(f"  No option symbols at all:    {diagnostics['no_option_symbols']}")
        print(f"  No option quotes/greeks:     {diagnostics['no_option_quotes']}")
        print(f"  Exceptions:                  {diagnostics['exceptions']}")
        print("=" * 80)

    def _print_strategy_diagnostics(
        self,
        label: str,
        analyzer,
        reached_evaluation: int,
    ) -> None:
        strategy_rejections = getattr(analyzer, "strategy_rejections_by_symbol", {})
        strategy_rejected_symbols = len(strategy_rejections)
        if strategy_rejected_symbols > 0:
            cause_totals = {
                "delta_bounds": 0,
                "open_interest": 0,
                "short_bid_ask_width": 0,
                "long_bid_ask_width": 0,
                "premium_zero_or_negative": 0,
                "risk_reward": 0,
                "no_long_strike": 0,
            }
            for counters in strategy_rejections.values():
                for key in cause_totals:
                    cause_totals[key] += int(counters.get(key, 0) or 0)

            labels = {
                "delta_bounds": "delta",
                "open_interest": "oi",
                "short_bid_ask_width": "short_ba",
                "long_bid_ask_width": "long_ba",
                "premium_zero_or_negative": "prem",
                "risk_reward": "r/r",
                "no_long_strike": "no_long",
            }
            top_three = sorted(
                [(key, value) for key, value in cause_totals.items() if value > 0],
                key=lambda item: item[1],
                reverse=True,
            )[:3]
            top_three_text = (
                ", ".join(f"{labels[key]}={value}" for key, value in top_three)
                if top_three
                else "none"
            )
            print(
                f"{label} rejects: {strategy_rejected_symbols}/{reached_evaluation} symbols | top causes: {top_three_text}"
            )
        else:
            print(f"{label} rejects: 0/{reached_evaluation} symbols | top causes: none")

    def _print_dte_warning(self, diagnostics: dict[str, int]) -> None:
        if diagnostics["no_target_exp"] <= 0 or diagnostics["total_analyzed"] <= 0:
            return

        dte_pct = (diagnostics["no_target_exp"] / diagnostics["total_analyzed"]) * 100
        if dte_pct > 30:
            print()
            print(
                f"WARNING: {diagnostics['no_target_exp']} symbols ({dte_pct:.0f}%) filtered due to DTE mismatch"
            )
            print(
                f"   Current settings: TARGET_DTE={config.TARGET_DTE} +/- {config.DTE_TOLERANCE} days"
            )
            print("   Consider widening DTE_TOLERANCE or adjusting TARGET_DTE")
