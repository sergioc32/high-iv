"""
CSV logging and schema migration helpers for spread analysis outputs.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from screener.strategy_types import PUT_CREDIT_SPREAD

CANDIDATE_FIELDNAMES = [
    "run_id",
    "snapshot_ts",
    "strategy_version",
    "strategy_id",
    "strategy_family",
    "option_side",
    "directional_bias",
    "short_leg_type",
    "long_leg_type",
    "symbol",
    "expiration_date",
    "dte",
    "stock_price",
    "year_high_price",
    "year_low_price",
    "range_position_52w",
    "distance_to_52w_high_pct",
    "distance_to_52w_low_pct",
    "short_strike",
    "long_strike",
    "width",
    "credit_mid",
    "credit_natural",
    "credit_expected",
    "fill_quality",
    "fill_edge",
    "fill_edge_pct",
    "mid_capture_pct",
    "fill_quality_score",
    "avg_width_pct",
    "mid_weight",
    "premium",
    "premium_per_width",
    "max_profit",
    "max_loss",
    "risk_reward_ratio",
    "ev_score",
    "short_delta",
    "short_iv",
    "atm_iv",
    "skew_ratio",
    "skew_diff",
    "earnings_within_dte",
    "anchor_vs_shift_status",
    "shift_steps_from_anchor",
    "short_strike_shift",
    "long_strike_shift",
    "shift_direction",
    "candidate_status",
    "selected",
    "rejection_reason_primary",
    "rejection_reason_flags",
]

REJECTION_FIELDNAMES = [
    "timestamp",
    "run_id",
    "snapshot_ts",
    "strategy_id",
    "strategy_family",
    "option_side",
    "directional_bias",
    "short_leg_type",
    "long_leg_type",
    "symbol",
    "strategy_version",
    "delta_bounds",
    "delta_bounds_min",
    "delta_bounds_max",
    "delta_bounds_missing",
    "itm_or_atm",
    "long_strike_unavailable",
    "short_leg_missing_quote",
    "long_leg_missing_quote",
    "open_interest",
    "short_bid_ask_width",
    "long_bid_ask_width",
    "credit_natural_too_low",
    "credit_expected_too_low",
    "premium_zero_or_negative",
    "risk_reward",
    "no_long_strike",
    "total_rejections",
]


def infer_strategy_version(
    timestamp_text: str | None,
    *,
    strategy_version: str,
    legacy_strategy_version: str,
    cutoff_date_text: str,
) -> str:
    """Infer strategy label for legacy rows from the configured cutoff date."""
    if not timestamp_text:
        return strategy_version

    cutoff_raw = (cutoff_date_text or "").strip()
    if not cutoff_raw:
        return strategy_version

    try:
        cutoff_date = datetime.fromisoformat(cutoff_raw).date()
    except ValueError:
        return strategy_version

    raw = str(timestamp_text).strip()
    if not raw:
        return strategy_version

    try:
        event_date = datetime.fromisoformat(raw[:10]).date()
    except ValueError:
        return strategy_version

    if event_date < cutoff_date:
        return legacy_strategy_version
    return strategy_version


def _blankify_none(row: dict[str, object]) -> dict[str, object]:
    return {key: ("" if value is None else value) for key, value in row.items()}


class CandidateLogWriter:
    def __init__(
        self,
        path: str | Path,
        *,
        strategy_version: str,
        legacy_strategy_version: str,
        cutoff_date_text: str,
    ) -> None:
        self.path = Path(path)
        self.strategy_version = strategy_version
        self.legacy_strategy_version = legacy_strategy_version
        self.cutoff_date_text = cutoff_date_text
        self.fieldnames = list(CANDIDATE_FIELDNAMES)

    def append_row(self, row: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = self.path.is_file()
        if file_exists:
            self._migrate_if_needed()

        with self.path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(_blankify_none(row))

    def _migrate_if_needed(self) -> None:
        with self.path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            existing_fields = reader.fieldnames or []
            needs_migration = any(
                field not in existing_fields for field in self.fieldnames
            )
            existing_rows = list(reader) if needs_migration else []

        if not needs_migration:
            return

        for row in existing_rows:
            for field in self.fieldnames:
                if field == "strategy_version":
                    row[field] = row.get(field) or infer_strategy_version(
                        row.get("snapshot_ts"),
                        strategy_version=self.strategy_version,
                        legacy_strategy_version=self.legacy_strategy_version,
                        cutoff_date_text=self.cutoff_date_text,
                    )
                else:
                    row[field] = row.get(field, "")

        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fieldnames)
            writer.writeheader()
            writer.writerows(existing_rows)


class RejectionLogWriter:
    def __init__(
        self,
        path: str | Path,
        *,
        strategy_version: str,
        legacy_strategy_version: str,
        cutoff_date_text: str,
    ) -> None:
        self.path = Path(path)
        self.strategy_version = strategy_version
        self.legacy_strategy_version = legacy_strategy_version
        self.cutoff_date_text = cutoff_date_text
        self.fieldnames = list(REJECTION_FIELDNAMES)

    def log(
        self,
        symbol: str,
        rejections: dict[str, int],
        *,
        run_id: str | None = None,
        snapshot_ts: str | None = None,
        strategy_identity: dict[str, str] | None = None,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = self.path.is_file()
        if file_exists:
            self._migrate_if_needed()

        identity = strategy_identity or PUT_CREDIT_SPREAD.log_fields()
        row = {
            "timestamp": datetime.now().isoformat(),
            "run_id": run_id,
            "snapshot_ts": snapshot_ts,
            "strategy_id": identity["strategy_id"],
            "strategy_family": identity["strategy_family"],
            "option_side": identity["option_side"],
            "directional_bias": identity["directional_bias"],
            "short_leg_type": identity["short_leg_type"],
            "long_leg_type": identity["long_leg_type"],
            "symbol": symbol,
            "strategy_version": self.strategy_version,
            "delta_bounds": rejections.get("delta_bounds", 0),
            "delta_bounds_min": rejections.get("delta_bounds_min", 0),
            "delta_bounds_max": rejections.get("delta_bounds_max", 0),
            "delta_bounds_missing": rejections.get("delta_bounds_missing", 0),
            "itm_or_atm": rejections.get("itm_or_atm", 0),
            "long_strike_unavailable": rejections.get("long_strike_unavailable", 0),
            "short_leg_missing_quote": rejections.get("short_leg_missing_quote", 0),
            "long_leg_missing_quote": rejections.get("long_leg_missing_quote", 0),
            "open_interest": rejections.get("open_interest", 0),
            "short_bid_ask_width": rejections.get("short_bid_ask_width", 0),
            "long_bid_ask_width": rejections.get("long_bid_ask_width", 0),
            "credit_natural_too_low": rejections.get("credit_natural_too_low", 0),
            "credit_expected_too_low": rejections.get("credit_expected_too_low", 0),
            "premium_zero_or_negative": rejections.get("premium_zero_or_negative", 0),
            "risk_reward": rejections.get("risk_reward", 0),
            "no_long_strike": rejections.get("no_long_strike", 0),
            "total_rejections": sum(
                int(rejections.get(key, 0) or 0)
                for key in [
                    "delta_bounds",
                    "itm_or_atm",
                    "long_strike_unavailable",
                    "short_leg_missing_quote",
                    "long_leg_missing_quote",
                    "open_interest",
                    "short_bid_ask_width",
                    "long_bid_ask_width",
                    "credit_natural_too_low",
                    "credit_expected_too_low",
                    "premium_zero_or_negative",
                    "risk_reward",
                    "no_long_strike",
                ]
            ),
        }

        with self.path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    def _migrate_if_needed(self) -> None:
        with self.path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            existing_fields = reader.fieldnames or []
            needs_migration = (
                "credit_conservative" in existing_fields
                or "strategy_version" not in existing_fields
                or "run_id" not in existing_fields
                or "snapshot_ts" not in existing_fields
                or "strategy_id" not in existing_fields
                or "strategy_family" not in existing_fields
                or "option_side" not in existing_fields
                or "directional_bias" not in existing_fields
                or "short_leg_type" not in existing_fields
                or "long_leg_type" not in existing_fields
                or "delta_bounds_min" not in existing_fields
                or "delta_bounds_max" not in existing_fields
                or "delta_bounds_missing" not in existing_fields
                or "long_strike_unavailable" not in existing_fields
                or "short_leg_missing_quote" not in existing_fields
                or "long_leg_missing_quote" not in existing_fields
                or "itm_or_atm" not in existing_fields
                or "credit_natural_too_low" not in existing_fields
                or "credit_expected_too_low" not in existing_fields
                or "open_interest" not in existing_fields
            )
            existing_rows = list(reader) if needs_migration else []

        if not needs_migration:
            return

        migrated_rows = [self._normalize_existing_row(row) for row in existing_rows]
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.fieldnames)
            writer.writeheader()
            writer.writerows(migrated_rows)

    def _normalize_existing_row(self, row: dict[str, str]) -> dict[str, object]:
        normalized: dict[str, object] = {}
        for field in self.fieldnames:
            if field == "strategy_version":
                normalized[field] = row.get(field) or infer_strategy_version(
                    row.get("timestamp"),
                    strategy_version=self.strategy_version,
                    legacy_strategy_version=self.legacy_strategy_version,
                    cutoff_date_text=self.cutoff_date_text,
                )
            elif field in {"timestamp", "symbol"} or field == "run_id":
                normalized[field] = row.get(field, "")
            elif field == "snapshot_ts":
                normalized[field] = row.get(field, row.get("timestamp", ""))
            elif field == "strategy_id":
                normalized[field] = row.get(field) or PUT_CREDIT_SPREAD.strategy_id
            elif field == "strategy_family":
                normalized[field] = row.get(field) or PUT_CREDIT_SPREAD.strategy_family
            elif field == "option_side":
                normalized[field] = row.get(field) or PUT_CREDIT_SPREAD.option_side
            elif field == "directional_bias":
                normalized[field] = row.get(field) or PUT_CREDIT_SPREAD.directional_bias
            elif field == "short_leg_type":
                normalized[field] = row.get(field) or PUT_CREDIT_SPREAD.short_leg_type
            elif field == "long_leg_type":
                normalized[field] = row.get(field) or PUT_CREDIT_SPREAD.long_leg_type
            elif field == "total_rejections":
                normalized[field] = sum(
                    int(row.get(key, 0) or 0)
                    for key in [
                        "delta_bounds",
                        "itm_or_atm",
                        "long_strike_unavailable",
                        "short_leg_missing_quote",
                        "long_leg_missing_quote",
                        "open_interest",
                        "short_bid_ask_width",
                        "long_bid_ask_width",
                        "credit_natural_too_low",
                        "credit_expected_too_low",
                        "premium_zero_or_negative",
                        "risk_reward",
                        "no_long_strike",
                    ]
                )
            else:
                normalized[field] = row.get(field, 0)
        return normalized
