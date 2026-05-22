"""Build a dense rejected-candidate analytics dataset.

This script reshapes ``opportunities/opportunity_candidates.csv`` into a
rejected-only analytics table with additional derived fields that make filter
review and tuning easier.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CANDIDATES_PATH = PROJECT_ROOT / "opportunities" / "opportunity_candidates.csv"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "analysis" / "rejected_candidate_dataset.csv"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402
from screener.spread_logging import CANDIDATE_FIELDNAMES  # noqa: E402
from screener.strategy_types import PUT_CREDIT_SPREAD  # noqa: E402

LIQUIDITY_REASONS = {
    "short_bid_ask_width",
    "long_bid_ask_width",
    "open_interest",
    "short_leg_missing_quote",
    "long_leg_missing_quote",
}

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

LEGACY_REASON_ALIASES: dict[str, str] = {
    "credit_conservative": "credit_expected_too_low",
    "delta_bounds": "delta_bounds_max",
}

DERIVED_COLUMNS = [
    "rejection_bucket",
    "delta_distance_from_target",
    "moneyness_pct",
    "premium_pct_of_width",
    "width_pct_of_stock",
    "sibling_selected_exists",
    "same_group_candidate_count",
    "same_group_liquidity_failure_count",
    "same_group_ranked_out_exists",
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


def parse_float(value: object) -> float | None:
    """Parse a float-like value, returning None for blanks/invalid values."""
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value or "").strip()
    if raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def as_bool_text(value: object) -> str:
    """Normalize a truthy CSV field to lowercase text."""
    return str(value or "").strip().lower()


def normalize_rejection_reason(reason: str) -> str:
    """Normalize legacy reason labels to the current analytics taxonomy."""
    raw = (reason or "").strip()
    return LEGACY_REASON_ALIASES.get(raw, raw)


def normalize_rejection_flags(flags: str) -> str:
    """Normalize and deduplicate pipe-delimited rejection flag labels."""
    raw = (flags or "").strip()
    if not raw:
        return ""

    normalized_parts: list[str] = []
    for part in raw.split("|"):
        normalized = normalize_rejection_reason(part)
        if normalized and normalized not in normalized_parts:
            normalized_parts.append(normalized)
    return "|".join(normalized_parts)


def normalize_strategy_id(strategy_id: str) -> str:
    """Default blank legacy rows to the original put credit spread strategy."""
    return (strategy_id or "").strip() or PUT_CREDIT_SPREAD.strategy_id


def resolve_target_delta(strategy_id: str) -> float:
    """Return the configured target delta for the given strategy."""
    normalized_strategy_id = normalize_strategy_id(strategy_id)
    if normalized_strategy_id == "call_credit_spread":
        return float(getattr(config, "CALL_TARGET_DELTA", config.TARGET_DELTA))
    return float(getattr(config, "PUT_TARGET_DELTA", config.TARGET_DELTA))


def compute_moneyness_pct(
    stock_price: float | None,
    short_strike: float | None,
    strategy_id: str,
) -> float | None:
    """Return positive OTM distance for both put and call credit spreads."""
    if stock_price in (None, 0) or short_strike is None:
        return None

    normalized_strategy_id = normalize_strategy_id(strategy_id)
    if normalized_strategy_id == "call_credit_spread":
        return (short_strike - stock_price) / stock_price
    return (stock_price - short_strike) / stock_price


def build_group_index(
    rows: list[dict[str, str]],
) -> dict[tuple[str, str, str, str], list[dict[str, str]]]:
    """Group rows by run, strategy, symbol, and expiration."""
    grouped: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = (
            (row.get("run_id") or "").strip(),
            normalize_strategy_id(row.get("strategy_id") or ""),
            (row.get("symbol") or "").strip(),
            (row.get("expiration_date") or "").strip(),
        )
        grouped[key].append(row)
    return grouped


def derive_row(
    row: dict[str, str],
    siblings: list[dict[str, str]],
) -> dict[str, object]:
    """Build one rejected-candidate output row with derived analysis fields."""
    stock_price = parse_float(row.get("stock_price"))
    short_strike = parse_float(row.get("short_strike"))
    width = parse_float(row.get("width"))
    premium = parse_float(row.get("premium"))
    short_delta = parse_float(row.get("short_delta"))
    strategy_id = normalize_strategy_id(row.get("strategy_id") or "")
    rejection_reason = normalize_rejection_reason(
        row.get("rejection_reason_primary") or ""
    )
    rejection_flags = normalize_rejection_flags(row.get("rejection_reason_flags") or "")

    delta_distance_from_target = (
        abs(short_delta - resolve_target_delta(strategy_id))
        if short_delta is not None
        else None
    )
    moneyness_pct = compute_moneyness_pct(stock_price, short_strike, strategy_id)
    premium_pct_of_width = (
        premium / (width * 100)
        if premium is not None and width not in (None, 0)
        else None
    )
    width_pct_of_stock = (
        width / stock_price
        if width is not None and stock_price not in (None, 0)
        else None
    )

    sibling_selected_exists = any(
        as_bool_text(item.get("selected")) == "true" for item in siblings
    )
    same_group_liquidity_failure_count = sum(
        1
        for item in siblings
        if (item.get("rejection_reason_primary") or "").strip() in LIQUIDITY_REASONS
    )
    same_group_ranked_out_exists = any(
        (item.get("rejection_reason_primary") or "").strip() == "selected_ranked_out"
        for item in siblings
    )

    derived = dict(row)
    derived.update(
        {
            "rejection_reason_primary": rejection_reason,
            "rejection_reason_flags": rejection_flags,
            "rejection_bucket": REASON_BUCKETS.get(rejection_reason, "other"),
            "delta_distance_from_target": (
                round(delta_distance_from_target, 4)
                if delta_distance_from_target is not None
                else ""
            ),
            "moneyness_pct": round(moneyness_pct, 4)
            if moneyness_pct is not None
            else "",
            "premium_pct_of_width": (
                round(premium_pct_of_width, 4)
                if premium_pct_of_width is not None
                else ""
            ),
            "width_pct_of_stock": (
                round(width_pct_of_stock, 4) if width_pct_of_stock is not None else ""
            ),
            "sibling_selected_exists": str(sibling_selected_exists),
            "same_group_candidate_count": str(len(siblings)),
            "same_group_liquidity_failure_count": str(
                same_group_liquidity_failure_count
            ),
            "same_group_ranked_out_exists": str(same_group_ranked_out_exists),
        }
    )
    return derived


def build_rejected_candidate_dataset(
    candidates_path: Path = DEFAULT_CANDIDATES_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    """Build and write the rejected-candidate dataset."""
    header, rows = load_csv_rows(candidates_path)
    grouped_rows = build_group_index(rows)
    rejected_rows = [
        row
        for row in rows
        if (row.get("candidate_status") or "").strip().lower() == "rejected"
    ]

    output_rows = [
        derive_row(
            row,
            grouped_rows[
                (
                    (row.get("run_id") or "").strip(),
                    normalize_strategy_id(row.get("strategy_id") or ""),
                    (row.get("symbol") or "").strip(),
                    (row.get("expiration_date") or "").strip(),
                )
            ],
        )
        for row in rejected_rows
    ]
    canonical_header = list(CANDIDATE_FIELDNAMES) + DERIVED_COLUMNS
    write_csv(output_path, canonical_header, output_rows)
    return output_path


def main() -> None:
    """Build the rejected-candidate dataset and print a compact summary."""
    output_path = build_rejected_candidate_dataset()
    _, rows = load_csv_rows(output_path)
    bucket_counter = Counter(
        (row.get("rejection_bucket") or "").strip() for row in rows
    )
    print(f"Rejected candidate dataset written to: {output_path}")
    print(f"Rejected candidate rows: {len(rows)}")
    print(f"Top rejection buckets: {bucket_counter.most_common(5)}")


if __name__ == "__main__":
    main()
