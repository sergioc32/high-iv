"""Generate a baseline report for the first model-score target dataset."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRAINING_DATASET = PROJECT_ROOT / "ml" / "training_dataset.csv"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "ml" / "reports"
DEFAULT_MD_REPORT = "model_score_baseline_report.md"
DEFAULT_CSV_REPORT = "model_score_baseline_report.csv"
REPORT_CSV_COLUMNS = ["section", "dimension", "group", "metric", "value"]


def load_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_float(value: object) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def as_bool(value: object) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def normalize_label(value: object) -> str:
    raw = str(value or "").strip()
    return raw if raw else "(blank)"


def markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    if not rows:
        return ["(none)"]
    divider = ["---"] * len(headers)
    lines = [f"| {' | '.join(headers)} |", f"| {' | '.join(divider)} |"]
    for row in rows:
        lines.append(f"| {' | '.join(row)} |")
    return lines


def summarize_target(rows: list[dict[str, str]]) -> dict[str, float]:
    rors = [
        value
        for row in rows
        if (value := parse_float(row.get("realized_return_on_risk"))) is not None
    ]
    annualized = [
        value
        for row in rows
        if (value := parse_float(row.get("annualized_return"))) is not None
    ]
    days = [
        value
        for row in rows
        if (value := parse_float(row.get("days_held"))) is not None
    ]
    wins = sum(1 for row in rows if (row.get("win_flag") or "").strip() == "1")
    if not rors:
        return {
            "trade_count": 0.0,
            "win_rate": 0.0,
            "avg_ror": 0.0,
            "median_ror": 0.0,
            "avg_annualized_return": 0.0,
            "avg_days_held": 0.0,
        }
    return {
        "trade_count": float(len(rors)),
        "win_rate": wins / len(rows) if rows else 0.0,
        "avg_ror": sum(rors) / len(rors),
        "median_ror": median(rors),
        "avg_annualized_return": (
            sum(annualized) / len(annualized) if annualized else 0.0
        ),
        "avg_days_held": (sum(days) / len(days) if days else 0.0),
    }


def build_group_summary(
    rows: list[dict[str, str]],
    group_name: str,
    key_fn,
) -> list[dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[key_fn(row)].append(row)
    output: list[dict[str, str]] = []
    for key, group_rows in grouped.items():
        stats = summarize_target(group_rows)
        output.append(
            {
                group_name: key,
                "trade_count": str(int(stats["trade_count"])),
                "win_rate": f"{stats['win_rate']:.2%}",
                "avg_ror": f"{stats['avg_ror']:.4f}",
                "median_ror": f"{stats['median_ror']:.4f}",
                "avg_annualized_return": f"{stats['avg_annualized_return']:.2f}",
                "avg_days_held": f"{stats['avg_days_held']:.2f}",
            }
        )
    output.sort(key=lambda row: (-int(row["trade_count"]), row[group_name]))
    return output


def alignment_bucket(row: dict[str, str]) -> str:
    score = parse_float(row.get("strategy_alignment_score"))
    if score is None:
        return "(blank)"
    if score < 60:
        return "<60"
    if score < 70:
        return "60-69"
    if score < 80:
        return "70-79"
    return "80+"


def render_markdown_report(dataset_path: Path, rows: list[dict[str, str]]) -> str:
    overall = summarize_target(rows)
    strategy_summary = build_group_summary(
        rows,
        "strategy_id",
        lambda row: normalize_label(row.get("strategy_id")),
    )
    provenance_summary = build_group_summary(
        rows,
        "feature_provenance",
        lambda row: normalize_label(row.get("feature_provenance")),
    )
    alignment_summary = build_group_summary(rows, "alignment_bucket", alignment_bucket)
    selector_summary = build_group_summary(
        rows,
        "selector_preferred_strategy",
        lambda row: normalize_label(row.get("selector_preferred_strategy")),
    )
    strategy_counts = Counter(normalize_label(row.get("strategy_id")) for row in rows)
    selector_populated = sum(
        1 for row in rows if str(row.get("selector_version") or "").strip()
    )
    lines = [
        "# Model Score Baseline Report",
        "",
        f"- Dataset: `{dataset_path}`",
        f"- Training rows: `{len(rows)}`",
        f"- Strategies present: `{dict(strategy_counts)}`",
        f"- Selector-version populated rows: `{selector_populated}`",
        "",
        "## Overall Target Summary",
        f"- Win rate: {overall['win_rate']:.2%}",
        f"- Avg realized return on risk: {overall['avg_ror']:.4f}",
        f"- Median realized return on risk: {overall['median_ror']:.4f}",
        f"- Avg annualized return: {overall['avg_annualized_return']:.2f}",
        f"- Avg days held: {overall['avg_days_held']:.2f}",
        "",
    ]
    if strategy_counts.get("call_credit_spread", 0) == 0:
        lines.extend(
            [
                "Baseline readiness note:",
                "- No call-credit-spread rows are present in the current trusted training set.",
                "- The first real supervised fit should therefore remain put-only until call-side closed history matures.",
                "",
            ]
        )

    section_specs = [
        ("## By Strategy", "strategy_id", strategy_summary),
        ("## By Feature Provenance", "feature_provenance", provenance_summary),
        ("## By Alignment Score Bucket", "alignment_bucket", alignment_summary),
        (
            "## By Selector Preferred Strategy",
            "selector_preferred_strategy",
            selector_summary,
        ),
    ]
    for title, key_name, summary in section_specs:
        lines.extend([title])
        lines.extend(
            markdown_table(
                [
                    key_name,
                    "Trades",
                    "Win Rate",
                    "Avg ROR",
                    "Median ROR",
                    "Avg Annualized Return",
                    "Avg Days Held",
                ],
                [
                    [
                        row[key_name],
                        row["trade_count"],
                        row["win_rate"],
                        row["avg_ror"],
                        row["median_ror"],
                        row["avg_annualized_return"],
                        row["avg_days_held"],
                    ]
                    for row in summary
                ],
            )
        )
        lines.append("")

    return "\n".join(lines)


def build_csv_rows(rows: list[dict[str, str]]) -> list[list[str]]:
    output: list[list[str]] = []
    overall = summarize_target(rows)
    for metric_name, value in overall.items():
        output.append(["overall", "target", "all", metric_name, str(value)])
    summaries = [
        (
            "strategy_id",
            build_group_summary(
                rows, "strategy_id", lambda row: normalize_label(row.get("strategy_id"))
            ),
        ),
        (
            "feature_provenance",
            build_group_summary(
                rows,
                "feature_provenance",
                lambda row: normalize_label(row.get("feature_provenance")),
            ),
        ),
        (
            "alignment_bucket",
            build_group_summary(rows, "alignment_bucket", alignment_bucket),
        ),
        (
            "selector_preferred_strategy",
            build_group_summary(
                rows,
                "selector_preferred_strategy",
                lambda row: normalize_label(row.get("selector_preferred_strategy")),
            ),
        ),
    ]
    for dimension, summary_rows in summaries:
        for row in summary_rows:
            group = row[dimension]
            for metric_name in (
                "trade_count",
                "win_rate",
                "avg_ror",
                "median_ror",
                "avg_annualized_return",
                "avg_days_held",
            ):
                output.append(
                    ["segmentation", dimension, group, metric_name, row[metric_name]]
                )
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-path",
        type=Path,
        default=DEFAULT_TRAINING_DATASET,
        help="Path to training_dataset.csv",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Directory for markdown and CSV output artifacts",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _, rows = load_csv_rows(args.dataset_path)
    markdown = render_markdown_report(args.dataset_path, rows)
    csv_rows = build_csv_rows(rows)
    md_path = args.reports_dir / DEFAULT_MD_REPORT
    csv_path = args.reports_dir / DEFAULT_CSV_REPORT
    write_text(md_path, markdown)
    write_csv(csv_path, REPORT_CSV_COLUMNS, csv_rows)
    print(f"Model score baseline markdown report written to: {md_path}")
    print(f"Model score baseline CSV artifact written to: {csv_path}")
    print(f"Training rows analyzed: {len(rows)}")


if __name__ == "__main__":
    main()
