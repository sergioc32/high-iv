"""
Option-chain lookup helpers shared by spread analyzers.
"""

from __future__ import annotations

from typing import Any


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _abs_delta(delta_value: Any) -> float | None:
    delta = _to_float(delta_value)
    return abs(delta) if delta is not None else None


def _normalize_iv(iv_value: Any) -> float | None:
    iv = _to_float(iv_value)
    if iv is None or iv <= 0:
        return None
    return iv / 100 if iv > 2.0 else iv


def get_option_by_strike(
    chain: dict[str, Any], target_strike: float | None, option_type: str
) -> dict[str, Any]:
    """Return option data for a strike while tolerating float/string key mismatches."""
    if target_strike is None:
        return {}

    strikes_map = chain.get("strikes", {})
    if not isinstance(strikes_map, dict):
        return {}

    direct = strikes_map.get(target_strike, {}).get(option_type)
    if direct:
        return direct

    target = _to_float(target_strike)
    if target is None:
        return {}

    for key, strike_data in strikes_map.items():
        key_float = _to_float(key)
        if key_float is None or not isinstance(strike_data, dict):
            continue
        if abs(key_float - target) > 1e-9:
            continue
        candidate_option = strike_data.get(option_type)
        if candidate_option:
            return candidate_option
        return {}
    return {}


def get_put_by_strike(
    chain: dict[str, Any], target_strike: float | None
) -> dict[str, Any]:
    """Return put data for a strike while tolerating float/string key mismatches."""
    return get_option_by_strike(chain, target_strike, "put")


def get_call_by_strike(
    chain: dict[str, Any], target_strike: float | None
) -> dict[str, Any]:
    """Return call data for a strike while tolerating float/string key mismatches."""
    return get_option_by_strike(chain, target_strike, "call")


def find_strike_by_delta(
    chain: dict[str, Any],
    target_delta: float,
    *,
    option_type: str,
    tolerance: float = 0.05,
) -> float | None:
    """Find the strike whose option delta is closest to the target absolute delta."""
    if not chain or "strikes" not in chain:
        return None

    best_strike = None
    best_diff = float("inf")
    for strike, data in chain["strikes"].items():
        if not isinstance(data, dict) or option_type not in data:
            continue

        option_delta = _abs_delta(data[option_type].get("delta"))
        strike_float = _to_float(strike)
        if option_delta is None or strike_float is None:
            continue

        diff = abs(option_delta - target_delta)
        if diff < best_diff and diff <= tolerance:
            best_diff = diff
            best_strike = strike_float
    return best_strike


def compute_option_skew_metrics(
    chain: dict[str, Any],
    stock_price: float,
    short_strike: float,
    *,
    option_type: str,
) -> dict[str, float | None]:
    """Compute short-strike skew metrics against the nearest ATM-style option."""
    strike_entries: list[tuple[float, dict[str, Any]]] = []
    for strike_key, strike_data in chain.get("strikes", {}).items():
        strike_float = _to_float(strike_key)
        if strike_float is None or not isinstance(strike_data, dict):
            continue
        option_data = strike_data.get(option_type)
        if not option_data:
            continue
        strike_entries.append((strike_float, option_data))

    atm_option: dict[str, Any] = {}
    best_delta_diff = float("inf")
    for _, option_data in strike_entries:
        iv_value = _normalize_iv(option_data.get("implied_volatility"))
        option_delta = _abs_delta(option_data.get("delta"))
        if iv_value is None or option_delta is None:
            continue
        delta_diff = abs(option_delta - 0.50)
        if delta_diff < best_delta_diff:
            best_delta_diff = delta_diff
            atm_option = option_data

    if not atm_option:
        for _, option_data in sorted(
            strike_entries,
            key=lambda item: (abs(item[0] - float(stock_price)), item[0]),
        ):
            if _normalize_iv(option_data.get("implied_volatility")) is not None:
                atm_option = option_data
                break

    short_option = get_option_by_strike(chain, short_strike, option_type)
    short_iv = _normalize_iv(short_option.get("implied_volatility"))
    atm_iv = _normalize_iv(atm_option.get("implied_volatility"))

    if short_iv is None or atm_iv is None or atm_iv <= 0:
        return {
            "short_iv": None,
            "atm_iv": None,
            "skew_ratio": None,
            "skew_diff": None,
        }

    skew_ratio = short_iv / atm_iv
    skew_diff = short_iv - atm_iv
    return {
        "short_iv": round(short_iv, 4),
        "atm_iv": round(atm_iv, 4),
        "skew_ratio": round(skew_ratio, 4),
        "skew_diff": round(skew_diff, 4),
    }


def compute_skew_metrics(
    chain: dict[str, Any], stock_price: float, short_strike: float
) -> dict[str, float | None]:
    """Compute short-strike skew metrics against the nearest ATM-style put."""
    return compute_option_skew_metrics(
        chain, stock_price, short_strike, option_type="put"
    )
