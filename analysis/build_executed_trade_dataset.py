"""Build a dense executed-trade analytics dataset.

This script reshapes the reconciled reporting dataset into a one-row-per-trade
table that is easier to use for trade-outcome analysis and future model prep.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.analytics_fields import MARKET_CONTEXT_FIELDS  # noqa: E402

DEFAULT_ANALYSIS_DATASET = PROJECT_ROOT / "analysis" / "analysis_dataset.csv"
DEFAULT_CANDIDATES_PATH = PROJECT_ROOT / "opportunities" / "opportunity_candidates.csv"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "analysis" / "executed_trade_dataset.csv"
DEFAULT_DAILY_OPPORTUNITIES_DIR = PROJECT_ROOT / "opportunities"

BASE_CANDIDATE_FIELDS = [
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
    "credit_mid",
    "credit_natural",
    "credit_expected",
    "fill_quality",
    "avg_width_pct",
    "mid_weight",
]

CANDIDATE_ONLY_FIELDS = [
    "year_high_price",
    "year_low_price",
    "range_position_52w",
    "distance_to_52w_high_pct",
    "distance_to_52w_low_pct",
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
    "fill_edge",
    "fill_edge_pct",
    "mid_capture_pct",
    "fill_quality_score",
    "anchor_vs_shift_status",
    "shift_steps_from_anchor",
    "short_strike_shift",
    "long_strike_shift",
    "shift_direction",
]

FEATURE_PROVENANCE_FIELDS = [
    "feature_provenance",
    "reviewed_setup_found",
    "reviewed_setup_match_type",
    "review_context_quality",
]

TRADE_METADATA_FIELDS = [
    "trade_status",
    "match_status",
    "entry_match_quality",
    "trade_id",
    "entry_date",
    "executed_short_strike",
    "executed_long_strike",
    "executed_width",
    "buying_power_used",
    "current_mark",
    "current_pnl",
    "current_pnl_pct",
    "dte_remaining",
    "days_held",
    "short_strike_breached",
    "exit_signal",
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
    "label_quality_weight",
    *FEATURE_PROVENANCE_FIELDS,
]


def load_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Load a CSV file and return its header and rows."""
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def write_csv(path: Path, header: list[str], rows: list[dict[str, object]]) -> None:
    """Write rows to CSV, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def as_bool(value: object) -> bool:
    """Parse common CSV boolean-like text values."""
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def parse_float(value: object) -> float | None:
    """Parse float-like CSV values, returning None for blanks or invalid data."""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def populate_derived_candidate_fields(output: dict[str, object]) -> None:
    """Backfill simple derived candidate fields when source rows omit them."""
    if str(output.get("premium_per_width", "")).strip():
        return

    premium = parse_float(output.get("premium"))
    width = parse_float(output.get("width"))
    if premium is None or width in {None, 0.0}:
        return

    output["premium_per_width"] = f"{premium / width:.4f}"


def candidate_lookup_key(row: dict[str, str]) -> tuple[str, str, str, str, str, str]:
    """Build a stable key for a candidate row."""
    return (
        (row.get("run_id") or "").strip(),
        (row.get("snapshot_ts") or "").strip(),
        (row.get("symbol") or "").strip(),
        (row.get("expiration_date") or "").strip(),
        (row.get("short_strike") or "").strip(),
        (row.get("long_strike") or "").strip(),
    )


def candidate_backfill_lookup_key(
    run_id: str,
    symbol: str,
    expiration_date: str,
    short_strike: str,
    long_strike: str,
) -> tuple[str, str, str, str, str]:
    """Build a fallback key from daily opportunity run metadata."""
    return (
        run_id.strip(),
        symbol.strip(),
        expiration_date.strip(),
        short_strike.strip(),
        long_strike.strip(),
    )


def run_id_from_daily_opportunity_file(filename: str) -> str:
    """Extract the originating run id from an opportunities_*.csv filename."""
    match = re.search(
        r"(?:(?:put|call)_spread_)?opportunities_(\d{8}_\d{6})",
        filename or "",
    )
    return match.group(1) if match else ""


def trade_identity_key(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    """Build a fallback trade identity key when trade_id is unavailable."""
    return (
        (row.get("trade_id") or "").strip(),
        (row.get("symbol") or "").strip(),
        (row.get("entry_date") or "").strip(),
        (row.get("executed_short_strike") or "").strip(),
        (row.get("executed_long_strike") or "").strip(),
    )


def build_candidate_lookup(
    candidate_rows: list[dict[str, str]],
) -> dict[tuple[str, str, str, str, str, str], dict[str, str]]:
    """Index candidate rows by identity so later schemas can be backfilled."""
    lookup: dict[tuple[str, str, str, str, str, str], dict[str, str]] = {}
    for row in candidate_rows:
        lookup[candidate_lookup_key(row)] = row
    return lookup


def build_candidate_backfill_lookup(
    candidate_rows: list[dict[str, str]],
) -> dict[tuple[str, str, str, str, str], dict[str, str]]:
    """Index candidate rows by run/file identity for promoted reviewed-context rows."""
    lookup: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
    for row in candidate_rows:
        run_id = (row.get("run_id") or "").strip()
        if not run_id:
            continue
        lookup[
            candidate_backfill_lookup_key(
                run_id,
                row.get("symbol") or "",
                row.get("expiration_date") or "",
                row.get("short_strike") or "",
                row.get("long_strike") or "",
            )
        ] = row
    return lookup


def daily_lookup_key(row: dict[str, str]) -> tuple[str, str]:
    """Build a stable key for a same-day opportunities row."""
    return (
        (row.get("daily_opportunity_file") or "").strip(),
        (row.get("daily_opportunity_row") or "").strip(),
    )


def build_daily_opportunity_lookup(
    opportunities_dir: Path,
) -> dict[tuple[str, str], dict[str, str]]:
    """Index opportunities_*.csv rows by file name and row number."""
    lookup: dict[tuple[str, str], dict[str, str]] = {}
    paths = (
        sorted(opportunities_dir.glob("opportunities_*.csv"))
        + sorted(opportunities_dir.glob("put_spread_opportunities_*.csv"))
        + sorted(opportunities_dir.glob("call_spread_opportunities_*.csv"))
    )
    seen_names: set[str] = set()
    for path in paths:
        if path.name in seen_names:
            continue
        seen_names.add(path.name)
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row_index, row in enumerate(reader, start=1):
                lookup[(path.name, str(row_index))] = row
    return lookup


def row_preference(row: dict[str, str]) -> tuple[int, int, int]:
    """Return a preference tuple so selected exact matches win deduping."""
    selected_score = 1 if as_bool(row.get("selected")) else 0
    match_status = (row.get("match_status") or "").strip().lower()
    match_score = {
        "exact_match": 3,
        "adjusted_match": 2,
        "missing_match": 1,
        "trade_only": 0,
    }.get(match_status, -1)
    actual_exit_score = 1 if as_bool(row.get("actual_exit_found")) else 0
    return selected_score, match_score, actual_exit_score


def label_quality_weight(row: dict[str, str]) -> str:
    """Return a label-quality weight for closed-trade learning use."""
    trade_status = (row.get("trade_status") or "").strip().lower()
    if trade_status != "closed":
        return ""

    match_status = (row.get("match_status") or "").strip().lower()
    has_actual_exit = as_bool(row.get("actual_exit_found"))
    if match_status == "exact_match" and has_actual_exit:
        return "1.0"
    if match_status == "adjusted_match" and has_actual_exit:
        return "0.8"
    if match_status in {"exact_match", "adjusted_match"}:
        return "0.5"
    if match_status == "trade_only":
        return "0.3"
    return ""


def derive_feature_provenance(
    source_row: dict[str, str],
    *,
    candidate_row_found: bool,
    daily_row_found: bool,
) -> dict[str, str]:
    """Describe where entry-time feature context came from."""
    match_status = (source_row.get("match_status") or "").strip().lower()
    daily_match_type = (
        (source_row.get("daily_opportunity_match_type") or "").strip().lower()
    )

    if match_status == "exact_match" and candidate_row_found:
        return {
            "feature_provenance": "candidate_log_exact",
            "reviewed_setup_found": "True",
            "reviewed_setup_match_type": "candidate_log_exact",
            "review_context_quality": "high",
        }
    if match_status == "adjusted_match" and candidate_row_found:
        return {
            "feature_provenance": "candidate_log_adjusted",
            "reviewed_setup_found": "True",
            "reviewed_setup_match_type": "candidate_log_adjusted",
            "review_context_quality": "high",
        }
    if daily_row_found and daily_match_type == "exact":
        return {
            "feature_provenance": "daily_opportunity_exact",
            "reviewed_setup_found": "True",
            "reviewed_setup_match_type": "daily_exact",
            "review_context_quality": "medium",
        }
    if daily_row_found and daily_match_type == "shifted":
        return {
            "feature_provenance": "daily_opportunity_shifted",
            "reviewed_setup_found": "True",
            "reviewed_setup_match_type": "daily_shifted",
            "review_context_quality": "medium",
        }
    if candidate_row_found:
        return {
            "feature_provenance": "candidate_log_backfill",
            "reviewed_setup_found": "True",
            "reviewed_setup_match_type": "candidate_log_backfill",
            "review_context_quality": "medium",
        }
    return {
        "feature_provenance": "none",
        "reviewed_setup_found": "False",
        "reviewed_setup_match_type": "none",
        "review_context_quality": "low",
    }


def build_output_row(
    source_row: dict[str, str],
    analysis_header: list[str],
    candidate_lookup: dict[tuple[str, str, str, str, str, str], dict[str, str]],
    candidate_backfill_lookup: dict[tuple[str, str, str, str, str], dict[str, str]],
    daily_opportunity_lookup: dict[tuple[str, str], dict[str, str]],
) -> dict[str, object]:
    """Build one executed-trade dataset row."""
    output = {column: source_row.get(column, "") for column in analysis_header}
    candidate_row = candidate_lookup.get(candidate_lookup_key(source_row), {})
    daily_row = daily_opportunity_lookup.get(daily_lookup_key(source_row), {})
    if not candidate_row and daily_row:
        daily_run_id = run_id_from_daily_opportunity_file(
            source_row.get("daily_opportunity_file")
            or daily_row.get("_source_file", "")
        )
        if daily_run_id:
            candidate_row = candidate_backfill_lookup.get(
                candidate_backfill_lookup_key(
                    daily_run_id,
                    daily_row.get("symbol") or source_row.get("symbol") or "",
                    daily_row.get("expiration_date")
                    or source_row.get("expiration_date")
                    or "",
                    daily_row.get("short_strike")
                    or source_row.get("short_strike")
                    or "",
                    daily_row.get("long_strike") or source_row.get("long_strike") or "",
                ),
                {},
            )
    feature_source_row = dict(daily_row)
    feature_source_row.update(candidate_row)

    for column in BASE_CANDIDATE_FIELDS + CANDIDATE_ONLY_FIELDS:
        if not str(output.get(column, "")).strip():
            output[column] = feature_source_row.get(column, "")
    populate_derived_candidate_fields(output)

    output.update(
        derive_feature_provenance(
            source_row,
            candidate_row_found=bool(candidate_row),
            daily_row_found=bool(daily_row),
        )
    )

    output["entry_match_quality"] = source_row.get("match_status", "")
    output["label_quality_weight"] = label_quality_weight(source_row)
    return output


def build_executed_trade_dataset(
    analysis_dataset_path: Path = DEFAULT_ANALYSIS_DATASET,
    candidates_path: Path = DEFAULT_CANDIDATES_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    daily_opportunities_dir: Path = DEFAULT_DAILY_OPPORTUNITIES_DIR,
) -> Path:
    """Build and write the executed-trade dataset."""
    analysis_header, analysis_rows = load_csv_rows(analysis_dataset_path)
    _, candidate_rows = load_csv_rows(candidates_path)
    candidate_index = build_candidate_lookup(candidate_rows)
    candidate_backfill_index = build_candidate_backfill_lookup(candidate_rows)
    daily_opportunity_lookup = build_daily_opportunity_lookup(daily_opportunities_dir)

    trade_rows = [
        row
        for row in analysis_rows
        if (row.get("trade_status") or "").strip().lower() in {"open", "closed"}
    ]

    best_by_trade: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
    for row in trade_rows:
        key = trade_identity_key(row)
        existing = best_by_trade.get(key)
        if existing is None or row_preference(row) > row_preference(existing):
            best_by_trade[key] = row

    output_header = (
        analysis_header
        + [
            field
            for field in BASE_CANDIDATE_FIELDS + CANDIDATE_ONLY_FIELDS
            if field not in analysis_header
        ]
        + [field for field in TRADE_METADATA_FIELDS if field not in analysis_header]
    )
    output_rows = [
        build_output_row(
            row,
            analysis_header,
            candidate_index,
            candidate_backfill_index,
            daily_opportunity_lookup,
        )
        for row in best_by_trade.values()
    ]
    output_rows.sort(
        key=lambda row: (
            str(row.get("close_date") or ""),
            str(row.get("entry_date") or ""),
            str(row.get("symbol") or ""),
            str(row.get("trade_id") or ""),
        )
    )
    write_csv(output_path, output_header, output_rows)
    return output_path


def main() -> None:
    """Build the executed-trade dataset and print a compact summary."""
    output_path = build_executed_trade_dataset()
    _, rows = load_csv_rows(output_path)
    closed_count = sum(
        1 for row in rows if (row.get("trade_status") or "").strip().lower() == "closed"
    )
    open_count = sum(
        1 for row in rows if (row.get("trade_status") or "").strip().lower() == "open"
    )
    print(f"Executed trade dataset written to: {output_path}")
    print(f"Executed trade rows: {len(rows)}")
    print(f"Closed trades: {closed_count}")
    print(f"Open trades: {open_count}")


if __name__ == "__main__":
    main()
