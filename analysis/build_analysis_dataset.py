"""
build_analysis_dataset.py

Builds a normalized analysis dataset by joining opportunity candidates with
trade outcomes (open and closed trades).

Matching strategy (Phase 1 — strict, no fuzzy):
  - Match on: symbol, expiration_date, short_strike, long_strike
  - Prefer trade whose entry_date is within DATE_TOLERANCE_DAYS of the candidate run date
  - match_status values: "exact_match", "missing_match", or "" (rejected candidates)
"""

import csv
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_PATH = PROJECT_ROOT / "opportunities" / "opportunity_candidates.csv"
TRADES_OPEN_PATH = PROJECT_ROOT / "trades" / "trades_open.csv"
TRADES_CLOSED_PATH = PROJECT_ROOT / "trades" / "trades_closed.csv"
OUTPUT_PATH = PROJECT_ROOT / "analysis" / "analysis_dataset.csv"

# Max calendar-day gap between candidate run date and trade entry date.
# 1 day covers same-day trades and trades entered the morning after a late screen.
DATE_TOLERANCE_DAYS = 1

# Output column order: entry-time features first, then match metadata, then outcomes.
OUTPUT_COLUMNS = [
    # --- Candidate identity ---
    "run_id",
    "snapshot_ts",
    "symbol",
    "expiration_date",
    "dte",
    "stock_price",
    "short_strike",
    "long_strike",
    "width",
    # --- Entry-time spread metrics ---
    "premium",
    "premium_per_width",
    "max_profit",
    "max_loss",
    "risk_reward_ratio",
    "ev_score",
    # --- Entry-time option metrics ---
    "short_delta",
    "short_iv",
    "atm_iv",
    "skew_ratio",
    "skew_diff",
    # --- Context ---
    "earnings_within_dte",
    # --- Candidate selection ---
    "candidate_status",
    "selected",
    "rejection_reason_primary",
    "rejection_reason_flags",
    # --- Match metadata ---
    "match_status",
    "trade_status",
    # --- Trade shared fields ---
    "trade_id",
    "entry_date",
    # --- Open trade monitoring fields ---
    "buying_power_used",
    "current_mark",
    "current_pnl",
    "current_pnl_pct",
    "dte_remaining",
    "days_held",
    "short_strike_breached",
    "exit_signal",
    # --- Closed trade outcome fields ---
    "close_date",
    "close_debit",
    "fees_estimated",
    "dte_at_close",
    "profit_loss",
    "profit_loss_pct",
    "profit_pct_of_max",
    "annualized_return",
    "is_estimated_exit",
    "exit_type",
    "exit_notes",
]

# Candidate columns that pass through directly to the output.
_CANDIDATE_PASSTHROUGH = [
    "run_id",
    "snapshot_ts",
    "symbol",
    "expiration_date",
    "dte",
    "stock_price",
    "short_strike",
    "long_strike",
    "width",
    "premium",
    "premium_per_width",
    "max_profit",
    "max_loss",
    "risk_reward_ratio",
    "ev_score",
    "short_delta",
    "short_iv",
    "atm_iv",
    "skew_ratio",
    "skew_diff",
    "earnings_within_dte",
    "candidate_status",
    "selected",
    "rejection_reason_primary",
    "rejection_reason_flags",
]

# Open-trade-specific columns to pull from trades_open.
_OPEN_TRADE_COLUMNS = [
    "buying_power_used",
    "current_mark",
    "current_pnl",
    "current_pnl_pct",
    "dte_remaining",
    "days_held",
    "short_strike_breached",
    "exit_signal",
]

# Closed-trade-specific columns to pull from trades_closed.
_CLOSED_TRADE_COLUMNS = [
    "close_date",
    "close_debit",
    "fees_estimated",
    "dte_at_close",
    "profit_loss",
    "profit_loss_pct",
    "profit_pct_of_max",
    "annualized_return",
    "is_estimated_exit",
    "exit_type",
    "exit_notes",
]


def load_csv(path: str) -> list[dict]:
    """Load a CSV file and return a list of row dicts."""
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _candidate_run_date(run_id: str) -> Optional[date]:
    """
    Parse the calendar date from a run_id string (format: YYYYMMDD_HHMMSS).

    Returns None if the run_id cannot be parsed.
    """
    try:
        return datetime.strptime(run_id[:8], "%Y%m%d").date()
    except (ValueError, TypeError):
        return None


def _normalize_strike(value: str) -> str:
    """
    Normalize a strike price string for reliable comparison.

    Converts "115.0" and "115" to the same canonical float string.
    """
    try:
        return str(float(value))
    except (ValueError, TypeError):
        return (value or "").strip()


def _make_spread_key(
    symbol: str, expiration: str, short_strike: str, long_strike: str
) -> tuple:
    """Build a normalized 4-tuple match key for a spread."""
    return (
        symbol.strip(),
        expiration.strip(),
        _normalize_strike(short_strike),
        _normalize_strike(long_strike),
    )


def _deduplicate_open_trades(rows: list[dict]) -> list[dict]:
    """
    Keep only the latest row per trade_id from trades_open.

    trades_open is appended on every monitoring run, so the same trade_id
    may appear many times with updated current_pnl, dte_remaining, etc.
    The last row in the file is the most recent snapshot.
    """
    latest: dict[str, dict] = {}
    for row in rows:
        latest[row.get("trade_id", "").strip()] = row
    return list(latest.values())


def build_trade_universe(
    open_rows: list[dict], closed_rows: list[dict]
) -> dict[tuple, list[dict]]:
    """
    Build a lookup dict keyed by (symbol, expiration, short_strike, long_strike).

    Each value is a list of matching trade rows (open or closed).
    Each row is tagged with an internal ``_trade_status`` field.
    """
    universe: dict[tuple, list[dict]] = {}

    for row in open_rows:
        row["_trade_status"] = "open"
        key = _make_spread_key(
            row.get("symbol", ""),
            row.get("expiration", ""),
            row.get("short_strike", ""),
            row.get("long_strike", ""),
        )
        universe.setdefault(key, []).append(row)

    for row in closed_rows:
        row["_trade_status"] = "closed"
        key = _make_spread_key(
            row.get("symbol", ""),
            row.get("expiration", ""),
            row.get("short_strike", ""),
            row.get("long_strike", ""),
        )
        universe.setdefault(key, []).append(row)

    return universe


def find_best_trade_match(
    candidate: dict, universe: dict[tuple, list[dict]]
) -> Optional[dict]:
    """
    Find the best matching trade for a selected candidate.

    Steps:
    1. Look up all trades with matching (symbol, expiration, short_strike, long_strike).
    2. Among matches, prefer the first trade whose entry_date is within
       DATE_TOLERANCE_DAYS of the candidate's run date.
    3. Return None if no match is found within tolerance.
    """
    key = _make_spread_key(
        candidate.get("symbol", ""),
        candidate.get("expiration_date", ""),
        candidate.get("short_strike", ""),
        candidate.get("long_strike", ""),
    )
    matches = universe.get(key, [])
    if not matches:
        return None

    run_date = _candidate_run_date(candidate.get("run_id", ""))
    if run_date is None:
        # Cannot apply date filter; return first structural match.
        return matches[0]

    for trade in matches:
        try:
            entry_date = datetime.strptime(
                trade.get("entry_date", "").strip(), "%Y-%m-%d"
            ).date()
            if abs((entry_date - run_date).days) <= DATE_TOLERANCE_DAYS:
                return trade
        except ValueError:
            continue

    # No match within the allowed date window.
    return None


def build_output_row(candidate: dict, trade: Optional[dict], match_status: str) -> dict:
    """
    Construct a single output row by merging candidate fields with trade outcome fields.

    Parameters
    ----------
    candidate:
        Row dict from opportunity_candidates.csv.
    trade:
        Matched trade row dict, or None if no match was found.
    match_status:
        One of "exact_match", "missing_match", or "" (for rejected candidates).
    """
    row: dict = {col: "" for col in OUTPUT_COLUMNS}

    for col in _CANDIDATE_PASSTHROUGH:
        row[col] = candidate.get(col, "")

    row["match_status"] = match_status

    if trade is None:
        return row

    row["trade_status"] = trade.get("_trade_status", "")
    row["trade_id"] = trade.get("trade_id", "")
    row["entry_date"] = trade.get("entry_date", "")

    for col in _OPEN_TRADE_COLUMNS:
        row[col] = trade.get(col, "")

    for col in _CLOSED_TRADE_COLUMNS:
        row[col] = trade.get(col, "")

    return row


def build_analysis_dataset() -> None:
    """
    Build and write the normalized analysis dataset to OUTPUT_PATH.

    Reads candidates, deduplicates open trades (keep latest snapshot per trade_id),
    joins on the 4-key spread identity, and emits one row per candidate with
    match_status and trade outcome columns appended.

    Prints a summary of match outcomes on completion.
    """
    for path in (CANDIDATES_PATH, TRADES_OPEN_PATH, TRADES_CLOSED_PATH):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Required input file not found: {path}")

    candidates = load_csv(CANDIDATES_PATH)
    open_trades = _deduplicate_open_trades(load_csv(TRADES_OPEN_PATH))
    closed_trades = load_csv(TRADES_CLOSED_PATH)

    trade_universe = build_trade_universe(open_trades, closed_trades)

    os.makedirs(OUTPUT_PATH.parent, exist_ok=True)

    exact_matches = 0
    missing_matches = 0
    not_applicable = 0

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()

        for candidate in candidates:
            is_selected = candidate.get("selected", "").strip().lower() == "true"

            if not is_selected:
                # Rejected candidates cannot be reconciled against a trade.
                writer.writerow(build_output_row(candidate, None, ""))
                not_applicable += 1
                continue

            trade = find_best_trade_match(candidate, trade_universe)
            if trade is not None:
                match_status = "exact_match"
                exact_matches += 1
            else:
                match_status = "missing_match"
                missing_matches += 1

            writer.writerow(build_output_row(candidate, trade, match_status))

    total = len(candidates)
    selected_total = exact_matches + missing_matches
    print(f"Analysis dataset written to: {OUTPUT_PATH}")
    print(f"Total candidates processed : {total}")
    print(f"  Rejected (not matched)   : {not_applicable}")
    print(f"  Selected — exact_match   : {exact_matches}")
    print(f"  Selected — missing_match : {missing_matches}")
    if selected_total > 0:
        match_rate = exact_matches / selected_total * 100
        print(f"  Match rate (selected)    : {match_rate:.1f}%")


if __name__ == "__main__":
    build_analysis_dataset()
