"""Capture broker order attempts for fillability analysis."""

from __future__ import annotations

import csv
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

OPTION_SYMBOL_PATTERN = re.compile(
    r"^(?P<underlying>[A-Z.\-]+)(?P<yymmdd>\d{6})(?P<option_type>[PC])(?P<strike>\d{8})$"
)

ORDER_ATTEMPT_FIELDNAMES = [
    "captured_at",
    "order_id",
    "status",
    "attempt_outcome",
    "underlying_symbol",
    "strategy_id",
    "option_side",
    "expiration_date",
    "short_strike",
    "long_strike",
    "width",
    "limit_price",
    "price_effect",
    "time_in_force",
    "received_at",
    "updated_at",
    "terminal_at",
    "filled_at",
    "filled_quantity",
    "remaining_quantity",
    "avg_fill_price",
    "short_option_symbol",
    "long_option_symbol",
    "leg_count",
]


@dataclass(frozen=True)
class ParsedLeg:
    symbol: str
    underlying: str
    expiration_date: str
    option_side: str
    strike: float
    action: str
    quantity: float | None
    fill_quantity: float
    fill_total: float
    latest_fill_at: str


def _safe_float(value: Any) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _format_float(value: float | None, precision: int = 4) -> str:
    if value is None:
        return ""
    return f"{value:.{precision}f}"


def _normalize_action(value: Any) -> str:
    return str(value or "").strip().lower()


def _parse_option_symbol(symbol: Any) -> tuple[str, str, str, float] | None:
    if not isinstance(symbol, str):
        return None
    compact = symbol.replace(" ", "").upper()
    match = OPTION_SYMBOL_PATTERN.match(compact)
    if not match:
        return None
    try:
        expiration = datetime.strptime(match.group("yymmdd"), "%y%m%d").date()
        strike = int(match.group("strike")) / 1000
    except ValueError:
        return None
    option_side = "put" if match.group("option_type") == "P" else "call"
    return match.group("underlying"), expiration.isoformat(), option_side, strike


def _parse_leg(leg: Mapping[str, Any]) -> ParsedLeg | None:
    parsed_symbol = _parse_option_symbol(leg.get("symbol"))
    if parsed_symbol is None:
        return None

    underlying, expiration_date, option_side, strike = parsed_symbol
    fills = leg.get("fills") if isinstance(leg.get("fills"), list) else []
    fill_quantity = 0.0
    fill_total = 0.0
    latest_fill_at = ""
    for fill in fills:
        if not isinstance(fill, Mapping):
            continue
        fill_price = _safe_float(fill.get("fill-price"))
        quantity = _safe_float(fill.get("quantity")) or 0.0
        if fill_price is None or quantity <= 0:
            continue
        fill_quantity += quantity
        fill_total += fill_price * quantity
        filled_at = str(fill.get("filled-at") or "")
        if filled_at > latest_fill_at:
            latest_fill_at = filled_at

    return ParsedLeg(
        symbol=str(leg.get("symbol") or ""),
        underlying=underlying,
        expiration_date=expiration_date,
        option_side=option_side,
        strike=strike,
        action=_normalize_action(leg.get("action")),
        quantity=_safe_float(leg.get("quantity")),
        fill_quantity=fill_quantity,
        fill_total=fill_total,
        latest_fill_at=latest_fill_at,
    )


def _attempt_outcome(status: str) -> str:
    normalized = status.strip().lower()
    if normalized == "filled":
        return "filled"
    if normalized == "expired":
        return "expired_unfilled"
    return normalized or "unknown"


class OrderAttemptService:
    """Export filled and expired option spread orders for fillability analysis."""

    def __init__(self, output_path: str | Path = "execution/order_attempts.csv"):
        self.output_path = Path(output_path)

    def capture_order_attempts(
        self,
        api,
        *,
        lookback_days: int = 14,
        statuses: list[str] | None = None,
        max_pages: int | None = None,
    ) -> Path:
        statuses = statuses or ["Filled", "Expired"]
        orders = api.get_account_orders(
            lookback_days=lookback_days,
            statuses=statuses,
            max_pages=max_pages,
        )
        rows = self.rows_from_orders(orders)
        self.write_rows(rows)
        return self.output_path

    def rows_from_orders(self, orders: list[dict[str, Any]]) -> list[dict[str, str]]:
        captured_at = datetime.now().isoformat(timespec="seconds")
        rows: list[dict[str, str]] = []
        for order in orders:
            row = self.row_from_order(order, captured_at=captured_at)
            if row is not None:
                rows.append(row)
        return rows

    def row_from_order(
        self, order: Mapping[str, Any], *, captured_at: str
    ) -> dict[str, str] | None:
        legs_payload = order.get("legs")
        if not isinstance(legs_payload, list):
            return None
        legs = [
            parsed
            for leg in legs_payload
            if isinstance(leg, Mapping) and (parsed := _parse_leg(leg)) is not None
        ]
        if len(legs) < 2:
            return None
        option_sides = {leg.option_side for leg in legs}
        expirations = {leg.expiration_date for leg in legs}
        underlyings = {leg.underlying for leg in legs}
        if len(option_sides) != 1 or len(expirations) != 1 or len(underlyings) != 1:
            return None

        short_legs = [
            leg for leg in legs if leg.action in {"sell to open", "buy to close"}
        ]
        long_legs = [
            leg for leg in legs if leg.action in {"buy to open", "sell to close"}
        ]
        if not short_legs or not long_legs:
            return None

        short_leg = short_legs[0]
        long_leg = long_legs[0]
        status = str(order.get("status") or "")
        filled_quantity = sum(leg.fill_quantity for leg in legs)
        fill_total = sum(leg.fill_total for leg in legs)
        avg_fill_price = fill_total / filled_quantity if filled_quantity > 0 else None
        width = abs(short_leg.strike - long_leg.strike)

        return {
            "captured_at": captured_at,
            "order_id": str(order.get("id") or ""),
            "status": status,
            "attempt_outcome": _attempt_outcome(status),
            "underlying_symbol": short_leg.underlying,
            "strategy_id": f"{short_leg.option_side}_credit_spread",
            "option_side": short_leg.option_side,
            "expiration_date": short_leg.expiration_date,
            "short_strike": _format_float(short_leg.strike),
            "long_strike": _format_float(long_leg.strike),
            "width": _format_float(width),
            "limit_price": str(order.get("price") or ""),
            "price_effect": str(order.get("price-effect") or ""),
            "time_in_force": str(order.get("time-in-force") or ""),
            "received_at": str(order.get("received-at") or ""),
            "updated_at": str(order.get("updated-at") or ""),
            "terminal_at": str(order.get("terminal-at") or ""),
            "filled_at": max((leg.latest_fill_at for leg in legs), default=""),
            "filled_quantity": _format_float(filled_quantity),
            "remaining_quantity": str(order.get("remaining-quantity") or ""),
            "avg_fill_price": _format_float(avg_fill_price),
            "short_option_symbol": short_leg.symbol,
            "long_option_symbol": long_leg.symbol,
            "leg_count": str(len(legs)),
        }

    def write_rows(self, rows: list[dict[str, str]]) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=ORDER_ATTEMPT_FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
