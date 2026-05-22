"""
Rule-based strategy selector for put/call suitability scoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import config


@dataclass(frozen=True)
class MarketProxyContext:
    symbol: str
    regime: str
    range_position_52w: float | None
    distance_to_52w_high_pct: float | None
    distance_to_52w_low_pct: float | None


@dataclass(frozen=True)
class MarketContext:
    market_regime_spy: str
    market_regime_qqq: str
    market_regime_summary: str
    selector_version: str


class StrategySelector:
    """Annotate opportunities with identify-only strategy suitability scores."""

    def __init__(self) -> None:
        self.mode = getattr(config, "STRATEGY_SELECTOR_MODE", "identify_only")
        self.selector_version = getattr(config, "SELECTOR_VERSION", "v1")

    @staticmethod
    def _to_float(value: object) -> float | None:
        try:
            if value in ("", None):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_range_percent(value: object) -> float | None:
        raw = StrategySelector._to_float(value)
        if raw is None:
            return None
        if raw <= 1.5:
            return raw * 100.0
        return raw

    @staticmethod
    def _parse_iso_date(value: object) -> date | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None

    def classify_market_regime(
        self,
        *,
        range_position_52w: object,
        distance_to_52w_high_pct: object,
        distance_to_52w_low_pct: object,
    ) -> str:
        range_pct = self._to_range_percent(range_position_52w)
        dist_high = self._to_float(distance_to_52w_high_pct)
        dist_low = self._to_float(distance_to_52w_low_pct)

        if range_pct is None:
            return "unknown"

        if (
            range_pct >= config.SELECTOR_MARKET_EXTENDED_BULLISH_MIN_RANGE
            and dist_high is not None
            and dist_high
            <= config.SELECTOR_MARKET_EXTENDED_BULLISH_MAX_DISTANCE_TO_HIGH_PCT
        ):
            return "extended_bullish"

        if (
            config.SELECTOR_MARKET_BULLISH_MIN_RANGE
            <= range_pct
            <= config.SELECTOR_MARKET_BULLISH_MAX_RANGE
            and dist_high is not None
            and dist_high <= config.SELECTOR_MARKET_BULLISH_MAX_DISTANCE_TO_HIGH_PCT
        ):
            return "bullish"

        if range_pct <= config.SELECTOR_MARKET_RISK_OFF_MAX_RANGE or (
            dist_low is not None
            and dist_low <= config.SELECTOR_MARKET_RISK_OFF_MAX_DISTANCE_TO_LOW_PCT
        ):
            return "risk_off"

        if (
            config.SELECTOR_MARKET_WEAK_MIN_RANGE
            <= range_pct
            <= config.SELECTOR_MARKET_WEAK_MAX_RANGE
        ):
            return "weak"

        if (
            config.SELECTOR_MARKET_NEUTRAL_MIN_RANGE
            <= range_pct
            <= config.SELECTOR_MARKET_NEUTRAL_MAX_RANGE
        ):
            return "neutral"

        return "unknown"

    def build_market_context(
        self, proxy_metrics: dict[str, dict[str, object]]
    ) -> MarketContext:
        proxy_contexts: dict[str, MarketProxyContext] = {}
        for proxy in getattr(config, "SELECTOR_MARKET_PROXIES", ("SPY", "QQQ")):
            metrics = proxy_metrics.get(proxy, {})
            regime = self.classify_market_regime(
                range_position_52w=metrics.get("range_position_52w"),
                distance_to_52w_high_pct=metrics.get("distance_to_52w_high_pct"),
                distance_to_52w_low_pct=metrics.get("distance_to_52w_low_pct"),
            )
            proxy_contexts[proxy] = MarketProxyContext(
                symbol=proxy,
                regime=regime,
                range_position_52w=self._to_float(metrics.get("range_position_52w")),
                distance_to_52w_high_pct=self._to_float(
                    metrics.get("distance_to_52w_high_pct")
                ),
                distance_to_52w_low_pct=self._to_float(
                    metrics.get("distance_to_52w_low_pct")
                ),
            )

        spy_regime = proxy_contexts.get(
            "SPY", MarketProxyContext("SPY", "unknown", None, None, None)
        ).regime
        qqq_regime = proxy_contexts.get(
            "QQQ", MarketProxyContext("QQQ", "unknown", None, None, None)
        ).regime
        summary = self._combine_market_regimes(spy_regime, qqq_regime)
        return MarketContext(
            market_regime_spy=spy_regime,
            market_regime_qqq=qqq_regime,
            market_regime_summary=summary,
            selector_version=self.selector_version,
        )

    def _combine_market_regimes(self, spy_regime: str, qqq_regime: str) -> str:
        regime_values = getattr(config, "SELECTOR_MARKET_REGIME_VALUES", {})
        spy_value = regime_values.get(spy_regime)
        qqq_value = regime_values.get(qqq_regime)
        if spy_value is None or qqq_value is None:
            return "unknown"
        if abs(spy_value - qqq_value) >= 3:
            return "mixed"
        average = (spy_value + qqq_value) / 2.0
        if average >= 3.5:
            return "extended_bullish"
        if average >= 2.5:
            return "bullish"
        if average >= 1.5:
            return "neutral"
        if average >= 0.5:
            return "weak"
        return "risk_off"

    def classify_symbol_extension(self, *, range_position_52w: object) -> str:
        range_pct = self._to_range_percent(range_position_52w)
        if range_pct is None:
            return "unknown"
        if range_pct >= config.SELECTOR_SYMBOL_NEAR_HIGH_MIN_RANGE:
            return "near_high"
        if (
            config.SELECTOR_SYMBOL_UPPER_RANGE_MIN
            <= range_pct
            <= config.SELECTOR_SYMBOL_UPPER_RANGE_MAX
        ):
            return "upper_range"
        if (
            config.SELECTOR_SYMBOL_MID_RANGE_MIN
            <= range_pct
            <= config.SELECTOR_SYMBOL_MID_RANGE_MAX
        ):
            return "mid_range"
        if (
            config.SELECTOR_SYMBOL_LOWER_RANGE_MIN
            <= range_pct
            <= config.SELECTOR_SYMBOL_LOWER_RANGE_MAX
        ):
            return "lower_range"
        if range_pct <= config.SELECTOR_SYMBOL_NEAR_LOW_MAX_RANGE:
            return "near_low"
        return "unknown"

    def _earnings_penalty(self, row: dict[str, object]) -> tuple[str, int]:
        earnings_date = self._parse_iso_date(row.get("earnings_within_dte"))
        expiration_date = self._parse_iso_date(row.get("expiration_date"))
        snapshot_date = self._parse_iso_date(row.get("snapshot_ts"))

        if earnings_date is None or expiration_date is None:
            return "post_cycle", 0

        if snapshot_date is not None:
            days_to_earnings = (earnings_date - snapshot_date).days
            if days_to_earnings <= config.SELECTOR_EARNINGS_IMMINENT_DAYS:
                return "imminent", config.SELECTOR_EARNINGS_IMMINENT_PENALTY

        remaining_dte_at_earnings = (expiration_date - earnings_date).days
        if (
            remaining_dte_at_earnings
            <= config.SELECTOR_EARNINGS_LATE_CYCLE_MAX_REMAINING_DTE
        ):
            return "late_cycle", config.SELECTOR_EARNINGS_LATE_CYCLE_PENALTY
        return "pre_cycle", config.SELECTOR_EARNINGS_PRE_CYCLE_PENALTY

    @staticmethod
    def _clamp_score(score: int) -> int:
        return max(0, min(100, score))

    def _score_band(self, score: int) -> str:
        if score >= config.SELECTOR_STRONG_MIN_SCORE:
            return "strong"
        if score >= config.SELECTOR_VIABLE_FLOOR:
            return "viable"
        if score > config.SELECTOR_WEAK_MAX_SCORE:
            return "marginal"
        return "weak"

    def _selector_confidence(self, put_score: int, call_score: int) -> str:
        spread = abs(put_score - call_score)
        if spread >= config.SELECTOR_CONFIDENCE_HIGH_SPREAD:
            return "high"
        if spread >= config.SELECTOR_CONFIDENCE_MEDIUM_SPREAD:
            return "medium"
        return "low"

    def _selector_state(self, put_score: int, call_score: int) -> str:
        if (
            put_score <= config.SELECTOR_WEAK_MAX_SCORE
            and call_score <= config.SELECTOR_WEAK_MAX_SCORE
        ) or (
            put_score < config.SELECTOR_VIABLE_FLOOR
            and call_score < config.SELECTOR_VIABLE_FLOOR
        ):
            return "none"
        if (
            call_score >= config.SELECTOR_VIABLE_FLOOR
            and call_score >= put_score + config.SELECTOR_CALL_MARGIN
        ):
            return "call"
        if (
            put_score >= config.SELECTOR_VIABLE_FLOOR
            and put_score >= call_score + config.SELECTOR_PUT_MARGIN
        ):
            return "put"
        if (
            put_score >= config.SELECTOR_VIABLE_FLOOR
            and call_score >= config.SELECTOR_VIABLE_FLOOR
        ):
            return "both"
        return "none"

    def _selector_reason(
        self,
        *,
        market_regime_summary: str,
        symbol_extension_bucket: str,
        earnings_stage: str,
        preferred_strategy: str,
    ) -> str:
        return (
            f"state={preferred_strategy};market={market_regime_summary};"
            f"symbol={symbol_extension_bucket};earnings={earnings_stage}"
        )

    def annotate_opportunities(
        self,
        opportunities: list[dict[str, object]],
        *,
        market_context: MarketContext,
    ) -> list[dict[str, object]]:
        if self.mode != "identify_only":
            return opportunities

        for opportunity in opportunities:
            symbol_bucket = self.classify_symbol_extension(
                range_position_52w=opportunity.get("range_position_52w")
            )
            earnings_stage, earnings_penalty = self._earnings_penalty(opportunity)

            put_score = self._clamp_score(
                int(
                    config.SELECTOR_BASE_SCORE
                    + config.PUT_SELECTOR_MARKET_ADJUSTMENTS.get(
                        market_context.market_regime_summary, 0
                    )
                    + config.PUT_SELECTOR_EXTENSION_ADJUSTMENTS.get(symbol_bucket, 0)
                    + earnings_penalty
                )
            )
            call_score = self._clamp_score(
                int(
                    config.SELECTOR_BASE_SCORE
                    + config.CALL_SELECTOR_MARKET_ADJUSTMENTS.get(
                        market_context.market_regime_summary, 0
                    )
                    + config.CALL_SELECTOR_EXTENSION_ADJUSTMENTS.get(symbol_bucket, 0)
                    + earnings_penalty
                )
            )

            preferred_strategy = self._selector_state(put_score, call_score)
            opportunity.update(
                {
                    "selector_version": market_context.selector_version,
                    "market_regime_spy": market_context.market_regime_spy,
                    "market_regime_qqq": market_context.market_regime_qqq,
                    "market_regime_summary": market_context.market_regime_summary,
                    "symbol_extension_bucket": symbol_bucket,
                    "put_selector_score": put_score,
                    "call_selector_score": call_score,
                    "put_selector_band": self._score_band(put_score),
                    "call_selector_band": self._score_band(call_score),
                    "selector_preferred_strategy": preferred_strategy,
                    "selector_confidence": self._selector_confidence(
                        put_score, call_score
                    ),
                    "selector_reason": self._selector_reason(
                        market_regime_summary=market_context.market_regime_summary,
                        symbol_extension_bucket=symbol_bucket,
                        earnings_stage=earnings_stage,
                        preferred_strategy=preferred_strategy,
                    ),
                    "selector_earnings_stage": earnings_stage,
                    "selector_earnings_penalty": earnings_penalty,
                }
            )
        return opportunities
