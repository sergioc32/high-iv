"""
Main entry point for options put spread screener
"""

import os
import sys
import time
import argparse
import json
import re
from typing import List, Optional
from datetime import date, datetime, timedelta
import pandas as pd
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.tastytrade import TastytradeAPI, SP500_FALLBACK
from screener.iv_screener import IVScreener
from screener.spread_analyzer import SpreadAnalyzer
from utils.display import (
    display_opportunities,
    display_summary,
    print_header,
    print_progress,
)
from analysis.ranking_engine import score_opportunities
from utils import cache
from utils.market_hours import is_market_open, get_market_status_display
import config


def fetch_watchlist_symbols(
    api, watchlist_name: str, fallback: Optional[List[str]] = None, public: bool = True
) -> List[str]:
    """
    Fetch symbols from a watchlist with error handling.

    Parameters:
    api: Authenticated API instance
    watchlist_name (str): Name of the watchlist to fetch
    fallback (list): Optional fallback list if watchlist not found
    public (bool): Whether the watchlist is public

    Returns:
    list: List of symbol strings, or empty list if not found and no fallback
    """
    try:
        symbols = api.get_watchlist(watchlist_name, public=public)
    except Exception as error:
        print(f"⚠ Failed to fetch watchlist '{watchlist_name}': {error}")
        symbols = []

    if not symbols:
        if fallback:
            print(
                f"⚠ '{watchlist_name}' watchlist not found, using fallback list of {len(fallback)} symbols"
            )
            return fallback
        print(f"⚠ '{watchlist_name}' watchlist not found, skipping")
        return []

    if not isinstance(symbols, list):
        print(
            f"⚠ '{watchlist_name}' returned unexpected type ({type(symbols).__name__}); skipping"
        )
        return fallback if fallback else []

    cleaned_symbols = [
        symbol.strip()
        for symbol in symbols
        if isinstance(symbol, str) and symbol.strip()
    ]
    return cleaned_symbols


def get_earnings_within_dte(earnings_date: Optional[str], expiration_date: str) -> str:
    """
    Return earnings date string when earnings falls between today and expiration.

    Parameters:
    earnings_date (Optional[str]): Earnings date in YYYY-MM-DD format
    expiration_date (str): Option expiration date in YYYY-MM-DD format

    Returns:
    str: Earnings date if within DTE window, otherwise empty string
    """
    if not earnings_date:
        return ""

    try:
        earnings_dt = datetime.strptime(earnings_date, "%Y-%m-%d").date()
        expiration_dt = datetime.strptime(expiration_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return ""

    today = date.today()
    return earnings_date if today <= earnings_dt <= expiration_dt else ""


def sync_positions(api):
    """
    Sync current account positions and update trades_open.csv
    Shows current P&L and alerts for positions at/above 50% profit
    """
    print()
    print("=" * 80)
    print("📊 SYNCING OPEN POSITIONS")
    print("=" * 80)
    print()

    # Fetch positions
    positions = api.get_account_positions()

    if not positions:
        print("✗ No positions found or failed to fetch")
        return

    # Parse into spreads
    spreads = api.parse_option_spreads(positions)

    if not spreads:
        print("✗ No option spreads found in account")
        return
    # for testing only, delete after
    # print(f"DEBUG: Raw positions data:")
    # import json
    # print(json.dumps(spreads, indent=2))

    print(f"✓ Found {len(spreads)} put credit spreads")
    print()

    # Display positions
    df = pd.DataFrame(spreads)

    # Ensure numeric fields are numeric for comparisons
    df["current_pnl_pct"] = pd.to_numeric(df.get("current_pnl_pct"), errors="coerce")
    df["dte_remaining"] = pd.to_numeric(df.get("dte_remaining"), errors="coerce")
    df["entry_credit"] = pd.to_numeric(df.get("entry_credit"), errors="coerce")
    df["current_mark"] = pd.to_numeric(df.get("current_mark"), errors="coerce")

    # Add underlying price for breach checks
    symbols = sorted(set(df["symbol"].dropna().tolist()))
    quotes = api.get_quotes_batch(symbols) if symbols else {}
    df["stock_price"] = df["symbol"].map(
        lambda s: (quotes.get(s) or {}).get("last_price")
    )
    df["short_strike_breached"] = df.apply(
        lambda row: (
            row.get("stock_price") is not None
            and row.get("short_strike") is not None
            and row.get("stock_price") <= row.get("short_strike")
        ),
        axis=1,
    )

    def _exit_signal(row) -> str:
        try:
            credit = float(row.get("entry_credit"))
            debit = float(row.get("current_mark"))
        except Exception:
            return "HOLD"

        if credit <= 0:
            return "HOLD"

        breached = bool(row.get("short_strike_breached"))
        dte = row.get("dte_remaining")

        if debit >= config.EXIT_HARD_STOP_MULTIPLE * credit:
            return "CLOSE - HARD STOP"
        if breached and debit >= config.EXIT_STRUCTURAL_MULTIPLE * credit:
            return "CLOSE - STRUCTURAL BREAK"
        if breached and dte is not None and dte <= config.EXIT_GAMMA_RISK_DTE:
            return "ALERT - GAMMA RISK"
        return "HOLD"

    df["exit_signal"] = df.apply(_exit_signal, axis=1)

    # Select columns for display
    display_cols = [
        "symbol",
        "short_strike",
        "long_strike",
        "entry_credit",
        "current_mark",
        "current_pnl",
        "current_pnl_pct",
        "dte_remaining",
        "days_held",
        "exit_signal",
    ]
    display_df = df[display_cols].copy()

    # Rename for readability
    display_df.columns = [
        "Symbol",
        "Short",
        "Long",
        "Entry $",
        "Mark $",
        "P/L $",
        "P/L %",
        "DTE",
        "Days",
        "Exit Signal",
    ]

    print(display_df.to_string(index=False))
    print()

    # Check for profit targets
    profit_targets = df[df["current_pnl_pct"] >= config.TARGET_PROFIT_PCT]

    if len(profit_targets) > 0:
        print("=" * 80)
        print(f"🎯 PROFIT TARGET ALERTS (≥{config.TARGET_PROFIT_PCT}%)")
        print("=" * 80)
        for _, row in profit_targets.iterrows():
            print(
                f"✅ {row['symbol']} {row['short_strike']}/{row['long_strike']}: "
                f"{row['current_pnl_pct']:.1f}% profit (${row['current_pnl']:.2f}) - CONSIDER CLOSING"
            )
        print()

    # Check for 21 DTE approaching
    dte_warnings = df[df["dte_remaining"] <= 21]

    if len(dte_warnings) > 0:
        print("=" * 80)
        print("⏰ DTE WARNINGS (≤21 days)")
        print("=" * 80)
        for _, row in dte_warnings.iterrows():
            print(
                f"⚠️  {row['symbol']} {row['short_strike']}/{row['long_strike']}: "
                f"{row['dte_remaining']} DTE remaining - {row['current_pnl_pct']:.1f}% profit"
            )
        print()

    # Exit signal alerts (non-HOLD)
    exit_alerts = df[df["exit_signal"] != "HOLD"]
    if len(exit_alerts) > 0:
        print("=" * 80)
        print("🚨 EXIT SIGNALS")
        print("=" * 80)
        for _, row in exit_alerts.iterrows():
            print(
                f"{row['exit_signal']}: {row['symbol']} {row['short_strike']}/{row['long_strike']} "
                f"Mark ${row['current_mark']:.2f} vs Credit ${row['entry_credit']:.2f} | "
                f"DTE {row['dte_remaining']}"
            )
        print()

    # Save to CSV and log any closed trades
    trades_file = "trades/trades_open.csv"
    os.makedirs("trades", exist_ok=True)
    # Load previous open trades before overwriting, to detect closures
    prev_df = None
    if os.path.exists(trades_file):
        try:
            prev_df = pd.read_csv(trades_file)
        except Exception:
            prev_df = None

    # Log closed trades (present before, now gone)
    if prev_df is not None and len(prev_df) > 0:
        try:
            log_closed_trades(prev_df, df)
        except Exception as e:
            print(f"⚠️  Failed to log closed trades: {e}")

    # Write current snapshot of open trades
    df.to_csv(trades_file, index=False)
    print(f"✓ Saved position data to {trades_file}")
    print()


def get_week_bounds(day: date):
    """Return Monday-Sunday bounds for the given date."""
    week_start = day - timedelta(days=day.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def get_latest_completed_week_bounds(today: date = None):
    """Return bounds for the latest fully completed Monday-Sunday week."""
    today = today or date.today()
    current_week_start, current_week_end = get_week_bounds(today)
    if today >= current_week_end:
        return current_week_start, current_week_end
    return current_week_start - timedelta(days=7), current_week_start - timedelta(
        days=1
    )


def _snapshot_filename(week_start: date, week_end: date):
    return f"snapshot_{week_start.isoformat()}_{week_end.isoformat()}.json"


def _extract_snapshot_windows(snapshot_dir: str):
    """Read existing snapshot windows from file names and JSON metadata."""
    windows = set()
    if not os.path.isdir(snapshot_dir):
        return windows

    name_pattern = re.compile(
        r"^snapshot_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.json$"
    )

    for filename in os.listdir(snapshot_dir):
        if not filename.startswith("snapshot_") or not filename.endswith(".json"):
            continue

        match = name_pattern.match(filename)
        if match:
            try:
                start = date.fromisoformat(match.group(1))
                end = date.fromisoformat(match.group(2))
                windows.add((start, end))
                continue
            except ValueError:
                pass

        filepath = os.path.join(snapshot_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            window = data.get("window", {})
            start = date.fromisoformat(str(window.get("start_date")))
            end = date.fromisoformat(str(window.get("end_date")))
            windows.add((start, end))
        except Exception:
            continue

    return windows


def _read_earliest_trade_date():
    """Find the earliest date present in trade CSV files."""
    candidates = []
    files_and_cols = [
        ("trades/trades_open.csv", "entry_date"),
        ("trades/trades_closed.csv", "close_date"),
    ]
    for file_path, col in files_and_cols:
        if not os.path.exists(file_path):
            continue
        try:
            df = pd.read_csv(file_path)
        except Exception:
            continue
        if col not in df.columns:
            continue
        parsed = pd.to_datetime(df[col], errors="coerce").dt.date.dropna()
        if not parsed.empty:
            candidates.append(parsed.min())

    if not candidates:
        return None
    return min(candidates)


def create_weekly_snapshot(week_start: date, week_end: date, overwrite: bool = False):
    """Create a weekly snapshot of all trades and config for one Monday-Sunday window."""

    snapshot_dir = "snapshots"
    os.makedirs(snapshot_dir, exist_ok=True)

    snapshot_dt = datetime.now()
    snapshot_file = os.path.join(snapshot_dir, _snapshot_filename(week_start, week_end))
    if os.path.exists(snapshot_file) and not overwrite:
        print(
            f"✓ Snapshot already exists for {week_start} to {week_end}: {snapshot_file}"
        )
        return False

    print()
    print("=" * 80)
    print("📸 CREATING WEEKLY SNAPSHOT")
    print("=" * 80)
    print()

    snapshot_data = {
        "snapshot_date": snapshot_dt.isoformat(),
        "config": {},
        "trades_open": [],
        "trades_closed": [],
        "summary": {},
    }

    snapshot_data["window"] = {
        "type": "calendar_week",
        "start_date": week_start.isoformat(),
        "end_date": week_end.isoformat(),
    }

    # Capture config parameters
    snapshot_data["config"] = {
        "IV_RANK_THRESHOLD": config.IV_RANK_THRESHOLD,
        "TARGET_DTE": config.TARGET_DTE,
        "TARGET_DELTA": config.TARGET_DELTA,
        "LONG_PUT_DELTA": config.LONG_PUT_DELTA,
        "PREFERRED_SPREAD_WIDTH": config.PREFERRED_SPREAD_WIDTH,
        "FALLBACK_SPREAD_WIDTH": config.FALLBACK_SPREAD_WIDTH,
        "MAX_RISK_REWARD_RATIO": config.MAX_RISK_REWARD_RATIO,
        "TARGET_EXIT_DTE": config.TARGET_EXIT_DTE,
        "TARGET_PROFIT_PCT": config.TARGET_PROFIT_PCT,
        "DTE_TOLERANCE": config.DTE_TOLERANCE,
    }

    # Load open trades
    trades_open_file = "trades/trades_open.csv"
    if os.path.exists(trades_open_file):
        try:
            df_open = pd.read_csv(trades_open_file)
            if "entry_date" in df_open.columns:
                entry_dates = pd.to_datetime(
                    df_open["entry_date"], errors="coerce"
                ).dt.date
                df_open = df_open[
                    (entry_dates >= week_start) & (entry_dates <= week_end)
                ]
            snapshot_data["trades_open"] = df_open.to_dict(orient="records")
            print(f"✓ Captured {len(df_open)} open trades (calendar week)")
        except Exception as e:
            print(f"⚠️  Failed to load open trades: {e}")
    else:
        print("⚠️  No open trades file found")

    # Load closed trades
    trades_closed_file = "trades/trades_closed.csv"
    if os.path.exists(trades_closed_file):
        try:
            df_closed = pd.read_csv(trades_closed_file)
            if "close_date" in df_closed.columns:
                close_dates = pd.to_datetime(
                    df_closed["close_date"], errors="coerce"
                ).dt.date
                df_closed = df_closed[
                    (close_dates >= week_start) & (close_dates <= week_end)
                ]
            snapshot_data["trades_closed"] = df_closed.to_dict(orient="records")
            print(f"✓ Captured {len(df_closed)} closed trades (calendar week)")
        except Exception as e:
            print(f"⚠️  Failed to load closed trades: {e}")
    else:
        print("⚠️  No closed trades file found")

    # Calculate summary stats
    snapshot_data["summary"] = {
        "total_open": len(snapshot_data["trades_open"]),
        "total_closed": len(snapshot_data["trades_closed"]),
        "total_trades": len(snapshot_data["trades_open"])
        + len(snapshot_data["trades_closed"]),
    }

    # Write snapshot
    with open(snapshot_file, "w", encoding="utf-8") as f:
        json.dump(snapshot_data, f, indent=2, default=str)

    print(f"✓ Snapshot saved to {snapshot_file}")
    print()
    print("Summary:")
    print(f"  Open trades: {snapshot_data['summary']['total_open']}")
    print(f"  Closed trades: {snapshot_data['summary']['total_closed']}")
    print(f"  Total trades tracked: {snapshot_data['summary']['total_trades']}")
    print()
    return True


def maybe_backfill_weekly_snapshots():
    """Create missing snapshots for completed weeks."""
    latest_week_start, _ = get_latest_completed_week_bounds()
    snapshot_dir = "snapshots"
    existing = _extract_snapshot_windows(snapshot_dir)

    earliest_trade_date = _read_earliest_trade_date()
    if earliest_trade_date:
        start_week_start, _ = get_week_bounds(earliest_trade_date)
    else:
        start_week_start = latest_week_start

    missing_weeks = []
    current = start_week_start
    while current <= latest_week_start:
        current_end = current + timedelta(days=6)
        if (current, current_end) not in existing:
            missing_weeks.append((current, current_end))
        current += timedelta(days=7)

    if not missing_weeks:
        print("✓ Weekly snapshots are up to date")
        return 0

    print(f"↻ Weekly snapshot backfill: {len(missing_weeks)} missing week(s) detected")
    created = 0
    for week_start, week_end in missing_weeks:
        if create_weekly_snapshot(week_start, week_end):
            created += 1
    print(f"✓ Weekly snapshot backfill complete: created {created} snapshot(s)")
    return created


def log_closed_trades(prev_df, current_df):
    """Identify trades closed since last sync and append to trades_closed.csv.
    Uses last known mark as an estimated exit debit when live fills aren’t available.
    Avoids duplicates based on trade_id.
    """
    prev_ids = (
        set(prev_df["trade_id"].astype(str)) if "trade_id" in prev_df.columns else set()
    )
    curr_ids = (
        set(current_df["trade_id"].astype(str))
        if "trade_id" in current_df.columns
        else set()
    )

    closed_ids = sorted(prev_ids - curr_ids)
    if not closed_ids:
        return

    closed_file = "trades/trades_closed.csv"
    os.makedirs("trades", exist_ok=True)

    # Load existing closed file to avoid duplicates
    existing_closed = None
    if os.path.exists(closed_file):
        try:
            existing_closed = pd.read_csv(closed_file)
        except Exception:
            existing_closed = None

    existing_ids = (
        set(existing_closed["trade_id"].astype(str))
        if (existing_closed is not None and "trade_id" in existing_closed.columns)
        else set()
    )

    records = []
    for tid in closed_ids:
        row = prev_df[prev_df["trade_id"].astype(str) == tid]
        if row.empty:
            continue

        r = row.iloc[0]

        def _safe_float(value):
            try:
                if pd.isna(value):
                    return None
                return float(value)
            except Exception:
                return None

        def _normalize_contract_value(
            value: float | None, trade_width: float | None, field_name: str
        ) -> float | None:
            """Normalize dollars-per-contract values and flag suspicious records."""
            if value is None:
                return None

            if trade_width is not None and trade_width > 0:
                width_cap = trade_width * 100

                # Auto-correct common x100 scaling mistake if corrected value is plausible.
                if value > (width_cap * 1.5) and (value / 100) <= (width_cap * 1.5):
                    corrected = value / 100
                    print(
                        f"⚠ Corrected {field_name} for {tid}: {value:.2f} -> {corrected:.2f} "
                        "(possible x100 scaling)"
                    )
                    return corrected

                # Flag extremely large values even if we cannot safely auto-correct.
                if value > (width_cap * 3):
                    print(
                        f"⚠ Suspicious {field_name} for {tid}: {value:.2f} "
                        f"exceeds expected cap ${width_cap:.2f}"
                    )

            return value

        entry_credit_per_contract = _safe_float(r.get("entry_credit"))
        width = _safe_float(r.get("width"))
        buying_power_used = _safe_float(r.get("buying_power_used"))
        exit_debit_per_contract = _safe_float(r.get("current_mark"))

        # Values in trades_open are already dollars per contract; do not scale again.
        entry_credit = _normalize_contract_value(
            entry_credit_per_contract, width, "entry_credit"
        )
        exit_debit_est = _normalize_contract_value(
            exit_debit_per_contract, width, "close_debit"
        )
        dte_at_close = (
            int(r["dte_remaining"])
            if "dte_remaining" in r and pd.notna(r["dte_remaining"])
            else None
        )

        # Compute metrics
        profit_loss = (
            (entry_credit - exit_debit_est)
            if (entry_credit is not None and exit_debit_est is not None)
            else None
        )
        profit_loss_pct = (
            (profit_loss / entry_credit * 100)
            if (profit_loss is not None and entry_credit)
            else None
        )
        max_profit = entry_credit if entry_credit is not None else None
        max_loss = (
            ((width * 100) - entry_credit)
            if (width is not None and entry_credit is not None)
            else None
        )
        if max_loss is not None and max_loss < 0:
            print(
                f"⚠ Skipping invalid closed trade {tid}: "
                f"computed max_loss={max_loss:.2f}"
            )
            continue
        profit_pct_of_max = (
            (profit_loss / max_profit * 100)
            if (profit_loss is not None and max_profit)
            else None
        )

        # Days held
        try:
            entry_date = (
                pd.to_datetime(r["entry_date"]).date()
                if pd.notna(r["entry_date"])
                else None
            )
        except Exception:
            entry_date = None
        close_date = date.today()
        days_held = (close_date - entry_date).days if entry_date else None

        # Annualized return based on buying power used
        annualized_return = None
        if (
            buying_power_used
            and profit_loss is not None
            and days_held
            and days_held > 0
        ):
            annualized_return = (
                (profit_loss / buying_power_used) * (365 / days_held) * 100
            )

        # Estimate fees: $1 to open + $1 to close = $2 total
        fees_estimated = 2.0

        record = {
            "trade_id": tid,
            "symbol": r.get("symbol"),
            "entry_date": r.get("entry_date"),
            "close_date": close_date.isoformat(),
            "short_strike": r.get("short_strike"),
            "long_strike": r.get("long_strike"),
            "width": width,
            "entry_credit": entry_credit,
            "close_debit": exit_debit_est,
            "fees_estimated": fees_estimated,
            "dte_at_close": dte_at_close,
            "days_held": days_held,
            "profit_loss": round(profit_loss, 2) if profit_loss is not None else None,
            "profit_loss_pct": round(profit_loss_pct, 2)
            if profit_loss_pct is not None
            else None,
            "max_profit": max_profit,
            "max_loss": round(max_loss, 2) if max_loss is not None else None,
            "profit_pct_of_max": round(profit_pct_of_max, 2)
            if profit_pct_of_max is not None
            else None,
            "annualized_return": round(annualized_return, 2)
            if annualized_return is not None
            else None,
            "is_estimated_exit": True,
            "exit_type": "api_detection",
            "exit_notes": "",
        }

        # Skip if already logged
        if tid not in existing_ids:
            records.append(record)

    if not records:
        return

    # Append to CSV, preserving header
    new_df = pd.DataFrame(records)
    if (
        os.path.exists(closed_file)
        and existing_closed is not None
        and len(existing_closed) >= 0
    ):
        combined = pd.concat([existing_closed, new_df], ignore_index=True)
        combined.to_csv(closed_file, index=False)
    else:
        # Ensure header matches existing schema
        cols = [
            "trade_id",
            "symbol",
            "entry_date",
            "close_date",
            "short_strike",
            "long_strike",
            "width",
            "entry_credit",
            "close_debit",
            "fees_estimated",
            "dte_at_close",
            "days_held",
            "profit_loss",
            "profit_loss_pct",
            "max_profit",
            "max_loss",
            "profit_pct_of_max",
            "annualized_return",
            "is_estimated_exit",
            "exit_type",
            "exit_notes",
        ]
        new_df = new_df.reindex(columns=cols)
        new_df.to_csv(closed_file, index=False)

    print(f"✓ Logged {len(records)} closed trade(s) to {closed_file}")


def main():
    # Parse command line arguments
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
    args = parser.parse_args()

    # Handle cache clearing
    if args.clear_cache_all:
        count = cache.clear_all(cache_dir=config.CACHE_DIR)
        print(f"✓ Cleared {count} cache files from {config.CACHE_DIR}")
        return

    # Handle weekly snapshot
    if args.weekly_snapshot:
        maybe_backfill_weekly_snapshots()
        return

    start_time = time.time()
    run_started_at = datetime.now()
    run_id = run_started_at.strftime("%Y%m%d_%H%M%S")
    snapshot_ts = run_started_at.isoformat()

    # Load environment variables
    load_dotenv()
    maybe_backfill_weekly_snapshots()
    # Handle fresh-day or sync-positions
    if args.fresh_day or args.sync_positions:
        if args.fresh_day:
            count = cache.clear_stale_daily(cache_dir=config.CACHE_DIR)
            print(f"✓ Cleared {count} stale cache files from previous days")
            print()

        # Authenticate and sync positions
        api = TastytradeAPI()
        if not api.authenticate():
            print("✗ Authentication failed")
            return

        sync_positions(api)

        # If only syncing positions, exit here
        if args.sync_positions and not args.fresh_day:
            return

        # Continue to screener if --fresh-day
        if args.fresh_day:
            print("Continuing to opportunity screener...")
            print()

    print_header()

    # Initialize API client
    print_progress("Authenticating with Tastytrade")
    api = TastytradeAPI()

    # api.debug = True

    if not api.authenticate():
        print("✗ Authentication failed. Please check your credentials.")
        return

    # Discover available watchlists
    # Check market hours and display status
    market_open = is_market_open()
    get_market_status_display()

    print()
    print("=" * 80)
    if market_open:
        print("🔔 MARKET STATUS: OPEN")
    else:
        print("🔕 MARKET STATUS: CLOSED")
        print("⚠  Results are indicative only - bid/ask spreads may be stale")
    print("=" * 80)
    print()

    # print_progress("Discovering available watchlists")
    # watchlists = api.list_watchlists()

    # print("✓ Available watchlists:")
    # for wl in watchlists:
    #     print(f"  - {wl['name']} (id: {wl['watchlist_id']})")

    # Step 1: Get watchlist symbols
    print_progress(
        "Fetching watchlist symbols for (SPY,IVR,NAS100,High Options Volume)"
    )

    all_symbols = []

    # Fetch watchlists with error handling
    all_symbols.extend(
        fetch_watchlist_symbols(
            api, config.WATCHLISTS["sp500"], fallback=SP500_FALLBACK, public=True
        )
    )
    all_symbols.extend(
        fetch_watchlist_symbols(api, config.WATCHLISTS["tasty_ivr"], public=True)
    )
    all_symbols.extend(
        fetch_watchlist_symbols(api, config.WATCHLISTS["nasdaq100"], public=True)
    )
    all_symbols.extend(
        fetch_watchlist_symbols(
            api, config.WATCHLISTS["high_options_volume"], public=True
        )
    )

    print(
        f"✓ Retrieved {len(all_symbols)} symbols from watchlists before de-duplication"
    )

    # Get Tasty Default watchlist (public) with fallback
    # tasty_default_symbols = api.get_watchlist('tasty default', public=True)
    # if not tasty_default_symbols:
    #     print(f"⚠ Tasty Default watchlist not found, skipping")
    # else:
    #     all_symbols.extend(tasty_default_symbols)

    # Remove duplicates
    all_symbols = list(set(all_symbols))
    # Remove manually excluded symbols
    # if config.EXCLUDE_SYMBOLS:
    #     before = len(all_symbols)
    #     all_symbols = [s for s in all_symbols if s not in config.EXCLUDE_SYMBOLS]
    #     removed = before - len(all_symbols)
    #     if removed:
    #         print(f"⚠ Excluded {removed} symbols via EXCLUDE_SYMBOLS: {config.EXCLUDE_SYMBOLS}")

    print(f"✓ Total symbols to screen: {len(all_symbols)}")

    if not all_symbols:
        print("✗ No symbols found in watchlists")
        return

    # Step 2: Get market metrics and screen by IV Rank
    print_progress("Fetching market metrics (IV Rank, IV Percentile)")

    # Batch request with rate limiting
    metrics_data = api.batch_request_with_delay(all_symbols, batch_size=100, delay=1.0)

    if not metrics_data:
        print("✗ Failed to retrieve market metrics")
        return

    # Enrich metrics with quote-based liquidity fields
    print_progress("Fetching quotes for liquidity filters")
    quotes_data = api.get_quotes_batch(all_symbols)
    for symbol, quote in quotes_data.items():
        if symbol in metrics_data and quote:
            if quote.get("last_price") is not None:
                metrics_data[symbol]["last_price"] = quote.get("last_price")
            if quote.get("volume") is not None:
                metrics_data[symbol]["volume"] = quote.get("volume")
            if quote.get("market_cap") is not None:
                metrics_data[symbol]["market_cap"] = quote.get("market_cap")
            metrics_data[symbol]["is_trading_halted"] = quote.get(
                "is_trading_halted", False
            )

    # Screen by IV Rank + liquidity guards
    print_progress("Screening by IV Rank")
    screener = IVScreener()
    high_iv_df = screener.filter_by_iv_rank(metrics_data)
    # high_iv_df = []
    if len(high_iv_df) == 0:
        print("✗ No stocks found after IV Rank and liquidity filters")
        return

    # Display screening results
    screener.display_screening_results(high_iv_df, max_display=20)

    # Get top candidates for options analysis
    top_candidates = screener.get_top_candidates(high_iv_df)

    print(f"\n⟳ Analyzing options chains for top {len(top_candidates)} candidates...")
    print("   (This may take a few minutes)\n")

    # Step 3: Analyze options chains for each candidate
    analyzer = SpreadAnalyzer(run_id=run_id, snapshot_ts=snapshot_ts)
    opportunities = []

    print_progress("Fetching quotes for top candidates")
    candidate_quotes = api.get_quotes_batch(top_candidates)

    print(f"⟳ Analyzing options chains for {len(top_candidates)} candidates...\n")

    # Diagnostic counters
    diagnostics = {
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

    print_progress("Phase 1: Fetching option chains for all candidates")

    # PHASE 1: Gather all chains and identify all put symbols
    candidate_data = {}  # Will store all data per symbol
    all_put_symbols = []  # Will collect ALL put symbols across ALL candidates

    for i, symbol in enumerate(top_candidates, 1):
        print(
            f"   [{i}/{len(top_candidates)}] Fetching chain for {symbol}...", end="\r"
        )
        diagnostics["total_analyzed"] += 1

        try:
            # Get current stock price from batch data
            quote = candidate_quotes.get(symbol)
            if not quote or not quote["last_price"]:
                diagnostics["no_quote"] += 1
                continue

            stock_price = quote["last_price"]

            # Get option expirations
            expirations = api.get_option_expirations(symbol)
            if not expirations:
                diagnostics["no_expirations"] += 1
                continue

            # Find target expiration
            target_exp = analyzer.find_target_expiration(expirations)
            if not target_exp:
                diagnostics["no_target_exp"] += 1
                continue

            # Get options chain for target expiration (returns option symbols)
            chain = api.get_option_chain(symbol, target_exp["expiration_date"])
            if not chain or not chain.get("strikes"):
                diagnostics["no_chain"] += 1
                continue

            # Extract all put symbols from the chain
            put_symbols = [
                data["put_symbol"]
                for data in chain["strikes"].values()
                if data.get("put_symbol")
            ]
            if not put_symbols:
                diagnostics["no_put_symbols"] += 1
                continue

            # Store everything for this symbol
            candidate_data[symbol] = {
                "stock_price": stock_price,
                "target_exp": target_exp,
                "chain": chain,
                "put_symbols": put_symbols,
            }

            # Add this symbol's puts to the master list
            all_put_symbols.extend(put_symbols)

            if config.CHAIN_FETCH_DELAY > 0:
                time.sleep(config.CHAIN_FETCH_DELAY)  # Rate limiting for chain fetches

        except Exception as e:
            diagnostics["exceptions"] += 1
            print(f"\n   ✗ Error fetching chain for {symbol}: {e}")
            continue

    print(f"\n✓ Fetched chains for {len(candidate_data)} symbols")
    print(f"✓ Found {len(all_put_symbols)} total put options to quote (before de-dupe)")

    if not all_put_symbols:
        print("✗ No put symbols found across all candidates")
    else:
        # De-duplicate option symbols
        unique_put_symbols = sorted(set(all_put_symbols))
        print(f"✓ De-duplicated to {len(unique_put_symbols)} unique put options")

        # PHASE 2: Chunked batch calls for option quotes with retry
        print_progress(
            f"Phase 2: Fetching quotes in chunks of {config.OPTION_QUOTE_BATCH_SIZE}"
        )

        all_option_quotes = {}
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

            # Retry logic for each chunk
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    chunk_quotes = api.get_option_quotes(chunk)
                    all_option_quotes.update(chunk_quotes)
                    break  # Success, exit retry loop
                except Exception as e:
                    if attempt < max_retries - 1:
                        print(
                            f"\n   ⚠️  Chunk {chunk_idx + 1} failed (attempt {attempt + 1}/{max_retries}), retrying..."
                        )
                        time.sleep(1.0)  # Brief pause before retry
                    else:
                        print(
                            f"\n   ✗ Chunk {chunk_idx + 1} failed after {max_retries} attempts: {e}"
                        )

            # Small delay between chunks to avoid rate limiting
            if chunk_idx < total_chunks - 1 and config.CHAIN_FETCH_DELAY > 0:
                time.sleep(config.CHAIN_FETCH_DELAY)

        print(
            f"\n✓ Retrieved {len(all_option_quotes)} option quotes across {total_chunks} chunk(s)"
        )

        # PHASE 3: Merge quotes back into chains and evaluate spreads
        print_progress("Phase 3: Evaluating spread opportunities")

        for i, (symbol, data) in enumerate(candidate_data.items(), 1):
            print(f"   [{i}/{len(candidate_data)}] Evaluating {symbol}...", end="\r")

            try:
                chain = data["chain"]

                # Merge option quotes back into chain structure
                for strike, strike_data in chain["strikes"].items():
                    put_symbol = strike_data.get("put_symbol")
                    if put_symbol and put_symbol in all_option_quotes:
                        strike_data["put"] = all_option_quotes[put_symbol]

                # Check if we got any valid quotes
                has_quotes = any(
                    "put" in strike_data for strike_data in chain["strikes"].values()
                )

                if not has_quotes:
                    diagnostics["no_option_quotes"] += 1
                    continue

                # Evaluate put spread opportunity
                diagnostics["reached_evaluation"] += 1
                symbol_metrics = metrics_data.get(symbol, {})
                earnings_within_dte = get_earnings_within_dte(
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

            except Exception as e:
                diagnostics["exceptions"] += 1
                print(f"\n   ✗ Error evaluating {symbol}: {e}")
                continue

    print("\n✓ Completed options analysis")

    # Print diagnostic summary
    print()
    print("=" * 80)
    print("📊 PIPELINE DIAGNOSTICS")
    print("=" * 80)
    print(f"Total symbols analyzed:        {diagnostics['total_analyzed']}")
    print(f"  ✓ Reached evaluation:        {diagnostics['reached_evaluation']}")
    print(f"  ✗ No quote data:             {diagnostics['no_quote']}")
    print(f"  ✗ No expirations:            {diagnostics['no_expirations']}")
    print(f"  ✗ No target DTE match:       {diagnostics['no_target_exp']}")
    print(f"  ✗ No option chain:           {diagnostics['no_chain']}")
    print(f"  ✗ No put symbols:            {diagnostics['no_put_symbols']}")
    print(f"  ✗ No option quotes/greeks:   {diagnostics['no_option_quotes']}")
    print(f"  ✗ Exceptions:                {diagnostics['exceptions']}")
    print("=" * 80)

    # One-line strategy rejection summary (post-evaluation filters)
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
            "delta_bounds": "Δ",
            "open_interest": "oi",
            "short_bid_ask_width": "short_ba",
            "long_bid_ask_width": "long_ba",
            "credit_conservative": "credit",
            "premium_zero_or_negative": "prem",
            "risk_reward": "r/r",
            "no_long_strike": "no_long",
        }
        top_three = sorted(
            [(k, v) for k, v in cause_totals.items() if v > 0],
            key=lambda item: item[1],
            reverse=True,
        )[:3]
        top_three_text = (
            ", ".join(f"{labels[key]}={value}" for key, value in top_three)
            if top_three
            else "none"
        )
        print(
            f"📉 Strategy rejects: {strategy_rejected_symbols}/{diagnostics['reached_evaluation']} symbols | top causes: {top_three_text}"
        )
    else:
        print(
            f"📉 Strategy rejects: 0/{diagnostics['reached_evaluation']} symbols | top causes: none"
        )

    # Alert if DTE filtering is significant bottleneck
    if diagnostics["no_target_exp"] > 0:
        dte_pct = (diagnostics["no_target_exp"] / diagnostics["total_analyzed"]) * 100
        if dte_pct > 30:  # Alert if >30% filtered by DTE
            print()
            print(
                f"⚠️  WARNING: {diagnostics['no_target_exp']} symbols ({dte_pct:.0f}%) filtered due to DTE mismatch"
            )
            print(
                f"   Current settings: TARGET_DTE={config.TARGET_DTE} ± {config.DTE_TOLERANCE} days"
            )
            print("   Consider widening DTE_TOLERANCE or adjusting TARGET_DTE")

    print()

    # Step 4: Filter and rank opportunities
    if opportunities:
        print_progress("Filtering and ranking opportunities")
        final_opportunities = analyzer.filter_opportunities(opportunities)

        # Display results
        final_opportunities = score_opportunities(final_opportunities)
        display_opportunities(final_opportunities)

        # Auto-save to CSV if enabled
        if config.AUTO_SAVE_CSV:
            df = pd.DataFrame(final_opportunities)
            preferred_order = [
                "symbol",
                "stock_price",
                "short_strike",
                "long_strike",
                "width",
                "premium",
                "max_loss",
                "risk_reward_ratio",
                "dte",
                "expiration_date",
                "earnings_within_dte",
                "skew_ratio",
                "skew_diff",
                "short_iv",
                "atm_iv",
            ]
            for col in preferred_order:
                if col not in df.columns:
                    df[col] = ""
            remaining_cols = [c for c in df.columns if c not in preferred_order]
            df = df[preferred_order + remaining_cols]
            # Add indicative suffix if market is closed
            suffix = "_indicative" if not market_open else ""
            filename = f"opportunities_{time.strftime('%Y%m%d_%H%M%S')}{suffix}.csv"
            filepath = os.path.join("opportunities", filename)
            os.makedirs("opportunities", exist_ok=True)
            df.to_csv(filepath, index=False)
            print(f"✓ Saved to {filepath}")
    else:
        print("\n✗ No trade opportunities found matching all criteria")

    # Display summary
    execution_time = time.time() - start_time
    display_summary(
        len(all_symbols), len(high_iv_df), len(opportunities), execution_time
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✗ Screening interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
