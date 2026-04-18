"""
Helpers for reconciling inferred closed trades against recent broker order history.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class ActualCloseMatch:
    close_debit_actual: float
    close_fill_timestamp: str | None
    close_order_id: int | None
    match_confidence: str
    exit_price_source: str = "order_history"


class ClosedTradeReconciliationService:
    def find_actual_close_for_trade(
        self,
        trade_row: Mapping[str, Any],
        recent_orders: list[dict[str, Any]],
    ) -> ActualCloseMatch | None:
        short_symbol = self._normalized_symbol(trade_row.get("short_option_symbol"))
        long_symbol = self._normalized_symbol(trade_row.get("long_option_symbol"))
        underlying_symbol = str(trade_row.get("symbol") or "").strip().upper()

        if not short_symbol or not long_symbol or not underlying_symbol:
            return None

        matching_orders: list[dict[str, Any]] = []
        for order in recent_orders:
            if not self._is_filled_close_order(order):
                continue
            if (
                str(order.get("underlying-symbol") or "").strip().upper()
                != underlying_symbol
            ):
                continue
            if self._match_confidence(order, short_symbol, long_symbol) != "exact_legs":
                continue
            matching_orders.append(order)

        if not matching_orders:
            return None

        matching_orders.sort(
            key=lambda order: self._order_sort_key(order),
            reverse=True,
        )
        best_order = matching_orders[0]
        close_debit_actual = self._extract_actual_close_debit(best_order)
        if close_debit_actual is None:
            return None

        return ActualCloseMatch(
            close_debit_actual=close_debit_actual,
            close_fill_timestamp=self._extract_fill_timestamp(best_order),
            close_order_id=self._safe_int(best_order.get("id")),
            match_confidence="exact_legs",
        )

    def _match_confidence(
        self,
        order: Mapping[str, Any],
        short_symbol: str,
        long_symbol: str,
    ) -> str:
        legs = order.get("legs")
        if not isinstance(legs, list):
            return "no_match"

        short_matched = False
        long_matched = False

        for leg in legs:
            if not isinstance(leg, Mapping):
                continue
            leg_symbol = self._normalized_symbol(leg.get("symbol"))
            action = self._normalized_action(leg.get("action"))
            if leg_symbol == short_symbol and action == "buy_to_close":
                short_matched = True
            if leg_symbol == long_symbol and action == "sell_to_close":
                long_matched = True

        if short_matched and long_matched:
            return "exact_legs"
        return "no_match"

    def _is_filled_close_order(self, order: Mapping[str, Any]) -> bool:
        if str(order.get("status") or "").strip().lower() != "filled":
            return False

        legs = order.get("legs")
        if not isinstance(legs, list) or len(legs) < 2:
            return False

        has_buy_to_close = False
        has_sell_to_close = False
        for leg in legs:
            if not isinstance(leg, Mapping):
                continue
            action = self._normalized_action(leg.get("action"))
            has_buy_to_close = has_buy_to_close or action == "buy_to_close"
            has_sell_to_close = has_sell_to_close or action == "sell_to_close"

        return has_buy_to_close and has_sell_to_close

    def _extract_actual_close_debit(self, order: Mapping[str, Any]) -> float | None:
        fill_based_debit = self._extract_actual_close_debit_from_fills(order)
        if fill_based_debit is not None:
            return fill_based_debit

        price_effect = str(order.get("price-effect") or "").strip().lower()
        if price_effect != "debit":
            return None

        price = self._safe_float(order.get("price"))
        if price is None:
            return None
        return round(price * 100, 2)

    def _extract_actual_close_debit_from_fills(
        self, order: Mapping[str, Any]
    ) -> float | None:
        legs = order.get("legs")
        if not isinstance(legs, list):
            return None

        buy_total = 0.0
        buy_qty = 0.0
        sell_total = 0.0
        sell_qty = 0.0

        for leg in legs:
            if not isinstance(leg, Mapping):
                continue
            fills = leg.get("fills")
            if not isinstance(fills, list) or not fills:
                continue

            action = self._normalized_action(leg.get("action"))
            for fill in fills:
                if not isinstance(fill, Mapping):
                    continue
                fill_price = self._safe_float(fill.get("fill-price"))
                fill_qty = self._safe_float(fill.get("quantity")) or 0.0
                if fill_price is None or fill_qty <= 0:
                    continue

                if action == "buy_to_close":
                    buy_total += fill_price * fill_qty
                    buy_qty += fill_qty
                elif action == "sell_to_close":
                    sell_total += fill_price * fill_qty
                    sell_qty += fill_qty

        if buy_qty <= 0 or sell_qty <= 0:
            return None

        buy_avg = buy_total / buy_qty
        sell_avg = sell_total / sell_qty
        return round((buy_avg - sell_avg) * 100, 2)

    def _extract_fill_timestamp(self, order: Mapping[str, Any]) -> str | None:
        latest_fill_dt: datetime | None = None
        latest_fill_raw: str | None = None

        legs = order.get("legs")
        if isinstance(legs, list):
            for leg in legs:
                if not isinstance(leg, Mapping):
                    continue
                fills = leg.get("fills")
                if not isinstance(fills, list):
                    continue
                for fill in fills:
                    if not isinstance(fill, Mapping):
                        continue
                    filled_at = fill.get("filled-at")
                    fill_dt = self._parse_datetime(filled_at)
                    if fill_dt is None:
                        continue
                    if latest_fill_dt is None or fill_dt > latest_fill_dt:
                        latest_fill_dt = fill_dt
                        latest_fill_raw = str(filled_at)

        if latest_fill_raw:
            return latest_fill_raw

        for fallback_field in ("terminal-at", "received-at"):
            fallback_value = order.get(fallback_field)
            if isinstance(fallback_value, str) and fallback_value.strip():
                return fallback_value

        return None

    def _order_sort_key(self, order: Mapping[str, Any]) -> datetime:
        for field_name in ("terminal-at", "received-at"):
            parsed = self._parse_datetime(order.get(field_name))
            if parsed is not None:
                return parsed
        return datetime.min

    @staticmethod
    def _normalized_symbol(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip().upper()

    @staticmethod
    def _normalized_action(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip().lower().replace(" ", "_")

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
