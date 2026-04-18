"""Rejection diagnostics for Phase 1 analytics.

This module compares two rejection views:
1. Symbol-level counters from ``rejections/rejections_tracking.csv``.
2. Candidate-level reasons from ``opportunities/opportunity_candidates.csv``.

It prints compact summaries that help identify high-frequency filters and where
candidate-level behavior diverges from symbol-level aggregates.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SYMBOL_REJECTIONS_PATH = PROJECT_ROOT / "rejections" / "rejections_tracking.csv"
DEFAULT_CANDIDATES_PATH = PROJECT_ROOT / "opportunities" / "opportunity_candidates.csv"

REASON_BUCKETS: dict[str, str] = {
    "delta_bounds": "delta",
    "delta_bounds_min": "delta",
    "delta_bounds_max": "delta",
    "delta_bounds_missing": "delta",
    "short_bid_ask_width": "liquidity",
    "long_bid_ask_width": "liquidity",
    "open_interest": "liquidity",
    "credit_natural_too_low": "pricing_economics",
    "credit_expected_too_low": "pricing_economics",
    "premium_zero_or_negative": "pricing_economics",
    "risk_reward": "pricing_economics",
    "no_long_strike": "structure",
    "long_strike_unavailable": "structure",
    "itm_or_atm": "structure",
    "short_leg_missing_quote": "data_quotes",
    "long_leg_missing_quote": "data_quotes",
    "selected_ranked_out": "selection",
}


def load_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Load a CSV file and return (header, rows)."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return reader.fieldnames or [], list(reader)


def as_int(value: str) -> int:
    """Convert text to integer, coercing blanks/invalid values to 0."""
    raw = (value or "").strip()
    if raw == "":
        return 0
    try:
        return int(float(raw))
    except ValueError:
        return 0


def is_rejection_counter_column(column_name: str) -> bool:
    """Return True for symbol-level rejection counter fields."""
    excluded = {"timestamp", "symbol", "strategy_version", "total_rejections"}
    return column_name not in excluded


def parse_iso_date(value: str) -> date | None:
    """Parse date or datetime-like text into a date object."""
    raw = (value or "").strip()
    if not raw:
        return None

    candidate = raw[:10]
    try:
        return date.fromisoformat(candidate)
    except ValueError:
        return None


def filter_rows_by_date(
    rows: list[dict[str, str]],
    timestamp_column: str,
    start_date: date | None,
    end_date: date | None,
) -> list[dict[str, str]]:
    """Filter rows by inclusive date bounds based on an ISO-like timestamp column."""
    if start_date is None and end_date is None:
        return rows

    filtered: list[dict[str, str]] = []
    for row in rows:
        row_date = parse_iso_date(row.get(timestamp_column, ""))
        if row_date is None:
            continue
        if start_date is not None and row_date < start_date:
            continue
        if end_date is not None and row_date > end_date:
            continue
        filtered.append(row)
    return filtered


def rollup_reason_totals(reason_totals: Counter[str]) -> Counter[str]:
    """Aggregate detailed reasons into broader diagnostic buckets."""
    bucket_totals: Counter[str] = Counter()
    for reason, count in reason_totals.items():
        bucket = REASON_BUCKETS.get(reason, "other")
        bucket_totals[bucket] += count
    return bucket_totals


def write_csv(path: Path, header: list[str], rows: Iterable[list[str]]) -> None:
    """Write rows to CSV with header, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def export_summaries(
    export_dir: Path,
    prefix: str,
    symbol_reason_totals: Counter[str],
    candidate_reason_totals: Counter[str],
    symbol_bucket_totals: Counter[str],
    candidate_bucket_totals: Counter[str],
) -> list[Path]:
    """Export reason-level and bucket-level summaries for weekly reporting."""
    reason_rows: list[list[str]] = []
    for reason, count in symbol_reason_totals.most_common():
        reason_rows.append(["symbol_level", reason, str(count)])
    for reason, count in candidate_reason_totals.most_common():
        reason_rows.append(["candidate_level", reason, str(count)])

    bucket_rows: list[list[str]] = []
    for bucket, count in symbol_bucket_totals.most_common():
        bucket_rows.append(["symbol_level", bucket, str(count)])
    for bucket, count in candidate_bucket_totals.most_common():
        bucket_rows.append(["candidate_level", bucket, str(count)])

    reason_path = export_dir / f"{prefix}_reason_summary.csv"
    bucket_path = export_dir / f"{prefix}_bucket_summary.csv"

    write_csv(reason_path, ["source", "reason", "count"], reason_rows)
    write_csv(bucket_path, ["source", "bucket", "count"], bucket_rows)
    return [reason_path, bucket_path]


def summarize_symbol_level(
    header: list[str], rows: list[dict[str, str]], top_n: int
) -> dict:
    """Build symbol-level rejection aggregates from tracking CSV."""
    counter_columns = [col for col in header if is_rejection_counter_column(col)]

    reason_totals: Counter[str] = Counter()
    symbol_totals: Counter[str] = Counter()
    symbols_with_rejections: set[str] = set()

    for row in rows:
        symbol = (row.get("symbol") or "").strip()
        total = as_int(row.get("total_rejections", "0"))
        if symbol:
            symbol_totals[symbol] += total
            if total > 0:
                symbols_with_rejections.add(symbol)

        for col in counter_columns:
            reason_totals[col] += as_int(row.get(col, "0"))

    return {
        "rows": len(rows),
        "unique_symbols": len(symbol_totals),
        "symbols_with_rejections": len(symbols_with_rejections),
        "reason_totals": reason_totals,
        "top_reasons": reason_totals.most_common(top_n),
        "top_symbols": symbol_totals.most_common(top_n),
    }


def summarize_candidate_level(rows: list[dict[str, str]], top_n: int) -> dict:
    """Build candidate-level rejection aggregates from candidate log."""
    rejected_rows = [
        row
        for row in rows
        if (row.get("candidate_status") or "").strip().lower() == "rejected"
    ]

    reason_counter: Counter[str] = Counter()
    symbol_reason_counter: dict[str, Counter[str]] = defaultdict(Counter)
    symbol_rejected_counter: Counter[str] = Counter()

    for row in rejected_rows:
        symbol = (row.get("symbol") or "").strip()
        reason = (row.get("rejection_reason_primary") or "").strip() or "(blank)"
        reason_counter[reason] += 1
        if symbol:
            symbol_rejected_counter[symbol] += 1
            symbol_reason_counter[symbol][reason] += 1

    top_symbols_with_reason = []
    for symbol, count in symbol_rejected_counter.most_common(top_n):
        top_reason, top_reason_count = symbol_reason_counter[symbol].most_common(1)[0]
        top_symbols_with_reason.append((symbol, count, top_reason, top_reason_count))

    return {
        "rows": len(rows),
        "rejected_rows": len(rejected_rows),
        "reason_totals": reason_counter,
        "top_reasons": reason_counter.most_common(top_n),
        "top_symbols": top_symbols_with_reason,
    }


def compare_reason_sets(
    symbol_reason_totals: Counter[str], candidate_reason_totals: Counter[str]
) -> dict:
    """Compare reason-name coverage between symbol-level and candidate-level logs."""
    symbol_set = set(symbol_reason_totals.keys())
    candidate_set = set(candidate_reason_totals.keys())
    return {
        "only_symbol_level": sorted(symbol_set - candidate_set),
        "only_candidate_level": sorted(candidate_set - symbol_set),
        "overlap": sorted(symbol_set & candidate_set),
    }


def format_count_lines(items: Iterable[tuple], prefix: str = "- ") -> list[str]:
    """Format tuples from ``most_common`` into readable bullet lines."""
    lines: list[str] = []
    for item in items:
        if len(item) == 2:
            name, count = item
            lines.append(f"{prefix}{name}: {count}")
        elif len(item) == 4:
            symbol, total, top_reason, top_reason_count = item
            lines.append(
                f"{prefix}{symbol}: {total} (top reason: {top_reason}={top_reason_count})"
            )
    return lines


def build_report_text(
    symbol_summary: dict,
    candidate_summary: dict,
    comparison: dict,
    symbol_bucket_totals: Counter[str],
    candidate_bucket_totals: Counter[str],
    start_date: date | None,
    end_date: date | None,
    exported_paths: list[Path],
    top_n: int,
) -> str:
    """Build the terminal report text."""
    date_window_text = "all dates"
    if start_date is not None or end_date is not None:
        start_text = start_date.isoformat() if start_date is not None else "-inf"
        end_text = end_date.isoformat() if end_date is not None else "+inf"
        date_window_text = f"{start_text} to {end_text}"

    lines = [
        "Rejection Diagnostics",
        f"- Date window: {date_window_text}",
        "",
        "Symbol-Level Summary (rejections_tracking.csv)",
        f"- Rows processed: {symbol_summary['rows']}",
        f"- Unique symbols: {symbol_summary['unique_symbols']}",
        f"- Symbols with non-zero rejections: {symbol_summary['symbols_with_rejections']}",
        f"- Top {top_n} rejection counters:",
        *format_count_lines(symbol_summary["top_reasons"]),
        f"- Top {top_n} symbols by total rejections:",
        *format_count_lines(symbol_summary["top_symbols"]),
        "",
        "Rollup Buckets (Symbol-Level)",
        *format_count_lines(symbol_bucket_totals.most_common(top_n)),
        "",
        "Candidate-Level Summary (opportunity_candidates.csv)",
        f"- Rows processed: {candidate_summary['rows']}",
        f"- Rejected candidate rows: {candidate_summary['rejected_rows']}",
        f"- Top {top_n} rejection reasons:",
        *format_count_lines(candidate_summary["top_reasons"]),
        f"- Top {top_n} symbols by rejected candidates:",
        *format_count_lines(candidate_summary["top_symbols"]),
        "",
        "Rollup Buckets (Candidate-Level)",
        *format_count_lines(candidate_bucket_totals.most_common(top_n)),
        "",
        "Reason Name Coverage Comparison",
        f"- Overlap count: {len(comparison['overlap'])}",
        (
            "- Only in symbol-level log: "
            + (", ".join(comparison["only_symbol_level"]) or "(none)")
        ),
        (
            "- Only in candidate-level log: "
            + (", ".join(comparison["only_candidate_level"]) or "(none)")
        ),
        "",
        "CSV Exports",
    ]

    if exported_paths:
        lines.extend(
            format_count_lines(
                [(str(path), "written") for path in exported_paths], prefix="- "
            )
        )
    else:
        lines.append("- (none)")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Summarize rejection diagnostics from symbol and candidate logs."
    )
    parser.add_argument(
        "--symbol-log",
        type=Path,
        default=DEFAULT_SYMBOL_REJECTIONS_PATH,
        help="Path to rejections_tracking.csv",
    )
    parser.add_argument(
        "--candidate-log",
        type=Path,
        default=DEFAULT_CANDIDATES_PATH,
        help="Path to opportunity_candidates.csv",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Number of top reasons/symbols to display",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="",
        help="Inclusive start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="",
        help="Inclusive end date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--symbol-date-column",
        type=str,
        default="timestamp",
        help="Timestamp column in symbol-level CSV for date filtering",
    )
    parser.add_argument(
        "--candidate-date-column",
        type=str,
        default="snapshot_ts",
        help="Timestamp column in candidate CSV for date filtering",
    )
    parser.add_argument(
        "--export-dir",
        type=Path,
        default=PROJECT_ROOT / "analysis" / "reports",
        help="Directory for CSV summary exports",
    )
    parser.add_argument(
        "--export-prefix",
        type=str,
        default="rejection_diagnostics",
        help="Filename prefix for exported CSV summaries",
    )
    return parser.parse_args()


def main() -> None:
    """Run rejection diagnostics and print a summary report."""
    args = parse_args()

    if not args.symbol_log.exists():
        raise FileNotFoundError(
            f"Symbol-level rejection log not found: {args.symbol_log}"
        )
    if not args.candidate_log.exists():
        raise FileNotFoundError(f"Candidate log not found: {args.candidate_log}")

    symbol_header, symbol_rows = load_csv_rows(args.symbol_log)
    _, candidate_rows = load_csv_rows(args.candidate_log)

    start_date = parse_iso_date(args.start_date)
    end_date = parse_iso_date(args.end_date)
    if args.start_date and start_date is None:
        raise ValueError("Invalid --start-date. Expected format YYYY-MM-DD.")
    if args.end_date and end_date is None:
        raise ValueError("Invalid --end-date. Expected format YYYY-MM-DD.")
    if start_date and end_date and start_date > end_date:
        raise ValueError("--start-date cannot be after --end-date.")

    symbol_rows = filter_rows_by_date(
        symbol_rows, args.symbol_date_column, start_date, end_date
    )
    candidate_rows = filter_rows_by_date(
        candidate_rows, args.candidate_date_column, start_date, end_date
    )

    symbol_summary = summarize_symbol_level(symbol_header, symbol_rows, args.top_n)
    candidate_summary = summarize_candidate_level(candidate_rows, args.top_n)
    symbol_bucket_totals = rollup_reason_totals(symbol_summary["reason_totals"])
    candidate_bucket_totals = rollup_reason_totals(candidate_summary["reason_totals"])
    comparison = compare_reason_sets(
        symbol_summary["reason_totals"], candidate_summary["reason_totals"]
    )

    exported_paths = export_summaries(
        export_dir=args.export_dir,
        prefix=args.export_prefix,
        symbol_reason_totals=symbol_summary["reason_totals"],
        candidate_reason_totals=candidate_summary["reason_totals"],
        symbol_bucket_totals=symbol_bucket_totals,
        candidate_bucket_totals=candidate_bucket_totals,
    )

    print(
        build_report_text(
            symbol_summary=symbol_summary,
            candidate_summary=candidate_summary,
            comparison=comparison,
            symbol_bucket_totals=symbol_bucket_totals,
            candidate_bucket_totals=candidate_bucket_totals,
            start_date=start_date,
            end_date=end_date,
            exported_paths=exported_paths,
            top_n=args.top_n,
        )
    )


if __name__ == "__main__":
    main()
