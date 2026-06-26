"""Shared exposure concentration summaries for analytics reports."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from utils.analytics_fields import MARKET_CONTEXT_FIELDS, THEME_FIELD_NAMES

RISK_AMOUNT_FIELDS = [
    "buying_power_used",
    "max_loss",
]

DEFAULT_CONCENTRATION_DIMENSIONS = [
    ("sector", "Sector"),
    ("industry", "Industry"),
    ("risk_theme_tags", "Risk Theme"),
    ("technical_theme_tags", "Technical Theme"),
    ("theme_tags", "All Theme"),
]


def _split_values(value: object, *, split_tags: bool) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    if not split_tags:
        return [raw]
    return [part.strip() for part in raw.split(",") if part.strip()]


def _parse_money(value: object) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    is_negative = raw.startswith("(") and raw.endswith(")")
    cleaned = raw.strip("()").replace("$", "").replace(",", "")
    try:
        amount = float(cleaned)
    except ValueError:
        return 0.0
    return -amount if is_negative else amount


def _row_risk_amount(row: dict[str, str]) -> float:
    for field_name in RISK_AMOUNT_FIELDS:
        amount = _parse_money(row.get(field_name))
        if amount:
            return abs(amount)
    return 0.0


def build_concentration_rows(
    rows: list[dict[str, str]],
    *,
    dimensions: Iterable[tuple[str, str]] = DEFAULT_CONCENTRATION_DIMENSIONS,
    top_n: int = 10,
) -> list[dict[str, str]]:
    """Summarize trade-count concentration by sector, industry, and tags."""
    total = len(rows)
    output_rows: list[dict[str, str]] = []
    for field_name, label in dimensions:
        counts: Counter[str] = Counter()
        risk_amounts: Counter[str] = Counter()
        split_tags = field_name in THEME_FIELD_NAMES
        for row in rows:
            row_risk_amount = _row_risk_amount(row)
            for value in _split_values(row.get(field_name), split_tags=split_tags):
                counts[value] += 1
                risk_amounts[value] += row_risk_amount

        for group, count in counts.most_common(top_n):
            output_rows.append(
                {
                    "dimension": field_name,
                    "label": label,
                    "group": group,
                    "trade_count": str(count),
                    "trade_share": f"{(count / total):.1%}" if total else "0.0%",
                    "risk_amount": f"{risk_amounts[group]:.2f}",
                    "risk_amount_display": f"${risk_amounts[group]:,.2f}",
                }
            )
    return output_rows


def build_exposure_concentration(
    *,
    open_rows: list[dict[str, str]],
    closed_rows: list[dict[str, str]],
    top_n: int,
) -> dict[str, list[dict[str, str]]]:
    """Build open and closed concentration rows for report consumers."""
    return {
        "open": build_concentration_rows(open_rows, top_n=top_n),
        "closed": build_concentration_rows(closed_rows, top_n=top_n),
    }


def build_exposure_metric_rows(
    exposure_rows: dict[str, list[dict[str, str]]],
) -> list[list[str]]:
    """Flatten exposure concentration rows for report metrics exports."""
    rows: list[list[str]] = []
    for cohort, concentration_rows in exposure_rows.items():
        for row in concentration_rows:
            dimension = f"{cohort}|{row['dimension']}"
            rows.append(
                [
                    "exposure_concentration",
                    dimension,
                    row["group"],
                    "trade_count",
                    row["trade_count"],
                ]
            )
            rows.append(
                [
                    "exposure_concentration",
                    dimension,
                    row["group"],
                    "trade_share",
                    row["trade_share"],
                ]
            )
            rows.append(
                [
                    "exposure_concentration",
                    dimension,
                    row["group"],
                    "risk_amount",
                    row["risk_amount"],
                ]
            )
    return rows


def build_exposure_markdown_section(
    exposure_rows: dict[str, list[dict[str, str]]],
    markdown_table,
) -> list[str]:
    """Render exposure concentration rows as a markdown report section."""
    lines = [
        "## Exposure Concentration",
        "Trade-share percentages use all trades in the cohort as the denominator. "
        "Theme rows can sum above 100% because one trade may carry multiple tags.",
        "",
        "### Open Trades",
    ]
    for cohort, heading in (("open", "Open Trades"), ("closed", "Closed Trades")):
        if cohort == "closed":
            lines.extend(["", f"### {heading}"])
        lines.extend(
            markdown_table(
                ["Dimension", "Group", "Trades", "Trade %", "Risk $"],
                [
                    [
                        row["label"],
                        row["group"],
                        row["trade_count"],
                        row["trade_share"],
                        row.get("risk_amount_display", row["risk_amount"]),
                    ]
                    for row in exposure_rows.get(cohort, [])
                ],
            )
        )
    return lines


__all__ = [
    "MARKET_CONTEXT_FIELDS",
    "RISK_AMOUNT_FIELDS",
    "THEME_FIELD_NAMES",
    "build_concentration_rows",
    "build_exposure_concentration",
    "build_exposure_markdown_section",
    "build_exposure_metric_rows",
]
