"""Deterministic entry-time theme tags for analytics."""

from __future__ import annotations

THEME_TAXONOMY_VERSION = "v1"


def _to_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_earnings_exposure(value: object) -> bool:
    raw = str(value or "").strip().lower()
    return raw not in {"", "false", "none", "no", "0"}


def build_theme_fields(
    *,
    iv_rank: object = None,
    market_cap: object = None,
    range_position_52w: object = None,
    price_change_90d: object = None,
    earnings_within_dte: object = None,
    avg_width_pct: object = None,
    credit_expected: object = None,
    width: object = None,
    min_credit_per_width: object = None,
    short_delta: object = None,
    target_delta: object = None,
    short_open_interest: object = None,
    long_open_interest: object = None,
    min_short_open_interest: object = None,
    min_long_open_interest: object = None,
) -> dict[str, str]:
    """Return versioned category fields and their combined tag field."""
    risk_tags: list[str] = []
    technical_tags: list[str] = []
    iv_rank_value = _to_float(iv_rank)
    market_cap_value = _to_float(market_cap)
    range_position_value = _to_float(range_position_52w)
    price_change_90d_value = _to_float(price_change_90d)
    avg_width_pct_value = _to_float(avg_width_pct)
    credit_expected_value = _to_float(credit_expected)
    width_value = _to_float(width)
    min_credit_per_width_value = _to_float(min_credit_per_width)
    short_delta_value = _to_float(short_delta)
    target_delta_value = _to_float(target_delta)
    short_open_interest_value = _to_float(short_open_interest)
    long_open_interest_value = _to_float(long_open_interest)
    min_short_open_interest_value = _to_float(min_short_open_interest)
    min_long_open_interest_value = _to_float(min_long_open_interest)

    if iv_rank_value is not None:
        if iv_rank_value >= 70:
            risk_tags.append("high_iv_rank_70_plus")
        if iv_rank_value >= 90:
            risk_tags.append("extreme_iv_rank_90_plus")

    is_small_cap = (
        market_cap_value is not None and 0 < market_cap_value < 10_000_000_000
    )
    if is_small_cap:
        risk_tags.append("small_cap")
        if iv_rank_value is not None and iv_rank_value >= 70:
            risk_tags.append("speculative_small_cap_high_iv")

    if _has_earnings_exposure(earnings_within_dte):
        risk_tags.append("earnings_exposure")

    if avg_width_pct_value is not None and avg_width_pct_value >= 0.20:
        risk_tags.append("wide_bid_ask_spread")

    if (
        credit_expected_value is not None
        and width_value not in {None, 0.0}
        and min_credit_per_width_value is not None
        and credit_expected_value / width_value <= min_credit_per_width_value * 1.25
    ):
        risk_tags.append("low_credit_quality")

    if short_delta_value is not None and target_delta_value is not None:
        delta_distance = abs(abs(short_delta_value) - abs(target_delta_value))
        if delta_distance <= 0.02:
            risk_tags.append("delta_near_target")
        if abs(short_delta_value) >= abs(target_delta_value) + 0.03:
            risk_tags.append("delta_stretched")

    low_short_oi = (
        short_open_interest_value is not None
        and min_short_open_interest_value is not None
        and short_open_interest_value <= min_short_open_interest_value * 2
    )
    low_long_oi = (
        long_open_interest_value is not None
        and min_long_open_interest_value is not None
        and long_open_interest_value <= min_long_open_interest_value * 2
    )
    if low_short_oi or low_long_oi:
        risk_tags.append("low_open_interest")

    if range_position_value is not None:
        if range_position_value >= 0.80:
            technical_tags.append("near_52w_high")
            if range_position_value >= 0.90:
                technical_tags.append("near_52w_high_extended")
        elif range_position_value <= 0.20:
            technical_tags.append("near_52w_low")
            if range_position_value <= 0.10:
                technical_tags.append("near_52w_low_distressed")

    if price_change_90d_value is not None and abs(price_change_90d_value) > 0.75:
        technical_tags.append("extreme_momentum")

    all_tags = risk_tags + technical_tags
    return {
        "risk_theme_tags": ",".join(risk_tags),
        "technical_theme_tags": ",".join(technical_tags),
        "theme_tags": ",".join(all_tags),
        "theme_taxonomy_version": THEME_TAXONOMY_VERSION,
    }


def build_theme_tags(**kwargs: object) -> str:
    """Return the combined theme tag field for compatibility."""
    return build_theme_fields(**kwargs)["theme_tags"]


def build_market_context_fields(
    *,
    underlying_quote: dict[str, object],
    range_position_52w: object = None,
    earnings_within_dte: object = None,
    avg_width_pct: object = None,
    credit_expected: object = None,
    width: object = None,
    min_credit_per_width: object = None,
    short_delta: object = None,
    target_delta: object = None,
    short_open_interest: object = None,
    long_open_interest: object = None,
    min_short_open_interest: object = None,
    min_long_open_interest: object = None,
) -> dict[str, object]:
    """Return sector, industry, and deterministic theme fields."""
    return {
        "sector": underlying_quote.get("sector"),
        "industry": underlying_quote.get("industry"),
        **build_theme_fields(
            iv_rank=underlying_quote.get("iv_rank"),
            market_cap=underlying_quote.get("market_cap"),
            range_position_52w=range_position_52w,
            price_change_90d=underlying_quote.get("price_change_90d"),
            earnings_within_dte=earnings_within_dte,
            avg_width_pct=avg_width_pct,
            credit_expected=credit_expected,
            width=width,
            min_credit_per_width=min_credit_per_width,
            short_delta=short_delta,
            target_delta=target_delta,
            short_open_interest=short_open_interest,
            long_open_interest=long_open_interest,
            min_short_open_interest=min_short_open_interest,
            min_long_open_interest=min_long_open_interest,
        ),
    }
