"""
Main entry point for options put spread screener.
"""

import argparse
import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from api.tastytrade import TastytradeAPI
from screener.call_spread_analyzer import CallSpreadAnalyzer
from services.position_sync_service import PositionSyncService
from services.screener_run_service import ScreenerRunService
from services.snapshot_service import SnapshotService
from utils import cache
from utils.display import display_summary, print_header, print_progress
from utils.market_hours import get_market_status_display, is_market_open


def _print_position_sync_result(result) -> None:
    if not result.success:
        print(f"X {result.message}")
        return

    print(f"OK Found {result.spreads_count} credit spreads")
    print()
    print(result.display_df.to_string(index=False))
    print()

    if len(result.profit_targets_df) > 0:
        print("=" * 80)
        print(f"PROFIT TARGET ALERTS (>={config.TARGET_PROFIT_PCT}%)")
        print("=" * 80)
        for _, row in result.profit_targets_df.iterrows():
            print(
                f"- {row['symbol']} {row['short_strike']}/{row['long_strike']}: "
                f"{row['current_pnl_pct']:.1f}% profit (${row['current_pnl']:.2f}) - CONSIDER CLOSING"
            )
        print()

    if len(result.dte_warnings_df) > 0:
        print("=" * 80)
        print("DTE WARNINGS (<=21 days)")
        print("=" * 80)
        for _, row in result.dte_warnings_df.iterrows():
            print(
                f"- {row['symbol']} {row['short_strike']}/{row['long_strike']}: "
                f"{row['dte_remaining']} DTE remaining - {row['current_pnl_pct']:.1f}% profit"
            )
        print()

    if len(result.exit_alerts_df) > 0:
        print("=" * 80)
        print("EXIT SIGNALS")
        print("=" * 80)
        for _, row in result.exit_alerts_df.iterrows():
            print(
                f"{row['exit_signal']}: {row['symbol']} {row['short_strike']}/{row['long_strike']} "
                f"Mark ${row['current_mark']:.2f} vs Credit ${row['entry_credit']:.2f} | "
                f"DTE {row['dte_remaining']}"
            )
        print()

    for message in result.closed_trade_messages:
        print(f"OK {message}")

    print(f"OK Saved position data to {result.trades_file}")
    print()


def _print_loss_close_review(result) -> None:
    if len(result.loss_close_review_df) == 0:
        return

    print("=" * 80)
    print(f"LOSS CLOSE REVIEW (>={config.LOSS_CLOSE_REVIEW_PCT}% OF CREDIT)")
    print("=" * 80)
    print(
        "Estimated P/L breached the loss threshold and live option quotes confirmed it."
    )
    print()
    for idx, (_, row) in enumerate(result.loss_close_review_df.iterrows(), start=1):
        print(
            f"{idx}. {row['symbol']} {row['short_strike']}/{row['long_strike']} "
            f"{str(row.get('option_side') or '').upper()} | "
            f"Est P/L {row['current_pnl_pct']:.1f}% (${row['current_pnl']:.2f}) | "
            f"Live P/L {row['live_pnl_pct']:.1f}% (${row['live_pnl']:.2f}) | "
            f"Limit debit ${row['close_limit_price']:.2f}"
        )
    print()


def _normalize_order_text(value) -> str:
    return str(value or "").strip().lower().replace("_", " ")


def _is_active_close_order(order: dict) -> bool:
    terminal_statuses = {
        "cancelled",
        "canceled",
        "expired",
        "filled",
        "rejected",
        "removed",
    }
    status = _normalize_order_text(order.get("status"))
    if status in terminal_statuses:
        return False

    legs = order.get("legs")
    if not isinstance(legs, list):
        return False
    actions = {_normalize_order_text(leg.get("action")) for leg in legs}
    return "buy to close" in actions and "sell to close" in actions


def _order_leg_symbols(order: dict) -> set[str]:
    legs = order.get("legs")
    if not isinstance(legs, list):
        return set()
    return {str(leg.get("symbol") or "").strip() for leg in legs if leg.get("symbol")}


def _find_working_close_order(row, orders: list[dict]) -> dict | None:
    target_symbols = {
        str(row.get("short_option_symbol") or "").strip(),
        str(row.get("long_option_symbol") or "").strip(),
    }
    if "" in target_symbols:
        return None

    for order in orders:
        if not _is_active_close_order(order):
            continue
        if target_symbols.issubset(_order_leg_symbols(order)):
            return order
    return None


def _order_display_value(order: dict, *keys: str, default: str = "") -> str:
    for key in keys:
        value = order.get(key)
        if value not in (None, ""):
            return str(value)
    return default


def _prompt_and_close_loss_candidates(api, result) -> None:
    if len(result.loss_close_review_df) == 0:
        return

    _print_loss_close_review(result)
    recent_orders = api.get_account_orders(statuses=[])
    pending_rows = []
    prompt_rows = []
    for _, row in result.loss_close_review_df.iterrows():
        working_order = _find_working_close_order(row, recent_orders)
        if working_order is None:
            prompt_rows.append(row)
        else:
            pending_rows.append((row, working_order))

    if pending_rows:
        print("=" * 80)
        print("WORKING CLOSE ORDERS")
        print("=" * 80)
        for row, order in pending_rows:
            order_id = _order_display_value(order, "id", "order-id", default="unknown")
            status = _order_display_value(order, "status", default="working")
            price = _order_display_value(order, "price", default="?")
            print(
                f"- {row['symbol']} {row['short_strike']}/{row['long_strike']}: "
                f"loss still confirmed at {row['live_pnl_pct']:.1f}%, "
                f"but close order {order_id} is already {status} at ${price} debit."
            )
        print()

    if not prompt_rows:
        print(
            "No duplicate close orders submitted; review working orders if prices need adjustment."
        )
        print()
        return

    print("Running order dry-runs before asking for approval...")
    dry_run_results = []
    for row in prompt_rows:
        payload = row.get("close_order_payload")
        if not isinstance(payload, dict):
            dry_run_results.append((row, None))
            continue
        dry_run_results.append((row, api.dry_run_order(payload)))

    valid_rows = [
        (row, dry_run) for row, dry_run in dry_run_results if dry_run is not None
    ]
    if not valid_rows:
        print("X No close orders passed dry-run validation. No orders submitted.")
        print()
        return

    invalid_count = len(dry_run_results) - len(valid_rows)
    if invalid_count:
        print(f"X {invalid_count} close order(s) failed dry-run and will be skipped.")
    print(f"{len(valid_rows)} close order(s) passed dry-run.")
    print()
    answer = input("Submit these close orders now? Type YES to submit: ").strip()
    if answer != "YES":
        print("No close orders submitted.")
        print()
        return

    for row, _ in valid_rows:
        payload = row.get("close_order_payload")
        response = api.submit_order(payload)
        if response is None:
            print(
                f"X Failed to submit close order for {row['symbol']} "
                f"{row['short_strike']}/{row['long_strike']}"
            )
            continue
        print(
            f"OK Submitted close order for {row['symbol']} "
            f"{row['short_strike']}/{row['long_strike']} at "
            f"${row['close_limit_price']:.2f} debit"
        )
    print()


def sync_positions(api, *, prompt_for_loss_closes: bool = True):
    """
    Sync current account positions and update trades_open.csv.
    Shows current P&L and alerts for positions at or above the profit target.
    """
    print()
    print("=" * 80)
    print("SYNCING OPEN POSITIONS")
    print("=" * 80)
    print()

    result = PositionSyncService().sync_positions(api)
    _print_position_sync_result(result)
    if prompt_for_loss_closes:
        _prompt_and_close_loss_candidates(api, result)
    return result


def _build_authenticated_api(
    *,
    show_progress: bool = False,
    auth_failure_message: str = "Authentication failed. Please check your credentials.",
) -> TastytradeAPI | None:
    if show_progress:
        print_progress("Authenticating with Tastytrade")

    api = TastytradeAPI()
    if not api.authenticate():
        print(f"X {auth_failure_message}")
        return None
    return api


def _display_market_status(market_open: bool) -> None:
    get_market_status_display()
    print()
    print("=" * 80)
    if market_open:
        print("MARKET STATUS: OPEN")
    else:
        print("MARKET STATUS: CLOSED")
        print("WARNING: Results are indicative only - bid/ask spreads may be stale")
    print("=" * 80)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Options Put Spread Screener")
    parser.add_argument(
        "--clear-cache-all", action="store_true", help="Clear all cached data and exit"
    )
    parser.add_argument(
        "--fresh-day",
        action="store_true",
        help="Clear cache entries from previous days (recommended for morning runs)",
    )
    parser.add_argument(
        "--sync-positions",
        action="store_true",
        help="Sync open positions from account and display alerts",
    )
    parser.add_argument(
        "--weekly-snapshot",
        action="store_true",
        help="Create weekly snapshot of trades and config parameters",
    )
    parser.add_argument(
        "--test-run",
        action="store_true",
        help="Run the screener without creating a trade-review queue.",
    )
    strategy_group = parser.add_mutually_exclusive_group()
    strategy_group.add_argument(
        "--puts-only",
        action="store_true",
        help="Analyze put credit spreads only",
    )
    strategy_group.add_argument(
        "--calls-only",
        action="store_true",
        help="Analyze call credit spreads only",
    )
    args = parser.parse_args()

    if args.clear_cache_all:
        count = cache.clear_all(cache_dir=config.CACHE_DIR)
        print(f"OK Cleared {count} cache files from {config.CACHE_DIR}")
        return

    if args.weekly_snapshot:
        SnapshotService().maybe_backfill_weekly_snapshots()
        return

    start_time = time.time()
    run_started_at = datetime.now()
    run_id = run_started_at.strftime("%Y%m%d_%H%M%S")
    snapshot_ts = run_started_at.isoformat()

    load_dotenv()
    SnapshotService().maybe_backfill_weekly_snapshots()

    if args.fresh_day:
        count = cache.clear_stale_daily(cache_dir=config.CACHE_DIR)
        print(f"OK Cleared {count} stale cache files from previous days")
        print()

    api: TastytradeAPI | None = None
    if args.sync_positions and not args.fresh_day:
        api = _build_authenticated_api(auth_failure_message="Authentication failed")
        if api is None:
            return

        sync_positions(api)
        return

    print_header()

    if api is None:
        api = _build_authenticated_api(show_progress=True)
        if api is None:
            return

    market_open = is_market_open()
    _display_market_status(market_open)
    if args.test_run:
        print("TEST RUN: review-queue capture disabled for this run")
        print()

    enabled_option_sides = ("put", "call")
    if args.puts_only:
        enabled_option_sides = ("put",)
    elif args.calls_only:
        enabled_option_sides = ("call",)

    screener_result = ScreenerRunService(
        call_analyzer_factory=CallSpreadAnalyzer,
        enabled_option_sides=enabled_option_sides,
    ).run(
        api=api,
        run_id=run_id,
        snapshot_ts=snapshot_ts,
        market_open=market_open,
        capture_review_queue=not args.test_run,
    )
    if not screener_result.success:
        return

    sync_positions(api)

    execution_time = time.time() - start_time
    display_summary(
        screener_result.all_symbols_count,
        screener_result.screened_symbols_count,
        screener_result.raw_opportunities_count,
        execution_time,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nX Screening interrupted by user")
        sys.exit(0)
    except Exception as error:
        print(f"\nX Fatal error: {error}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
