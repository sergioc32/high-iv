"""Generate a trade-outcome review report from the executed-trade dataset."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from analysis.exposure_summary import (  # noqa: E402
    build_exposure_concentration,
    build_exposure_markdown_section,
    build_exposure_metric_rows,
)

DEFAULT_EXECUTED_TRADES = PROJECT_ROOT / "analysis" / "executed_trade_dataset.csv"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "analysis" / "reports"
REPORT_CSV_COLUMNS = ["section", "dimension", "group", "metric", "value"]

SELECTOR_REVIEW_FIELDS = [
    ("selector_version", "Selector Version"),
    ("alignment_score_version", "Alignment Score Version"),
    ("selector_preferred_strategy", "Preferred Strategy"),
    ("put_selector_score", "Put Selector Score"),
    ("call_selector_score", "Call Selector Score"),
    ("market_regime_summary", "Market Regime"),
    ("symbol_extension_bucket", "Symbol Extension"),
    ("always_review_symbol", "Always Review Symbol"),
    (
        "always_review_forced_into_analysis",
        "Always Review Forced Into Analysis",
    ),
    ("always_review_source", "Always Review Source"),
    ("review_decision", "Review Decision"),
    ("review_decision_reason", "Review Decision Reason"),
]


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


def normalize_group_label(value: object) -> str:
    """Normalize grouped labels for reporting output."""
    raw = str(value or "").strip()
    return raw if raw else "(blank)"


def always_review_flag_label(value: object) -> str:
    """Normalize always-review boolean flags for grouped reporting."""
    raw = str(value or "").strip()
    if raw == "":
        return "(blank)"
    return "true" if as_bool(raw) else "false"


def selector_alignment_group(row: dict[str, str]) -> str:
    """Summarize whether selector preference matched the executed strategy."""
    preferred = (row.get("selector_preferred_strategy") or "").strip().lower()
    strategy_id = (row.get("strategy_id") or "").strip().lower()
    if not preferred:
        return "missing_preference"
    if preferred == "both":
        return "both"
    if preferred == "none":
        return "none"
    if not strategy_id:
        return "missing_strategy"
    if preferred == "put" and strategy_id == "put_credit_spread":
        return "preferred_match"
    if preferred == "call" and strategy_id == "call_credit_spread":
        return "preferred_match"
    return "preferred_mismatch"


def build_field_coverage_rows(
    rows: list[dict[str, str]],
    *,
    cohort_name: str,
    fields: list[tuple[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Summarize how completely a cohort is populated for selector fields."""
    selected_fields = fields or SELECTOR_REVIEW_FIELDS
    total = len(rows)
    coverage_rows: list[dict[str, str]] = []
    for field_name, label in selected_fields:
        populated = sum(
            1 for row in rows if str(row.get(field_name) or "").strip() != ""
        )
        coverage_rows.append(
            {
                "cohort": cohort_name,
                "feature": label,
                "populated": str(populated),
                "total": str(total),
                "share": f"{(populated / total):.1%}" if total else "0.0%",
            }
        )
    return coverage_rows


def coverage_share_for_feature(
    coverage_rows: list[dict[str, str]],
    *,
    feature: str,
) -> float:
    """Return population share for one feature coverage row, defaulting to 0.0."""
    for row in coverage_rows:
        if row.get("feature") == feature:
            share_text = (row.get("share") or "").strip().rstrip("%")
            try:
                return float(share_text) / 100.0
            except ValueError:
                return 0.0
    return 0.0


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
    alignment_version_summary = build_group_summary(
        closed_rows,
        "alignment_score_version",
        lambda row: normalize_group_label(row.get("alignment_score_version")),
        top_n,
    )
    selector_version_summary = build_group_summary(
        closed_rows,
        "selector_version",
        lambda row: normalize_group_label(row.get("selector_version")),
        top_n,
    )
    selector_preferred_summary = build_group_summary(
        closed_rows,
        "selector_preferred_strategy",
        lambda row: normalize_group_label(row.get("selector_preferred_strategy")),
        top_n,
    )
    selector_alignment_summary = build_group_summary(
        closed_rows,
        "selector_alignment",
        selector_alignment_group,
        top_n,
    )
    selector_confidence_summary = build_group_summary(
        closed_rows,
        "selector_confidence",
        lambda row: normalize_group_label(row.get("selector_confidence")),
        top_n,
    )
    market_regime_summary = build_group_summary(
        closed_rows,
        "market_regime_summary",
        lambda row: normalize_group_label(row.get("market_regime_summary")),
        top_n,
    )
    symbol_extension_summary = build_group_summary(
        closed_rows,
        "symbol_extension_bucket",
        lambda row: normalize_group_label(row.get("symbol_extension_bucket")),
        top_n,
    )
    always_review_symbol_summary = build_group_summary(
        closed_rows,
        "always_review_symbol",
        lambda row: always_review_flag_label(row.get("always_review_symbol")),
        top_n,
    )
    always_review_forced_summary = build_group_summary(
        closed_rows,
        "always_review_forced_into_analysis",
        lambda row: always_review_flag_label(
            row.get("always_review_forced_into_analysis")
        ),
        top_n,
    )
    always_review_source_summary = build_group_summary(
        closed_rows,
        "always_review_source",
        lambda row: normalize_group_label(row.get("always_review_source")),
        top_n,
    )
    review_decision_summary = build_group_summary(
        closed_rows,
        "review_decision",
        lambda row: normalize_group_label(row.get("review_decision")),
        top_n,
    )
    review_reason_summary = build_group_summary(
        closed_rows,
        "review_decision_reason",
        lambda row: normalize_group_label(row.get("review_decision_reason")),
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
    selector_coverage_rows = build_field_coverage_rows(
        closed_rows,
        cohort_name="closed_trades",
    )
    exposure_concentration_rows = build_exposure_concentration(
        open_rows=open_rows,
        closed_rows=closed_rows,
        top_n=top_n,
    )

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
    ]
    lines.extend(
        build_exposure_markdown_section(
            exposure_concentration_rows,
            markdown_table,
        )
    )
    lines.extend(
        [
            "",
            "## Cohort Comparison",
        ]
    )
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
    lines.extend(["", "### Alignment Score Version"])
    lines.extend(
        markdown_table(
            ["Version", "Trades", "Win Rate", "Avg PnL", "Median PnL", "Total PnL"],
            [
                [
                    row["alignment_score_version"],
                    row["trade_count"],
                    row["win_rate"],
                    row["avg_pnl"],
                    row["median_pnl"],
                    row["total_pnl"],
                ]
                for row in alignment_version_summary
            ],
        )
    )
    lines.extend(["", "### Selector Version"])
    lines.extend(
        markdown_table(
            ["Version", "Trades", "Win Rate", "Avg PnL", "Median PnL", "Total PnL"],
            [
                [
                    row["selector_version"],
                    row["trade_count"],
                    row["win_rate"],
                    row["avg_pnl"],
                    row["median_pnl"],
                    row["total_pnl"],
                ]
                for row in selector_version_summary
            ],
        )
    )
    lines.extend(["", "## Strategy Selector Review"])
    lines.append(
        "Selector scores are informational-only in v1. These tables show how often "
        "the selector favored each state and whether that preference matched the "
        "executed strategy."
    )
    lines.extend(
        markdown_table(
            ["Feature", "Populated", "Total", "Share"],
            [
                [
                    row["feature"],
                    row["populated"],
                    row["total"],
                    row["share"],
                ]
                for row in selector_coverage_rows
            ],
        )
    )
    selector_share = coverage_share_for_feature(
        selector_coverage_rows,
        feature="Selector Version",
    )
    if selector_share < 1.0:
        lines.extend(
            [
                "",
                f"- Selector-version coverage across closed trades: {selector_share:.1%}",
                "- Lower coverage is expected until more trades opened after selector rollout have closed and entered the outcome dataset.",
            ]
        )
    lines.extend(["", "### Preferred Strategy"])
    lines.extend(
        markdown_table(
            ["State", "Trades", "Win Rate", "Avg PnL", "Median PnL", "Total PnL"],
            [
                [
                    row["selector_preferred_strategy"],
                    row["trade_count"],
                    row["win_rate"],
                    row["avg_pnl"],
                    row["median_pnl"],
                    row["total_pnl"],
                ]
                for row in selector_preferred_summary
            ],
        )
    )
    lines.extend(["", "### Selector Alignment"])
    lines.extend(
        markdown_table(
            ["Alignment", "Trades", "Win Rate", "Avg PnL", "Median PnL", "Total PnL"],
            [
                [
                    row["selector_alignment"],
                    row["trade_count"],
                    row["win_rate"],
                    row["avg_pnl"],
                    row["median_pnl"],
                    row["total_pnl"],
                ]
                for row in selector_alignment_summary
            ],
        )
    )
    lines.extend(["", "## Selector Context Segmentation"])
    lines.extend(["", "### Selector Confidence"])
    lines.extend(
        markdown_table(
            ["Confidence", "Trades", "Win Rate", "Avg PnL", "Median PnL", "Total PnL"],
            [
                [
                    row["selector_confidence"],
                    row["trade_count"],
                    row["win_rate"],
                    row["avg_pnl"],
                    row["median_pnl"],
                    row["total_pnl"],
                ]
                for row in selector_confidence_summary
            ],
        )
    )
    lines.extend(["", "### Market Regime"])
    lines.extend(
        markdown_table(
            ["Regime", "Trades", "Win Rate", "Avg PnL", "Median PnL", "Total PnL"],
            [
                [
                    row["market_regime_summary"],
                    row["trade_count"],
                    row["win_rate"],
                    row["avg_pnl"],
                    row["median_pnl"],
                    row["total_pnl"],
                ]
                for row in market_regime_summary
            ],
        )
    )
    lines.extend(["", "### Symbol Extension"])
    lines.extend(
        markdown_table(
            ["Extension", "Trades", "Win Rate", "Avg PnL", "Median PnL", "Total PnL"],
            [
                [
                    row["symbol_extension_bucket"],
                    row["trade_count"],
                    row["win_rate"],
                    row["avg_pnl"],
                    row["median_pnl"],
                    row["total_pnl"],
                ]
                for row in symbol_extension_summary
            ],
        )
    )
    lines.extend(["", "### Always-Review Symbol"])
    lines.extend(
        markdown_table(
            ["Flag", "Trades", "Win Rate", "Avg PnL", "Median PnL", "Total PnL"],
            [
                [
                    row["always_review_symbol"],
                    row["trade_count"],
                    row["win_rate"],
                    row["avg_pnl"],
                    row["median_pnl"],
                    row["total_pnl"],
                ]
                for row in always_review_symbol_summary
            ],
        )
    )
    lines.extend(["", "### Always-Review Forced State"])
    lines.extend(
        markdown_table(
            ["State", "Trades", "Win Rate", "Avg PnL", "Median PnL", "Total PnL"],
            [
                [
                    row["always_review_forced_into_analysis"],
                    row["trade_count"],
                    row["win_rate"],
                    row["avg_pnl"],
                    row["median_pnl"],
                    row["total_pnl"],
                ]
                for row in always_review_forced_summary
            ],
        )
    )
    lines.extend(["", "### Always-Review Source"])
    lines.extend(
        markdown_table(
            ["Source", "Trades", "Win Rate", "Avg PnL", "Median PnL", "Total PnL"],
            [
                [
                    row["always_review_source"],
                    row["trade_count"],
                    row["win_rate"],
                    row["avg_pnl"],
                    row["median_pnl"],
                    row["total_pnl"],
                ]
                for row in always_review_source_summary
            ],
        )
    )
    lines.extend(["", "### Review Decision"])
    lines.extend(
        markdown_table(
            ["Decision", "Trades", "Win Rate", "Avg PnL", "Median PnL", "Total PnL"],
            [
                [
                    row["review_decision"],
                    row["trade_count"],
                    row["win_rate"],
                    row["avg_pnl"],
                    row["median_pnl"],
                    row["total_pnl"],
                ]
                for row in review_decision_summary
            ],
        )
    )
    lines.extend(["", "### Review Decision Reason"])
    lines.extend(
        markdown_table(
            ["Reason", "Trades", "Win Rate", "Avg PnL", "Median PnL", "Total PnL"],
            [
                [
                    row["review_decision_reason"],
                    row["trade_count"],
                    row["win_rate"],
                    row["avg_pnl"],
                    row["median_pnl"],
                    row["total_pnl"],
                ]
                for row in review_reason_summary
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
            f"- Markdown: {format_repo_relative_path(markdown_output_path)}",
            f"- CSV: {format_repo_relative_path(csv_output_path)}",
        ]
    )
    return "\n".join(lines)


def build_metrics_rows(
    closed_rows: list[dict[str, str]],
    top_n: int,
    open_rows: list[dict[str, str]] | None = None,
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
    selector_coverage_rows = build_field_coverage_rows(
        closed_rows,
        cohort_name="closed_trades",
    )
    exposure_rows = build_exposure_concentration(
        open_rows=open_rows or [],
        closed_rows=closed_rows,
        top_n=top_n,
    )

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
        (
            "alignment_score_version",
            lambda row: normalize_group_label(row.get("alignment_score_version")),
        ),
        (
            "selector_version",
            lambda row: normalize_group_label(row.get("selector_version")),
        ),
        (
            "selector_preferred_strategy",
            lambda row: normalize_group_label(row.get("selector_preferred_strategy")),
        ),
        ("selector_alignment", selector_alignment_group),
        (
            "selector_confidence",
            lambda row: normalize_group_label(row.get("selector_confidence")),
        ),
        (
            "market_regime_summary",
            lambda row: normalize_group_label(row.get("market_regime_summary")),
        ),
        (
            "symbol_extension_bucket",
            lambda row: normalize_group_label(row.get("symbol_extension_bucket")),
        ),
        (
            "always_review_symbol",
            lambda row: always_review_flag_label(row.get("always_review_symbol")),
        ),
        (
            "always_review_forced_into_analysis",
            lambda row: always_review_flag_label(
                row.get("always_review_forced_into_analysis")
            ),
        ),
        (
            "always_review_source",
            lambda row: normalize_group_label(row.get("always_review_source")),
        ),
        (
            "review_decision",
            lambda row: normalize_group_label(row.get("review_decision")),
        ),
        (
            "review_decision_reason",
            lambda row: normalize_group_label(row.get("review_decision_reason")),
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
    for row in selector_coverage_rows:
        rows.append(
            [
                "selector_coverage",
                row["feature"],
                row["cohort"],
                "populated",
                row["populated"],
            ]
        )
        rows.append(
            [
                "selector_coverage",
                row["feature"],
                row["cohort"],
                "share",
                row["share"],
            ]
        )
    rows.extend(build_exposure_metric_rows(exposure_rows))
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
    metric_rows = build_metrics_rows(closed_rows, args.top_n, open_rows=open_rows)
    write_csv(csv_output_path, REPORT_CSV_COLUMNS, metric_rows)

    print(f"Trade outcome markdown report written to: {markdown_output_path}")
    print(f"Trade outcome CSV artifact written to: {csv_output_path}")
    print(f"Closed trades analyzed: {len(closed_rows)}")
    print(f"Open trades included: {len(open_rows)}")


if __name__ == "__main__":
    main()
