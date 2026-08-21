"""Generate an order-attempt fillability review from broker order history."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import median

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ORDER_ATTEMPTS = PROJECT_ROOT / "execution" / "order_attempts.csv"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "analysis" / "reports"
REPORT_CSV_COLUMNS = ["section", "dimension", "group", "metric", "value"]


def load_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Load a CSV file and return header plus rows."""
    if not path.exists():
        return [], []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    """Write CSV rows and create parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_text(path: Path, content: str) -> None:
    """Write text content and create parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_float(value: object) -> float | None:
    """Parse float-like text into a float."""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def format_money(value: float | None) -> str:
    """Format a dollar/credit value for report tables."""
    if value is None:
        return "(missing)"
    return f"{value:.2f}"


def normalize_label(value: object) -> str:
    """Normalize grouped labels for reporting output."""
    raw = str(value or "").strip()
    return raw if raw else "(blank)"


def markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Build a simple markdown table."""
    if not rows:
        return ["(none)"]
    divider = ["---"] * len(headers)
    lines = [f"| {' | '.join(headers)} |", f"| {' | '.join(divider)} |"]
    for row in rows:
        lines.append(f"| {' | '.join(row)} |")
    return lines


def summarize_attempts(rows: list[dict[str, str]]) -> dict[str, float]:
    """Summarize fillability outcomes for a group of order attempts."""
    total = len(rows)
    filled = sum(
        1
        for row in rows
        if (row.get("attempt_outcome") or "").strip().lower() == "filled"
    )
    expired = sum(
        1
        for row in rows
        if (row.get("attempt_outcome") or "").strip().lower() == "expired_unfilled"
    )
    limit_prices = [
        value
        for row in rows
        if (value := parse_float(row.get("limit_price"))) is not None
    ]
    return {
        "attempt_count": float(total),
        "filled_count": float(filled),
        "expired_count": float(expired),
        "fill_rate": (filled / total) if total else 0.0,
        "expired_rate": (expired / total) if total else 0.0,
        "avg_limit_credit": (
            sum(limit_prices) / len(limit_prices) if limit_prices else 0.0
        ),
        "median_limit_credit": median(limit_prices) if limit_prices else 0.0,
    }


def build_group_summary(
    rows: list[dict[str, str]],
    key_name: str,
    key_fn,
    top_n: int,
) -> list[dict[str, str]]:
    """Build grouped fillability summary rows."""
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[key_fn(row)].append(row)
    summary_rows: list[dict[str, str]] = []
    for key, group_rows in grouped.items():
        stats = summarize_attempts(group_rows)
        summary_rows.append(
            {
                key_name: key,
                "attempt_count": str(int(stats["attempt_count"])),
                "filled_count": str(int(stats["filled_count"])),
                "expired_count": str(int(stats["expired_count"])),
                "fill_rate": f"{stats['fill_rate']:.2%}",
                "expired_rate": f"{stats['expired_rate']:.2%}",
                "avg_limit_credit": format_money(stats["avg_limit_credit"]),
                "median_limit_credit": format_money(stats["median_limit_credit"]),
            }
        )
    summary_rows.sort(
        key=lambda row: (
            -int(row["attempt_count"]),
            -float(row["expired_rate"].rstrip("%")),
            row[key_name],
        )
    )
    return summary_rows[:top_n]


def build_markdown_report(
    *,
    rows: list[dict[str, str]],
    dataset_path: Path,
    markdown_output_path: Path,
    csv_output_path: Path,
    top_n: int,
) -> str:
    """Build the order-attempt review markdown."""
    overall = summarize_attempts(rows)
    strategy_summary = build_group_summary(
        rows,
        "strategy_id",
        lambda row: normalize_label(row.get("strategy_id")),
        top_n,
    )
    outcome_summary = build_group_summary(
        rows,
        "attempt_outcome",
        lambda row: normalize_label(row.get("attempt_outcome")),
        top_n,
    )
    symbol_summary = build_group_summary(
        rows,
        "underlying_symbol",
        lambda row: normalize_label(row.get("underlying_symbol")),
        top_n,
    )
    expired_rows = [
        row
        for row in rows
        if (row.get("attempt_outcome") or "").strip().lower() == "expired_unfilled"
    ]

    lines = [
        "# Order Attempt Review",
        "",
        f"- Source dataset: `{dataset_path}`",
        f"- Attempts analyzed: {len(rows)}",
        "",
        "## Executive Summary",
        f"- Fill rate: {overall['fill_rate']:.2%}",
        f"- Expired-unfilled rate: {overall['expired_rate']:.2%}",
        f"- Filled attempts: {int(overall['filled_count'])}",
        f"- Expired-unfilled attempts: {int(overall['expired_count'])}",
        f"- Avg limit credit: {format_money(overall['avg_limit_credit'])}",
        "",
        "## By Outcome",
    ]
    lines.extend(
        markdown_table(
            [
                "Outcome",
                "Attempts",
                "Filled",
                "Expired",
                "Fill Rate",
                "Expired Rate",
                "Avg Limit",
                "Median Limit",
            ],
            [
                [
                    row["attempt_outcome"],
                    row["attempt_count"],
                    row["filled_count"],
                    row["expired_count"],
                    row["fill_rate"],
                    row["expired_rate"],
                    row["avg_limit_credit"],
                    row["median_limit_credit"],
                ]
                for row in outcome_summary
            ],
        )
    )
    lines.extend(["", "## By Strategy"])
    lines.extend(
        markdown_table(
            [
                "Strategy",
                "Attempts",
                "Filled",
                "Expired",
                "Fill Rate",
                "Expired Rate",
                "Avg Limit",
                "Median Limit",
            ],
            [
                [
                    row["strategy_id"],
                    row["attempt_count"],
                    row["filled_count"],
                    row["expired_count"],
                    row["fill_rate"],
                    row["expired_rate"],
                    row["avg_limit_credit"],
                    row["median_limit_credit"],
                ]
                for row in strategy_summary
            ],
        )
    )
    lines.extend(["", "## By Symbol"])
    lines.extend(
        markdown_table(
            [
                "Symbol",
                "Attempts",
                "Filled",
                "Expired",
                "Fill Rate",
                "Expired Rate",
                "Avg Limit",
                "Median Limit",
            ],
            [
                [
                    row["underlying_symbol"],
                    row["attempt_count"],
                    row["filled_count"],
                    row["expired_count"],
                    row["fill_rate"],
                    row["expired_rate"],
                    row["avg_limit_credit"],
                    row["median_limit_credit"],
                ]
                for row in symbol_summary
            ],
        )
    )
    lines.extend(["", "## Expired-Unfilled Attempts"])
    lines.extend(
        markdown_table(
            [
                "Order",
                "Symbol",
                "Strategy",
                "Short",
                "Long",
                "Limit",
                "Received",
            ],
            [
                [
                    str(row.get("order_id") or ""),
                    str(row.get("underlying_symbol") or ""),
                    str(row.get("strategy_id") or ""),
                    str(row.get("short_strike") or ""),
                    str(row.get("long_strike") or ""),
                    str(row.get("limit_price") or ""),
                    str(row.get("received_at") or ""),
                ]
                for row in expired_rows[:top_n]
            ],
        )
    )
    lines.extend(
        [
            "",
            "## Notes",
            "- This report summarizes submitted broker orders, not analyzer-rejected candidates.",
            "- `expired_unfilled` is a fillability label for orders you attempted, while rejected candidates remain capture-only until a later recovery-analysis phase.",
            "",
            "## Artifacts",
            f"- Markdown: `{markdown_output_path}`",
            f"- CSV: `{csv_output_path}`",
        ]
    )
    return "\n".join(lines)


def build_metrics_rows(rows: list[dict[str, str]], top_n: int) -> list[list[str]]:
    """Build flattened CSV metric rows."""
    output: list[list[str]] = []
    overall = summarize_attempts(rows)
    for metric in (
        "attempt_count",
        "filled_count",
        "expired_count",
        "fill_rate",
        "expired_rate",
        "avg_limit_credit",
        "median_limit_credit",
    ):
        output.append(["overview", "all", "all", metric, str(overall.get(metric, ""))])

    for dimension, key_fn in (
        ("strategy_id", lambda row: normalize_label(row.get("strategy_id"))),
        ("attempt_outcome", lambda row: normalize_label(row.get("attempt_outcome"))),
        (
            "underlying_symbol",
            lambda row: normalize_label(row.get("underlying_symbol")),
        ),
    ):
        for row in build_group_summary(rows, dimension, key_fn, top_n):
            group = row[dimension]
            for metric in (
                "attempt_count",
                "filled_count",
                "expired_count",
                "fill_rate",
                "expired_rate",
                "avg_limit_credit",
                "median_limit_credit",
            ):
                output.append(["group_summary", dimension, group, metric, row[metric]])
    return output


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for order-attempt review."""
    parser = argparse.ArgumentParser(
        description="Generate markdown and CSV order-attempt fillability review."
    )
    parser.add_argument(
        "--order-attempts",
        type=Path,
        default=DEFAULT_ORDER_ATTEMPTS,
        help="Path to execution/order_attempts.csv",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Directory for report artifacts.",
    )
    parser.add_argument(
        "--output-prefix",
        default="order_attempt_review",
        help="Filename prefix for markdown/csv report artifacts.",
    )
    parser.add_argument("--top-n", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    """Generate order-attempt review outputs."""
    args = parse_args()
    _, rows = load_csv_rows(args.order_attempts)

    markdown_output_path = args.reports_dir / f"{args.output_prefix}.md"
    csv_output_path = args.reports_dir / f"{args.output_prefix}.csv"
    markdown = build_markdown_report(
        rows=rows,
        dataset_path=args.order_attempts,
        markdown_output_path=markdown_output_path,
        csv_output_path=csv_output_path,
        top_n=args.top_n,
    )
    metric_rows = build_metrics_rows(rows, args.top_n)

    write_text(markdown_output_path, markdown)
    write_csv(csv_output_path, REPORT_CSV_COLUMNS, metric_rows)
    print(f"Order-attempt markdown report written to: {markdown_output_path}")
    print(f"Order-attempt CSV artifact written to: {csv_output_path}")


if __name__ == "__main__":
    main()
