"""Audit the leakage-safe training dataset for readiness and trustworthiness."""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRAINING_DATASET = PROJECT_ROOT / "ml" / "training_dataset.csv"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "ml" / "reports"
DEFAULT_MD_REPORT = "training_data_audit.md"
DEFAULT_CSV_REPORT = "training_data_audit.csv"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml.build_training_dataset import (  # noqa: E402
    DERIVED_FEATURE_COLUMNS,
    FEATURE_COLUMNS,
    LEAKAGE_EXCLUDED_FEATURE_COLUMNS,
    OUTPUT_COLUMNS,
)


@dataclass(frozen=True)
class AuditIssue:
    """Represent one audit issue in the training dataset."""

    category: str
    severity: str
    message: str
    row_number: int | None = None
    trade_id: str = ""


def load_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Load a CSV file and return its header and rows."""
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    """Write a CSV artifact, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_text(path: Path, content: str) -> None:
    """Write a text artifact, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_float(value: object) -> float | None:
    """Parse float-like values, returning None for blanks/invalid text."""
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_date(value: object) -> date | None:
    """Parse an ISO-like date string into a date object."""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def as_bool(value: object) -> bool:
    """Parse common CSV boolean-like text values."""
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def audit_schema(header: list[str]) -> list[AuditIssue]:
    """Check schema completeness and ordering against the frozen training contract."""
    issues: list[AuditIssue] = []
    missing = [column for column in OUTPUT_COLUMNS if column not in header]
    extra = [column for column in header if column not in OUTPUT_COLUMNS]

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

    if header[: len(OUTPUT_COLUMNS)] != OUTPUT_COLUMNS:
        issues.append(
            AuditIssue(
                category="schema",
                severity="warning",
                message="Training dataset column order differs from canonical contract.",
            )
        )

    leaked_columns = sorted(
        set(FEATURE_COLUMNS + DERIVED_FEATURE_COLUMNS)
        & LEAKAGE_EXCLUDED_FEATURE_COLUMNS
    )
    if leaked_columns:
        issues.append(
            AuditIssue(
                category="leakage",
                severity="error",
                message=f"Leakage-prone columns present in feature schema: {', '.join(leaked_columns)}",
            )
        )

    return issues


def audit_duplicates(rows: list[dict[str, str]]) -> list[AuditIssue]:
    """Detect duplicate trade rows in the training dataset."""
    issues: list[AuditIssue] = []
    seen: Counter[str] = Counter()
    for row in rows:
        trade_id = (row.get("trade_id") or "").strip()
        seen[trade_id] += 1

    for trade_id, count in seen.items():
        if trade_id and count > 1:
            issues.append(
                AuditIssue(
                    category="duplicates",
                    severity="error",
                    message=f"Duplicate trade_id detected: {trade_id} ({count} rows)",
                    trade_id=trade_id,
                )
            )
    return issues


def audit_row_integrity(rows: list[dict[str, str]]) -> list[AuditIssue]:
    """Validate row-level date, label, and sample-weight integrity."""
    issues: list[AuditIssue] = []
    for index, row in enumerate(rows, start=2):
        trade_id = (row.get("trade_id") or "").strip()
        entry_date = parse_date(row.get("entry_date"))
        close_date = parse_date(row.get("close_date"))
        sample_weight = parse_float(row.get("sample_weight"))
        label_quality_weight = parse_float(row.get("label_quality_weight"))
        win_flag = (row.get("win_flag") or "").strip()
        profit_loss = parse_float(row.get("profit_loss"))
        feature_provenance = (row.get("feature_provenance") or "").strip()
        time_split_group = (row.get("time_split_group") or "").strip().lower()
        split_flags = [
            (row.get("is_train") or "").strip(),
            (row.get("is_validation") or "").strip(),
            (row.get("is_test") or "").strip(),
        ]

        if not trade_id:
            issues.append(
                AuditIssue(
                    category="required_fields",
                    severity="error",
                    row_number=index,
                    message="Missing trade_id.",
                )
            )

        if entry_date is None or close_date is None:
            issues.append(
                AuditIssue(
                    category="dates",
                    severity="error",
                    row_number=index,
                    trade_id=trade_id,
                    message="Missing or invalid entry_date/close_date.",
                )
            )
        elif close_date < entry_date:
            issues.append(
                AuditIssue(
                    category="dates",
                    severity="error",
                    row_number=index,
                    trade_id=trade_id,
                    message=(
                        f"close_date {close_date.isoformat()} is before entry_date "
                        f"{entry_date.isoformat()}."
                    ),
                )
            )

        if profit_loss is None:
            issues.append(
                AuditIssue(
                    category="labels",
                    severity="error",
                    row_number=index,
                    trade_id=trade_id,
                    message="Missing profit_loss on a training row.",
                )
            )
        elif win_flag not in {"0", "1"}:
            issues.append(
                AuditIssue(
                    category="labels",
                    severity="error",
                    row_number=index,
                    trade_id=trade_id,
                    message=f"Invalid win_flag value: {win_flag}",
                )
            )

        if sample_weight is None or sample_weight <= 0:
            issues.append(
                AuditIssue(
                    category="sample_weight",
                    severity="error",
                    row_number=index,
                    trade_id=trade_id,
                    message=f"Invalid sample_weight value: {row.get('sample_weight', '')}",
                )
            )
        elif sample_weight > 1.0:
            issues.append(
                AuditIssue(
                    category="sample_weight",
                    severity="warning",
                    row_number=index,
                    trade_id=trade_id,
                    message=f"sample_weight exceeds 1.0: {sample_weight}",
                )
            )

        if label_quality_weight is None or label_quality_weight <= 0:
            issues.append(
                AuditIssue(
                    category="sample_weight",
                    severity="warning",
                    row_number=index,
                    trade_id=trade_id,
                    message=(
                        "label_quality_weight missing or non-positive; "
                        "row may be too weak for supervised use."
                    ),
                )
            )

        if feature_provenance == "none" and as_bool(row.get("reviewed_setup_found")):
            issues.append(
                AuditIssue(
                    category="consistency",
                    severity="warning",
                    row_number=index,
                    trade_id=trade_id,
                    message=("feature_provenance=none but reviewed_setup_found=True."),
                )
            )

        if time_split_group and time_split_group not in {"train", "validation", "test"}:
            issues.append(
                AuditIssue(
                    category="time_split",
                    severity="error",
                    row_number=index,
                    trade_id=trade_id,
                    message=f"Invalid time_split_group value: {time_split_group}",
                )
            )

        active_split_flags = sum(flag == "1" for flag in split_flags)
        if active_split_flags not in {0, 1}:
            issues.append(
                AuditIssue(
                    category="time_split",
                    severity="error",
                    row_number=index,
                    trade_id=trade_id,
                    message="Multiple active time-split indicators on one row.",
                )
            )
        elif active_split_flags == 1:
            expected_group = (
                "train"
                if split_flags[0] == "1"
                else "validation"
                if split_flags[1] == "1"
                else "test"
            )
            if time_split_group != expected_group:
                issues.append(
                    AuditIssue(
                        category="time_split",
                        severity="error",
                        row_number=index,
                        trade_id=trade_id,
                        message=(
                            "time_split_group does not match the active split flag."
                        ),
                    )
                )

    return issues


def build_missingness_summary(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Summarize feature missingness for the leakage-safe feature set."""
    total_rows = len(rows)
    summary: list[dict[str, str]] = []
    for column in FEATURE_COLUMNS + DERIVED_FEATURE_COLUMNS:
        missing_count = sum(1 for row in rows if not str(row.get(column, "")).strip())
        missing_pct = (missing_count / total_rows * 100) if total_rows else 0.0
        summary.append(
            {
                "column": column,
                "missing_count": str(missing_count),
                "missing_pct": f"{missing_pct:.1f}",
                "status": (
                    "error"
                    if missing_pct >= 75
                    else "warning"
                    if missing_pct >= 25
                    else "ok"
                ),
            }
        )
    summary.sort(key=lambda item: (-float(item["missing_pct"]), item["column"]))
    return summary


def missingness_to_issues(missingness: list[dict[str, str]]) -> list[AuditIssue]:
    """Convert high-missingness findings into audit issues."""
    issues: list[AuditIssue] = []
    for item in missingness:
        status = item["status"]
        if status not in {"warning", "error"}:
            continue
        issues.append(
            AuditIssue(
                category="missingness",
                severity=status,
                message=(
                    f"{item['column']} missingness is {item['missing_pct']}% "
                    f"(missing_count={item['missing_count']})"
                ),
            )
        )
    return issues


def summarize_counts(rows: list[dict[str, str]], column: str) -> Counter[str]:
    """Count values in a column, coercing blanks to a visible bucket."""
    counter: Counter[str] = Counter()
    for row in rows:
        key = (row.get(column) or "").strip() or "(blank)"
        counter[key] += 1
    return counter


def time_split_integrity(rows: list[dict[str, str]]) -> tuple[bool, str]:
    """Check whether chronological train/validation/test splits exist and are ordered."""
    groups = {"train": [], "validation": [], "test": []}
    split_policy_values = {
        (row.get("time_split_policy") or "").strip()
        for row in rows
        if (row.get("time_split_policy") or "").strip()
    }

    for row in rows:
        group = (row.get("time_split_group") or "").strip().lower()
        if group not in groups:
            continue
        entry_date = parse_date(row.get("entry_date"))
        if entry_date is not None:
            groups[group].append(entry_date)

    if len(split_policy_values) != 1:
        return False, "Expected exactly one non-blank time_split_policy value."

    if any(len(groups[group]) == 0 for group in groups):
        return False, "Train, validation, and test groups must all be populated."

    train_max = max(groups["train"])
    validation_min = min(groups["validation"])
    validation_max = max(groups["validation"])
    test_min = min(groups["test"])
    if not (train_max <= validation_min <= validation_max <= test_min):
        return False, "Time split groups are not chronologically ordered by entry_date."

    return True, next(iter(split_policy_values))


def build_readiness_gates(
    rows: list[dict[str, str]], issues: list[AuditIssue]
) -> tuple[list[dict[str, str]], str]:
    """Evaluate model-readiness gates and return gate rows plus an overall verdict."""
    matched_rows = [
        row
        for row in rows
        if (row.get("match_status") or "").strip().lower()
        in {"exact_match", "adjusted_match"}
    ]
    matched_count = len(matched_rows)
    losing_matched = sum(
        1 for row in matched_rows if (parse_float(row.get("profit_loss")) or 0.0) < 0
    )
    matched_symbols = {
        (row.get("symbol") or "").strip()
        for row in matched_rows
        if (row.get("symbol") or "").strip()
    }
    actual_exit_count = sum(1 for row in rows if as_bool(row.get("actual_exit_found")))
    actual_exit_rate = (actual_exit_count / len(rows) * 100) if rows else 0.0
    low_confidence_rows = [
        row
        for row in rows
        if (row.get("feature_provenance") or "").strip().lower() == "none"
    ]
    low_confidence_max_weight = max(
        (parse_float(row.get("sample_weight")) or 0.0 for row in low_confidence_rows),
        default=0.0,
    )
    split_ok, split_detail = time_split_integrity(rows)

    critical_issue_count = sum(
        1
        for issue in issues
        if issue.category != "missingness" and issue.severity == "error"
    )

    gates: list[dict[str, str]] = []

    def add_gate(name: str, passed: bool, value: str, target: str, detail: str) -> None:
        gates.append(
            {
                "gate": name,
                "status": "pass" if passed else "fail",
                "value": value,
                "target": target,
                "detail": detail,
            }
        )

    add_gate(
        "matched_closed_trades_minimum",
        matched_count >= 50,
        str(matched_count),
        ">= 50",
        "Exact and adjusted matched rows only.",
    )
    add_gate(
        "matched_closed_trades_preferred",
        matched_count >= 75,
        str(matched_count),
        ">= 75",
        "Preferred scale before serious supervised modeling.",
    )
    add_gate(
        "losing_matched_trades",
        losing_matched >= 20,
        str(losing_matched),
        ">= 20",
        "Loss coverage matters for balanced learning.",
    )
    add_gate(
        "unique_symbols_in_matched_history",
        len(matched_symbols) >= 20,
        str(len(matched_symbols)),
        ">= 20",
        "Unique symbols among exact and adjusted matches.",
    )
    add_gate(
        "actual_exit_rate",
        actual_exit_rate >= 80.0,
        f"{actual_exit_rate:.1f}%",
        ">= 80.0%",
        f"{actual_exit_count} of {len(rows)} training rows have actual exits.",
    )
    add_gate(
        "low_confidence_rows_downweighted",
        low_confidence_max_weight <= 0.20,
        f"max_weight={low_confidence_max_weight:.2f}",
        "<= 0.20",
        f"{len(low_confidence_rows)} rows have feature_provenance=none.",
    )
    add_gate(
        "no_critical_integrity_or_leakage_errors",
        critical_issue_count == 0,
        str(critical_issue_count),
        "0",
        "Excludes missingness-only findings from the critical-error count.",
    )
    add_gate(
        "time_aware_validation_split",
        split_ok,
        split_detail if split_ok else "invalid_or_missing",
        "implemented",
        (
            f"Chronological split check result: {split_detail}."
            if not split_ok
            else f"Chronological split policy verified: {split_detail}."
        ),
    )

    mandatory_gate_names = {
        "matched_closed_trades_minimum",
        "losing_matched_trades",
        "unique_symbols_in_matched_history",
        "actual_exit_rate",
        "low_confidence_rows_downweighted",
        "no_critical_integrity_or_leakage_errors",
        "time_aware_validation_split",
    }
    mandatory_pass = all(
        gate["status"] == "pass"
        for gate in gates
        if gate["gate"] in mandatory_gate_names
    )
    foundation_pass = all(
        gate["status"] == "pass"
        for gate in gates
        if gate["gate"]
        in {
            "actual_exit_rate",
            "low_confidence_rows_downweighted",
            "no_critical_integrity_or_leakage_errors",
        }
    )

    if mandatory_pass:
        verdict = "ready_for_baseline_weighted_experiments"
    elif foundation_pass:
        verdict = "data_foundation_ok_but_sample_limited"
    else:
        verdict = "not_ready_for_supervised_modeling"

    return gates, verdict


def summarize_issues(issues: list[AuditIssue]) -> dict[str, Counter[str] | int]:
    """Aggregate issue counts by category and severity."""
    by_category: Counter[str] = Counter()
    by_severity: Counter[str] = Counter()
    for issue in issues:
        by_category[issue.category] += 1
        by_severity[issue.severity] += 1
    return {
        "total": len(issues),
        "by_category": by_category,
        "by_severity": by_severity,
    }


def render_markdown_report(
    *,
    dataset_path: Path,
    rows: list[dict[str, str]],
    issues: list[AuditIssue],
    missingness: list[dict[str, str]],
) -> str:
    """Render a human-readable markdown audit report."""
    issue_summary = summarize_issues(issues)
    readiness_gates, readiness_verdict = build_readiness_gates(rows, issues)
    provenance_counts = summarize_counts(rows, "feature_provenance")
    match_counts = summarize_counts(rows, "match_status")
    exit_source_counts = summarize_counts(rows, "exit_price_source")
    split_counts = summarize_counts(rows, "time_split_group")
    actual_exit_count = sum(1 for row in rows if as_bool(row.get("actual_exit_found")))
    estimated_exit_count = len(rows) - actual_exit_count
    win_count = sum(1 for row in rows if (row.get("win_flag") or "").strip() == "1")
    loss_count = sum(1 for row in rows if (row.get("win_flag") or "").strip() == "0")
    entry_dates = [parse_date(row.get("entry_date")) for row in rows]
    close_dates = [parse_date(row.get("close_date")) for row in rows]
    entry_dates = [item for item in entry_dates if item is not None]
    close_dates = [item for item in close_dates if item is not None]

    lines = [
        "# Training Data Audit",
        "",
        f"- Dataset: `{dataset_path}`",
        f"- Total rows: `{len(rows)}`",
        f"- Total issues: `{issue_summary['total']}`",
        f"- Severity breakdown: `{dict(issue_summary['by_severity'])}`",
        f"- Category breakdown: `{dict(issue_summary['by_category'])}`",
        f"- Readiness verdict: `{readiness_verdict}`",
        "",
        "## Dataset shape",
        "",
        f"- Entry date range: `{min(entry_dates).isoformat() if entry_dates else ''}` to `{max(entry_dates).isoformat() if entry_dates else ''}`",
        f"- Close date range: `{min(close_dates).isoformat() if close_dates else ''}` to `{max(close_dates).isoformat() if close_dates else ''}`",
        f"- Wins: `{win_count}`",
        f"- Losses: `{loss_count}`",
        f"- Actual exits: `{actual_exit_count}`",
        f"- Estimated exits: `{estimated_exit_count}`",
        "",
        "## Match status mix",
        "",
    ]

    for key, count in match_counts.most_common():
        lines.append(f"- `{key}`: `{count}`")

    lines.extend(
        [
            "",
            "## Feature provenance mix",
            "",
        ]
    )
    for key, count in provenance_counts.most_common():
        lines.append(f"- `{key}`: `{count}`")

    lines.extend(
        [
            "",
            "## Exit price source mix",
            "",
        ]
    )
    for key, count in exit_source_counts.most_common():
        lines.append(f"- `{key}`: `{count}`")

    lines.extend(
        [
            "",
            "## Time split mix",
            "",
        ]
    )
    for key, count in split_counts.most_common():
        lines.append(f"- `{key}`: `{count}`")

    lines.extend(
        [
            "",
            "## Readiness gates",
            "",
        ]
    )
    for gate in readiness_gates:
        lines.append(
            f"- `{gate['gate']}`: `{gate['status']}` "
            f"(value=`{gate['value']}`, target=`{gate['target']}`) "
            f"- {gate['detail']}"
        )

    lines.extend(
        [
            "",
            "## Highest-missing features",
            "",
        ]
    )
    for item in missingness[:15]:
        lines.append(
            f"- `{item['column']}`: `{item['missing_count']}` missing "
            f"(`{item['missing_pct']}%`, status=`{item['status']}`)"
        )

    lines.extend(
        [
            "",
            "## Sample issues",
            "",
        ]
    )
    if not issues:
        lines.append("- No issues found.")
    else:
        for issue in issues[:20]:
            prefix = (
                f"row {issue.row_number}" if issue.row_number is not None else "dataset"
            )
            trade = f", trade_id={issue.trade_id}" if issue.trade_id else ""
            lines.append(
                f"- `{issue.severity}` `{issue.category}` `{prefix}{trade}`: {issue.message}"
            )
        if len(issues) > 20:
            lines.append(f"- ... `{len(issues) - 20}` more issues not shown")

    return "\n".join(lines) + "\n"


def build_csv_summary(
    *,
    rows: list[dict[str, str]],
    issues: list[AuditIssue],
    missingness: list[dict[str, str]],
) -> list[list[str]]:
    """Build a machine-readable CSV summary artifact."""
    summary_rows: list[list[str]] = []

    issue_summary = summarize_issues(issues)
    readiness_gates, readiness_verdict = build_readiness_gates(rows, issues)
    summary_rows.append(["summary", "total_rows", str(len(rows)), "info", ""])
    summary_rows.append(
        ["summary", "total_issues", str(issue_summary["total"]), "info", ""]
    )
    summary_rows.append(["summary", "readiness_verdict", readiness_verdict, "info", ""])

    for severity, count in Counter(issue.severity for issue in issues).most_common():
        summary_rows.append(["issue_severity", severity, str(count), "info", ""])

    for category, count in Counter(issue.category for issue in issues).most_common():
        summary_rows.append(["issue_category", category, str(count), "info", ""])

    for key, count in summarize_counts(rows, "match_status").most_common():
        summary_rows.append(["match_status", key, str(count), "info", ""])

    for key, count in summarize_counts(rows, "feature_provenance").most_common():
        summary_rows.append(["feature_provenance", key, str(count), "info", ""])

    for key, count in summarize_counts(rows, "exit_price_source").most_common():
        summary_rows.append(["exit_price_source", key, str(count), "info", ""])

    for key, count in summarize_counts(rows, "time_split_group").most_common():
        summary_rows.append(["time_split_group", key, str(count), "info", ""])

    for gate in readiness_gates:
        summary_rows.append(
            [
                "readiness_gate",
                gate["gate"],
                gate["value"],
                gate["status"],
                f"target={gate['target']}; {gate['detail']}",
            ]
        )

    for item in missingness:
        summary_rows.append(
            [
                "missingness",
                item["column"],
                item["missing_pct"],
                item["status"],
                f"missing_count={item['missing_count']}",
            ]
        )

    for issue in issues:
        summary_rows.append(
            [
                "issue",
                issue.category,
                issue.trade_id or "",
                issue.severity,
                issue.message,
            ]
        )

    return summary_rows


def run_training_data_audit(
    dataset_path: Path,
) -> tuple[list[dict[str, str]], list[AuditIssue], list[dict[str, str]]]:
    """Run all current training-data audit checks."""
    if not dataset_path.exists():
        issues = [
            AuditIssue(
                category="files",
                severity="error",
                message=f"Training dataset not found: {dataset_path}",
            )
        ]
        return [], issues, []

    header, rows = load_csv_rows(dataset_path)
    issues: list[AuditIssue] = []
    issues.extend(audit_schema(header))
    issues.extend(audit_duplicates(rows))
    issues.extend(audit_row_integrity(rows))
    missingness = build_missingness_summary(rows)
    issues.extend(missingness_to_issues(missingness))
    return rows, issues, missingness


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
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
        help="Directory for markdown and CSV audit artifacts",
    )
    return parser.parse_args()


def main() -> None:
    """Run the training-data audit and write markdown/CSV artifacts."""
    args = parse_args()
    rows, issues, missingness = run_training_data_audit(args.dataset_path)

    markdown = render_markdown_report(
        dataset_path=args.dataset_path,
        rows=rows,
        issues=issues,
        missingness=missingness,
    )
    csv_rows = build_csv_summary(rows=rows, issues=issues, missingness=missingness)

    markdown_path = args.reports_dir / DEFAULT_MD_REPORT
    csv_path = args.reports_dir / DEFAULT_CSV_REPORT
    write_text(markdown_path, markdown)
    write_csv(csv_path, ["section", "metric", "value", "status", "detail"], csv_rows)

    print(f"Training data audit markdown report written to: {markdown_path}")
    print(f"Training data audit CSV artifact written to: {csv_path}")
    print(f"Training rows analyzed: {len(rows)}")
    print(f"Total issues found: {len(issues)}")


if __name__ == "__main__":
    main()
