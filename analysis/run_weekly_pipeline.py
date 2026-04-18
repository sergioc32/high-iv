"""Run the weekly analytics pipeline in one command.

This helper executes, in order:
1. ``analysis/rejection_diagnostics.py``
2. ``analysis/weekly_report.py``

Both steps share the same date window and prefix so weekly exports stay aligned.
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
    """Parse CLI arguments for the weekly pipeline helper."""
    parser = argparse.ArgumentParser(
        description="Run rejection diagnostics and weekly report with shared settings."
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="",
        help="Inclusive start date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="",
        help="Inclusive end date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default="rejection_diagnostics",
        help=(
            "Shared prefix for rejection CSV exports and weekly report ingestion. "
            "Example: weekly_2026_03_31"
        ),
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
        help="Filename prefix for weekly markdown/csv outputs.",
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


def parse_iso_date(value: str, flag_name: str) -> date:
    """Parse an ISO date value and raise a clear CLI error when invalid."""
    try:
        return date.fromisoformat(value.strip())
    except ValueError as error:
        raise ValueError(f"Invalid {flag_name}: expected YYYY-MM-DD") from error


def resolve_window(start_date_arg: str, end_date_arg: str) -> tuple[str, str]:
    """Resolve date window, defaulting to latest completed week when omitted."""
    start_raw = start_date_arg.strip()
    end_raw = end_date_arg.strip()

    if not start_raw and not end_raw:
        start_date, end_date = get_latest_completed_week_bounds()
        return start_date.isoformat(), end_date.isoformat()

    if start_raw and not end_raw:
        start_date = parse_iso_date(start_raw, "--start-date")
        return start_date.isoformat(), start_date.isoformat()

    if end_raw and not start_raw:
        end_date = parse_iso_date(end_raw, "--end-date")
        return end_date.isoformat(), end_date.isoformat()

    start_date = parse_iso_date(start_raw, "--start-date")
    end_date = parse_iso_date(end_raw, "--end-date")
    if start_date > end_date:
        raise ValueError("--start-date cannot be after --end-date")
    return start_date.isoformat(), end_date.isoformat()


def run_command(command: list[str], label: str) -> None:
    """Execute a subprocess command and stream output to the console."""
    print(f"\n==> {label}")
    print(" ".join(command))
    subprocess.run(command, check=True, cwd=PROJECT_ROOT)


def main() -> None:
    """Run rejection diagnostics then weekly report with matching window/prefix."""
    args = parse_args()
    start_date, end_date = resolve_window(args.start_date, args.end_date)

    print(f"Resolved window: {start_date} to {end_date}")

    diagnostics_cmd = [
        sys.executable,
        "analysis/rejection_diagnostics.py",
        "--export-prefix",
        args.prefix,
        "--export-dir",
        str(args.reports_dir),
        "--top-n",
        str(args.top_n),
        "--start-date",
        start_date,
        "--end-date",
        end_date,
    ]

    weekly_report_cmd = [
        sys.executable,
        "analysis/weekly_report.py",
        "--rejection-prefix",
        args.prefix,
        "--reports-dir",
        str(args.reports_dir),
        "--output-prefix",
        args.output_prefix,
        "--top-n",
        str(args.top_n),
        "--start-date",
        start_date,
        "--end-date",
        end_date,
    ]

    run_command(diagnostics_cmd, "Running rejection diagnostics")
    run_command(weekly_report_cmd, "Running weekly analytics report")

    print("\nWeekly pipeline complete.")
    print(
        "Artifacts available in "
        f"{args.reports_dir} with prefix '{args.prefix}' and report prefix "
        f"'{args.output_prefix}'."
    )


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        print(f"✗ {error}")
        sys.exit(2)
