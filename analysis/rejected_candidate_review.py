"""Generate a rejected-candidate review report from dense analytics datasets."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
from statistics import mean

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REJECTED_DATASET = PROJECT_ROOT / "analysis" / "rejected_candidate_dataset.csv"
DEFAULT_CANDIDATES_PATH = PROJECT_ROOT / "opportunities" / "opportunity_candidates.csv"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "analysis" / "reports"
REPORT_CSV_COLUMNS = ["section", "dimension", "group", "metric", "value"]
LEGACY_REASON_ALIASES = {
    "credit_conservative": "credit_expected_too_low",
}
REASON_BUCKETS = {
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
    """Load a CSV file and return header plus rows."""
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    """Write CSV rows and create parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def format_repo_relative_path(path: Path) -> str:
    """Render a path relative to the repo root when possible."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def parse_float(value: object) -> float | None:
    """Parse float-like text into a float."""
    raw = str(value or "").strip()
    if raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def as_bool(value: object) -> bool:
    """Parse common CSV boolean-like values."""
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Build a simple markdown table."""
    if not rows:
        return ["(none)"]
    divider = ["---"] * len(headers)
    lines = [
        f"| {' | '.join(headers)} |",
        f"| {' | '.join(divider)} |",
    ]
    for row in rows:
        lines.append(f"| {' | '.join(row)} |")
    return lines


def normalize_reason(reason: str) -> str:
    """Normalize legacy rejection names to the current taxonomy."""
    normalized = LEGACY_REASON_ALIASES.get(reason, reason)
    return normalized or "(blank)"


def normalized_bucket(reason: str) -> str:
    """Map a normalized reason into its bucket."""
    return REASON_BUCKETS.get(normalize_reason(reason), "other")


def average_feature(rows: list[dict[str, str]], column: str) -> float | None:
    """Return the average of a numeric column across rows."""
    values = [
        value for row in rows if (value := parse_float(row.get(column))) is not None
    ]
    if not values:
        return None
    return mean(values)


def build_feature_coverage_rows(
    candidate_rows: list[dict[str, str]],
    rejected_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Summarize feature-population coverage for selected vs rejected rows."""
    selected_rows = [
        row
        for row in candidate_rows
        if (row.get("candidate_status") or "").strip().lower() == "selected"
    ]
    coverage_features = [
        "range_position_52w",
        "distance_to_52w_high_pct",
        "distance_to_52w_low_pct",
        "fill_quality_score",
        "fill_edge",
        "mid_capture_pct",
        "anchor_vs_shift_status",
        "shift_steps_from_anchor",
    ]
    coverage_rows: list[dict[str, str]] = []
    cohorts = [
        ("selected", selected_rows),
        ("rejected", rejected_rows),
    ]
    for feature in coverage_features:
        for cohort_name, cohort_rows in cohorts:
            populated = sum(
                1 for row in cohort_rows if str(row.get(feature) or "").strip() != ""
            )
            total = len(cohort_rows)
            coverage_rows.append(
                {
                    "feature": feature,
                    "cohort": cohort_name,
                    "populated": str(populated),
                    "total": str(total),
                    "share": f"{(populated / total):.1%}" if total else "0.0%",
                }
            )
    return coverage_rows


def build_near_miss_rows(
    rejected_rows: list[dict[str, str]],
    normalized_reason: str,
    top_n: int,
) -> list[dict[str, str]]:
    """Return the top near-miss rows for a specific rejection reason."""
    candidates = [
        row
        for row in rejected_rows
        if normalize_reason((row.get("rejection_reason_primary") or "").strip())
        == normalized_reason
    ]

    def sort_key(row: dict[str, str]) -> tuple[float, float]:
        premium_pct_of_width = parse_float(row.get("premium_pct_of_width"))
        risk_reward_ratio = parse_float(row.get("risk_reward_ratio"))
        delta_distance = parse_float(row.get("delta_distance_from_target"))
        ev_score = parse_float(row.get("ev_score"))

        if normalized_reason == "credit_expected_too_low":
            return (-(premium_pct_of_width or -999), -(ev_score or -999))
        if normalized_reason == "risk_reward":
            return (risk_reward_ratio or 999, -(ev_score or -999))
        if normalized_reason == "delta_bounds_max":
            return (delta_distance or 999, -(ev_score or -999))
        if normalized_reason == "selected_ranked_out":
            return (-(ev_score or -999), -(premium_pct_of_width or -999))
        return (-(ev_score or -999), -(premium_pct_of_width or -999))

    deduped_rows: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str, str, str]] = set()
    for row in sorted(candidates, key=sort_key):
        dedupe_key = (
            (row.get("symbol") or "").strip(),
            (row.get("expiration_date") or "").strip(),
            (row.get("short_strike") or "").strip(),
            (row.get("long_strike") or "").strip(),
        )
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        deduped_rows.append(row)
        if len(deduped_rows) >= top_n:
            break
    return deduped_rows


def build_selected_vs_rejected_summary(
    candidate_rows: list[dict[str, str]],
    rejected_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Compare selected and rejected populations on a few core numeric fields."""
    selected_rows = [
        row
        for row in candidate_rows
        if (row.get("candidate_status") or "").strip().lower() == "selected"
    ]

    features = [
        "premium_per_width",
        "short_delta",
        "skew_ratio",
        "fill_quality",
        "range_position_52w",
        "distance_to_52w_high_pct",
        "fill_quality_score",
    ]
    rows: list[dict[str, str]] = []
    for feature in features:
        selected_avg = average_feature(selected_rows, feature)
        rejected_avg = average_feature(rejected_rows, feature)
        rows.append(
            {
                "feature": feature,
                "selected_avg": (
                    f"{selected_avg:.4f}" if selected_avg is not None else "(missing)"
                ),
                "rejected_avg": (
                    f"{rejected_avg:.4f}" if rejected_avg is not None else "(missing)"
                ),
            }
        )
    return rows


def build_markdown_report(
    *,
    rejected_rows: list[dict[str, str]],
    candidate_rows: list[dict[str, str]],
    top_n: int,
    markdown_output_path: Path,
    csv_output_path: Path,
) -> str:
    """Build the markdown rejected-candidate review."""
    reason_counter = Counter(
        normalize_reason((row.get("rejection_reason_primary") or "").strip())
        for row in rejected_rows
    )
    bucket_counter = Counter(
        normalized_bucket((row.get("rejection_reason_primary") or "").strip())
        for row in rejected_rows
    )
    symbol_counter = Counter(
        (row.get("symbol") or "").strip() or "(blank)" for row in rejected_rows
    )
    selected_vs_rejected = build_selected_vs_rejected_summary(
        candidate_rows, rejected_rows
    )
    feature_coverage_rows = build_feature_coverage_rows(candidate_rows, rejected_rows)

    lines = [
        "# Rejected Candidate Review",
        "",
        f"- Rejected rows analyzed: {len(rejected_rows)}",
        f"- Source dataset: {format_repo_relative_path(DEFAULT_REJECTED_DATASET)}",
        "",
        "## Executive Summary",
        f"- Top rejection bucket: {bucket_counter.most_common(1)[0][0] if bucket_counter else '(none)'}",
        f"- Top rejection reason: {reason_counter.most_common(1)[0][0] if reason_counter else '(none)'}",
        f"- Symbols with rejections: {len(symbol_counter)}",
        "",
        "## Top Rejection Buckets",
    ]
    lines.extend(
        markdown_table(
            ["Bucket", "Count"],
            [
                [bucket, str(count)]
                for bucket, count in bucket_counter.most_common(top_n)
            ],
        )
    )
    lines.extend(["", "## Top Rejection Reasons"])
    lines.extend(
        markdown_table(
            ["Reason", "Count"],
            [
                [reason, str(count)]
                for reason, count in reason_counter.most_common(top_n)
            ],
        )
    )
    lines.extend(["", "## Top Symbols By Rejections"])
    lines.extend(
        markdown_table(
            ["Symbol", "Rejected Rows"],
            [
                [symbol, str(count)]
                for symbol, count in symbol_counter.most_common(top_n)
            ],
        )
    )
    lines.extend(["", "## Selected vs Rejected Feature Comparison"])
    lines.extend(
        markdown_table(
            ["Feature", "Selected Avg", "Rejected Avg"],
            [
                [row["feature"], row["selected_avg"], row["rejected_avg"]]
                for row in selected_vs_rejected
            ],
        )
    )
    lines.extend(["", "## Feature Coverage"])
    lines.extend(
        markdown_table(
            ["Feature", "Cohort", "Populated", "Total", "Share"],
            [
                [
                    row["feature"],
                    row["cohort"],
                    row["populated"],
                    row["total"],
                    row["share"],
                ]
                for row in feature_coverage_rows
            ],
        )
    )

    for reason in (
        "credit_expected_too_low",
        "risk_reward",
        "delta_bounds_max",
        "selected_ranked_out",
    ):
        near_miss_rows = build_near_miss_rows(rejected_rows, reason, top_n)
        lines.extend(["", f"## Near-Miss Review: {reason}"])
        lines.extend(
            markdown_table(
                [
                    "Symbol",
                    "DTE",
                    "Premium/Width",
                    "Delta",
                    "Skew",
                    "Fill Score",
                    "52W Position",
                    "EV",
                ],
                [
                    [
                        str(row.get("symbol") or ""),
                        str(row.get("dte") or ""),
                        str(row.get("premium_pct_of_width") or ""),
                        str(row.get("short_delta") or ""),
                        str(row.get("skew_ratio") or ""),
                        str(row.get("fill_quality_score") or ""),
                        str(row.get("range_position_52w") or ""),
                        str(row.get("ev_score") or ""),
                    ]
                    for row in near_miss_rows
                ],
            )
        )

    lines.extend(
        [
            "",
            "## Artifacts",
            f"- Markdown: {format_repo_relative_path(markdown_output_path)}",
            f"- CSV: {format_repo_relative_path(csv_output_path)}",
        ]
    )
    return "\n".join(lines)


def build_metrics_rows(
    rejected_rows: list[dict[str, str]],
    candidate_rows: list[dict[str, str]],
    top_n: int,
) -> list[list[str]]:
    """Build flattened CSV metric rows."""
    reason_counter = Counter(
        normalize_reason((row.get("rejection_reason_primary") or "").strip())
        for row in rejected_rows
    )
    bucket_counter = Counter(
        normalized_bucket((row.get("rejection_reason_primary") or "").strip())
        for row in rejected_rows
    )
    symbol_counter = Counter(
        (row.get("symbol") or "").strip() or "(blank)" for row in rejected_rows
    )
    selected_vs_rejected = build_selected_vs_rejected_summary(
        candidate_rows, rejected_rows
    )
    feature_coverage_rows = build_feature_coverage_rows(candidate_rows, rejected_rows)

    rows: list[list[str]] = []
    rows.append(["overview", "counts", "all", "rejected_rows", str(len(rejected_rows))])

    for bucket, count in bucket_counter.most_common(top_n):
        rows.append(["rejections", "bucket", bucket, "count", str(count)])
    for reason, count in reason_counter.most_common(top_n):
        rows.append(["rejections", "reason", reason, "count", str(count)])
    for symbol, count in symbol_counter.most_common(top_n):
        rows.append(["rejections", "symbol", symbol, "count", str(count)])
    for row in selected_vs_rejected:
        rows.append(
            [
                "comparison",
                "selected_vs_rejected",
                row["feature"],
                "selected_avg",
                row["selected_avg"],
            ]
        )
        rows.append(
            [
                "comparison",
                "selected_vs_rejected",
                row["feature"],
                "rejected_avg",
                row["rejected_avg"],
            ]
        )
    for row in feature_coverage_rows:
        rows.append(
            [
                "coverage",
                row["feature"],
                row["cohort"],
                "populated",
                row["populated"],
            ]
        )
        rows.append(
            [
                "coverage",
                row["feature"],
                row["cohort"],
                "share",
                row["share"],
            ]
        )

    return rows


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for rejected-candidate review."""
    parser = argparse.ArgumentParser(
        description="Generate markdown and CSV rejected-candidate review outputs."
    )
    parser.add_argument(
        "--rejected-dataset",
        type=Path,
        default=DEFAULT_REJECTED_DATASET,
        help="Path to rejected_candidate_dataset.csv",
    )
    parser.add_argument(
        "--candidate-log",
        type=Path,
        default=DEFAULT_CANDIDATES_PATH,
        help="Path to opportunity_candidates.csv",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Directory for markdown and CSV outputs.",
    )
    parser.add_argument(
        "--output-prefix",
        type=str,
        default="rejected_candidate_review",
        help="Prefix for generated markdown and CSV report files.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Maximum rows per top-N section.",
    )
    return parser.parse_args()


def main() -> None:
    """Generate rejected-candidate review outputs."""
    args = parse_args()
    _, rejected_rows = load_csv_rows(args.rejected_dataset)
    _, candidate_rows = load_csv_rows(args.candidate_log)

    markdown_output_path = args.reports_dir / f"{args.output_prefix}.md"
    csv_output_path = args.reports_dir / f"{args.output_prefix}.csv"
    report_text = build_markdown_report(
        rejected_rows=rejected_rows,
        candidate_rows=candidate_rows,
        top_n=args.top_n,
        markdown_output_path=markdown_output_path,
        csv_output_path=csv_output_path,
    )
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_output_path.write_text(report_text, encoding="utf-8")
    metric_rows = build_metrics_rows(rejected_rows, candidate_rows, args.top_n)
    write_csv(csv_output_path, REPORT_CSV_COLUMNS, metric_rows)

    print(f"Rejected-candidate markdown report written to: {markdown_output_path}")
    print(f"Rejected-candidate CSV artifact written to: {csv_output_path}")
    print(f"Rejected rows analyzed: {len(rejected_rows)}")


if __name__ == "__main__":
    main()
