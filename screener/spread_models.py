"""
Typed models used by the spread analyzer internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class RejectionReason(StrEnum):
    ITM_OR_ATM = "itm_or_atm"
    LONG_STRIKE_UNAVAILABLE = "long_strike_unavailable"
    SHORT_LEG_MISSING_QUOTE = "short_leg_missing_quote"
    LONG_LEG_MISSING_QUOTE = "long_leg_missing_quote"
    DELTA_BOUNDS_MISSING = "delta_bounds_missing"
    DELTA_BOUNDS_MAX = "delta_bounds_max"
    OPEN_INTEREST = "open_interest"
    SHORT_BID_ASK_WIDTH = "short_bid_ask_width"
    LONG_BID_ASK_WIDTH = "long_bid_ask_width"
    CREDIT_NATURAL_TOO_LOW = "credit_natural_too_low"
    CREDIT_EXPECTED_TOO_LOW = "credit_expected_too_low"
    PREMIUM_ZERO_OR_NEGATIVE = "premium_zero_or_negative"
    RISK_REWARD = "risk_reward"
    NO_LONG_STRIKE = "no_long_strike"
    SELECTED_RANKED_OUT = "selected_ranked_out"


@dataclass(slots=True)
class CreditComponents:
    credit_mid: float
    credit_natural: float
    credit_expected: float
    fill_quality: float | None
    short_width_pct: float
    long_width_pct: float
    avg_width_pct: float
    mid_weight: float
    natural_weight: float


@dataclass(slots=True)
class SpreadMetrics:
    premium: float
    max_loss: float
    max_profit: float
    risk_reward_ratio: float
    short_strike: float
    long_strike: float
    width: float
    short_delta: float | None
    short_bid: float
    short_ask: float
    long_bid: float
    long_ask: float
    credit_components: CreditComponents


@dataclass(slots=True)
class CandidatePair:
    shift_steps: int
    short_strike: float
    long_strike: float
    width: float


@dataclass(slots=True)
class CandidateEvaluation:
    shift_steps: int
    short_strike: float
    long_strike: float
    width: float
    short_delta: float | None
    premium: float
    max_loss: float
    risk_reward_ratio: float
    ev_score: float
    market_width: float
    credit_components: CreditComponents


@dataclass(slots=True)
class SelectionResult:
    anchor_strike: float
    anchor_delta: float | None
    chosen: CandidateEvaluation
    anchor_candidate: CandidateEvaluation | None
    skew_steps_from_anchor: int


@dataclass(slots=True)
class RejectionCounters:
    delta_bounds: int = 0
    delta_bounds_min: int = 0
    delta_bounds_max: int = 0
    delta_bounds_missing: int = 0
    itm_or_atm: int = 0
    long_strike_unavailable: int = 0
    short_leg_missing_quote: int = 0
    long_leg_missing_quote: int = 0
    open_interest: int = 0
    short_bid_ask_width: int = 0
    long_bid_ask_width: int = 0
    credit_natural_too_low: int = 0
    credit_expected_too_low: int = 0
    premium_zero_or_negative: int = 0
    risk_reward: int = 0
    no_long_strike: int = 0

    _totals: tuple[str, ...] = field(
        default=(
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
        ),
        init=False,
        repr=False,
    )

    def record(self, reason: RejectionReason) -> None:
        if reason is RejectionReason.DELTA_BOUNDS_MISSING:
            self.delta_bounds += 1
            self.delta_bounds_missing += 1
            return
        if reason is RejectionReason.DELTA_BOUNDS_MAX:
            self.delta_bounds += 1
            self.delta_bounds_max += 1
            return

        field_name = reason.value
        if hasattr(self, field_name):
            setattr(self, field_name, getattr(self, field_name) + 1)

    def total_rejections(self) -> int:
        return sum(getattr(self, field_name) for field_name in self._totals)

    def as_dict(self) -> dict[str, int]:
        data = {
            "delta_bounds": self.delta_bounds,
            "delta_bounds_min": self.delta_bounds_min,
            "delta_bounds_max": self.delta_bounds_max,
            "delta_bounds_missing": self.delta_bounds_missing,
            "itm_or_atm": self.itm_or_atm,
            "long_strike_unavailable": self.long_strike_unavailable,
            "short_leg_missing_quote": self.short_leg_missing_quote,
            "long_leg_missing_quote": self.long_leg_missing_quote,
            "open_interest": self.open_interest,
            "short_bid_ask_width": self.short_bid_ask_width,
            "long_bid_ask_width": self.long_bid_ask_width,
            "credit_natural_too_low": self.credit_natural_too_low,
            "credit_expected_too_low": self.credit_expected_too_low,
            "premium_zero_or_negative": self.premium_zero_or_negative,
            "risk_reward": self.risk_reward,
            "no_long_strike": self.no_long_strike,
        }
        data["total_rejections"] = self.total_rejections()
        return data
