"""
Shared numeric helpers and spread economics for the analyzer.
"""

from __future__ import annotations

from typing import Any

from screener.spread_models import CreditComponents, SpreadMetrics


def to_float(value: Any) -> float | None:
    """Convert a numeric-like value to float when possible."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def abs_delta(delta_value: Any) -> float | None:
    """Return absolute delta in decimal form."""
    delta = to_float(delta_value)
    return abs(delta) if delta is not None else None


def normalize_iv(iv_value: Any) -> float | None:
    """Normalize IV into decimal form, for example ``0.25`` for 25%."""
    iv = to_float(iv_value)
    if iv is None or iv <= 0:
        return None
    return iv / 100 if iv > 2.0 else iv


def calculate_credit_components(
    short_bid: float,
    short_ask: float,
    long_bid: float,
    long_ask: float,
    *,
    credit_width_pct_tight: float,
    credit_width_pct_ok: float,
    credit_width_pct_wide: float,
    credit_mid_weight_tight: float,
    credit_mid_weight_ok: float,
    credit_mid_weight_moderate: float,
    credit_mid_weight_very_wide: float,
) -> CreditComponents:
    """Return natural, mid, and dynamically weighted expected credits."""
    short_mid = (short_bid + short_ask) / 2
    long_mid = (long_bid + long_ask) / 2

    credit_mid = (short_mid - long_mid) * 100
    credit_natural = (short_bid - long_ask) * 100

    short_width = short_ask - short_bid
    long_width = long_ask - long_bid
    short_width_pct = short_width / short_mid if short_mid > 0 else float("inf")
    long_width_pct = long_width / long_mid if long_mid > 0 else float("inf")
    avg_width_pct = (short_width_pct + long_width_pct) / 2

    if avg_width_pct < credit_width_pct_tight:
        mid_weight = credit_mid_weight_tight
    elif avg_width_pct < credit_width_pct_ok:
        mid_weight = credit_mid_weight_ok
    elif avg_width_pct < credit_width_pct_wide:
        mid_weight = credit_mid_weight_moderate
    else:
        mid_weight = credit_mid_weight_very_wide

    natural_weight = 1.0 - mid_weight
    weighted = (mid_weight * credit_mid) + (natural_weight * credit_natural)
    credit_expected = max(credit_natural, min(weighted, credit_mid))
    fill_quality = credit_expected / credit_mid if credit_mid > 0 else None

    return CreditComponents(
        credit_mid=credit_mid,
        credit_natural=credit_natural,
        credit_expected=credit_expected,
        fill_quality=fill_quality,
        short_width_pct=short_width_pct,
        long_width_pct=long_width_pct,
        avg_width_pct=avg_width_pct,
        mid_weight=mid_weight,
        natural_weight=natural_weight,
    )


def compute_ev_score(
    premium: float | None,
    max_loss: float | None,
    short_delta: float | None,
) -> float:
    """Compute the expected-value-adjusted return proxy used for ranking."""
    if premium is None or max_loss is None or short_delta is None or max_loss <= 0:
        return 0.0
    return (premium / max_loss) * (1.0 - short_delta)


def compute_spread_metrics(
    *,
    short_strike: float,
    long_strike: float,
    width: float,
    short_bid: float,
    short_ask: float,
    long_bid: float,
    long_ask: float,
    short_delta: float | None,
    credit_width_pct_tight: float,
    credit_width_pct_ok: float,
    credit_width_pct_wide: float,
    credit_mid_weight_tight: float,
    credit_mid_weight_ok: float,
    credit_mid_weight_moderate: float,
    credit_mid_weight_very_wide: float,
) -> SpreadMetrics | None:
    """Compute spread metrics from leg quotes using the shared credit model."""
    if any(
        value is None or value <= 0
        for value in [short_bid, short_ask, long_bid, long_ask]
    ):
        return None

    credit_components = calculate_credit_components(
        short_bid,
        short_ask,
        long_bid,
        long_ask,
        credit_width_pct_tight=credit_width_pct_tight,
        credit_width_pct_ok=credit_width_pct_ok,
        credit_width_pct_wide=credit_width_pct_wide,
        credit_mid_weight_tight=credit_mid_weight_tight,
        credit_mid_weight_ok=credit_mid_weight_ok,
        credit_mid_weight_moderate=credit_mid_weight_moderate,
        credit_mid_weight_very_wide=credit_mid_weight_very_wide,
    )

    premium = credit_components.credit_expected
    if premium <= 0:
        return None

    max_loss = (width * 100) - premium
    risk_reward_ratio = max_loss / premium

    return SpreadMetrics(
        premium=premium,
        max_loss=max_loss,
        max_profit=premium,
        risk_reward_ratio=risk_reward_ratio,
        short_strike=short_strike,
        long_strike=long_strike,
        width=width,
        short_delta=short_delta,
        short_bid=short_bid,
        short_ask=short_ask,
        long_bid=long_bid,
        long_ask=long_ask,
        credit_components=credit_components,
    )


def format_rejection_summary(rejections: dict[str, int]) -> str:
    """Format non-zero rejection counters into a one-line summary string."""
    parts: list[str] = []

    delta_total = int(rejections.get("delta_bounds", 0) or 0)
    if delta_total > 0:
        delta_min = int(rejections.get("delta_bounds_min", 0) or 0)
        delta_max = int(rejections.get("delta_bounds_max", 0) or 0)
        delta_missing = int(rejections.get("delta_bounds_missing", 0) or 0)
        detail_parts: list[str] = []
        if delta_min > 0:
            detail_parts.append(f"min={delta_min}")
        if delta_max > 0:
            detail_parts.append(f"max={delta_max}")
        if delta_missing > 0:
            detail_parts.append(f"missing={delta_missing}")
        detail = f" ({', '.join(detail_parts)})" if detail_parts else ""
        parts.append(f"delta={delta_total}{detail}")

    order = [
        ("itm_or_atm", "itm/atm"),
        ("long_strike_unavailable", "no_long_shift"),
        ("short_leg_missing_quote", "short_quote_missing"),
        ("long_leg_missing_quote", "long_quote_missing"),
        ("open_interest", "oi"),
        ("short_bid_ask_width", "short_ba"),
        ("long_bid_ask_width", "long_ba"),
        ("credit_natural_too_low", "nat_credit"),
        ("credit_expected_too_low", "exp_credit"),
        ("premium_zero_or_negative", "prem"),
        ("risk_reward", "r/r"),
        ("no_long_strike", "no_long"),
    ]
    parts.extend(
        f"{label}={rejections.get(key, 0)}"
        for key, label in order
        if rejections.get(key, 0) > 0
    )
    return ", ".join(parts) if parts else "no tracked rejections"
