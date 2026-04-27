"""Generate a trade-outcome review report from the executed-trade dataset."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import median

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXECUTED_TRADES = PROJECT_ROOT / "analysis" / "executed_trade_dataset.csv"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "analysis" / "reports"
REPORT_CSV_COLUMNS = ["section", "dimension", "group", "metric", "value"]


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


def dte_band(value: object) -> str:
    """Bucket DTE into a few practical groups."""
    number = parse_float(value)
    if number is None:
        return "(missing)"
    dte_value = int(round(number))
    if dte_value <= 7:
        return "00-07"
    if dte_value <= 21:
        return "08-21"
    if dte_value <= 45:
        return "22-45"
    return "46+"


def delta_band(value: object) -> str:
    """Bucket short delta into broad groups."""
    number = parse_float(value)
    if number is None:
        return "(missing)"
    if number < 0.10:
        return "<0.10"
    if number < 0.20:
        return "0.10-0.19"
    if number < 0.30:
        return "0.20-0.29"
    return ">=0.30"


def summarize_performance(rows: list[dict[str, str]]) -> dict[str, float]:
    """Summarize trade performance for a row group."""
    pnls = [
        value
        for row in rows
        if (value := parse_float(row.get("profit_loss"))) is not None
    ]
    if not pnls:
        return {
            "trade_count": float(len(rows)),
            "win_rate": 0.0,
            "avg_pnl": 0.0,
            "median_pnl": 0.0,
            "total_pnl": 0.0,
        }
    wins = [value for value in pnls if value > 0]
    return {
        "trade_count": float(len(pnls)),
        "win_rate": len(wins) / len(pnls),
        "avg_pnl": sum(pnls) / len(pnls),
        "median_pnl": median(pnls),
        "total_pnl": sum(pnls),
    }


def build_group_summary(
    rows: list[dict[str, str]],
    key_name: str,
    key_fn,
    top_n: int,
) -> list[dict[str, str]]:
    """Build grouped performance rows."""
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[key_fn(row)].append(row)
    summary_rows: list[dict[str, str]] = []
    for key, group_rows in grouped.items():
        perf = summarize_performance(group_rows)
        summary_rows.append(
            {
                key_name: key,
                "trade_count": str(int(perf["trade_count"])),
                "win_rate": f"{perf['win_rate']:.2%}",
                "avg_pnl": f"{perf['avg_pnl']:.2f}",
                "median_pnl": f"{perf['median_pnl']:.2f}",
                "total_pnl": f"{perf['total_pnl']:.2f}",
            }
        )
    summary_rows.sort(
        key=lambda row: (-int(row["trade_count"]), -float(row["total_pnl"]))
    )
    return summary_rows[:top_n]


def build_feature_coverage_rows(
    closed_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Summarize feature-population coverage for closed-trade cohorts."""
    cohorts = [
        ("all_closed", closed_rows),
        (
            "feature_linked",
            [
                row
                for row in closed_rows
                if (row.get("match_status") or "").strip().lower()
                in {"exact_match", "adjusted_match"}
            ],
        ),
        (
            "trade_only",
            [
                row
                for row in closed_rows
                if (row.get("match_status") or "").strip().lower() == "trade_only"
            ],
        ),
    ]
    coverage_features = [
        "short_delta",
        "range_position_52w",
        "distance_to_52w_high_pct",
        "fill_quality_score",
        "fill_edge",
        "mid_capture_pct",
        "anchor_vs_shift_status",
        "shift_steps_from_anchor",
    ]
    coverage_rows: list[dict[str, str]] = []
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


def build_markdown_report(
    *,
    closed_rows: list[dict[str, str]],
    open_rows: list[dict[str, str]],
    top_n: int,
    markdown_output_path: Path,
    csv_output_path: Path,
) -> str:
    """Build the trade outcome review markdown."""
    overall = summarize_performance(closed_rows)
    feature_linked_rows = [
        row
        for row in closed_rows
        if (row.get("match_status") or "").strip().lower()
        in {"exact_match", "adjusted_match"}
    ]
    trade_only_rows = [
        row
        for row in closed_rows
        if (row.get("match_status") or "").strip().lower() == "trade_only"
    ]
    cohort_rows = [
        ("all_closed", closed_rows),
        ("feature_linked", feature_linked_rows),
        ("trade_only", trade_only_rows),
    ]
    match_summary = build_group_summary(
        closed_rows,
        "match_status",
        lambda row: (row.get("match_status") or "").strip() or "(blank)",
        top_n,
    )
    actual_exit_summary = build_group_summary(
        closed_rows,
        "actual_exit_found",
        lambda row: "actual" if as_bool(row.get("actual_exit_found")) else "estimated",
        top_n,
    )
    exit_source_summary = build_group_summary(
        closed_rows,
        "exit_price_source",
        lambda row: (row.get("exit_price_source") or "").strip() or "(blank)",
        top_n,
    )
    strategy_summary = build_group_summary(
        closed_rows,
        "strategy_version",
        lambda row: (row.get("strategy_version") or "").strip() or "(blank)",
        top_n,
    )
    dte_summary = build_group_summary(
        feature_linked_rows,
        "dte_band",
        lambda row: dte_band(row.get("dte")),
        top_n,
    )
    delta_summary = build_group_summary(
        feature_linked_rows,
        "delta_band",
        lambda row: delta_band(row.get("short_delta")),
        top_n,
    )
    fill_summary = build_group_summary(
        feature_linked_rows,
        "fill_quality_score_present",
        lambda row: (
            "present"
            if str(row.get("fill_quality_score") or "").strip() != ""
            else "missing"
        ),
        top_n,
    )
    feature_coverage_rows = build_feature_coverage_rows(closed_rows)

    lines = [
        "# Trade Outcome Review",
        "",
        f"- Closed trades analyzed: {len(closed_rows)}",
        f"- Open trades included: {len(open_rows)}",
        "",
        "## Executive Summary",
        f"- Win rate: {overall['win_rate']:.2%}",
        f"- Avg pnl: {overall['avg_pnl']:.2f}",
        f"- Median pnl: {overall['median_pnl']:.2f}",
        f"- Total pnl: {overall['total_pnl']:.2f}",
        f"- Feature-linked closed trades: {len(feature_linked_rows)}",
        f"- Trade-only closed trades: {len(trade_only_rows)}",
        "",
        "## Cohort Comparison",
    ]
    lines.extend(
        markdown_table(
            ["Cohort", "Trades", "Win Rate", "Avg PnL", "Median PnL", "Total PnL"],
            [
                [
                    cohort_name,
                    str(int(cohort_perf["trade_count"])),
                    f"{cohort_perf['win_rate']:.2%}",
                    f"{cohort_perf['avg_pnl']:.2f}",
                    f"{cohort_perf['median_pnl']:.2f}",
                    f"{cohort_perf['total_pnl']:.2f}",
                ]
                for cohort_name, cohort_perf in (
                    (name, summarize_performance(rows)) for name, rows in cohort_rows
                )
            ],
        )
    )
    lines.extend(
        [
            "",
            "## Match Quality",
        ]
    )
    lines.extend(
        markdown_table(
            [
                "Match Status",
                "Trades",
                "Win Rate",
                "Avg PnL",
                "Median PnL",
                "Total PnL",
            ],
            [
                [
                    row["match_status"],
                    row["trade_count"],
                    row["win_rate"],
                    row["avg_pnl"],
                    row["median_pnl"],
                    row["total_pnl"],
                ]
                for row in match_summary
            ],
        )
    )
    lines.extend(["", "## Actual vs Estimated Exit"])
    lines.extend(
        markdown_table(
            ["Exit Type", "Trades", "Win Rate", "Avg PnL", "Median PnL", "Total PnL"],
            [
                [
                    row["actual_exit_found"],
                    row["trade_count"],
                    row["win_rate"],
                    row["avg_pnl"],
                    row["median_pnl"],
                    row["total_pnl"],
                ]
                for row in actual_exit_summary
            ],
        )
    )
    lines.extend(["", "## Exit Price Sources"])
    lines.extend(
        markdown_table(
            ["Source", "Trades", "Win Rate", "Avg PnL", "Median PnL", "Total PnL"],
            [
                [
                    row["exit_price_source"],
                    row["trade_count"],
                    row["win_rate"],
                    row["avg_pnl"],
                    row["median_pnl"],
                    row["total_pnl"],
                ]
                for row in exit_source_summary
            ],
        )
    )
    lines.extend(["", "## Strategy Version"])
    lines.extend(
        markdown_table(
            ["Strategy", "Trades", "Win Rate", "Avg PnL", "Median PnL", "Total PnL"],
            [
                [
                    row["strategy_version"],
                    row["trade_count"],
                    row["win_rate"],
                    row["avg_pnl"],
                    row["median_pnl"],
                    row["total_pnl"],
                ]
                for row in strategy_summary
            ],
        )
    )
    lines.extend(["", "## Feature-Linked DTE Segmentation"])
    lines.extend(
        markdown_table(
            ["DTE Band", "Trades", "Win Rate", "Avg PnL", "Median PnL", "Total PnL"],
            [
                [
                    row["dte_band"],
                    row["trade_count"],
                    row["win_rate"],
                    row["avg_pnl"],
                    row["median_pnl"],
                    row["total_pnl"],
                ]
                for row in dte_summary
            ],
        )
    )
    lines.extend(["", "## Feature-Linked Delta Segmentation"])
    lines.extend(
        markdown_table(
            ["Delta Band", "Trades", "Win Rate", "Avg PnL", "Median PnL", "Total PnL"],
            [
                [
                    row["delta_band"],
                    row["trade_count"],
                    row["win_rate"],
                    row["avg_pnl"],
                    row["median_pnl"],
                    row["total_pnl"],
                ]
                for row in delta_summary
            ],
        )
    )
    lines.extend(["", "## Feature-Linked Fill-Signal Coverage"])
    lines.extend(
        markdown_table(
            [
                "Fill Signals",
                "Trades",
                "Win Rate",
                "Avg PnL",
                "Median PnL",
                "Total PnL",
            ],
            [
                [
                    row["fill_quality_score_present"],
                    row["trade_count"],
                    row["win_rate"],
                    row["avg_pnl"],
                    row["median_pnl"],
                    row["total_pnl"],
                ]
                for row in fill_summary
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
    lines.extend(
        [
            "",
            "## Artifacts",
            f"- Markdown: {markdown_output_path}",
            f"- CSV: {csv_output_path}",
        ]
    )
    return "\n".join(lines)


def build_metrics_rows(
    closed_rows: list[dict[str, str]], top_n: int
) -> list[list[str]]:
    """Build flattened CSV metric rows."""
    rows: list[list[str]] = []
    overall = summarize_performance(closed_rows)
    feature_linked_rows = [
        row
        for row in closed_rows
        if (row.get("match_status") or "").strip().lower()
        in {"exact_match", "adjusted_match"}
    ]
    trade_only_rows = [
        row
        for row in closed_rows
        if (row.get("match_status") or "").strip().lower() == "trade_only"
    ]
    for metric_name, value in overall.items():
        rows.append(["overview", "performance", "all", metric_name, str(value)])
    for cohort_name, cohort_rows in (
        ("all_closed", closed_rows),
        ("feature_linked", feature_linked_rows),
        ("trade_only", trade_only_rows),
    ):
        cohort_summary = summarize_performance(cohort_rows)
        for metric_name, value in cohort_summary.items():
            rows.append(["cohort", "performance", cohort_name, metric_name, str(value)])
    feature_coverage_rows = build_feature_coverage_rows(closed_rows)

    group_specs = [
        (
            "match_status",
            lambda row: (row.get("match_status") or "").strip() or "(blank)",
        ),
        (
            "actual_exit_found",
            lambda row: (
                "actual" if as_bool(row.get("actual_exit_found")) else "estimated"
            ),
        ),
        (
            "exit_price_source",
            lambda row: (row.get("exit_price_source") or "").strip() or "(blank)",
        ),
        (
            "strategy_version",
            lambda row: (row.get("strategy_version") or "").strip() or "(blank)",
        ),
        ("dte_band", lambda row: dte_band(row.get("dte"))),
        ("delta_band", lambda row: delta_band(row.get("short_delta"))),
    ]
    for dimension, key_fn in group_specs:
        source_rows = (
            feature_linked_rows
            if dimension in {"dte_band", "delta_band"}
            else closed_rows
        )
        summary_rows = build_group_summary(source_rows, dimension, key_fn, top_n)
        for row in summary_rows:
            for metric_name in (
                "trade_count",
                "win_rate",
                "avg_pnl",
                "median_pnl",
                "total_pnl",
            ):
                rows.append(
                    [
                        "segmentation",
                        dimension,
                        row[dimension],
                        metric_name,
                        row[metric_name],
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
    """Parse CLI arguments for trade outcome review."""
    parser = argparse.ArgumentParser(
        description="Generate markdown and CSV trade outcome review outputs."
    )
    parser.add_argument(
        "--executed-trades",
        type=Path,
        default=DEFAULT_EXECUTED_TRADES,
        help="Path to executed_trade_dataset.csv",
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
        default="trade_outcome_review",
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
    """Generate trade outcome review outputs."""
    args = parse_args()
    _, rows = load_csv_rows(args.executed_trades)
    closed_rows = [
        row
        for row in rows
        if (row.get("trade_status") or "").strip().lower() == "closed"
    ]
    open_rows = [
        row for row in rows if (row.get("trade_status") or "").strip().lower() == "open"
    ]

    markdown_output_path = args.reports_dir / f"{args.output_prefix}.md"
    csv_output_path = args.reports_dir / f"{args.output_prefix}.csv"
    report_text = build_markdown_report(
        closed_rows=closed_rows,
        open_rows=open_rows,
        top_n=args.top_n,
        markdown_output_path=markdown_output_path,
        csv_output_path=csv_output_path,
    )
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_output_path.write_text(report_text, encoding="utf-8")
    metric_rows = build_metrics_rows(closed_rows, args.top_n)
    write_csv(csv_output_path, REPORT_CSV_COLUMNS, metric_rows)

    print(f"Trade outcome markdown report written to: {markdown_output_path}")
    print(f"Trade outcome CSV artifact written to: {csv_output_path}")
    print(f"Closed trades analyzed: {len(closed_rows)}")
    print(f"Open trades included: {len(open_rows)}")


if __name__ == "__main__":
    main()
