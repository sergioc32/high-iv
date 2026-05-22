"""Build a leakage-safe training dataset from executed trades."""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from statistics import mean

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXECUTED_DATASET = PROJECT_ROOT / "analysis" / "executed_trade_dataset.csv"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "ml" / "training_dataset.csv"
FEATURE_SCHEMA_VERSION = "v2_model_score_entry_core"
TIME_SPLIT_POLICY = "entry_date_chronological_70_15_15"
TRAIN_FRACTION = 0.70
VALIDATION_FRACTION = 0.15

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402

TARGET_DELTA = float(getattr(config, "TARGET_DELTA", 0.16))

METADATA_COLUMNS = [
    "feature_schema_version",
    "trade_id",
    "symbol",
    "strategy_id",
    "run_id",
    "snapshot_ts",
    "entry_date",
    "close_date",
    "match_status",
    "entry_match_quality",
    "feature_provenance",
    "reviewed_setup_found",
    "reviewed_setup_match_type",
    "review_context_quality",
    "actual_exit_found",
    "exit_price_source",
    "match_confidence",
    "label_quality_weight",
    "sample_weight",
    "time_split_policy",
    "time_split_group",
    "is_train",
    "is_validation",
    "is_test",
]

FEATURE_COLUMNS = [
    "strategy_version",
    "alignment_score_version",
    "selector_version",
    "option_side",
    "directional_bias",
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
    "short_delta",
    "short_iv",
    "atm_iv",
    "skew_ratio",
    "skew_diff",
    "earnings_within_dte",
    "credit_mid",
    "credit_natural",
    "credit_expected",
    "fill_quality",
    "avg_width_pct",
    "mid_weight",
    "year_high_price",
    "year_low_price",
    "range_position_52w",
    "distance_to_52w_high_pct",
    "distance_to_52w_low_pct",
    "fill_edge",
    "fill_edge_pct",
    "mid_capture_pct",
    "fill_quality_score",
    "anchor_vs_shift_status",
    "shift_steps_from_anchor",
    "shift_direction",
    "strategy_alignment_score",
    "total_rank_score",
    "put_selector_score",
    "call_selector_score",
    "selector_preferred_strategy",
    "selector_confidence",
    "market_regime_summary",
    "symbol_extension_bucket",
    "selector_earnings_stage",
    "selector_earnings_penalty",
]

DERIVED_FEATURE_COLUMNS = [
    "moneyness_pct",
    "distance_to_short_strike_points",
    "distance_to_short_strike_pct",
    "width_pct_of_stock",
    "premium_pct_of_width",
    "iv_spread",
    "delta_distance_from_target",
    "has_earnings_before_exit",
    "dte_bucket",
    "delta_bucket",
    "skew_bucket",
    "width_bucket",
    "range_position_bucket",
]

LABEL_COLUMNS = [
    "win_flag",
    "realized_return_on_risk",
    "profit_loss",
    "profit_loss_pct",
    "profit_pct_of_max",
    "annualized_return",
    "days_held",
]

OUTPUT_COLUMNS = (
    METADATA_COLUMNS + FEATURE_COLUMNS + DERIVED_FEATURE_COLUMNS + LABEL_COLUMNS
)

LEAKAGE_EXCLUDED_FEATURE_COLUMNS = {
    "trade_status",
    "close_date",
    "close_debit",
    "close_debit_actual",
    "close_debit_estimated",
    "profit_loss",
    "profit_loss_pct",
    "profit_pct_of_max",
    "annualized_return",
    "current_mark",
    "current_pnl",
    "current_pnl_pct",
    "dte_remaining",
    "exit_signal",
    "match_status",
    "actual_exit_found",
    "exit_price_source",
}

PROVENANCE_SAMPLE_WEIGHTS: dict[str, float] = {
    "candidate_log_exact": 1.0,
    "candidate_log_adjusted": 0.85,
    "daily_opportunity_exact": 0.7,
    "daily_opportunity_shifted": 0.6,
    "candidate_log_backfill": 0.5,
    "none": 0.2,
}

INCLUDED_MATCH_STATUSES = {"exact_match", "adjusted_match"}


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
    """Parse float-like CSV text, returning None for blanks/invalid values."""
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_date(value: object) -> str:
    """Normalize ISO-like date text for stable chronological sorting."""
    raw = str(value or "").strip()
    return raw[:10] if raw else ""


def canonical_strategy_id(row: dict[str, str]) -> str:
    """Resolve strategy_id with safe backward-compatible inference."""
    strategy_id = (row.get("strategy_id") or "").strip()
    if strategy_id:
        return strategy_id

    option_side = (row.get("option_side") or "").strip().lower()
    if option_side == "put":
        return "put_credit_spread"
    if option_side == "call":
        return "call_credit_spread"

    directional_bias = (row.get("directional_bias") or "").strip().lower()
    if directional_bias == "bullish":
        return "put_credit_spread"
    if directional_bias == "bearish":
        return "call_credit_spread"

    return "put_credit_spread"


def as_bool(value: object) -> bool:
    """Parse common boolean-like CSV text values."""
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def format_float(value: float | None, precision: int = 6) -> str:
    """Format numeric output consistently for CSV export."""
    if value is None:
        return ""
    return f"{value:.{precision}f}"


def bool_flag(value: bool | None) -> str:
    """Represent boolean-like values as model-friendly 1/0 text."""
    if value is None:
        return ""
    return "1" if value else "0"


def bucket_value(
    value: float | None, boundaries: list[tuple[float, str]], fallback: str
) -> str:
    """Map numeric values into ordered bucket labels."""
    if value is None:
        return ""
    for upper_bound, label in boundaries:
        if value <= upper_bound:
            return label
    return fallback


def validate_feature_schema() -> None:
    """Validate that leakage fields are excluded from the feature columns."""
    duplicates = [
        column for column in OUTPUT_COLUMNS if OUTPUT_COLUMNS.count(column) > 1
    ]
    if duplicates:
        duplicate_list = ", ".join(sorted(set(duplicates)))
        raise ValueError(f"Duplicate output columns detected: {duplicate_list}")

    leaked_columns = sorted(
        set(FEATURE_COLUMNS + DERIVED_FEATURE_COLUMNS)
        & LEAKAGE_EXCLUDED_FEATURE_COLUMNS
    )
    if leaked_columns:
        leaked_list = ", ".join(leaked_columns)
        raise ValueError(
            f"Leakage-prone columns present in feature schema: {leaked_list}"
        )


def recommended_sample_weight(row: dict[str, str]) -> str:
    """Return provenance-aware sample weight for model training."""
    provenance = (row.get("feature_provenance") or "").strip()
    base_weight = PROVENANCE_SAMPLE_WEIGHTS.get(provenance, 0.2)
    if not as_bool(row.get("actual_exit_found")):
        base_weight *= 0.75
    return format_float(base_weight, precision=2)


def assign_time_splits(rows: list[dict[str, object]]) -> None:
    """Assign chronological train/validation/test indicators in place."""
    if not rows:
        return

    ordered_rows = sorted(
        rows,
        key=lambda row: (
            parse_date(row.get("entry_date")),
            parse_date(row.get("close_date")),
            str(row.get("trade_id") or ""),
        ),
    )
    total = len(ordered_rows)
    if total == 1 or total == 2:
        train_count = 1
        validation_count = 0
    else:
        train_count = max(1, int(total * TRAIN_FRACTION))
        validation_count = max(1, int(total * VALIDATION_FRACTION))
        remaining_for_test = total - train_count - validation_count
        if remaining_for_test < 1:
            validation_count = max(1, validation_count - (1 - remaining_for_test))
            remaining_for_test = total - train_count - validation_count
            if remaining_for_test < 1:
                train_count = max(1, train_count - 1)
                remaining_for_test = total - train_count - validation_count

    validation_end = train_count + validation_count

    for index, row in enumerate(ordered_rows):
        if index < train_count:
            split_group = "train"
        elif index < validation_end:
            split_group = "validation"
        else:
            split_group = "test"

        row["time_split_policy"] = TIME_SPLIT_POLICY
        row["time_split_group"] = split_group
        row["is_train"] = bool_flag(split_group == "train")
        row["is_validation"] = bool_flag(split_group == "validation")
        row["is_test"] = bool_flag(split_group == "test")


def derive_features(row: dict[str, str]) -> dict[str, str]:
    """Compute derived entry-time features for model input."""
    stock_price = parse_float(row.get("stock_price"))
    short_strike = parse_float(row.get("short_strike"))
    width = parse_float(row.get("width"))
    premium = parse_float(row.get("premium"))
    short_delta = parse_float(row.get("short_delta"))
    short_iv = parse_float(row.get("short_iv"))
    atm_iv = parse_float(row.get("atm_iv"))
    dte = parse_float(row.get("dte"))
    skew_ratio = parse_float(row.get("skew_ratio"))
    range_position = parse_float(row.get("range_position_52w"))

    moneyness_pct = (
        (stock_price - short_strike) / stock_price
        if stock_price not in (None, 0) and short_strike is not None
        else None
    )
    distance_to_short_strike_points = (
        stock_price - short_strike
        if stock_price is not None and short_strike is not None
        else None
    )
    distance_to_short_strike_pct = (
        distance_to_short_strike_points / stock_price
        if stock_price not in (None, 0) and distance_to_short_strike_points is not None
        else None
    )
    width_pct_of_stock = (
        width / stock_price
        if width not in (None, 0) and stock_price not in (None, 0)
        else None
    )
    premium_pct_of_width = (
        premium / (width * 100)
        if premium is not None and width not in (None, 0)
        else None
    )
    iv_spread = (
        short_iv - atm_iv if short_iv is not None and atm_iv is not None else None
    )
    delta_distance_from_target = (
        abs(abs(short_delta) - TARGET_DELTA) if short_delta is not None else None
    )

    return {
        "moneyness_pct": format_float(moneyness_pct),
        "distance_to_short_strike_points": format_float(
            distance_to_short_strike_points
        ),
        "distance_to_short_strike_pct": format_float(distance_to_short_strike_pct),
        "width_pct_of_stock": format_float(width_pct_of_stock),
        "premium_pct_of_width": format_float(premium_pct_of_width),
        "iv_spread": format_float(iv_spread),
        "delta_distance_from_target": format_float(delta_distance_from_target),
        "has_earnings_before_exit": bool_flag(as_bool(row.get("earnings_within_dte"))),
        "dte_bucket": bucket_value(
            dte,
            [(14, "lte_14"), (30, "15_30"), (45, "31_45"), (60, "46_60")],
            "gt_60",
        ),
        "delta_bucket": bucket_value(
            abs(short_delta) if short_delta is not None else None,
            [(0.15, "lte_0_15"), (0.20, "0_15_0_20"), (0.25, "0_20_0_25")],
            "gt_0_25",
        ),
        "skew_bucket": bucket_value(
            skew_ratio,
            [(0.90, "lt_0_90"), (1.00, "0_90_1_00"), (1.10, "1_00_1_10")],
            "gte_1_10",
        ),
        "width_bucket": bucket_value(
            width,
            [(2, "lte_2"), (5, "3_5"), (10, "6_10")],
            "gt_10",
        ),
        "range_position_bucket": bucket_value(
            range_position,
            [(0.20, "0_20"), (0.40, "20_40"), (0.60, "40_60"), (0.80, "60_80")],
            "80_100",
        ),
    }


def build_output_row(row: dict[str, str]) -> dict[str, object]:
    """Build one leakage-safe training row from an executed-trade row."""
    output = {column: "" for column in OUTPUT_COLUMNS}

    for column in METADATA_COLUMNS:
        if column == "feature_schema_version":
            output[column] = FEATURE_SCHEMA_VERSION
        elif column == "strategy_id":
            output[column] = canonical_strategy_id(row)
        elif column == "sample_weight":
            output[column] = recommended_sample_weight(row)
        elif column == "time_split_policy":
            output[column] = TIME_SPLIT_POLICY
        elif column in {"time_split_group", "is_train", "is_validation", "is_test"}:
            output[column] = ""
        else:
            output[column] = row.get(column, "")

    for column in FEATURE_COLUMNS:
        output[column] = row.get(column, "")

    if not str(output.get("strategy_id") or "").strip():
        output["strategy_id"] = canonical_strategy_id(row)

    output.update(derive_features(row))

    profit_loss = parse_float(row.get("profit_loss"))
    max_loss = parse_float(row.get("max_loss"))
    output["win_flag"] = bool_flag(profit_loss > 0 if profit_loss is not None else None)
    output["realized_return_on_risk"] = format_float(
        (profit_loss / max_loss)
        if profit_loss is not None and max_loss not in {None, 0.0}
        else None
    )
    for column in (
        "profit_loss",
        "profit_loss_pct",
        "profit_pct_of_max",
        "annualized_return",
        "days_held",
    ):
        output[column] = row.get(column, "")

    return output


def build_training_dataset(
    executed_dataset_path: Path = DEFAULT_EXECUTED_DATASET,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    """Build and write the leakage-safe training dataset."""
    validate_feature_schema()
    _, rows = load_csv_rows(executed_dataset_path)

    closed_rows = [
        row
        for row in rows
        if (row.get("trade_status") or "").strip().lower() == "closed"
        and (row.get("profit_loss") or "").strip() != ""
        and (row.get("max_loss") or "").strip() != ""
        and (row.get("match_status") or "").strip().lower() in INCLUDED_MATCH_STATUSES
        and as_bool(row.get("reviewed_setup_found"))
    ]

    output_rows = [build_output_row(row) for row in closed_rows]
    assign_time_splits(output_rows)
    output_rows.sort(
        key=lambda row: (
            str(row.get("entry_date") or ""),
            str(row.get("close_date") or ""),
            str(row.get("symbol") or ""),
            str(row.get("trade_id") or ""),
        )
    )
    write_csv(output_path, OUTPUT_COLUMNS, output_rows)
    return output_path


def main() -> None:
    """Build the training dataset and print a compact summary."""
    output_path = build_training_dataset()
    _, rows = load_csv_rows(output_path)
    exact_like = sum(
        1
        for row in rows
        if (row.get("match_status") or "").strip().lower()
        in {"exact_match", "adjusted_match"}
    )
    actual_exit = sum(1 for row in rows if as_bool(row.get("actual_exit_found")))
    realized_returns = [
        parse_float(row.get("realized_return_on_risk"))
        for row in rows
        if parse_float(row.get("realized_return_on_risk")) is not None
    ]
    strategy_counts: dict[str, int] = {}
    for row in rows:
        key = (row.get("strategy_id") or "").strip() or "(blank)"
        strategy_counts[key] = strategy_counts.get(key, 0) + 1
    split_counts = {
        split: sum(1 for row in rows if (row.get("time_split_group") or "") == split)
        for split in ("train", "validation", "test")
    }
    print(f"Training dataset written to: {output_path}")
    print(f"Training rows: {len(rows)}")
    print(f"Matched rows (exact+adjusted): {exact_like}")
    print(f"Rows with actual exits: {actual_exit}")
    if realized_returns:
        print(
            "Realized return on risk: "
            f"mean={mean(realized_returns):.4f}, "
            f"min={min(realized_returns):.4f}, "
            f"max={max(realized_returns):.4f}"
        )
    print(f"Strategy counts: {strategy_counts}")
    print(
        "Time split counts: "
        f"train={split_counts['train']}, "
        f"validation={split_counts['validation']}, "
        f"test={split_counts['test']}"
    )


if __name__ == "__main__":
    main()
