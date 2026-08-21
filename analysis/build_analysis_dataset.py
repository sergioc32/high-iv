"""
build_analysis_dataset.py

Builds a normalized analysis dataset by joining opportunity candidates with
trade outcomes (open and closed trades).

Matching strategy:
    - First pass exact match on: symbol, expiration_date, short_strike, long_strike.
    - Fallback adjusted match for manual execution tweaks using:
        symbol + expiration + entry_date tolerance + same width, then closest strikes.
    - match_status values: "exact_match", "adjusted_match", "missing_match", or ""
        (rejected candidates).
"""

import csv
import glob
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from utils.analytics_fields import MARKET_CONTEXT_FIELDS  # noqa: E402

CANDIDATES_PATH = PROJECT_ROOT / "opportunities" / "opportunity_candidates.csv"
TRADES_OPEN_PATH = PROJECT_ROOT / "trades" / "trades_open.csv"
TRADES_CLOSED_PATH = PROJECT_ROOT / "trades" / "trades_closed.csv"
OUTPUT_PATH = PROJECT_ROOT / "analysis" / "analysis_dataset.csv"
DAILY_OPPORTUNITIES_GLOBS = (
    str(PROJECT_ROOT / "opportunities" / "opportunities_*.csv"),
    str(PROJECT_ROOT / "opportunities" / "put_spread_opportunities_*.csv"),
    str(PROJECT_ROOT / "opportunities" / "call_spread_opportunities_*.csv"),
)
REVIEW_QUEUE_GLOB = str(
    PROJECT_ROOT
    / getattr(config, "REVIEW_QUEUE_DIR", "opportunities_review")
    / "review_queue_*.csv"
)

# Max calendar-day gap between candidate run date and trade entry date.
# A wider window captures manual execution timing differences while preserving
# symbol/expiration/width and strike proximity constraints.
DATE_TOLERANCE_DAYS = 7

# Output column order: entry-time features first, then match metadata, then outcomes.
OUTPUT_COLUMNS = [
    # --- Candidate identity ---
    "run_id",
    "snapshot_ts",
    "strategy_version",
    "strategy_id",
    "strategy_family",
    "option_side",
    "directional_bias",
    "short_leg_type",
    "long_leg_type",
    "symbol",
    *MARKET_CONTEXT_FIELDS,
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
    # --- Candidate scoring context ---
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
    "review_decision",
    "review_decision_reason",
    "review_decision_note",
    "review_queue_file",
    "review_queue_row",
    # --- Candidate selection ---
    "candidate_status",
    "selected",
    "rejection_reason_primary",
    "rejection_reason_flags",
    "anchor_vs_shift_status",
    "shift_steps_from_anchor",
    # --- Match metadata ---
    "match_status",
    "trade_status",
    "execution_alignment",
    "shift_direction",
    "trade_only_reason",
    "short_strike_shift",
    "long_strike_shift",
    "was_in_daily_opportunities_file",
    "daily_opportunity_match_type",
    "daily_opportunity_file",
    "daily_opportunity_row",
    "daily_short_strike",
    "daily_long_strike",
    "daily_short_strike_shift",
    "daily_long_strike_shift",
    # --- Trade shared fields ---
    "trade_id",
    "entry_date",
    "executed_short_strike",
    "executed_long_strike",
    "executed_width",
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
    "close_debit_estimated",
    "close_debit_actual",
    "actual_exit_found",
    "exit_price_source",
    "close_fill_timestamp",
    "close_order_id",
    "match_confidence",
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
    "strategy_version",
    "strategy_id",
    "strategy_family",
    "option_side",
    "directional_bias",
    "short_leg_type",
    "long_leg_type",
    "symbol",
    *MARKET_CONTEXT_FIELDS,
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
    "anchor_vs_shift_status",
    "shift_steps_from_anchor",
]

_DAILY_OPPORTUNITY_PASSTHROUGH = [
    "strategy_version",
    "strategy_id",
    "option_side",
    "directional_bias",
    *MARKET_CONTEXT_FIELDS,
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
    "close_debit_estimated",
    "close_debit_actual",
    "actual_exit_found",
    "exit_price_source",
    "close_fill_timestamp",
    "close_order_id",
    "match_confidence",
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

CURRENT_STRATEGY_VERSION = getattr(config, "STRATEGY_VERSION", "v2_dynamic")
LEGACY_STRATEGY_VERSION = getattr(config, "LEGACY_STRATEGY_VERSION", "v1_conservative")
STRATEGY_VERSION_CUTOFF_DATE = getattr(
    config, "STRATEGY_VERSION_CUTOFF_DATE", "2026-04-09"
)


def _parse_date(value: str) -> date | None:
    """Parse ISO-like date/datetime text into date object."""
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _parse_config_cutoff_date() -> date | None:
    """Parse configured strategy-version cutover date."""
    raw = (STRATEGY_VERSION_CUTOFF_DATE or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _resolve_strategy_version_for_date(event_date: date | None) -> str:
    """Resolve strategy version by configured cutover date."""
    if event_date is None:
        return CURRENT_STRATEGY_VERSION

    cutoff_date = _parse_config_cutoff_date()
    if cutoff_date is None:
        return CURRENT_STRATEGY_VERSION

    if event_date < cutoff_date:
        return LEGACY_STRATEGY_VERSION
    return CURRENT_STRATEGY_VERSION


def _candidate_snapshot_date(candidate: dict) -> date | None:
    """Return candidate snapshot date when available."""
    snapshot_ts = (candidate.get("snapshot_ts") or "").strip()
    if not snapshot_ts:
        return None
    return _parse_date(snapshot_ts)


def _candidate_strategy_version(candidate: dict) -> str:
    """Resolve candidate strategy version with backward-compatible fallback."""
    explicit_version = (candidate.get("strategy_version") or "").strip()
    if explicit_version:
        return explicit_version

    snapshot_date = _candidate_snapshot_date(candidate)
    if snapshot_date is not None:
        return _resolve_strategy_version_for_date(snapshot_date)

    run_date = _candidate_run_date(candidate.get("run_id", ""))
    return _resolve_strategy_version_for_date(run_date)


def load_csv(path: str) -> list[dict]:
    """Load a CSV file and return a list of row dicts."""
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _candidate_run_date(run_id: str) -> date | None:
    """
    Parse the calendar date from a run_id string (format: YYYYMMDD_HHMMSS).

    Returns None if the run_id cannot be parsed.
    """
    try:
        return datetime.strptime(run_id[:8], "%Y%m%d").date()
    except (ValueError, TypeError):
        return None


def _min_candidate_run_date(candidates: list[dict]) -> date | None:
    """Return the earliest run date present in the candidate log."""
    dates: list[date] = []
    for row in candidates:
        run_date = _candidate_run_date(row.get("run_id", ""))
        if run_date is not None:
            dates.append(run_date)
    return min(dates) if dates else None


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


def _make_symbol_expiration_key(symbol: str, expiration: str) -> tuple[str, str]:
    """Build a normalized (symbol, expiration) key."""
    return (symbol.strip(), expiration.strip())


def _make_review_queue_key(
    *,
    run_id: str,
    snapshot_ts: str,
    strategy_id: str,
    symbol: str,
    expiration_date: str,
    short_strike: str,
    long_strike: str,
) -> tuple[str, str, str, str, str, str, str]:
    """Build a stable identity key for review-queue decisions."""
    return (
        run_id.strip(),
        snapshot_ts.strip(),
        strategy_id.strip(),
        symbol.strip(),
        expiration_date.strip(),
        _normalize_strike(short_strike),
        _normalize_strike(long_strike),
    )


def _daily_opportunity_run_id(filename: str) -> str:
    """Extract run id from a daily opportunities filename when present."""
    match = re.search(
        r"(?:(?:put|call)_spread_)?opportunities_(\d{8}_\d{6})",
        filename or "",
    )
    return match.group(1) if match else ""


def _daily_opportunity_run_datetime(filename: str) -> datetime | None:
    """Parse embedded run timestamp from a daily opportunities filename."""
    run_id = _daily_opportunity_run_id(filename)
    if not run_id:
        return None
    try:
        return datetime.strptime(run_id, "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def _parse_snapshot_datetime(value: str) -> datetime | None:
    """Parse snapshot timestamp text into datetime when possible."""
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _trade_expiration(row: dict) -> str:
    """Return expiration value from trade rows across schema variants."""
    expiration = (row.get("expiration") or row.get("expiration_date") or "").strip()
    if expiration:
        return expiration

    # Fallback for legacy trade rows where expiration column is blank but trade_id embeds it.
    trade_id = (row.get("trade_id") or "").strip()
    if trade_id:
        date_tokens = re.findall(r"\d{4}-\d{2}-\d{2}", trade_id)
        if len(date_tokens) >= 2:
            return date_tokens[1]
        if len(date_tokens) == 1:
            return date_tokens[0]

    return ""


def _parse_float_or_none(value: str) -> float | None:
    """Parse numeric text to float, returning None for blanks/invalid text."""
    try:
        return float((value or "").strip())
    except (ValueError, TypeError):
        return None


def _compute_shift_fields(candidate: dict, trade: dict) -> tuple[str, str, str, str]:
    """Compute strike shift metadata between candidate and executed trade."""
    candidate_short = _parse_float_or_none(candidate.get("short_strike", ""))
    candidate_long = _parse_float_or_none(candidate.get("long_strike", ""))
    executed_short = _parse_float_or_none(trade.get("short_strike", ""))
    executed_long = _parse_float_or_none(trade.get("long_strike", ""))

    if (
        candidate_short is None
        or candidate_long is None
        or executed_short is None
        or executed_long is None
    ):
        return "", "", "", "unknown"

    short_shift = executed_short - candidate_short
    long_shift = executed_long - candidate_long

    if short_shift == 0 and long_shift == 0:
        direction = "none"
    elif short_shift < 0 and long_shift < 0:
        direction = "otm_shift"
    elif short_shift > 0 and long_shift > 0:
        direction = "itm_shift"
    else:
        direction = "mixed_shift"

    return (
        f"{short_shift:.4f}",
        f"{long_shift:.4f}",
        ("shifted" if direction != "none" else "exact"),
        direction,
    )


def _load_daily_opportunities_index() -> dict[date, list[dict]]:
    """Load daily opportunities files and index rows by file date."""
    index: dict[date, list[dict]] = {}
    seen_paths: set[str] = set()
    matched_paths: list[str] = []
    for pattern in DAILY_OPPORTUNITIES_GLOBS:
        for path in glob.glob(pattern):
            if path in seen_paths:
                continue
            seen_paths.add(path)
            matched_paths.append(path)

    for path in sorted(matched_paths):
        filename = os.path.basename(path)
        match = re.search(
            r"(?:(?:put|call)_spread_)?opportunities_(\d{8})_\d+.*\.csv$",
            filename,
        )
        if not match:
            continue

        try:
            file_date = datetime.strptime(match.group(1), "%Y%m%d").date()
        except ValueError:
            continue

        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row_index, row in enumerate(reader, start=1):
                row["_source_file"] = filename
                row["_row_index"] = str(row_index)
                index.setdefault(file_date, []).append(row)

    return index


def _load_review_queue_lookup() -> dict[tuple[str, str, str, str, str, str, str], dict]:
    """Load review-queue rows and index them by stable candidate identity."""
    lookup: dict[tuple[str, str, str, str, str, str, str], dict] = {}
    for path in sorted(glob.glob(REVIEW_QUEUE_GLOB)):
        filename = os.path.basename(path)
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row_index, row in enumerate(reader, start=1):
                key = _make_review_queue_key(
                    run_id=row.get("run_id", ""),
                    snapshot_ts=row.get("snapshot_ts", ""),
                    strategy_id=row.get("strategy_id", ""),
                    symbol=row.get("symbol", ""),
                    expiration_date=row.get("expiration_date", ""),
                    short_strike=row.get("short_strike", ""),
                    long_strike=row.get("long_strike", ""),
                )
                if not any(key):
                    continue
                row["_source_file"] = filename
                row["_row_index"] = str(row_index)
                lookup[key] = row
    return lookup


def _enrich_with_review_queue_match(row: dict, candidate: dict) -> None:
    """Attach manual review-queue decisions to a candidate-backed analytics row."""
    key = _make_review_queue_key(
        run_id=candidate.get("run_id", ""),
        snapshot_ts=candidate.get("snapshot_ts", ""),
        strategy_id=candidate.get("strategy_id", ""),
        symbol=candidate.get("symbol", ""),
        expiration_date=candidate.get("expiration_date", ""),
        short_strike=candidate.get("short_strike", ""),
        long_strike=candidate.get("long_strike", ""),
    )
    review_row = build_output_row.review_queue_lookup.get(key)
    if not review_row:
        return

    row["review_decision"] = review_row.get("decision", "")
    row["review_decision_reason"] = review_row.get("decision_reason", "")
    row["review_decision_note"] = review_row.get("decision_note", "")
    row["review_queue_file"] = review_row.get("_source_file", "")
    row["review_queue_row"] = review_row.get("_row_index", "")


def _promote_trade_only_match_from_daily_context(row: dict) -> None:
    """Upgrade trade-only rows when daily opportunity linkage proves reviewed context."""
    daily_match_type = (row.get("daily_opportunity_match_type") or "").strip().lower()
    if daily_match_type not in {"exact", "shifted"}:
        return

    row["candidate_status"] = "reviewed_context"
    row["match_status"] = (
        "exact_match" if daily_match_type == "exact" else "adjusted_match"
    )
    row["execution_alignment"] = "exact" if daily_match_type == "exact" else "shifted"
    row["trade_only_reason"] = ""

    short_shift = _parse_float_or_none(row.get("daily_short_strike_shift", ""))
    long_shift = _parse_float_or_none(row.get("daily_long_strike_shift", ""))
    if short_shift is None or long_shift is None:
        if daily_match_type == "exact":
            row["short_strike_shift"] = "0.0000"
            row["long_strike_shift"] = "0.0000"
            row["shift_direction"] = "none"
        return

    row["short_strike_shift"] = f"{short_shift:.4f}"
    row["long_strike_shift"] = f"{long_shift:.4f}"
    if short_shift == 0 and long_shift == 0:
        row["shift_direction"] = "none"
    elif short_shift < 0 and long_shift < 0:
        row["shift_direction"] = "otm_shift"
    elif short_shift > 0 and long_shift > 0:
        row["shift_direction"] = "itm_shift"
    else:
        row["shift_direction"] = "mixed_shift"


def _find_daily_opportunity_match(
    *,
    run_id: str,
    snapshot_ts: str,
    row_date: date | None,
    symbol: str,
    expiration_date: str,
    short_strike: str,
    long_strike: str,
    width: str,
    daily_index: dict[date, list[dict]],
) -> tuple[dict | None, str]:
    """Find exact/shifted match in same-day opportunities list."""
    if row_date is None:
        return None, "none"

    day_rows = daily_index.get(row_date, [])
    if not day_rows:
        return None, "none"

    key = _make_spread_key(symbol, expiration_date, short_strike, long_strike)
    exact_matches: list[dict] = []
    snapshot_dt = _parse_snapshot_datetime(snapshot_ts)
    for candidate_row in day_rows:
        day_key = _make_spread_key(
            candidate_row.get("symbol", ""),
            candidate_row.get("expiration_date", ""),
            candidate_row.get("short_strike", ""),
            candidate_row.get("long_strike", ""),
        )
        if day_key == key:
            exact_matches.append(candidate_row)

    if exact_matches:
        exact_matches.sort(
            key=lambda row: (
                (
                    abs(
                        (
                            _daily_opportunity_run_datetime(row.get("_source_file", ""))
                            - snapshot_dt
                        ).total_seconds()
                    )
                    if (
                        snapshot_dt is not None
                        and _daily_opportunity_run_datetime(row.get("_source_file", ""))
                        is not None
                    )
                    else float("inf")
                ),
                0
                if _daily_opportunity_run_id(row.get("_source_file", "")) == run_id
                else 1,
                int((row.get("_row_index") or "0").strip() or "0"),
                row.get("_source_file", ""),
            )
        )
        return exact_matches[0], "exact"

    # Shifted fallback: same symbol/expiration/width and nearest strikes.
    filtered: list[tuple[float, int, float, dict]] = []
    for candidate_row in day_rows:
        if (candidate_row.get("symbol") or "").strip() != symbol.strip():
            continue
        if (
            candidate_row.get("expiration_date") or ""
        ).strip() != expiration_date.strip():
            continue
        if _normalize_strike(candidate_row.get("width", "")) != _normalize_strike(
            width
        ):
            continue

        try:
            score = abs(
                float(_normalize_strike(candidate_row.get("short_strike", "")))
                - float(_normalize_strike(short_strike))
            ) + abs(
                float(_normalize_strike(candidate_row.get("long_strike", "")))
                - float(_normalize_strike(long_strike))
            )
        except ValueError:
            continue
        same_run_penalty = (
            0
            if _daily_opportunity_run_id(candidate_row.get("_source_file", ""))
            == run_id
            else 1
        )
        run_dt = _daily_opportunity_run_datetime(candidate_row.get("_source_file", ""))
        time_distance = (
            abs((run_dt - snapshot_dt).total_seconds())
            if snapshot_dt is not None and run_dt is not None
            else float("inf")
        )
        filtered.append((time_distance, same_run_penalty, score, candidate_row))

    if not filtered:
        return None, "none"

    filtered.sort(
        key=lambda item: (item[0], item[1], item[2], item[3].get("_source_file", ""))
    )
    return filtered[0][3], "shifted"


def _enrich_with_daily_opportunity_match(
    row: dict,
    *,
    run_id: str,
    snapshot_ts: str,
    row_date: date | None,
    symbol: str,
    expiration_date: str,
    short_strike: str,
    long_strike: str,
    width: str,
    daily_index: dict[date, list[dict]],
) -> None:
    """Annotate output row with same-day opportunities file match metadata."""
    match_row, match_type = _find_daily_opportunity_match(
        run_id=run_id,
        snapshot_ts=snapshot_ts,
        row_date=row_date,
        symbol=symbol,
        expiration_date=expiration_date,
        short_strike=short_strike,
        long_strike=long_strike,
        width=width,
        daily_index=daily_index,
    )

    row["was_in_daily_opportunities_file"] = (
        "True" if match_row is not None else "False"
    )
    row["daily_opportunity_match_type"] = match_type

    if match_row is None:
        return

    row["daily_opportunity_file"] = match_row.get("_source_file", "")
    row["daily_opportunity_row"] = match_row.get("_row_index", "")
    row["daily_short_strike"] = match_row.get("short_strike", "")
    row["daily_long_strike"] = match_row.get("long_strike", "")
    for field in _DAILY_OPPORTUNITY_PASSTHROUGH:
        value = match_row.get(field, "")
        if value != "":
            row[field] = value

    shift_steps_from_anchor = (match_row.get("skew_steps_from_anchor") or "").strip()
    if shift_steps_from_anchor:
        row["shift_steps_from_anchor"] = shift_steps_from_anchor
        try:
            row["anchor_vs_shift_status"] = (
                "anchor" if int(float(shift_steps_from_anchor)) == 0 else "shifted"
            )
        except ValueError:
            row["anchor_vs_shift_status"] = ""

    candidate_short = _parse_float_or_none(short_strike)
    candidate_long = _parse_float_or_none(long_strike)
    daily_short = _parse_float_or_none(match_row.get("short_strike", ""))
    daily_long = _parse_float_or_none(match_row.get("long_strike", ""))
    if (
        candidate_short is not None
        and candidate_long is not None
        and daily_short is not None
        and daily_long is not None
    ):
        row["daily_short_strike_shift"] = f"{(daily_short - candidate_short):.4f}"
        row["daily_long_strike_shift"] = f"{(daily_long - candidate_long):.4f}"


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
) -> tuple[dict[tuple, list[dict]], dict[tuple[str, str], list[dict]]]:
    """
    Build a lookup dict keyed by (symbol, expiration, short_strike, long_strike).

    Each value is a list of matching trade rows (open or closed).
    Each row is tagged with an internal ``_trade_status`` field.
    """
    universe: dict[tuple, list[dict]] = {}
    by_symbol_expiration: dict[tuple[str, str], list[dict]] = {}

    for row in open_rows:
        row["_trade_status"] = "open"
        key = _make_spread_key(
            row.get("symbol", ""),
            _trade_expiration(row),
            row.get("short_strike", ""),
            row.get("long_strike", ""),
        )
        universe.setdefault(key, []).append(row)
        symbol_expiration_key = _make_symbol_expiration_key(
            row.get("symbol", ""), _trade_expiration(row)
        )
        by_symbol_expiration.setdefault(symbol_expiration_key, []).append(row)

    for row in closed_rows:
        row["_trade_status"] = "closed"
        key = _make_spread_key(
            row.get("symbol", ""),
            _trade_expiration(row),
            row.get("short_strike", ""),
            row.get("long_strike", ""),
        )
        universe.setdefault(key, []).append(row)
        symbol_expiration_key = _make_symbol_expiration_key(
            row.get("symbol", ""), _trade_expiration(row)
        )
        by_symbol_expiration.setdefault(symbol_expiration_key, []).append(row)

    return universe, by_symbol_expiration


def find_best_trade_match(
    candidate: dict,
    universe: dict[tuple, list[dict]],
    trades_by_symbol_expiration: dict[tuple[str, str], list[dict]],
) -> tuple[dict | None, str]:
    """
    Find the best matching trade for a selected candidate.

     Steps:
     1. Look up exact spread matches.
     2. If no exact match in date tolerance, attempt adjusted match on
         same symbol/expiration and same width (closest strikes wins).
     3. Return (None, "missing_match") if no suitable match is found.
    """
    key = _make_spread_key(
        candidate.get("symbol", ""),
        candidate.get("expiration_date", ""),
        candidate.get("short_strike", ""),
        candidate.get("long_strike", ""),
    )
    matches = universe.get(key, [])
    run_date = _candidate_run_date(candidate.get("run_id", ""))

    def in_date_window(trade_row: dict) -> bool:
        if run_date is None:
            return True
        try:
            entry_date = datetime.strptime(
                trade_row.get("entry_date", "").strip(), "%Y-%m-%d"
            ).date()
        except ValueError:
            return False
        return abs((entry_date - run_date).days) <= DATE_TOLERANCE_DAYS

    def status_priority(trade_row: dict) -> int:
        return (
            0
            if (trade_row.get("_trade_status") or "").strip().lower() == "closed"
            else 1
        )

    for trade in sorted(matches, key=status_priority):
        if in_date_window(trade):
            return trade, "exact_match"

    # Exact strike match not found within date tolerance; try adjusted matching.
    symbol_expiration_key = _make_symbol_expiration_key(
        candidate.get("symbol", ""), candidate.get("expiration_date", "")
    )
    nearby = trades_by_symbol_expiration.get(symbol_expiration_key, [])
    if not nearby:
        return None, "missing_match"

    candidate_width = _normalize_strike(candidate.get("width", ""))
    candidate_short = _normalize_strike(candidate.get("short_strike", ""))
    candidate_long = _normalize_strike(candidate.get("long_strike", ""))

    filtered_nearby: list[dict] = []
    for trade in sorted(nearby, key=status_priority):
        if not in_date_window(trade):
            continue

        trade_width = _normalize_strike(trade.get("width", ""))
        if candidate_width and trade_width and trade_width != candidate_width:
            continue
        filtered_nearby.append(trade)

    if not filtered_nearby:
        return None, "missing_match"

    # Score candidates by strike distance; lower is better.
    # Keeps manual adjustments (e.g., 100/95 -> 95/90) as learnable matches.
    best_trade: dict | None = None
    best_score: float | None = None
    best_priority: int | None = None
    for trade in filtered_nearby:
        try:
            short_distance = abs(
                float(_normalize_strike(trade.get("short_strike", "")))
                - float(candidate_short)
            )
            long_distance = abs(
                float(_normalize_strike(trade.get("long_strike", "")))
                - float(candidate_long)
            )
            score = short_distance + long_distance
            priority = status_priority(trade)
            if (
                best_score is None
                or score < best_score
                or (
                    score == best_score
                    and best_priority is not None
                    and priority < best_priority
                )
            ):
                best_score = score
                best_priority = priority
                best_trade = trade
        except ValueError:
            continue

    if best_trade is None:
        return None, "missing_match"

    return best_trade, "adjusted_match"


def build_output_row(candidate: dict, trade: dict | None, match_status: str) -> dict:
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

    row["strategy_version"] = _candidate_strategy_version(candidate)
    _enrich_with_review_queue_match(row, candidate)

    row["match_status"] = match_status

    if trade is None:
        candidate_row_date = _candidate_snapshot_date(candidate)
        if candidate_row_date is None:
            candidate_row_date = _candidate_run_date(candidate.get("run_id", ""))
        _enrich_with_daily_opportunity_match(
            row,
            run_id=(candidate.get("run_id") or "").strip(),
            snapshot_ts=(candidate.get("snapshot_ts") or "").strip(),
            row_date=candidate_row_date,
            symbol=row.get("symbol", ""),
            expiration_date=row.get("expiration_date", ""),
            short_strike=row.get("short_strike", ""),
            long_strike=row.get("long_strike", ""),
            width=row.get("width", ""),
            daily_index=build_output_row.daily_index,
        )
        return row

    row["trade_status"] = trade.get("_trade_status", "")
    row["executed_short_strike"] = trade.get("short_strike", "")
    row["executed_long_strike"] = trade.get("long_strike", "")
    row["executed_width"] = trade.get("width", "")

    short_shift, long_shift, alignment, direction = _compute_shift_fields(
        candidate, trade
    )
    row["short_strike_shift"] = short_shift
    row["long_strike_shift"] = long_shift
    row["execution_alignment"] = alignment
    row["shift_direction"] = direction

    row["trade_id"] = trade.get("trade_id", "")
    row["entry_date"] = trade.get("entry_date", "")

    for col in _OPEN_TRADE_COLUMNS:
        row[col] = trade.get(col, "")

    for col in _CLOSED_TRADE_COLUMNS:
        row[col] = trade.get(col, "")

    try:
        entry_date = datetime.strptime(
            (trade.get("entry_date") or "").strip(), "%Y-%m-%d"
        ).date()
    except ValueError:
        entry_date = _candidate_run_date(candidate.get("run_id", ""))

    _enrich_with_daily_opportunity_match(
        row,
        run_id=(candidate.get("run_id") or "").strip(),
        snapshot_ts=(candidate.get("snapshot_ts") or "").strip(),
        row_date=entry_date,
        symbol=row.get("symbol", ""),
        expiration_date=row.get("expiration_date", ""),
        short_strike=row.get("short_strike", ""),
        long_strike=row.get("long_strike", ""),
        width=row.get("width", ""),
        daily_index=build_output_row.daily_index,
    )
    _promote_trade_only_match_from_daily_context(row)

    return row


def build_trade_only_row(trade: dict, reason: str) -> dict:
    """Construct an output row for a trade with no candidate match."""
    row: dict = {col: "" for col in OUTPUT_COLUMNS}

    row["symbol"] = trade.get("symbol", "")
    row["strategy_id"] = trade.get("strategy_id", "")
    row["strategy_family"] = trade.get("strategy_family", "")
    row["option_side"] = trade.get("option_side", "")
    row["directional_bias"] = trade.get("directional_bias", "")
    row["short_leg_type"] = trade.get("short_leg_type", "")
    row["long_leg_type"] = trade.get("long_leg_type", "")
    row["expiration_date"] = _trade_expiration(trade)
    row["short_strike"] = trade.get("short_strike", "")
    row["long_strike"] = trade.get("long_strike", "")
    row["width"] = trade.get("width", "")

    # Backfill entry DTE from lifecycle fields when no candidate row exists.
    try:
        dte_at_close = int(float((trade.get("dte_at_close") or "").strip()))
        days_held = int(float((trade.get("days_held") or "").strip()))
        row["dte"] = str(dte_at_close + days_held)
    except (ValueError, TypeError):
        row["dte"] = ""

    row["candidate_status"] = "executed_unmatched"
    row["selected"] = "False"
    row["match_status"] = "trade_only"
    row["execution_alignment"] = "trade_only"
    row["shift_direction"] = "unknown"
    row["trade_only_reason"] = reason
    row["executed_short_strike"] = trade.get("short_strike", "")
    row["executed_long_strike"] = trade.get("long_strike", "")
    row["executed_width"] = trade.get("width", "")

    row["trade_status"] = trade.get("_trade_status", "")
    row["trade_id"] = trade.get("trade_id", "")
    row["entry_date"] = trade.get("entry_date", "")
    row["strategy_version"] = _resolve_strategy_version_for_date(
        _parse_date(row.get("entry_date", ""))
    )

    for col in _OPEN_TRADE_COLUMNS:
        row[col] = trade.get(col, "")

    for col in _CLOSED_TRADE_COLUMNS:
        row[col] = trade.get(col, "")

    try:
        entry_date = datetime.strptime(
            (trade.get("entry_date") or "").strip(), "%Y-%m-%d"
        ).date()
    except ValueError:
        entry_date = None

    _enrich_with_daily_opportunity_match(
        row,
        run_id="",
        snapshot_ts="",
        row_date=entry_date,
        symbol=row.get("symbol", ""),
        expiration_date=row.get("expiration_date", ""),
        short_strike=row.get("short_strike", ""),
        long_strike=row.get("long_strike", ""),
        width=row.get("width", ""),
        daily_index=build_output_row.daily_index,
    )
    _promote_trade_only_match_from_daily_context(row)

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
    daily_index = _load_daily_opportunities_index()
    review_queue_lookup = _load_review_queue_lookup()
    build_output_row.daily_index = daily_index
    build_output_row.review_queue_lookup = review_queue_lookup
    earliest_candidate_date = _min_candidate_run_date(candidates)
    open_trades = _deduplicate_open_trades(load_csv(TRADES_OPEN_PATH))
    closed_trades = load_csv(TRADES_CLOSED_PATH)

    trade_universe, trades_by_symbol_expiration = build_trade_universe(
        open_trades, closed_trades
    )

    os.makedirs(OUTPUT_PATH.parent, exist_ok=True)

    exact_matches = 0
    adjusted_matches = 0
    missing_matches = 0
    not_applicable = 0
    trade_only_rows = 0
    matched_trade_ids: set[str] = set()
    trade_row_exact = 0
    trade_row_adjusted = 0
    trade_row_closed = 0
    trade_row_open = 0

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()

        for candidate in candidates:
            is_selected = candidate.get("selected", "").strip().lower() == "true"
            is_ranked_out = (
                candidate.get("rejection_reason_primary", "").strip().lower()
            ) == "selected_ranked_out"

            if not is_selected and not is_ranked_out:
                # Hard-rejected candidates are not reconciled against a trade.
                writer.writerow(build_output_row(candidate, None, ""))
                not_applicable += 1
                continue

            trade, match_status = find_best_trade_match(
                candidate,
                trade_universe,
                trades_by_symbol_expiration,
            )
            if trade is not None and match_status == "exact_match":
                exact_matches += 1
                trade_row_exact += 1
                trade_id = (trade.get("trade_id") or "").strip()
                if trade_id:
                    matched_trade_ids.add(trade_id)
                if (trade.get("_trade_status") or "").strip().lower() == "open":
                    trade_row_open += 1
                elif (trade.get("_trade_status") or "").strip().lower() == "closed":
                    trade_row_closed += 1
            elif trade is not None and match_status == "adjusted_match":
                adjusted_matches += 1
                trade_row_adjusted += 1
                trade_id = (trade.get("trade_id") or "").strip()
                if trade_id:
                    matched_trade_ids.add(trade_id)
                if (trade.get("_trade_status") or "").strip().lower() == "open":
                    trade_row_open += 1
                elif (trade.get("_trade_status") or "").strip().lower() == "closed":
                    trade_row_closed += 1
            else:
                missing_matches += 1

            writer.writerow(build_output_row(candidate, trade, match_status))

        # Ensure all closed trades are represented for outcome analytics, even
        # when there is no candidate row match.
        for trade in closed_trades:
            trade_id = (trade.get("trade_id") or "").strip()
            if trade_id and trade_id in matched_trade_ids:
                continue

            reason = "no_candidate_match_found"
            try:
                entry_date = datetime.strptime(
                    (trade.get("entry_date") or "").strip(), "%Y-%m-%d"
                ).date()
                if (
                    earliest_candidate_date is not None
                    and entry_date < earliest_candidate_date
                ):
                    reason = "pre_candidate_log_coverage"
            except ValueError:
                reason = "invalid_entry_date"

            writer.writerow(build_trade_only_row(trade, reason))
            trade_only_rows += 1
            trade_row_closed += 1

    total = len(candidates)
    selected_total = exact_matches + adjusted_matches + missing_matches
    trade_row_total = trade_row_exact + trade_row_adjusted + trade_only_rows
    print(f"Analysis dataset written to: {OUTPUT_PATH}")
    print(f"Total candidates processed : {total}")
    print(f"  Rejected (not matched)   : {not_applicable}")
    print("Selected candidate direct-match diagnostic (narrow):")
    print("  Measures only direct matches from selected candidate-log rows.")
    print("  Does not include later recovery from daily opportunity snapshots.")
    print(f"  exact_match              : {exact_matches}")
    print(f"  adjusted_match           : {adjusted_matches}")
    print(f"  missing_match            : {missing_matches}")
    if selected_total > 0:
        exact_rate = exact_matches / selected_total * 100
        total_rate = (exact_matches + adjusted_matches) / selected_total * 100
        print(f"  direct exact rate        : {exact_rate:.1f}%")
        print(f"  direct exact+adjusted    : {total_rate:.1f}%")
    print("Final trade-row reconciliation stats (primary):")
    print("  This is the main summary for how many executed trades were recovered.")
    print(f"  exact_match              : {trade_row_exact}")
    print(f"  adjusted_match           : {trade_row_adjusted}")
    print(f"  trade_only               : {trade_only_rows}")
    print(f"  trade rows total         : {trade_row_total}")
    print(f"  open trade rows          : {trade_row_open}")
    print(f"  closed trade rows        : {trade_row_closed}")


if __name__ == "__main__":
    build_analysis_dataset()
