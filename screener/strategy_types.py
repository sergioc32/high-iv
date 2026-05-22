"""
Strategy identity metadata for spread analyzers.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpreadStrategyIdentity:
    strategy_id: str
    strategy_family: str
    option_side: str
    directional_bias: str
    short_leg_type: str
    long_leg_type: str
    long_strike_direction: int

    def log_fields(self) -> dict[str, str]:
        return {
            "strategy_id": self.strategy_id,
            "strategy_family": self.strategy_family,
            "option_side": self.option_side,
            "directional_bias": self.directional_bias,
            "short_leg_type": self.short_leg_type,
            "long_leg_type": self.long_leg_type,
        }


PUT_CREDIT_SPREAD = SpreadStrategyIdentity(
    strategy_id="put_credit_spread",
    strategy_family="credit_spread",
    option_side="put",
    directional_bias="bullish",
    short_leg_type="short_put",
    long_leg_type="long_put",
    long_strike_direction=-1,
)

CALL_CREDIT_SPREAD = SpreadStrategyIdentity(
    strategy_id="call_credit_spread",
    strategy_family="credit_spread",
    option_side="call",
    directional_bias="bearish",
    short_leg_type="short_call",
    long_leg_type="long_call",
    long_strike_direction=1,
)
