"""
Weekly trade snapshot creation and backfill orchestration.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

import config


class SnapshotService:
    def __init__(
        self,
        snapshot_dir: str = "snapshots",
        trades_open_file: str = "trades/trades_open.csv",
        trades_closed_file: str = "trades/trades_closed.csv",
    ) -> None:
        self.snapshot_dir = Path(snapshot_dir)
        self.trades_open_file = Path(trades_open_file)
        self.trades_closed_file = Path(trades_closed_file)

    def get_week_bounds(self, day: date) -> tuple[date, date]:
        """Return Monday-Sunday bounds for the given date."""
        week_start = day - timedelta(days=day.weekday())
        week_end = week_start + timedelta(days=6)
        return week_start, week_end

    def get_latest_completed_week_bounds(
        self,
        today: date | None = None,
    ) -> tuple[date, date]:
        """Return bounds for the latest fully completed Monday-Sunday week."""
        resolved_today = today or date.today()
        current_week_start, current_week_end = self.get_week_bounds(resolved_today)
        if resolved_today >= current_week_end:
            return current_week_start, current_week_end
        return current_week_start - timedelta(days=7), current_week_start - timedelta(
            days=1
        )

    def create_weekly_snapshot(
        self,
        week_start: date,
        week_end: date,
        overwrite: bool = False,
    ) -> bool:
        """Create a weekly snapshot of all trades and config for one Monday-Sunday window."""
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

        snapshot_dt = datetime.now()
        snapshot_file = self.snapshot_dir / self._snapshot_filename(
            week_start, week_end
        )
        if snapshot_file.exists() and not overwrite:
            print(
                f"Snapshot already exists for {week_start} to {week_end}: {snapshot_file}"
            )
            return False

        print()
        print("=" * 80)
        print("CREATING WEEKLY SNAPSHOT")
        print("=" * 80)
        print()

        open_records = self._load_trade_records(
            self.trades_open_file,
            "entry_date",
            week_start,
            week_end,
        )
        closed_records = self._load_trade_records(
            self.trades_closed_file,
            "close_date",
            week_start,
            week_end,
        )

        snapshot_data = {
            "snapshot_date": snapshot_dt.isoformat(),
            "window": {
                "type": "calendar_week",
                "start_date": week_start.isoformat(),
                "end_date": week_end.isoformat(),
            },
            "config": self._snapshot_config(),
            "trades_open": open_records,
            "trades_closed": closed_records,
            "summary": {
                "total_open": len(open_records),
                "total_closed": len(closed_records),
                "total_trades": len(open_records) + len(closed_records),
            },
        }

        with snapshot_file.open("w", encoding="utf-8") as handle:
            json.dump(snapshot_data, handle, indent=2, default=str)

        print(f"Snapshot saved to {snapshot_file}")
        print()
        print("Summary:")
        print(f"  Open trades: {snapshot_data['summary']['total_open']}")
        print(f"  Closed trades: {snapshot_data['summary']['total_closed']}")
        print(f"  Total trades tracked: {snapshot_data['summary']['total_trades']}")
        print()
        return True

    def maybe_backfill_weekly_snapshots(self, today: date | None = None) -> int:
        """Create missing snapshots for completed weeks."""
        latest_week_start, _ = self.get_latest_completed_week_bounds(today=today)
        existing = self._extract_snapshot_windows()

        earliest_trade_date = self._read_earliest_trade_date()
        if earliest_trade_date:
            start_week_start, _ = self.get_week_bounds(earliest_trade_date)
        else:
            start_week_start = latest_week_start

        missing_weeks: list[tuple[date, date]] = []
        current = start_week_start
        while current <= latest_week_start:
            current_end = current + timedelta(days=6)
            if (current, current_end) not in existing:
                missing_weeks.append((current, current_end))
            current += timedelta(days=7)

        if not missing_weeks:
            print("Weekly snapshots are up to date")
            return 0

        print(
            f"Weekly snapshot backfill: {len(missing_weeks)} missing week(s) detected"
        )
        created = 0
        for week_start, week_end in missing_weeks:
            if self.create_weekly_snapshot(week_start, week_end):
                created += 1
        print(f"Weekly snapshot backfill complete: created {created} snapshot(s)")
        return created

    def _snapshot_filename(self, week_start: date, week_end: date) -> str:
        return f"snapshot_{week_start.isoformat()}_{week_end.isoformat()}.json"

    def _extract_snapshot_windows(self) -> set[tuple[date, date]]:
        """Read existing snapshot windows from file names and JSON metadata."""
        windows: set[tuple[date, date]] = set()
        if not self.snapshot_dir.is_dir():
            return windows

        name_pattern = re.compile(
            r"^snapshot_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.json$"
        )

        for path in self.snapshot_dir.iterdir():
            if not path.is_file() or not path.name.startswith("snapshot_"):
                continue
            if path.suffix != ".json":
                continue

            match = name_pattern.match(path.name)
            if match:
                try:
                    start = date.fromisoformat(match.group(1))
                    end = date.fromisoformat(match.group(2))
                except ValueError:
                    pass
                else:
                    windows.add((start, end))
                    continue

            try:
                with path.open(encoding="utf-8") as handle:
                    data = json.load(handle)
                window = data.get("window", {})
                start = date.fromisoformat(str(window.get("start_date")))
                end = date.fromisoformat(str(window.get("end_date")))
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue

            windows.add((start, end))

        return windows

    def _read_earliest_trade_date(self) -> date | None:
        """Find the earliest date present in trade CSV files."""
        candidates: list[date] = []
        for file_path, column in (
            (self.trades_open_file, "entry_date"),
            (self.trades_closed_file, "close_date"),
        ):
            if not file_path.exists():
                continue
            try:
                frame = pd.read_csv(file_path)
            except Exception:
                continue
            if column not in frame.columns:
                continue
            parsed = pd.to_datetime(frame[column], errors="coerce").dt.date.dropna()
            if not parsed.empty:
                candidates.append(parsed.min())

        if not candidates:
            return None
        return min(candidates)

    def _load_trade_records(
        self,
        file_path: Path,
        date_column: str,
        week_start: date,
        week_end: date,
    ) -> list[dict[str, object]]:
        if not file_path.exists():
            print(f"No trades file found at {file_path}")
            return []

        try:
            frame = pd.read_csv(file_path)
        except Exception as exc:
            print(f"Failed to load trades from {file_path}: {exc}")
            return []

        if date_column in frame.columns:
            trade_dates = pd.to_datetime(frame[date_column], errors="coerce").dt.date
            frame = frame[(trade_dates >= week_start) & (trade_dates <= week_end)]

        records = frame.to_dict(orient="records")
        print(f"Captured {len(records)} records from {file_path.name}")
        return records

    def _snapshot_config(self) -> dict[str, object]:
        return {
            "IV_RANK_THRESHOLD": config.IV_RANK_THRESHOLD,
            "TARGET_DTE": config.TARGET_DTE,
            "TARGET_DELTA": config.TARGET_DELTA,
            "LONG_PUT_DELTA": config.LONG_PUT_DELTA,
            "PREFERRED_SPREAD_WIDTH": config.PREFERRED_SPREAD_WIDTH,
            "FALLBACK_SPREAD_WIDTH": config.FALLBACK_SPREAD_WIDTH,
            "MAX_RISK_REWARD_RATIO": config.MAX_RISK_REWARD_RATIO,
            "TARGET_EXIT_DTE": config.TARGET_EXIT_DTE,
            "TARGET_PROFIT_PCT": config.TARGET_PROFIT_PCT,
            "DTE_TOLERANCE": config.DTE_TOLERANCE,
        }
