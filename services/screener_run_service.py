"""
Application service for the end-to-end spread screening pipeline.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date, datetime

import config
from analysis.ranking_engine import score_opportunities
from api.tastytrade import SP500_FALLBACK
from screener.iv_screener import IVScreener
from screener.spread_analyzer import SpreadAnalyzer
from services.persistence_service import PersistenceService
from services.run_models import ScreenerRunResult
from utils.display import display_opportunities, print_progress


class ScreenerRunService:
    def __init__(
        self,
        screener: IVScreener | None = None,
        analyzer_factory: Callable[..., object] = SpreadAnalyzer,
        scorer: Callable[
            [list[dict[str, object]]], list[dict[str, object]]
        ] = score_opportunities,
        display_opportunities_fn: Callable[
            [list[dict[str, object]]], None
        ] = display_opportunities,
        print_progress_fn: Callable[[str], None] = print_progress,
        opportunities_dir: str = "opportunities",
        persistence_service: PersistenceService | None = None,
    ) -> None:
        self.screener = screener or IVScreener()
        self.analyzer_factory = analyzer_factory
        self.scorer = scorer
        self.display_opportunities = display_opportunities_fn
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
        self._enrich_metrics_with_quotes(metrics_data, quotes_data)

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

        analyzer = self.analyzer_factory(run_id=run_id, snapshot_ts=snapshot_ts)
        opportunities: list[dict[str, object]] = []

        self.print_progress("Fetching quotes for top candidates")
        candidate_quotes = api.get_quotes_batch(top_candidates)

        print(f"Analyzing options chains for {len(top_candidates)} candidates...\n")

        diagnostics = self._initialize_diagnostics()

        self.print_progress("Phase 1: Fetching option chains for all candidates")
        candidate_data, all_put_symbols = self._collect_candidate_option_data(
            api=api,
            analyzer=analyzer,
            top_candidates=top_candidates,
            candidate_quotes=candidate_quotes,
            diagnostics=diagnostics,
        )

        print(f"\nFetched chains for {len(candidate_data)} symbols")
        print(
            f"Found {len(all_put_symbols)} total put options to quote (before de-dupe)"
        )

        if not all_put_symbols:
            print("No put symbols found across all candidates")
        else:
            unique_put_symbols = sorted(set(all_put_symbols))
            print(f"De-duplicated to {len(unique_put_symbols)} unique put options")

            all_option_quotes = self._fetch_option_quotes(api, unique_put_symbols)
            self._evaluate_candidates(
                analyzer=analyzer,
                candidate_data=candidate_data,
                all_option_quotes=all_option_quotes,
                metrics_data=metrics_data,
                diagnostics=diagnostics,
                opportunities=opportunities,
            )

        print("\nCompleted options analysis")
        self._print_diagnostics(diagnostics, analyzer)
        self._print_dte_warning(diagnostics)
        print()

        final_opportunities: list[dict[str, object]] = []
        saved_csv_path: str | None = None
        if opportunities:
            self.print_progress("Filtering and ranking opportunities")
            final_opportunities = analyzer.filter_opportunities(opportunities)
            final_opportunities = self.scorer(final_opportunities)
            self.display_opportunities(final_opportunities)

            if config.AUTO_SAVE_CSV:
                saved_csv_path = self.persistence_service.save_opportunities(
                    final_opportunities,
                    market_open=market_open,
                )
                print(f"Saved to {saved_csv_path}")
        else:
            print("\nNo trade opportunities found matching all criteria")

        return ScreenerRunResult(
            success=True,
            all_symbols_count=len(all_symbols),
            screened_symbols_count=len(high_iv_df),
            raw_opportunities_count=len(opportunities),
            final_opportunities=final_opportunities,
            diagnostics=diagnostics,
            saved_csv_path=saved_csv_path,
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
    ) -> None:
        for symbol, quote in quotes_data.items():
            if symbol in metrics_data and quote:
                if quote.get("last_price") is not None:
                    metrics_data[symbol]["last_price"] = quote.get("last_price")
                if quote.get("volume") is not None:
                    metrics_data[symbol]["volume"] = quote.get("volume")
                if quote.get("market_cap") is not None:
                    metrics_data[symbol]["market_cap"] = quote.get("market_cap")
                metrics_data[symbol]["is_trading_halted"] = quote.get(
                    "is_trading_halted",
                    False,
                )

    def _initialize_diagnostics(self) -> dict[str, int]:
        return {
            "total_analyzed": 0,
            "no_quote": 0,
            "no_expirations": 0,
            "no_target_exp": 0,
            "no_chain": 0,
            "no_put_symbols": 0,
            "no_option_quotes": 0,
            "exceptions": 0,
            "reached_evaluation": 0,
        }

    def _collect_candidate_option_data(
        self,
        api,
        analyzer,
        top_candidates: list[str],
        candidate_quotes: dict[str, dict[str, object]],
        diagnostics: dict[str, int],
    ) -> tuple[dict[str, dict[str, object]], list[str]]:
        candidate_data: dict[str, dict[str, object]] = {}
        all_put_symbols: list[str] = []

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

                put_symbols = [
                    data["put_symbol"]
                    for data in chain["strikes"].values()
                    if data.get("put_symbol")
                ]
                if not put_symbols:
                    diagnostics["no_put_symbols"] += 1
                    continue

                candidate_data[symbol] = {
                    "stock_price": stock_price,
                    "target_exp": target_exp,
                    "chain": chain,
                    "put_symbols": put_symbols,
                }
                all_put_symbols.extend(put_symbols)

                if config.CHAIN_FETCH_DELAY > 0:
                    time.sleep(config.CHAIN_FETCH_DELAY)

            except Exception as error:
                diagnostics["exceptions"] += 1
                print(f"\n   Error fetching chain for {symbol}: {error}")

        return candidate_data, all_put_symbols

    def _fetch_option_quotes(
        self, api, unique_put_symbols: list[str]
    ) -> dict[str, object]:
        self.print_progress(
            f"Phase 2: Fetching quotes in chunks of {config.OPTION_QUOTE_BATCH_SIZE}"
        )
        all_option_quotes: dict[str, object] = {}
        chunk_size = config.OPTION_QUOTE_BATCH_SIZE
        total_chunks = (len(unique_put_symbols) + chunk_size - 1) // chunk_size

        for chunk_idx in range(total_chunks):
            start_idx = chunk_idx * chunk_size
            end_idx = min(start_idx + chunk_size, len(unique_put_symbols))
            chunk = unique_put_symbols[start_idx:end_idx]

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

    def _evaluate_candidates(
        self,
        analyzer,
        candidate_data: dict[str, dict[str, object]],
        all_option_quotes: dict[str, object],
        metrics_data: dict[str, dict[str, object]],
        diagnostics: dict[str, int],
        opportunities: list[dict[str, object]],
    ) -> None:
        self.print_progress("Phase 3: Evaluating spread opportunities")

        for index, (symbol, data) in enumerate(candidate_data.items(), 1):
            print(
                f"   [{index}/{len(candidate_data)}] Evaluating {symbol}...", end="\r"
            )

            try:
                chain = data["chain"]
                for strike_data in chain["strikes"].values():
                    put_symbol = strike_data.get("put_symbol")
                    if put_symbol and put_symbol in all_option_quotes:
                        strike_data["put"] = all_option_quotes[put_symbol]

                has_quotes = any(
                    "put" in strike_data for strike_data in chain["strikes"].values()
                )
                if not has_quotes:
                    diagnostics["no_option_quotes"] += 1
                    continue

                diagnostics["reached_evaluation"] += 1
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
                print(f"\n   Error evaluating {symbol}: {error}")

    def _print_diagnostics(self, diagnostics: dict[str, int], analyzer) -> None:
        print()
        print("=" * 80)
        print("PIPELINE DIAGNOSTICS")
        print("=" * 80)
        print(f"Total symbols analyzed:        {diagnostics['total_analyzed']}")
        print(f"  Reached evaluation:          {diagnostics['reached_evaluation']}")
        print(f"  No quote data:               {diagnostics['no_quote']}")
        print(f"  No expirations:              {diagnostics['no_expirations']}")
        print(f"  No target DTE match:         {diagnostics['no_target_exp']}")
        print(f"  No option chain:             {diagnostics['no_chain']}")
        print(f"  No put symbols:              {diagnostics['no_put_symbols']}")
        print(f"  No option quotes/greeks:     {diagnostics['no_option_quotes']}")
        print(f"  Exceptions:                  {diagnostics['exceptions']}")
        print("=" * 80)

        strategy_rejections = getattr(analyzer, "strategy_rejections_by_symbol", {})
        strategy_rejected_symbols = len(strategy_rejections)
        if strategy_rejected_symbols > 0:
            cause_totals = {
                "delta_bounds": 0,
                "open_interest": 0,
                "short_bid_ask_width": 0,
                "long_bid_ask_width": 0,
                "credit_conservative": 0,
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
                "credit_conservative": "credit",
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
                f"Strategy rejects: {strategy_rejected_symbols}/{diagnostics['reached_evaluation']} symbols | top causes: {top_three_text}"
            )
        else:
            print(
                f"Strategy rejects: 0/{diagnostics['reached_evaluation']} symbols | top causes: none"
            )

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
