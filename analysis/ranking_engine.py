"""Explainable ranking engine for selected spread candidates.

This module ranks selected opportunities from the candidate log (or a live batch)
using only entry-time fields. It produces deterministic component scores and a
strategy_alignment_score that can be used for display, reporting, and backtesting.

Component design (Phase 1 v2 — asymmetric delta + skew integration, soft mode):
- delta:     Asymmetric piecewise preference curve. Sub-target delta earns a bonus;
             above-target is penalized with increasing steepness above RANK_DELTA_PENALTY_STEEP.
             No hard ceiling enforced in RANKING_MODE="soft".
- skew:      Weighted blend of skew_ratio and skew_diff percentile ranks using
             RANK_SKEW_RATIO_WEIGHT / RANK_SKEW_DIFF_WEIGHT.
- ev:        Percentile rank of recomputed ev_score among historical selected candidates.
- liquidity: Proxy based on sibling candidate liquidity failures within the same run group.

Directional adjustment:
- OTM candidates (delta < RANK_DELTA_TARGET):            score * RANK_OTM_BONUS_MULTIPLIER
- ITM-drift candidates (delta > RANK_DELTA_PENALTY_STEEP): score * RANK_ITM_PENALTY_MULTIPLIER

Output:
- CSV written to analysis/reports/opportunity_rankings_<run_id>.csv by default.
- Terminal summary of top-ranked opportunities including alignment zone and flags.
- score_opportunities() can be called with a live batch list for inline screener scoring.
"""

from __future__ import annotations

import argparse
import csv
import sys
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import config  # noqa: E402 (config is expected to be in the project root)
from screener.strategy_types import CALL_CREDIT_SPREAD, PUT_CREDIT_SPREAD

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CANDIDATES_PATH = PROJECT_ROOT / "opportunities" / "opportunity_candidates.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "analysis" / "reports"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


LIQUIDITY_REASONS = {
    "short_bid_ask_width",
    "long_bid_ask_width",
    "open_interest",
    "short_leg_missing_quote",
    "long_leg_missing_quote",
}

# Weights sourced from config at module load — retune via RANK_WEIGHT_* without code changes.
COMPONENT_WEIGHTS: dict[str, float] = {
    "delta": config.RANK_WEIGHT_DELTA,
    "skew": config.RANK_WEIGHT_SKEW,
    "ev": config.RANK_WEIGHT_EV,
    "liquidity": config.RANK_WEIGHT_LIQUIDITY,
}


@dataclass(frozen=True)
class CalibrationSet:
    """Historical selected-candidate feature distributions for percentile scoring."""

    premium_per_width: list[float]
    skew_ratio: list[float]
    skew_diff: list[float]
    risk_reward_ratio: list[float]
    ev_scores: list[float]


@dataclass(frozen=True)
class StrategyRankingProfile:
    """Strategy-aware ranking configuration."""

    strategy_id: str
    delta_target: float
    delta_bonus_floor: float
    delta_penalty_start: float
    delta_penalty_steep: float
    delta_hard_ceiling: float
    delta_bonus_max: float
    delta_penalty_max: float
    skew_ratio_weight: float
    skew_diff_weight: float
    otm_bonus_multiplier: float
    itm_penalty_multiplier: float
    extension_preference: str
    component_weights: dict[str, float]


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    """Load a CSV file into a list of row dictionaries."""
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def parse_float(value) -> float | None:
    """Parse a float value, returning None for blanks and invalid text.

    Accepts both string fields (from CSV rows) and already-numeric values
    (from live opportunity dicts), so scoring functions work in both contexts.
    """
    if isinstance(value, (int, float)):
        return float(value)
    raw = (value or "").strip()
    if raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_iso_date(value: object) -> date | None:
    """Parse an ISO-like date/datetime string into a date object."""
    raw = str(value or "").strip()
    if raw == "":
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def normalize_strategy_id(strategy_id: object) -> str:
    """Default blank legacy rows to the original put credit spread strategy."""
    return str(strategy_id or "").strip() or PUT_CREDIT_SPREAD.strategy_id


def strategy_profile(strategy_id: object) -> StrategyRankingProfile:
    """Return the ranking profile for a spread strategy."""
    normalized_strategy_id = normalize_strategy_id(strategy_id)
    if normalized_strategy_id == CALL_CREDIT_SPREAD.strategy_id:
        return StrategyRankingProfile(
            strategy_id=normalized_strategy_id,
            delta_target=config.CALL_RANK_DELTA_TARGET,
            delta_bonus_floor=config.CALL_RANK_DELTA_BONUS_FLOOR,
            delta_penalty_start=config.CALL_RANK_DELTA_PENALTY_START,
            delta_penalty_steep=config.CALL_RANK_DELTA_PENALTY_STEEP,
            delta_hard_ceiling=config.CALL_RANK_DELTA_HARD_CEILING,
            delta_bonus_max=config.CALL_RANK_DELTA_BONUS_MAX,
            delta_penalty_max=config.CALL_RANK_DELTA_PENALTY_MAX,
            skew_ratio_weight=config.CALL_RANK_SKEW_RATIO_WEIGHT,
            skew_diff_weight=config.CALL_RANK_SKEW_DIFF_WEIGHT,
            otm_bonus_multiplier=config.CALL_RANK_OTM_BONUS_MULTIPLIER,
            itm_penalty_multiplier=config.CALL_RANK_ITM_PENALTY_MULTIPLIER,
            extension_preference="near_52w_high",
            component_weights={
                "delta": config.CALL_RANK_WEIGHT_DELTA,
                "skew": config.CALL_RANK_WEIGHT_SKEW,
                "ev": config.CALL_RANK_WEIGHT_EV,
                "liquidity": config.CALL_RANK_WEIGHT_LIQUIDITY,
                "extension": config.CALL_RANK_WEIGHT_EXTENSION,
            },
        )

    return StrategyRankingProfile(
        strategy_id=PUT_CREDIT_SPREAD.strategy_id,
        delta_target=config.PUT_RANK_DELTA_TARGET,
        delta_bonus_floor=config.PUT_RANK_DELTA_BONUS_FLOOR,
        delta_penalty_start=config.PUT_RANK_DELTA_PENALTY_START,
        delta_penalty_steep=config.PUT_RANK_DELTA_PENALTY_STEEP,
        delta_hard_ceiling=config.PUT_RANK_DELTA_HARD_CEILING,
        delta_bonus_max=config.PUT_RANK_DELTA_BONUS_MAX,
        delta_penalty_max=config.PUT_RANK_DELTA_PENALTY_MAX,
        skew_ratio_weight=config.PUT_RANK_SKEW_RATIO_WEIGHT,
        skew_diff_weight=config.PUT_RANK_SKEW_DIFF_WEIGHT,
        otm_bonus_multiplier=config.PUT_RANK_OTM_BONUS_MULTIPLIER,
        itm_penalty_multiplier=config.PUT_RANK_ITM_PENALTY_MULTIPLIER,
        extension_preference="near_52w_low",
        component_weights={
            "delta": config.PUT_RANK_WEIGHT_DELTA,
            "skew": config.PUT_RANK_WEIGHT_SKEW,
            "ev": config.PUT_RANK_WEIGHT_EV,
            "liquidity": config.PUT_RANK_WEIGHT_LIQUIDITY,
            "extension": config.PUT_RANK_WEIGHT_EXTENSION,
        },
    )


def merge_alignment_flags(base_flags: str, extra_flag: str) -> str:
    """Merge a single extra flag into the existing comma-separated flag string."""
    if not extra_flag:
        return base_flags or "ok"
    if not base_flags or base_flags == "ok":
        return extra_flag
    return f"{base_flags},{extra_flag}"


def earnings_adjustment(row: dict) -> tuple[float, str]:
    """Return earnings-aware score multiplier and optional impact flag.

    Logic:
    - No earnings in DTE window: no adjustment.
    - Earnings very near term: strong penalty.
    - Earnings before planned exit horizon: moderate penalty.
    - Earnings after planned exit but before expiration: minor penalty.
    """
    earnings_date = parse_iso_date(row.get("earnings_within_dte", ""))
    if earnings_date is None:
        return 1.0, ""

    ref_date = parse_iso_date(row.get("snapshot_ts", "")) or date.today()
    dte = parse_float(row.get("dte", ""))
    if dte is None:
        return config.RANK_EARNINGS_PRE_EXIT_MULTIPLIER, "earnings_pre_exit"

    days_to_earnings = (earnings_date - ref_date).days
    if days_to_earnings <= config.RANK_EARNINGS_NEAR_TERM_DAYS:
        return config.RANK_EARNINGS_NEAR_TERM_MULTIPLIER, "earnings_near_term"

    planned_holding_days = max(0, int(round(dte - config.TARGET_EXIT_DTE)))
    if days_to_earnings <= planned_holding_days:
        return config.RANK_EARNINGS_PRE_EXIT_MULTIPLIER, "earnings_pre_exit"

    return config.RANK_EARNINGS_POST_EXIT_MULTIPLIER, "earnings_post_exit"


def is_selected_row(row: dict[str, str]) -> bool:
    """Return True when a candidate row represents a selected spread."""
    return (row.get("selected") or "").strip().lower() == "true"


def latest_run_id(rows: Iterable[dict[str, str]]) -> str:
    """Return the latest run_id in the candidate log."""
    run_ids = sorted(
        {(row.get("run_id") or "").strip() for row in rows if row.get("run_id")}
    )
    if not run_ids:
        raise ValueError("No run_id values found in candidate log.")
    return run_ids[-1]


def build_calibration_set(rows: Iterable[dict[str, str]]) -> CalibrationSet:
    """Build sorted historical feature lists from selected candidate rows."""
    premium_per_width: list[float] = []
    skew_ratio: list[float] = []
    skew_diff: list[float] = []
    risk_reward_ratio: list[float] = []
    ev_scores: list[float] = []

    for row in rows:
        if not is_selected_row(row):
            continue

        premium = parse_float(row.get("premium_per_width", ""))
        ratio = parse_float(row.get("skew_ratio", ""))
        diff = parse_float(row.get("skew_diff", ""))
        risk_reward = parse_float(row.get("risk_reward_ratio", ""))
        ev = recompute_ev_score(row)

        if premium is not None:
            premium_per_width.append(premium)
        if ratio is not None:
            skew_ratio.append(ratio)
        if diff is not None:
            skew_diff.append(diff)
        if risk_reward is not None:
            risk_reward_ratio.append(risk_reward)
        if ev is not None:
            ev_scores.append(ev)

    return CalibrationSet(
        premium_per_width=sorted(premium_per_width),
        skew_ratio=sorted(skew_ratio),
        skew_diff=sorted(skew_diff),
        risk_reward_ratio=sorted(risk_reward_ratio),
        ev_scores=sorted(ev_scores),
    )


def build_calibration_sets(
    rows: Iterable[dict[str, str]],
) -> dict[str, CalibrationSet]:
    """Build one calibration set per strategy from selected candidate rows."""
    rows_by_strategy: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        rows_by_strategy[normalize_strategy_id(row.get("strategy_id"))].append(row)
    return {
        strategy_id: build_calibration_set(strategy_rows)
        for strategy_id, strategy_rows in rows_by_strategy.items()
    }


def percentile_rank(
    values: list[float], value: float, *, higher_is_better: bool
) -> float | None:
    """Return a 0-1 percentile rank with tie averaging.

    When ``higher_is_better`` is False, values are scored so that lower raw
    numbers produce higher percentile scores.
    """
    if not values:
        return None

    working_values = values
    working_value = value
    if not higher_is_better:
        working_values = [-item for item in reversed(values)]
        working_value = -value

    left = bisect_left(working_values, working_value)
    right = bisect_right(working_values, working_value)
    midpoint = (left + right) / 2.0
    return midpoint / len(working_values)


def recompute_ev_score(row: dict[str, str]) -> float | None:
    """Compute ev_score when the stored column is blank or stale."""
    premium = parse_float(row.get("premium", ""))
    max_loss = parse_float(row.get("max_loss", ""))
    short_delta = parse_float(row.get("short_delta", ""))
    if premium is None or max_loss is None or short_delta is None or max_loss <= 0:
        return None
    return (premium / max_loss) * (1.0 - short_delta)


def liquidity_score(
    row: dict[str, str],
    rows_by_group: dict[tuple[str, str, str, str], list[dict[str, str]]],
) -> tuple[float | None, int]:
    """Score liquidity based on sibling candidate resilience within the same run group."""
    group_key = (
        (row.get("run_id") or "").strip(),
        normalize_strategy_id(row.get("strategy_id")),
        (row.get("symbol") or "").strip(),
        (row.get("expiration_date") or "").strip(),
    )
    group_rows = rows_by_group.get(group_key, [])
    if not group_rows:
        return None, 0

    liquidity_failures = sum(
        1
        for group_row in group_rows
        if (group_row.get("rejection_reason_primary") or "").strip()
        in LIQUIDITY_REASONS
    )
    total_candidates = len(group_rows)
    return max(0.0, 1.0 - (liquidity_failures / total_candidates)), total_candidates


def delta_preference_score(row: dict) -> float | None:
    """Asymmetric piecewise delta preference score.

    Sub-target delta earns a linear bonus (up to RANK_DELTA_BONUS_MAX).
    Above-target delta incurs a linear penalty (up to RANK_DELTA_PENALTY_MAX at
    RANK_DELTA_PENALTY_STEEP), then continues decaying at the same rate to zero.
    In RANKING_MODE="soft" the hard ceiling is never enforced.

    Score range: [0.0, 1.0 + RANK_DELTA_BONUS_MAX].
    """
    short_delta = parse_float(row.get("short_delta", ""))
    if short_delta is None:
        return None

    profile = strategy_profile(row.get("strategy_id"))
    target = profile.delta_target
    bonus_floor = profile.delta_bonus_floor
    penalty_steep = profile.delta_penalty_steep
    bonus_max = profile.delta_bonus_max
    penalty_max = profile.delta_penalty_max

    if short_delta <= bonus_floor:
        # At or below bonus floor: floor receives the full bonus
        return 1.0 + bonus_max

    if short_delta <= target:
        # Bonus zone: linear from bonus_max at floor to 0 at target
        t = (target - short_delta) / (target - bonus_floor)
        return 1.0 + t * bonus_max

    if short_delta <= penalty_steep:
        # Shallow penalty zone: linear from 0 at target to -penalty_max at steep
        t = (short_delta - target) / (penalty_steep - target)
        return 1.0 - t * penalty_max

    # Steep zone: continues at the same slope past penalty_steep toward 0
    slope = penalty_max / (penalty_steep - target)
    return max(0.0, (1.0 - penalty_max) - (short_delta - penalty_steep) * slope)


def skew_component_score(row: dict, calibration: CalibrationSet) -> float | None:
    """Weighted blend of skew_ratio and skew_diff percentile ranks.

    Weights are defined by RANK_SKEW_RATIO_WEIGHT and RANK_SKEW_DIFF_WEIGHT.
    Falls back to the single available sub-score if one feature is missing.
    """
    profile = strategy_profile(row.get("strategy_id"))
    ratio_weight = profile.skew_ratio_weight
    diff_weight = profile.skew_diff_weight

    ratio_score: float | None = None
    diff_score: float | None = None

    skew_ratio = parse_float(row.get("skew_ratio", ""))
    if skew_ratio is not None:
        ratio_score = percentile_rank(
            calibration.skew_ratio, skew_ratio, higher_is_better=True
        )

    skew_diff = parse_float(row.get("skew_diff", ""))
    if skew_diff is not None:
        diff_score = percentile_rank(
            calibration.skew_diff, skew_diff, higher_is_better=True
        )

    if ratio_score is not None and diff_score is not None:
        return ratio_weight * ratio_score + diff_weight * diff_score
    if ratio_score is not None:
        return ratio_score
    if diff_score is not None:
        return diff_score
    return None


def ev_component_score(row: dict, calibration: CalibrationSet) -> float | None:
    """Score the candidate's expected value percentile against historical selected candidates."""
    ev = parse_float(row.get("ev_score", "")) or recompute_ev_score(row)
    if ev is None or not calibration.ev_scores:
        return None
    return percentile_rank(calibration.ev_scores, ev, higher_is_better=True)


def _clamp_zero_one(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(1.0, value))


def extension_component_score(row: dict) -> float | None:
    """Score 52-week extension in a strategy-aware direction."""
    profile = strategy_profile(row.get("strategy_id"))
    if profile.component_weights.get("extension", 0.0) <= 0:
        return None

    range_position = _clamp_zero_one(parse_float(row.get("range_position_52w", "")))
    if profile.extension_preference == "near_52w_high":
        distance_metric = parse_float(row.get("distance_to_52w_high_pct", ""))
        distance_score = (
            1.0 - _clamp_zero_one(distance_metric)
            if distance_metric is not None
            else None
        )
        range_score = range_position
    else:
        distance_metric = parse_float(row.get("distance_to_52w_low_pct", ""))
        distance_score = (
            1.0 - _clamp_zero_one(distance_metric)
            if distance_metric is not None
            else None
        )
        range_score = 1.0 - range_position if range_position is not None else None

    parts = [value for value in (range_score, distance_score) if value is not None]
    if not parts:
        return None
    return sum(parts) / len(parts)


def directional_adjustment_factor(row: dict) -> float:
    """Return a multiplier that rewards preferred OTM candidates and penalises ITM drift.

    OTM (delta < RANK_DELTA_TARGET):              * RANK_OTM_BONUS_MULTIPLIER  (1.05)
    ITM drift (delta > RANK_DELTA_PENALTY_STEEP): * RANK_ITM_PENALTY_MULTIPLIER (0.90)
    On-target zone: no adjustment (1.0).
    """
    short_delta = parse_float(row.get("short_delta", ""))
    if short_delta is None:
        return 1.0
    profile = strategy_profile(row.get("strategy_id"))
    if short_delta < profile.delta_target:
        return profile.otm_bonus_multiplier
    if short_delta > profile.delta_penalty_steep:
        return profile.itm_penalty_multiplier
    return 1.0


def compute_alignment_flags(
    row: dict, component_scores: dict[str, float | None]
) -> str:
    """Return a comma-separated tag string describing alignment characteristics."""
    flags: list[str] = []
    short_delta = parse_float(row.get("short_delta", ""))
    profile = strategy_profile(row.get("strategy_id"))
    if short_delta is not None:
        if short_delta <= profile.delta_target:
            flags.append("otm_preferred")
        if short_delta > profile.delta_penalty_steep:
            flags.append("itm_drift")
        if short_delta >= profile.delta_hard_ceiling:
            flags.append("near_ceiling")

    skew = component_scores.get("skew")
    if skew is not None:
        if skew >= 0.70:
            flags.append("rich_skew")
        elif skew < 0.30:
            flags.append("weak_skew")

    extension = component_scores.get("extension")
    if extension is not None:
        if profile.extension_preference == "near_52w_high":
            if extension >= 0.75:
                flags.append("near_52w_high")
            elif extension < 0.30:
                flags.append("far_from_52w_high")
        else:
            if extension >= 0.75:
                flags.append("near_52w_low")
            elif extension < 0.30:
                flags.append("far_from_52w_low")

    return ",".join(flags) if flags else "ok"


def confidence_score(
    component_scores: dict[str, float | None],
    calibration_count: int,
    group_size: int,
) -> tuple[float, str]:
    """Estimate confidence from feature coverage and calibration support."""
    available_components = sum(
        1 for value in component_scores.values() if value is not None
    )
    coverage = available_components / len(component_scores)
    historical_support = min(1.0, calibration_count / 50.0)
    expected_group_size = 1 + config.SKEW_WINDOW_OTM + config.SKEW_WINDOW_ITM
    sibling_support = min(1.0, group_size / max(expected_group_size, 1))

    score = (0.50 * coverage) + (0.35 * historical_support) + (0.15 * sibling_support)
    if score >= 0.80:
        band = "high"
    elif score >= 0.60:
        band = "medium"
    else:
        band = "low"
    return score, band


def weighted_total_score(row: dict, component_scores: dict[str, float | None]) -> float:
    """Combine component scores into a 0-100 total rank score."""
    component_weights = strategy_profile(row.get("strategy_id")).component_weights
    available_weights = {
        name: weight
        for name, weight in component_weights.items()
        if component_scores.get(name) is not None and weight > 0
    }
    if not available_weights:
        return 0.0

    weight_sum = sum(available_weights.values())
    total = 0.0
    for name, weight in available_weights.items():
        normalized_weight = weight / weight_sum
        total += normalized_weight * float(component_scores[name])
    return total * 100.0


def summarize_strengths(component_scores: dict[str, float | None]) -> str:
    """Create a compact human-readable explanation from component scores."""
    present = [
        (name, value) for name, value in component_scores.items() if value is not None
    ]
    if not present:
        return "insufficient_features"

    present.sort(key=lambda item: item[1], reverse=True)
    strengths = ",".join(name for name, _ in present[:2])
    watch_items = ",".join(name for name, _ in present[-2:])
    return f"strengths={strengths};watch={watch_items}"


def rows_grouped_by_run_symbol_expiration(
    rows: Iterable[dict[str, str]],
) -> dict[tuple[str, str, str, str], list[dict[str, str]]]:
    """Group candidate rows by run, strategy, symbol, and expiration."""
    grouped: dict[tuple[str, str, str, str], list[dict[str, str]]] = {}
    for row in rows:
        key = (
            (row.get("run_id") or "").strip(),
            normalize_strategy_id(row.get("strategy_id")),
            (row.get("symbol") or "").strip(),
            (row.get("expiration_date") or "").strip(),
        )
        grouped.setdefault(key, []).append(row)
    return grouped


def output_path_for_run(output_dir: Path, run_id: str) -> Path:
    """Build the default CSV output path for a ranked run."""
    return output_dir / f"opportunity_rankings_{run_id}.csv"


def rank_selected_candidates(
    rows: list[dict[str, str]], run_id: str
) -> list[dict[str, str | float | int]]:
    """Rank selected candidates for a single run."""
    calibrations = build_calibration_sets(rows)
    rows_by_group = rows_grouped_by_run_symbol_expiration(rows)
    selected_rows = [
        row
        for row in rows
        if is_selected_row(row) and (row.get("run_id") or "").strip() == run_id
    ]
    if not selected_rows:
        raise ValueError(f"No selected candidates found for run_id={run_id}.")

    calibration_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if is_selected_row(row):
            calibration_counts[normalize_strategy_id(row.get("strategy_id"))] += 1
    ranked_rows: list[dict[str, str | float | int]] = []

    for row in selected_rows:
        strategy_id = normalize_strategy_id(row.get("strategy_id"))
        calibration = calibrations.get(strategy_id, CalibrationSet([], [], [], [], []))
        liquidity, group_size = liquidity_score(row, rows_by_group)
        component_scores: dict[str, float | None] = {
            "delta": delta_preference_score(row),
            "skew": skew_component_score(row, calibration),
            "ev": ev_component_score(row, calibration),
            "liquidity": liquidity,
            "extension": extension_component_score(row),
        }
        base_score = weighted_total_score(row, component_scores)
        adjustment = directional_adjustment_factor(row)
        earnings_multiplier, earnings_flag = earnings_adjustment(row)
        strategy_alignment_score = round(
            min(100.0, base_score * adjustment * earnings_multiplier),
            4,
        )
        flags = compute_alignment_flags(row, component_scores)
        flags = merge_alignment_flags(flags, earnings_flag)
        confidence, confidence_band = confidence_score(
            component_scores,
            calibration_count=calibration_counts.get(strategy_id, 0),
            group_size=group_size,
        )
        ev_val = round(
            recompute_ev_score(row) or parse_float(row.get("ev_score", "")) or 0.0,
            6,
        )
        short_delta_val = parse_float(row.get("short_delta", ""))
        ranked_rows.append(
            {
                "run_id": (row.get("run_id") or "").strip(),
                "snapshot_ts": (row.get("snapshot_ts") or "").strip(),
                "strategy_id": strategy_id,
                "symbol": (row.get("symbol") or "").strip(),
                "expiration_date": (row.get("expiration_date") or "").strip(),
                "dte": (row.get("dte") or "").strip(),
                "short_strike": (row.get("short_strike") or "").strip(),
                "long_strike": (row.get("long_strike") or "").strip(),
                "width": (row.get("width") or "").strip(),
                "premium": (row.get("premium") or "").strip(),
                "premium_per_width": (row.get("premium_per_width") or "").strip(),
                "max_loss": (row.get("max_loss") or "").strip(),
                "risk_reward_ratio": (row.get("risk_reward_ratio") or "").strip(),
                "short_delta": (row.get("short_delta") or "").strip(),
                "skew_ratio": (row.get("skew_ratio") or "").strip(),
                "skew_diff": (row.get("skew_diff") or "").strip(),
                "ev_score": ev_val,
                "delta_preference_component": round(component_scores["delta"], 4)
                if component_scores["delta"] is not None
                else "",
                "skew_component": round(component_scores["skew"], 4)
                if component_scores["skew"] is not None
                else "",
                "ev_component": round(component_scores["ev"], 4)
                if component_scores["ev"] is not None
                else "",
                "liquidity_component": round(component_scores["liquidity"], 4)
                if component_scores["liquidity"] is not None
                else "",
                "extension_component": round(component_scores["extension"], 4)
                if component_scores["extension"] is not None
                else "",
                "directional_adjustment": round(adjustment, 4),
                "earnings_adjustment": round(earnings_multiplier, 4),
                "strategy_alignment_score": strategy_alignment_score,
                "total_rank_score": strategy_alignment_score,  # backward-compat alias
                "alignment_flags": flags,
                "confidence_score": round(confidence, 4),
                "confidence_band": confidence_band,
                "liquidity_group_size": group_size,
                "calibration_selected_count": calibration_counts.get(strategy_id, 0),
                "explanation_summary": summarize_strengths(component_scores),
                "delta_zone": (
                    "otm"
                    if short_delta_val is not None
                    and short_delta_val < strategy_profile(strategy_id).delta_target
                    else "itm_drift"
                    if short_delta_val is not None
                    and short_delta_val
                    > strategy_profile(strategy_id).delta_penalty_steep
                    else "on_target"
                ),
            }
        )

    ranked_rows.sort(
        key=lambda row: (
            -float(row["strategy_alignment_score"]),
            -float(row["confidence_score"]),
            -float(row["ev_score"]),
            str(row["symbol"]),
        )
    )

    for rank, row in enumerate(ranked_rows, start=1):
        row["rank"] = rank

    return ranked_rows


def write_rankings(path: Path, rows: list[dict[str, str | float | int]]) -> None:
    """Write ranked opportunities to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return

    header = [
        "rank",
        "run_id",
        "snapshot_ts",
        "strategy_id",
        "symbol",
        "expiration_date",
        "dte",
        "short_strike",
        "long_strike",
        "width",
        "premium",
        "premium_per_width",
        "max_loss",
        "risk_reward_ratio",
        "short_delta",
        "skew_ratio",
        "skew_diff",
        "ev_score",
        "delta_preference_component",
        "skew_component",
        "ev_component",
        "liquidity_component",
        "extension_component",
        "directional_adjustment",
        "earnings_adjustment",
        "strategy_alignment_score",
        "total_rank_score",
        "alignment_flags",
        "delta_zone",
        "confidence_score",
        "confidence_band",
        "liquidity_group_size",
        "calibration_selected_count",
        "explanation_summary",
    ]

    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def build_report(
    rows: list[dict[str, str | float | int]], output_path: Path, top_n: int
) -> str:
    """Build a compact terminal summary of the ranking output."""
    lines = [
        "Opportunity Ranking Report",
        f"- Output CSV: {output_path}",
        f"- Rows ranked: {len(rows)}",
        f"- Top {min(top_n, len(rows))} opportunities:",
    ]

    for row in rows[:top_n]:
        lines.append(
            "- "
            f"#{row['rank']} {row['strategy_id']} {row['symbol']} "
            f"{row['short_strike']}/{row['long_strike']} "
            f"align={row['strategy_alignment_score']} ev={row['ev_score']} "
            f"d={row['short_delta']} zone={row['delta_zone']} "
            f"conf={row['confidence_band']} flags=[{row['alignment_flags']}]"
        )

    return "\n".join(lines)


def score_opportunities(opportunities: list[dict]) -> list[dict]:
    """Add strategy_alignment_score and alignment_flags to a live screener batch.

    Uses within-batch calibration for percentile components (skew, ev) since no
    historical CSV is loaded. Delta preference and directional adjustment are
    purely config-driven and require no calibration.

    Returns: the same list with each dict updated in-place (also returned for
    convenience with sorted order by alignment score descending).
    """
    if not opportunities:
        return opportunities

    opportunities_by_strategy: dict[str, list[dict]] = defaultdict(list)
    for opp in opportunities:
        opportunities_by_strategy[normalize_strategy_id(opp.get("strategy_id"))].append(
            opp
        )

    for strategy_id, strategy_opportunities in opportunities_by_strategy.items():
        ev_list: list[float] = []
        skew_ratio_list: list[float] = []
        skew_diff_list: list[float] = []

        for opp in strategy_opportunities:
            ev_val = opp.get("ev_score_chosen") or opp.get("ev_score")
            if ev_val is not None:
                ev = parse_float(ev_val)
                if ev is not None:
                    ev_list.append(ev)
            sr = parse_float(opp.get("skew_ratio"))
            if sr is not None:
                skew_ratio_list.append(sr)
            sd = parse_float(opp.get("skew_diff"))
            if sd is not None:
                skew_diff_list.append(sd)

        calibration = CalibrationSet(
            premium_per_width=[],
            skew_ratio=sorted(skew_ratio_list),
            skew_diff=sorted(skew_diff_list),
            risk_reward_ratio=[],
            ev_scores=sorted(ev_list),
        )

        for opp in strategy_opportunities:
            # Build a proxy row using the live dict keys the scoring functions expect
            proxy: dict = {
                "strategy_id": strategy_id,
                "short_delta": opp.get("short_delta"),
                "skew_ratio": opp.get("skew_ratio"),
                "skew_diff": opp.get("skew_diff"),
                "ev_score": opp.get("ev_score_chosen") or opp.get("ev_score"),
                "dte": opp.get("dte"),
                "snapshot_ts": opp.get("snapshot_ts"),
                "earnings_within_dte": opp.get("earnings_within_dte"),
                "range_position_52w": opp.get("range_position_52w"),
                "distance_to_52w_high_pct": opp.get("distance_to_52w_high_pct"),
                "distance_to_52w_low_pct": opp.get("distance_to_52w_low_pct"),
            }

            component_scores: dict[str, float | None] = {
                "delta": delta_preference_score(proxy),
                "skew": skew_component_score(proxy, calibration),
                "ev": ev_component_score(proxy, calibration),
                "liquidity": 0.5,  # neutral; rejection data not available in live mode
                "extension": extension_component_score(proxy),
            }

            base_score = weighted_total_score(proxy, component_scores)
            adjustment = directional_adjustment_factor(proxy)
            earnings_multiplier, earnings_flag = earnings_adjustment(proxy)
            opp["strategy_alignment_score"] = round(
                min(100.0, base_score * adjustment * earnings_multiplier),
                2,
            )
            base_flags = compute_alignment_flags(proxy, component_scores)
            opp["alignment_flags"] = merge_alignment_flags(base_flags, earnings_flag)
            opp["earnings_adjustment"] = round(earnings_multiplier, 4)

    return sorted(
        opportunities,
        key=lambda o: o.get("strategy_alignment_score") or 0.0,
        reverse=True,
    )


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the ranking engine."""
    parser = argparse.ArgumentParser(
        description="Rank selected spread opportunities with explainable component scores."
    )
    parser.add_argument(
        "--candidate-log",
        type=Path,
        default=DEFAULT_CANDIDATES_PATH,
        help="Path to opportunity_candidates.csv",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default="",
        help="Specific run_id to rank; defaults to latest run in the candidate log",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional explicit output CSV path",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="Number of ranked rows to display in the terminal summary",
    )
    return parser.parse_args()


def main() -> None:
    """Load candidate history, rank the requested run, and export CSV results."""
    args = parse_args()

    if not args.candidate_log.exists():
        raise FileNotFoundError(f"Candidate log not found: {args.candidate_log}")

    rows = load_csv_rows(args.candidate_log)
    run_id = args.run_id.strip() or latest_run_id(rows)
    ranked_rows = rank_selected_candidates(rows, run_id)

    output_path = args.output or output_path_for_run(DEFAULT_OUTPUT_DIR, run_id)
    write_rankings(output_path, ranked_rows)
    print(build_report(ranked_rows, output_path, args.top_n))


if __name__ == "__main__":
    main()
