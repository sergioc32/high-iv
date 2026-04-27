"""Run full weekly Phase 1 analysis closeout in one command.

This helper executes:
1. analysis/build_analysis_dataset.py
2. analysis/data_quality_audit.py
3. analysis/run_weekly_pipeline.py for latest completed week
4. Optional catch-up: previous week if weekly report is missing

Default week semantics follow run_weekly_pipeline.py (Monday-Sunday windows).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "analysis" / "reports"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for weekly closeout runner."""
    parser = argparse.ArgumentParser(
        description=(
            "Run full weekly analysis closeout (dataset build, audit, weekly pipeline) "
            "with optional prior-week catch-up."
        )
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Directory for report artifacts.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Top-N rows for diagnostics/report segment tables.",
    )
    parser.add_argument(
        "--output-prefix",
        type=str,
        default="weekly_report",
        help="Prefix used by weekly_report output files.",
    )
    parser.add_argument(
        "--skip-build-dataset",
        action="store_true",
        help="Skip analysis/build_analysis_dataset.py.",
    )
    parser.add_argument(
        "--skip-audit",
        action="store_true",
        help="Skip analysis/data_quality_audit.py.",
    )
    parser.add_argument(
        "--no-catchup",
        action="store_true",
        help="Disable auto-run for previous week when that week's report is missing.",
    )
    return parser.parse_args()


def get_week_bounds(day: date) -> tuple[date, date]:
    """Return Monday-Sunday bounds for a given calendar date."""
    week_start = day - timedelta(days=day.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def get_latest_completed_week_bounds(today: date | None = None) -> tuple[date, date]:
    """Return bounds for the latest fully completed Monday-Sunday week."""
    today = today or date.today()
    current_week_start, current_week_end = get_week_bounds(today)
    if today >= current_week_end:
        return current_week_start, current_week_end
    return current_week_start - timedelta(days=7), current_week_start - timedelta(
        days=1
    )


def run_command(command: list[str], label: str) -> None:
    """Execute a subprocess command and stream output."""
    print(f"\n==> {label}")
    print(" ".join(command))
    subprocess.run(command, check=True, cwd=PROJECT_ROOT)


def report_exists(reports_dir: Path, output_prefix: str, week_end: date) -> bool:
    """Check if weekly report artifacts already exist for a week-end date."""
    suffix = week_end.isoformat()
    markdown_path = reports_dir / f"{output_prefix}_{suffix}.md"
    csv_path = reports_dir / f"{output_prefix}_{suffix}.csv"
    return markdown_path.exists() and csv_path.exists()


def pipeline_command(
    *,
    start_date: date,
    end_date: date,
    reports_dir: Path,
    top_n: int,
    output_prefix: str,
) -> list[str]:
    """Build run_weekly_pipeline.py command for a specific date window."""
    prefix = f"weekly_{end_date.isoformat().replace('-', '_')}"
    return [
        sys.executable,
        "analysis/run_weekly_pipeline.py",
        "--start-date",
        start_date.isoformat(),
        "--end-date",
        end_date.isoformat(),
        "--prefix",
        prefix,
        "--reports-dir",
        str(reports_dir),
        "--top-n",
        str(top_n),
        "--output-prefix",
        output_prefix,
    ]


def main() -> None:
    """Run full weekly closeout and optional prior-week catch-up."""
    args = parse_args()

    latest_start, latest_end = get_latest_completed_week_bounds()
    previous_start = latest_start - timedelta(days=7)
    previous_end = latest_end - timedelta(days=7)

    print(
        f"Latest completed week: {latest_start.isoformat()} to {latest_end.isoformat()}"
    )

    if not args.skip_build_dataset:
        run_command(
            [sys.executable, "analysis/build_analysis_dataset.py"],
            "Building analysis dataset",
        )

    if not args.skip_audit:
        run_command(
            [sys.executable, "analysis/data_quality_audit.py"],
            "Running data quality audit",
        )

    run_command(
        [sys.executable, "analysis/build_rejected_candidate_dataset.py"],
        "Building rejected candidate dataset",
    )
    run_command(
        [sys.executable, "analysis/build_executed_trade_dataset.py"],
        "Building executed trade dataset",
    )

    run_command(
        pipeline_command(
            start_date=latest_start,
            end_date=latest_end,
            reports_dir=args.reports_dir,
            top_n=args.top_n,
            output_prefix=args.output_prefix,
        ),
        f"Running weekly pipeline for latest week ({latest_start.isoformat()} to {latest_end.isoformat()})",
    )

    run_command(
        [
            sys.executable,
            "analysis/rejected_candidate_review.py",
            "--reports-dir",
            str(args.reports_dir),
        ],
        "Running rejected candidate review",
    )
    run_command(
        [
            sys.executable,
            "analysis/trade_outcome_review.py",
            "--reports-dir",
            str(args.reports_dir),
        ],
        "Running trade outcome review",
    )

    if not args.no_catchup:
        if report_exists(args.reports_dir, args.output_prefix, previous_end):
            print(
                "\nCatch-up check: previous week report already exists "
                f"for week ending {previous_end.isoformat()}. Skipping catch-up."
            )
        else:
            run_command(
                pipeline_command(
                    start_date=previous_start,
                    end_date=previous_end,
                    reports_dir=args.reports_dir,
                    top_n=args.top_n,
                    output_prefix=args.output_prefix,
                ),
                (
                    "Running catch-up weekly pipeline for previous week "
                    f"({previous_start.isoformat()} to {previous_end.isoformat()})"
                ),
            )

    print("\nWeekly closeout complete.")


if __name__ == "__main__":
    main()
