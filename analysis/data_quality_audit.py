"""Data quality audit checks for Phase 1 analytics datasets.

This script focuses on the highest-value validation checks for the current
analytics workflow:

1. Schema drift checks for the candidate dataset.
2. Numeric range and consistency checks on candidate rows.
3. Duplicate candidate detection within the same run.

The output is a human-readable audit summary intended for manual review.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from screener.spread_logging import CANDIDATE_FIELDNAMES  # noqa: E402
from screener.strategy_types import CALL_CREDIT_SPREAD, PUT_CREDIT_SPREAD  # noqa: E402

CANDIDATES_PATH = PROJECT_ROOT / "opportunities" / "opportunity_candidates.csv"

EXPECTED_CANDIDATE_COLUMNS = list(CANDIDATE_FIELDNAMES)

ALLOWED_CANDIDATE_STATUS = {
    "selected",
    "rejected",
    "reviewed_context",
    "executed_unmatched",
}
ALLOWED_SELECTED_VALUES = {"true", "false"}
VALID_ECONOMICS_EXPECTED_REASONS = {
    "",
    "selected_ranked_out",
    "risk_reward",
}


@dataclass(frozen=True)
class AuditIssue:
    """Represent one audit issue found in a dataset."""

    category: str
    severity: str
    message: str
    row_number: int | None = None


def load_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Load a CSV file and return its header and rows."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return reader.fieldnames or [], list(reader)


def parse_float(value: str) -> float | None:
    """Parse a string to float, returning None for blanks or invalid values."""
    raw = (value or "").strip()
    if raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_bool_text(value: str) -> bool | None:
    """Parse a CSV boolean-like string into bool."""
    raw = (value or "").strip().lower()
    if raw == "true":
        return True
    if raw == "false":
        return False
    return None


def normalize_strategy_id(strategy_id: str) -> str:
    """Default blank legacy rows to the original put credit spread strategy."""
    return (strategy_id or "").strip() or PUT_CREDIT_SPREAD.strategy_id


def audit_candidate_schema(header: list[str]) -> list[AuditIssue]:
    """Check candidate dataset schema against the expected contract."""
    issues: list[AuditIssue] = []
    missing = [col for col in EXPECTED_CANDIDATE_COLUMNS if col not in header]
    extra = [col for col in header if col not in EXPECTED_CANDIDATE_COLUMNS]

    if missing:
        issues.append(
            AuditIssue(
                category="schema",
                severity="error",
                message=f"Missing expected columns: {', '.join(missing)}",
            )
        )

    if extra:
        issues.append(
            AuditIssue(
                category="schema",
                severity="warning",
                message=f"Unexpected extra columns: {', '.join(extra)}",
            )
        )

    if header[: len(EXPECTED_CANDIDATE_COLUMNS)] != EXPECTED_CANDIDATE_COLUMNS:
        issues.append(
            AuditIssue(
                category="schema",
                severity="warning",
                message="Candidate column order differs from canonical contract.",
            )
        )

    return issues


def audit_candidate_duplicates(rows: list[dict[str, str]]) -> list[AuditIssue]:
    """Detect duplicate candidate identity rows within the same run."""
    issues: list[AuditIssue] = []
    counts: Counter[tuple[str, str, str, str, str, str, str]] = Counter()

    for row in rows:
        key = (
            row.get("run_id", ""),
            normalize_strategy_id(row.get("strategy_id", "")),
            row.get("symbol", ""),
            row.get("expiration_date", ""),
            row.get("short_strike", ""),
            row.get("long_strike", ""),
            row.get("candidate_status", ""),
        )
        counts[key] += 1

    for key, count in counts.items():
        if count <= 1:
            continue
        (
            run_id,
            strategy_id,
            symbol,
            expiration_date,
            short_strike,
            long_strike,
            status,
        ) = key
        issues.append(
            AuditIssue(
                category="duplicates",
                severity="warning",
                message=(
                    "Duplicate candidate rows detected for "
                    f"run_id={run_id}, strategy_id={strategy_id}, "
                    f"symbol={symbol}, expiration={expiration_date}, "
                    f"short={short_strike}, long={long_strike}, status={status} "
                    f"({count} rows)"
                ),
            )
        )

    return issues


def audit_candidate_ranges(rows: list[dict[str, str]]) -> list[AuditIssue]:
    """Validate required fields, numeric ranges, and row consistency."""
    issues: list[AuditIssue] = []

    for index, row in enumerate(rows, start=2):
        symbol = (row.get("symbol") or "").strip()
        run_id = (row.get("run_id") or "").strip()
        expiration_date = (row.get("expiration_date") or "").strip()

        if not run_id or not symbol or not expiration_date:
            issues.append(
                AuditIssue(
                    category="required_fields",
                    severity="error",
                    row_number=index,
                    message="Missing required identity field(s).",
                )
            )

        dte = parse_float(row.get("dte", ""))
        stock_price = parse_float(row.get("stock_price", ""))
        short_strike = parse_float(row.get("short_strike", ""))
        long_strike = parse_float(row.get("long_strike", ""))
        width = parse_float(row.get("width", ""))
        credit_mid = parse_float(row.get("credit_mid", ""))
        credit_natural = parse_float(row.get("credit_natural", ""))
        credit_expected = parse_float(row.get("credit_expected", ""))
        fill_quality = parse_float(row.get("fill_quality", ""))
        avg_width_pct = parse_float(row.get("avg_width_pct", ""))
        mid_weight = parse_float(row.get("mid_weight", ""))
        premium = parse_float(row.get("premium", ""))
        premium_per_width = parse_float(row.get("premium_per_width", ""))
        max_profit = parse_float(row.get("max_profit", ""))
        risk_reward_ratio = parse_float(row.get("risk_reward_ratio", ""))
        ev_score = parse_float(row.get("ev_score", ""))
        short_delta = parse_float(row.get("short_delta", ""))
        short_iv = parse_float(row.get("short_iv", ""))
        atm_iv = parse_float(row.get("atm_iv", ""))
        skew_ratio = parse_float(row.get("skew_ratio", ""))
        selected = parse_bool_text(row.get("selected", ""))
        strategy_id = normalize_strategy_id(row.get("strategy_id", ""))
        candidate_status = (row.get("candidate_status") or "").strip().lower()
        rejection_reason = (row.get("rejection_reason_primary") or "").strip()

        economics_should_be_valid = selected is True or (
            rejection_reason in VALID_ECONOMICS_EXPECTED_REASONS
        )

        if dte is None or dte < 0:
            issues.append(
                AuditIssue(
                    category="ranges",
                    severity="error",
                    row_number=index,
                    message=f"Invalid dte for {symbol}: {row.get('dte', '')}",
                )
            )

        if stock_price is None or stock_price <= 0:
            issues.append(
                AuditIssue(
                    category="ranges",
                    severity="error",
                    row_number=index,
                    message=(
                        f"Invalid stock_price for {symbol}: "
                        f"{row.get('stock_price', '')}"
                    ),
                )
            )

        if short_strike is None or short_strike <= 0:
            issues.append(
                AuditIssue(
                    category="ranges",
                    severity="error",
                    row_number=index,
                    message=(
                        f"Invalid short_strike for {symbol}: "
                        f"{row.get('short_strike', '')}"
                    ),
                )
            )

        if width is not None and width <= 0:
            issues.append(
                AuditIssue(
                    category="ranges",
                    severity="error",
                    row_number=index,
                    message=f"Invalid width for {symbol}: {row.get('width', '')}",
                )
            )

        if (
            long_strike is not None
            and short_strike is not None
            and (
                (
                    strategy_id == PUT_CREDIT_SPREAD.strategy_id
                    and long_strike >= short_strike
                )
                or (
                    strategy_id == CALL_CREDIT_SPREAD.strategy_id
                    and long_strike <= short_strike
                )
            )
        ):
            comparator_text = (
                "below" if strategy_id == PUT_CREDIT_SPREAD.strategy_id else "above"
            )
            issues.append(
                AuditIssue(
                    category="consistency",
                    severity="error",
                    row_number=index,
                    message=(
                        f"long_strike must be {comparator_text} short_strike for {symbol}: "
                        f"{short_strike}/{long_strike}"
                    ),
                )
            )

        if width is not None and short_strike is not None and long_strike is not None:
            expected_width = round(abs(short_strike - long_strike), 4)
            if round(width, 4) != expected_width:
                issues.append(
                    AuditIssue(
                        category="consistency",
                        severity="warning",
                        row_number=index,
                        message=(
                            f"Width mismatch for {symbol}: width={width}, "
                            f"short-long={expected_width}"
                        ),
                    )
                )

        if avg_width_pct is not None and avg_width_pct < 0:
            issues.append(
                AuditIssue(
                    category="ranges",
                    severity="warning",
                    row_number=index,
                    message=(
                        f"avg_width_pct cannot be negative for {symbol}: "
                        f"{avg_width_pct}"
                    ),
                )
            )

        if mid_weight is not None and not 0 <= mid_weight <= 1:
            issues.append(
                AuditIssue(
                    category="ranges",
                    severity="warning",
                    row_number=index,
                    message=(f"mid_weight outside [0, 1] for {symbol}: {mid_weight}"),
                )
            )

        if economics_should_be_valid and fill_quality is not None and fill_quality < 0:
            issues.append(
                AuditIssue(
                    category="ranges",
                    severity="warning",
                    row_number=index,
                    message=(
                        f"fill_quality cannot be negative for {symbol}: {fill_quality}"
                    ),
                )
            )

        if (
            credit_natural is not None
            and credit_expected is not None
            and credit_expected < credit_natural
        ):
            issues.append(
                AuditIssue(
                    category="consistency",
                    severity="warning",
                    row_number=index,
                    message=(
                        f"credit_expected is below credit_natural for {symbol}: "
                        f"expected={credit_expected}, natural={credit_natural}"
                    ),
                )
            )

        if (
            credit_mid is not None
            and credit_expected is not None
            and credit_expected > credit_mid
        ):
            issues.append(
                AuditIssue(
                    category="consistency",
                    severity="warning",
                    row_number=index,
                    message=(
                        f"credit_expected is above credit_mid for {symbol}: "
                        f"expected={credit_expected}, mid={credit_mid}"
                    ),
                )
            )

        if short_delta is not None and not 0 <= short_delta <= 1:
            issues.append(
                AuditIssue(
                    category="ranges",
                    severity="error",
                    row_number=index,
                    message=(f"short_delta outside [0, 1] for {symbol}: {short_delta}"),
                )
            )

        for field_name, value in (
            ("short_iv", short_iv),
            ("atm_iv", atm_iv),
        ):
            if value is not None and not 0 < value <= 5:
                issues.append(
                    AuditIssue(
                        category="ranges",
                        severity="warning",
                        row_number=index,
                        message=(
                            f"{field_name} outside expected range (0, 5] for "
                            f"{symbol}: {value}"
                        ),
                    )
                )

        if skew_ratio is not None and skew_ratio <= 0:
            issues.append(
                AuditIssue(
                    category="ranges",
                    severity="warning",
                    row_number=index,
                    message=f"skew_ratio must be positive for {symbol}: {skew_ratio}",
                )
            )

        if risk_reward_ratio is not None and risk_reward_ratio < 0:
            issues.append(
                AuditIssue(
                    category="ranges",
                    severity="error",
                    row_number=index,
                    message=(
                        f"risk_reward_ratio cannot be negative for {symbol}: "
                        f"{risk_reward_ratio}"
                    ),
                )
            )

        if economics_should_be_valid and ev_score is not None and ev_score < 0:
            issues.append(
                AuditIssue(
                    category="ranges",
                    severity="warning",
                    row_number=index,
                    message=f"ev_score should not be negative for {symbol}: {ev_score}",
                )
            )

        if (
            economics_should_be_valid
            and premium_per_width is not None
            and premium_per_width < 0
        ):
            issues.append(
                AuditIssue(
                    category="ranges",
                    severity="warning",
                    row_number=index,
                    message=(
                        f"premium_per_width is negative for {symbol}: "
                        f"{premium_per_width}"
                    ),
                )
            )

        if (
            economics_should_be_valid
            and premium is not None
            and max_profit is not None
            and round(premium, 4) != round(max_profit, 4)
        ):
            issues.append(
                AuditIssue(
                    category="consistency",
                    severity="warning",
                    row_number=index,
                    message=(
                        f"premium and max_profit differ for {symbol}: "
                        f"premium={premium}, max_profit={max_profit}"
                    ),
                )
            )

        if candidate_status not in ALLOWED_CANDIDATE_STATUS:
            issues.append(
                AuditIssue(
                    category="enums",
                    severity="error",
                    row_number=index,
                    message=(
                        f"candidate_status has invalid value for {symbol}: "
                        f"{row.get('candidate_status', '')}"
                    ),
                )
            )

        selected_raw = (row.get("selected") or "").strip().lower()
        if selected_raw not in ALLOWED_SELECTED_VALUES:
            issues.append(
                AuditIssue(
                    category="enums",
                    severity="error",
                    row_number=index,
                    message=(
                        f"selected has invalid value for {symbol}: "
                        f"{row.get('selected', '')}"
                    ),
                )
            )
        elif selected is not None:
            if selected and candidate_status != "selected":
                issues.append(
                    AuditIssue(
                        category="consistency",
                        severity="error",
                        row_number=index,
                        message=(
                            f"selected=True but candidate_status={candidate_status} "
                            f"for {symbol}"
                        ),
                    )
                )
            if (
                not selected
                and candidate_status in {"selected", "rejected"}
                and candidate_status != "rejected"
            ):
                issues.append(
                    AuditIssue(
                        category="consistency",
                        severity="error",
                        row_number=index,
                        message=(
                            f"selected=False but candidate_status={candidate_status} "
                            f"for {symbol}"
                        ),
                    )
                )

    return issues


def summarize_issues(issues: Iterable[AuditIssue]) -> str:
    """Build a compact human-readable issue summary."""
    issues_list = list(issues)
    if not issues_list:
        return "No issues found."

    by_category: dict[str, int] = defaultdict(int)
    by_severity: dict[str, int] = defaultdict(int)
    for issue in issues_list:
        by_category[issue.category] += 1
        by_severity[issue.severity] += 1

    lines = [
        "Data Quality Audit Summary",
        f"Total issues: {len(issues_list)}",
        (
            "Severity breakdown: "
            + ", ".join(
                f"{severity}={count}" for severity, count in sorted(by_severity.items())
            )
        ),
        (
            "Category breakdown: "
            + ", ".join(
                f"{category}={count}" for category, count in sorted(by_category.items())
            )
        ),
        "",
        "Sample issues:",
    ]

    for issue in issues_list[:20]:
        prefix = f"Row {issue.row_number}: " if issue.row_number else ""
        lines.append(f"- [{issue.severity}] {issue.category}: {prefix}{issue.message}")

    if len(issues_list) > 20:
        lines.append(f"- ... {len(issues_list) - 20} more issues not shown")

    return "\n".join(lines)


def run_candidate_audit() -> list[AuditIssue]:
    """Run the current Phase 1 audit checks on candidate data."""
    if not CANDIDATES_PATH.exists():
        return [
            AuditIssue(
                category="files",
                severity="error",
                message=f"Candidate dataset not found: {CANDIDATES_PATH}",
            )
        ]

    header, rows = load_csv_rows(CANDIDATES_PATH)
    issues: list[AuditIssue] = []
    issues.extend(audit_candidate_schema(header))
    issues.extend(audit_candidate_duplicates(rows))
    issues.extend(audit_candidate_ranges(rows))
    return issues


def main() -> None:
    """Execute the audit and print a review-oriented summary."""
    issues = run_candidate_audit()
    print(summarize_issues(issues))


if __name__ == "__main__":
    main()
