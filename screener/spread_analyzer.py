"""
Options spread analysis - evaluates put spread opportunities.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import config
from screener.spread_logging import CandidateLogWriter, RejectionLogWriter
from screener.spread_models import (
    CandidateEvaluation,
    CandidatePair,
    RejectionCounters,
    RejectionReason,
    SelectionResult,
)
from screener.spread_scoring import (
    abs_delta,
    compute_ev_score,
    compute_skew_metrics,
    compute_spread_metrics,
    format_rejection_summary,
    get_put_by_strike,
    normalize_iv,
    to_float,
)


class _CandidateEvaluator:
    """Evaluate one shift candidate against the configured strategy rules."""

    def __init__(
        self,
        analyzer: SpreadAnalyzer,
        *,
        symbol: str,
        chain: dict[str, Any],
        stock_price: float,
        expiration_info: dict[str, Any] | None,
        earnings_within_dte: str,
        rejections: RejectionCounters,
    ) -> None:
        self.analyzer = analyzer
        self.symbol = symbol
        self.chain = chain
        self.stock_price = stock_price
        self.expiration_info = expiration_info
        self.earnings_within_dte = earnings_within_dte
        self.rejections = rejections

    def evaluate(self, candidate: CandidatePair) -> CandidateEvaluation | None:
        if candidate.short_strike >= self.stock_price:
            self._reject(RejectionReason.ITM_OR_ATM, candidate)
            return None

        short_put = get_put_by_strike(self.chain, candidate.short_strike)
        if not short_put:
            self._reject(RejectionReason.SHORT_LEG_MISSING_QUOTE, candidate)
            return None

        short_delta = abs_delta(short_put.get("delta"))
        if short_delta is None:
            self._reject(RejectionReason.DELTA_BOUNDS_MISSING, candidate)
            return None

        if self.analyzer._is_delta_above_max(short_delta):
            self._reject(RejectionReason.DELTA_BOUNDS_MAX, candidate)
            return None

        if self.analyzer.enable_oi_filter:
            short_open_interest = to_float(short_put.get("open_interest"))
            if (
                short_open_interest is None
                or short_open_interest
                < self.analyzer.min_option_open_interest_short_leg
            ):
                self._reject(RejectionReason.OPEN_INTEREST, candidate)
                return None

        short_bid = to_float(short_put.get("bid"))
        short_ask = to_float(short_put.get("ask"))
        if not self.analyzer.check_bid_ask_width(
            short_bid, short_ask, is_short_leg=True
        ):
            self._reject(RejectionReason.SHORT_BID_ASK_WIDTH, candidate)
            return None

        long_put = get_put_by_strike(self.chain, candidate.long_strike)
        if not long_put:
            self._reject(RejectionReason.LONG_LEG_MISSING_QUOTE, candidate)
            return None

        if self.analyzer.enable_oi_filter:
            long_open_interest = to_float(long_put.get("open_interest"))
            if (
                long_open_interest is None
                or long_open_interest < self.analyzer.min_option_open_interest_long_leg
            ):
                self._reject(RejectionReason.OPEN_INTEREST, candidate)
                return None

        long_bid = to_float(long_put.get("bid"))
        long_ask = to_float(long_put.get("ask"))
        if not self.analyzer.check_bid_ask_width(
            long_bid, long_ask, is_short_leg=False
        ):
            self._reject(RejectionReason.LONG_BID_ASK_WIDTH, candidate)
            return None

        metrics = compute_spread_metrics(
            short_strike=candidate.short_strike,
            long_strike=candidate.long_strike,
            width=candidate.width,
            short_bid=short_bid,
            short_ask=short_ask,
            long_bid=long_bid,
            long_ask=long_ask,
            short_delta=short_delta,
            credit_width_pct_tight=self.analyzer.credit_width_pct_tight,
            credit_width_pct_ok=self.analyzer.credit_width_pct_ok,
            credit_width_pct_wide=self.analyzer.credit_width_pct_wide,
            credit_mid_weight_tight=self.analyzer.credit_mid_weight_tight,
            credit_mid_weight_ok=self.analyzer.credit_mid_weight_ok,
            credit_mid_weight_moderate=self.analyzer.credit_mid_weight_moderate,
            credit_mid_weight_very_wide=self.analyzer.credit_mid_weight_very_wide,
        )
        if metrics is None:
            self._reject(RejectionReason.PREMIUM_ZERO_OR_NEGATIVE, candidate)
            return None

        min_natural_allowed = -(
            candidate.width * 100 * self.analyzer.min_natural_credit_pct
        )
        if metrics.credit_components.credit_natural < min_natural_allowed:
            self._reject(
                RejectionReason.CREDIT_NATURAL_TOO_LOW,
                candidate,
                premium=metrics.credit_components.credit_expected,
                max_loss=(candidate.width * 100)
                - metrics.credit_components.credit_expected,
                risk_reward_ratio=(
                    (
                        (candidate.width * 100)
                        - metrics.credit_components.credit_expected
                    )
                    / metrics.credit_components.credit_expected
                    if metrics.credit_components.credit_expected > 0
                    else None
                ),
                credit_mid=metrics.credit_components.credit_mid,
                credit_natural=metrics.credit_components.credit_natural,
                credit_expected=metrics.credit_components.credit_expected,
                fill_quality=metrics.credit_components.fill_quality,
                avg_width_pct=metrics.credit_components.avg_width_pct,
                mid_weight=metrics.credit_components.mid_weight,
            )
            return None

        min_credit_required = candidate.width * self.analyzer.min_credit_per_width * 100
        if metrics.credit_components.credit_expected < min_credit_required:
            self._reject(
                RejectionReason.CREDIT_EXPECTED_TOO_LOW,
                candidate,
                premium=metrics.credit_components.credit_expected,
                max_loss=(candidate.width * 100)
                - metrics.credit_components.credit_expected,
                risk_reward_ratio=(
                    (
                        (candidate.width * 100)
                        - metrics.credit_components.credit_expected
                    )
                    / metrics.credit_components.credit_expected
                    if metrics.credit_components.credit_expected > 0
                    else None
                ),
                credit_mid=metrics.credit_components.credit_mid,
                credit_natural=metrics.credit_components.credit_natural,
                credit_expected=metrics.credit_components.credit_expected,
                fill_quality=metrics.credit_components.fill_quality,
                avg_width_pct=metrics.credit_components.avg_width_pct,
                mid_weight=metrics.credit_components.mid_weight,
            )
            return None

        if metrics.premium <= 0:
            self._reject(
                RejectionReason.PREMIUM_ZERO_OR_NEGATIVE,
                candidate,
                premium=metrics.premium,
                credit_mid=metrics.credit_components.credit_mid,
                credit_natural=metrics.credit_components.credit_natural,
                credit_expected=metrics.credit_components.credit_expected,
                fill_quality=metrics.credit_components.fill_quality,
                avg_width_pct=metrics.credit_components.avg_width_pct,
                mid_weight=metrics.credit_components.mid_weight,
            )
            return None

        if metrics.risk_reward_ratio > self.analyzer.max_risk_reward:
            self._reject(
                RejectionReason.RISK_REWARD,
                candidate,
                premium=metrics.premium,
                max_loss=metrics.max_loss,
                risk_reward_ratio=metrics.risk_reward_ratio,
                credit_mid=metrics.credit_components.credit_mid,
                credit_natural=metrics.credit_components.credit_natural,
                credit_expected=metrics.credit_components.credit_expected,
                fill_quality=metrics.credit_components.fill_quality,
                avg_width_pct=metrics.credit_components.avg_width_pct,
                mid_weight=metrics.credit_components.mid_weight,
            )
            return None

        market_width = (short_ask - short_bid) + (long_ask - long_bid)
        ev_score = compute_ev_score(metrics.premium, metrics.max_loss, short_delta)
        return CandidateEvaluation(
            shift_steps=candidate.shift_steps,
            short_strike=candidate.short_strike,
            long_strike=candidate.long_strike,
            width=candidate.width,
            short_delta=short_delta,
            premium=metrics.premium,
            max_loss=metrics.max_loss,
            risk_reward_ratio=metrics.risk_reward_ratio,
            ev_score=ev_score,
            market_width=market_width,
            credit_components=metrics.credit_components,
        )

    def _reject(
        self,
        reason: RejectionReason,
        candidate: CandidatePair,
        *,
        premium: float | None = None,
        max_loss: float | None = None,
        risk_reward_ratio: float | None = None,
        credit_mid: float | None = None,
        credit_natural: float | None = None,
        credit_expected: float | None = None,
        fill_quality: float | None = None,
        avg_width_pct: float | None = None,
        mid_weight: float | None = None,
    ) -> None:
        self.rejections.record(reason)
        self.analyzer._log_candidate(
            symbol=self.symbol,
            expiration_info=self.expiration_info,
            stock_price=self.stock_price,
            chain=self.chain,
            short_strike=candidate.short_strike,
            long_strike=candidate.long_strike,
            width=candidate.width,
            premium=premium,
            max_loss=max_loss,
            risk_reward_ratio=risk_reward_ratio,
            earnings_within_dte=self.earnings_within_dte,
            candidate_status="rejected",
            selected=False,
            rejection_reason_primary=reason.value,
            rejection_reason_flags=reason.value,
            credit_mid=credit_mid,
            credit_natural=credit_natural,
            credit_expected=credit_expected,
            fill_quality=fill_quality,
            avg_width_pct=avg_width_pct,
            mid_weight=mid_weight,
        )


class SpreadAnalyzer:
    def __init__(self, run_id: str | None = None, snapshot_ts: str | None = None):
        self.target_dte = config.TARGET_DTE
        self.dte_tolerance = config.DTE_TOLERANCE
        self.target_delta = config.TARGET_DELTA
        self.min_delta = config.MIN_DELTA
        self.max_delta = config.MAX_DELTA
        self.long_delta = config.LONG_PUT_DELTA
        self.preferred_width = config.PREFERRED_SPREAD_WIDTH
        self.fallback_width = config.FALLBACK_SPREAD_WIDTH
        self.max_strike_increment = config.MAX_STRIKE_INCREMENT
        self.max_risk_reward = config.MAX_RISK_REWARD_RATIO
        self.skew_window_otm = config.SKEW_WINDOW_OTM
        self.skew_window_itm = config.SKEW_WINDOW_ITM
        self.min_score_improvement = config.MIN_SCORE_IMPROVEMENT_PCT
        self.max_short_bid_ask_width = config.MAX_SHORT_LEG_BID_ASK_WIDTH
        self.max_short_bid_ask_width_pct = config.MAX_SHORT_LEG_BID_ASK_WIDTH_PCT
        self.max_long_bid_ask_width = config.MAX_LONG_LEG_BID_ASK_WIDTH
        self.max_long_bid_ask_width_pct = config.MAX_LONG_LEG_BID_ASK_WIDTH_PCT
        self.min_credit_per_width = config.MIN_CREDIT_PER_WIDTH
        self.min_natural_credit_pct = getattr(config, "MIN_NATURAL_CREDIT_PCT", 0.05)
        self.credit_width_pct_tight = getattr(
            config, "CREDIT_DYNAMIC_WIDTH_PCT_TIGHT", 0.10
        )
        self.credit_width_pct_ok = getattr(config, "CREDIT_DYNAMIC_WIDTH_PCT_OK", 0.20)
        self.credit_width_pct_wide = getattr(
            config, "CREDIT_DYNAMIC_WIDTH_PCT_WIDE", 0.35
        )
        self.credit_mid_weight_tight = getattr(
            config, "CREDIT_DYNAMIC_MID_WEIGHT_TIGHT", 0.85
        )
        self.credit_mid_weight_ok = getattr(
            config, "CREDIT_DYNAMIC_MID_WEIGHT_OK", 0.75
        )
        self.credit_mid_weight_moderate = getattr(
            config, "CREDIT_DYNAMIC_MID_WEIGHT_MODERATE", 0.65
        )
        self.credit_mid_weight_very_wide = getattr(
            config, "CREDIT_DYNAMIC_MID_WEIGHT_VERY_WIDE", 0.55
        )
        self.enable_oi_filter = getattr(config, "ENABLE_OI_FILTER", True)
        fallback_oi_per_leg = getattr(config, "MIN_OPTION_OPEN_INTEREST_PER_LEG", 0)
        self.min_option_open_interest_short_leg = getattr(
            config,
            "MIN_OPTION_OPEN_INTEREST_SHORT_LEG",
            fallback_oi_per_leg,
        )
        self.min_option_open_interest_long_leg = getattr(
            config,
            "MIN_OPTION_OPEN_INTEREST_LONG_LEG",
            fallback_oi_per_leg,
        )
        self.strategy_version = getattr(config, "STRATEGY_VERSION", "v2_dynamic")
        self.legacy_strategy_version = getattr(
            config, "LEGACY_STRATEGY_VERSION", "v1_conservative"
        )
        self.strategy_version_cutoff_date = getattr(
            config, "STRATEGY_VERSION_CUTOFF_DATE", "2026-04-09"
        )
        self.run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.snapshot_ts = snapshot_ts or datetime.now().isoformat()
        self.candidate_logger = CandidateLogWriter(
            "opportunities/opportunity_candidates.csv",
            strategy_version=self.strategy_version,
            legacy_strategy_version=self.legacy_strategy_version,
            cutoff_date_text=self.strategy_version_cutoff_date,
        )
        self.rejection_logger = RejectionLogWriter(
            "rejections/rejections_tracking.csv",
            strategy_version=self.strategy_version,
            legacy_strategy_version=self.legacy_strategy_version,
            cutoff_date_text=self.strategy_version_cutoff_date,
        )
        self.strategy_rejections_by_symbol: dict[str, dict[str, int]] = {}

    @staticmethod
    def _normalize_iv(iv_value: Any) -> float | None:
        return normalize_iv(iv_value)

    @staticmethod
    def _get_put_by_strike(
        chain: dict[str, Any], target_strike: float | None
    ) -> dict[str, Any]:
        return get_put_by_strike(chain, target_strike)

    @staticmethod
    def _format_rejection_summary(rejections: dict[str, int]) -> str:
        return format_rejection_summary(rejections)

    def _extract_short_delta(self, put_data: dict[str, Any] | None) -> float | None:
        if not put_data:
            return None
        return abs_delta(put_data.get("delta"))

    def _is_delta_above_max(self, short_delta: float | None) -> bool:
        return short_delta is not None and short_delta > self.max_delta

    def _find_anchor_strike(self, chain: dict[str, Any]) -> float | None:
        return self.find_strike_by_delta(chain, self.target_delta)

    def _build_available_strikes(self, chain: dict[str, Any]) -> list[float]:
        return sorted(
            {
                strike_float
                for strike, data in chain.get("strikes", {}).items()
                if isinstance(data, dict)
                and (strike_float := to_float(strike)) is not None
            }
        )

    def _determine_locked_width(
        self, anchor_strike: float, strikes_set: set[float]
    ) -> float | None:
        for width_candidate in (
            self.preferred_width,
            self.fallback_width,
            self.max_strike_increment,
        ):
            if width_candidate is None or width_candidate <= 0:
                continue
            if (anchor_strike - width_candidate) in strikes_set:
                return float(width_candidate)
        return None

    def _build_candidate_pairs(
        self,
        *,
        anchor_index: int,
        available_strikes: list[float],
        locked_width: float,
        strikes_set: set[float],
        symbol: str,
        chain: dict[str, Any],
        stock_price: float,
        expiration_info: dict[str, Any] | None,
        earnings_within_dte: str,
        rejections: RejectionCounters,
    ) -> list[CandidatePair]:
        candidate_pairs: list[CandidatePair] = []
        for shift_steps in range(-self.skew_window_otm, self.skew_window_itm + 1):
            short_index = anchor_index + shift_steps
            if short_index < 0 or short_index >= len(available_strikes):
                continue

            short_strike = available_strikes[short_index]
            long_strike = short_strike - locked_width
            if long_strike not in strikes_set:
                rejections.record(RejectionReason.LONG_STRIKE_UNAVAILABLE)
                self._log_candidate(
                    symbol=symbol,
                    expiration_info=expiration_info,
                    stock_price=stock_price,
                    chain=chain,
                    short_strike=short_strike,
                    long_strike=long_strike,
                    width=locked_width,
                    earnings_within_dte=earnings_within_dte,
                    candidate_status="rejected",
                    selected=False,
                    rejection_reason_primary=RejectionReason.LONG_STRIKE_UNAVAILABLE.value,
                    rejection_reason_flags=RejectionReason.LONG_STRIKE_UNAVAILABLE.value,
                )
                continue

            candidate_pairs.append(
                CandidatePair(
                    shift_steps=shift_steps,
                    short_strike=short_strike,
                    long_strike=long_strike,
                    width=locked_width,
                )
            )
        return candidate_pairs

    def _select_best_candidate(
        self,
        *,
        anchor_strike: float,
        anchor_delta: float | None,
        valid_candidates: list[CandidateEvaluation],
    ) -> SelectionResult | None:
        if not valid_candidates:
            return None

        ranked = sorted(
            valid_candidates, key=lambda candidate: candidate.ev_score, reverse=True
        )
        best_candidate = ranked[0]
        anchor_candidate = next(
            (candidate for candidate in ranked if candidate.shift_steps == 0),
            None,
        )

        chosen = best_candidate
        if anchor_candidate and best_candidate.shift_steps != 0:
            improvement_pct = self._score_improvement_pct(
                anchor_candidate, best_candidate
            )
            if improvement_pct is None or improvement_pct < self.min_score_improvement:
                chosen = anchor_candidate

        return SelectionResult(
            anchor_strike=anchor_strike,
            anchor_delta=anchor_delta,
            chosen=chosen,
            anchor_candidate=anchor_candidate,
            skew_steps_from_anchor=chosen.shift_steps,
        )

    @staticmethod
    def _score_improvement_pct(
        base: CandidateEvaluation, challenger: CandidateEvaluation
    ) -> float | None:
        if base.ev_score <= 0:
            return None
        return ((challenger.ev_score - base.ev_score) / base.ev_score) * 100

    def _log_candidate(
        self,
        *,
        symbol: str,
        expiration_info: dict[str, Any] | None,
        stock_price: float,
        chain: dict[str, Any],
        short_strike: float | None,
        long_strike: float | None = None,
        width: float | None = None,
        premium: float | None = None,
        max_loss: float | None = None,
        risk_reward_ratio: float | None = None,
        ev_score: float | None = None,
        earnings_within_dte: str = "",
        candidate_status: str = "rejected",
        selected: bool = False,
        rejection_reason_primary: str = "",
        rejection_reason_flags: str = "",
        credit_mid: float | None = None,
        credit_natural: float | None = None,
        credit_expected: float | None = None,
        fill_quality: float | None = None,
        avg_width_pct: float | None = None,
        mid_weight: float | None = None,
    ) -> None:
        skew_metrics = (
            compute_skew_metrics(chain, stock_price, short_strike)
            if short_strike is not None
            else {
                "short_iv": None,
                "atm_iv": None,
                "skew_ratio": None,
                "skew_diff": None,
            }
        )
        short_put = get_put_by_strike(chain, short_strike)
        short_delta = abs_delta(short_put.get("delta")) if short_put else None
        premium_per_width = None
        if premium is not None and width:
            premium_per_width = round(premium / (width * 100), 4)

        computed_ev_score = ev_score
        if computed_ev_score is None:
            computed_ev_score = compute_ev_score(premium, max_loss, short_delta)

        row = {
            "run_id": self.run_id,
            "snapshot_ts": self.snapshot_ts,
            "strategy_version": self.strategy_version,
            "symbol": symbol,
            "expiration_date": expiration_info.get("expiration_date")
            if expiration_info
            else None,
            "dte": expiration_info.get("days_to_expiration")
            if expiration_info
            else None,
            "stock_price": round(stock_price, 4) if stock_price is not None else None,
            "short_strike": short_strike,
            "long_strike": long_strike,
            "width": width,
            "credit_mid": round(credit_mid, 2) if credit_mid is not None else None,
            "credit_natural": round(credit_natural, 2)
            if credit_natural is not None
            else None,
            "credit_expected": round(credit_expected, 2)
            if credit_expected is not None
            else None,
            "fill_quality": round(fill_quality, 4)
            if fill_quality is not None
            else None,
            "avg_width_pct": round(avg_width_pct, 4)
            if avg_width_pct is not None
            else None,
            "mid_weight": round(mid_weight, 4) if mid_weight is not None else None,
            "premium": round(premium, 2) if premium is not None else None,
            "premium_per_width": premium_per_width,
            "max_profit": round(premium, 2) if premium is not None else None,
            "max_loss": round(max_loss, 2) if max_loss is not None else None,
            "risk_reward_ratio": round(risk_reward_ratio, 4)
            if risk_reward_ratio is not None
            else None,
            "ev_score": round(computed_ev_score, 6)
            if computed_ev_score is not None
            else None,
            "short_delta": short_delta,
            "short_iv": skew_metrics.get("short_iv"),
            "atm_iv": skew_metrics.get("atm_iv"),
            "skew_ratio": skew_metrics.get("skew_ratio"),
            "skew_diff": skew_metrics.get("skew_diff"),
            "earnings_within_dte": earnings_within_dte,
            "candidate_status": candidate_status,
            "selected": selected,
            "rejection_reason_primary": rejection_reason_primary,
            "rejection_reason_flags": rejection_reason_flags,
        }
        self.candidate_logger.append_row(row)

    def log_rejections(self, symbol: str, rejections: dict[str, int]) -> None:
        self.rejection_logger.log(symbol, rejections)

    def find_target_expiration(
        self, expirations: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        if not expirations:
            return None

        closest = min(
            expirations,
            key=lambda expiration: abs(
                expiration["days_to_expiration"] - self.target_dte
            ),
        )
        if abs(closest["days_to_expiration"] - self.target_dte) <= self.dte_tolerance:
            return closest
        return None

    def detect_strike_increment(self, strikes: list[float]) -> float | None:
        if not strikes or len(strikes) < 2:
            return None

        sorted_strikes = sorted(strikes)
        diffs = [
            round(sorted_strikes[index + 1] - sorted_strikes[index], 2)
            for index in range(len(sorted_strikes) - 1)
        ]
        positive_diffs = [diff for diff in diffs if diff > 0]
        if not positive_diffs:
            return None

        increment_counts: dict[float, int] = {}
        for diff in positive_diffs:
            increment_counts[diff] = increment_counts.get(diff, 0) + 1
        return max(increment_counts, key=increment_counts.get)

    def check_bid_ask_width(
        self, bid: float | None, ask: float | None, is_short_leg: bool = True
    ) -> bool:
        if bid is None or ask is None or bid <= 0 or ask <= 0:
            return False

        width = ask - bid
        mid = (bid + ask) / 2
        if is_short_leg:
            if width <= self.max_short_bid_ask_width:
                return True
            if mid > 0 and (width / mid) <= self.max_short_bid_ask_width_pct:
                return True
        else:
            if width <= self.max_long_bid_ask_width:
                return True
            if mid > 0 and (width / mid) <= self.max_long_bid_ask_width_pct:
                return True
        return False

    def find_strike_by_delta(
        self, chain: dict[str, Any], target_delta: float, tolerance: float = 0.05
    ) -> float | None:
        if not chain or "strikes" not in chain:
            return None

        best_strike = None
        best_diff = float("inf")
        for strike, data in chain["strikes"].items():
            if not isinstance(data, dict) or "put" not in data:
                continue

            put_delta = abs_delta(data["put"].get("delta"))
            strike_float = to_float(strike)
            if put_delta is None or strike_float is None:
                continue

            diff = abs(put_delta - target_delta)
            if diff < best_diff and diff <= tolerance:
                best_diff = diff
                best_strike = strike_float
        return best_strike

    def find_spread_strikes(
        self,
        chain: dict[str, Any],
        stock_price: float,
        expiration_info: dict[str, Any] | None = None,
        earnings_within_dte: str = "",
        debug_symbol: str | None = None,
    ) -> dict[str, Any] | None:
        rejections = RejectionCounters()

        anchor_strike = self._find_anchor_strike(chain)
        if anchor_strike is None:
            return None

        anchor_put = get_put_by_strike(chain, anchor_strike)
        if not anchor_put:
            return None
        anchor_delta = abs_delta(anchor_put.get("delta"))

        available_strikes = self._build_available_strikes(chain)
        if not available_strikes:
            return None

        strikes_set = set(available_strikes)
        if anchor_strike not in strikes_set:
            anchor_strike = min(
                available_strikes,
                key=lambda strike: abs(strike - anchor_strike),
            )
        anchor_index = available_strikes.index(anchor_strike)

        locked_width = self._determine_locked_width(anchor_strike, strikes_set)
        symbol = debug_symbol or str(chain.get("symbol") or "")
        if locked_width is None:
            rejections.record(RejectionReason.NO_LONG_STRIKE)
            self._log_candidate(
                symbol=symbol,
                expiration_info=expiration_info,
                stock_price=stock_price,
                chain=chain,
                short_strike=anchor_strike,
                long_strike=None,
                width=None,
                earnings_within_dte=earnings_within_dte,
                candidate_status="rejected",
                selected=False,
                rejection_reason_primary=RejectionReason.NO_LONG_STRIKE.value,
                rejection_reason_flags=RejectionReason.NO_LONG_STRIKE.value,
            )
            return None

        candidate_pairs = self._build_candidate_pairs(
            anchor_index=anchor_index,
            available_strikes=available_strikes,
            locked_width=locked_width,
            strikes_set=strikes_set,
            symbol=symbol,
            chain=chain,
            stock_price=stock_price,
            expiration_info=expiration_info,
            earnings_within_dte=earnings_within_dte,
            rejections=rejections,
        )

        evaluator = _CandidateEvaluator(
            self,
            symbol=symbol,
            chain=chain,
            stock_price=stock_price,
            expiration_info=expiration_info,
            earnings_within_dte=earnings_within_dte,
            rejections=rejections,
        )
        valid_candidates = [
            result
            for result in (
                evaluator.evaluate(candidate) for candidate in candidate_pairs
            )
            if result is not None
        ]

        if not valid_candidates:
            if debug_symbol:
                rejection_data = rejections.as_dict()
                if rejections.total_rejections() > 0:
                    self.strategy_rejections_by_symbol[debug_symbol] = dict(
                        rejection_data
                    )
                    self.log_rejections(debug_symbol, rejection_data)
                    rejection_summary = self._format_rejection_summary(rejection_data)
                    print(
                        f"\n   x {debug_symbol}: No valid spreads found. Rejections: "
                        f"{rejection_summary}"
                    )
            return None

        selection = self._select_best_candidate(
            anchor_strike=anchor_strike,
            anchor_delta=anchor_delta,
            valid_candidates=valid_candidates,
        )
        if selection is None:
            return None

        for candidate in valid_candidates:
            if (
                candidate.short_strike == selection.chosen.short_strike
                and candidate.long_strike == selection.chosen.long_strike
            ):
                continue
            self._log_candidate(
                symbol=symbol,
                expiration_info=expiration_info,
                stock_price=stock_price,
                chain=chain,
                short_strike=candidate.short_strike,
                long_strike=candidate.long_strike,
                width=candidate.width,
                premium=candidate.premium,
                max_loss=candidate.max_loss,
                risk_reward_ratio=candidate.risk_reward_ratio,
                ev_score=candidate.ev_score,
                earnings_within_dte=earnings_within_dte,
                candidate_status="rejected",
                selected=False,
                rejection_reason_primary=RejectionReason.SELECTED_RANKED_OUT.value,
                rejection_reason_flags=RejectionReason.SELECTED_RANKED_OUT.value,
                credit_mid=candidate.credit_components.credit_mid,
                credit_natural=candidate.credit_components.credit_natural,
                credit_expected=candidate.credit_components.credit_expected,
                fill_quality=candidate.credit_components.fill_quality,
                avg_width_pct=candidate.credit_components.avg_width_pct,
                mid_weight=candidate.credit_components.mid_weight,
            )

        return {
            "short_strike": selection.chosen.short_strike,
            "long_strike": selection.chosen.long_strike,
            "width": selection.chosen.width,
            "anchor_strike": selection.anchor_strike,
            "anchor_delta": selection.anchor_delta,
            "chosen_delta": selection.chosen.short_delta,
            "ratio_anchor": selection.anchor_candidate.risk_reward_ratio
            if selection.anchor_candidate
            else None,
            "ratio_chosen": selection.chosen.risk_reward_ratio,
            "ev_score_anchor": selection.anchor_candidate.ev_score
            if selection.anchor_candidate
            else None,
            "ev_score_chosen": selection.chosen.ev_score,
            "skew_steps_from_anchor": selection.skew_steps_from_anchor,
        }

    def calculate_spread_metrics(
        self, chain: dict[str, Any], spread_strikes: dict[str, Any]
    ) -> dict[str, Any] | None:
        short_strike = to_float(spread_strikes["short_strike"])
        long_strike = to_float(spread_strikes["long_strike"])
        width = to_float(spread_strikes["width"])
        if short_strike is None or long_strike is None or width is None:
            return None

        short_put = get_put_by_strike(chain, short_strike)
        long_put = get_put_by_strike(chain, long_strike)
        if not short_put or not long_put:
            return None

        short_bid = to_float(short_put.get("bid"))
        short_ask = to_float(short_put.get("ask"))
        long_bid = to_float(long_put.get("bid"))
        long_ask = to_float(long_put.get("ask"))
        short_delta = abs_delta(short_put.get("delta"))

        metrics = compute_spread_metrics(
            short_strike=short_strike,
            long_strike=long_strike,
            width=width,
            short_bid=short_bid,
            short_ask=short_ask,
            long_bid=long_bid,
            long_ask=long_ask,
            short_delta=short_delta,
            credit_width_pct_tight=self.credit_width_pct_tight,
            credit_width_pct_ok=self.credit_width_pct_ok,
            credit_width_pct_wide=self.credit_width_pct_wide,
            credit_mid_weight_tight=self.credit_mid_weight_tight,
            credit_mid_weight_ok=self.credit_mid_weight_ok,
            credit_mid_weight_moderate=self.credit_mid_weight_moderate,
            credit_mid_weight_very_wide=self.credit_mid_weight_very_wide,
        )
        if metrics is None:
            return None

        return {
            "premium": metrics.premium,
            "max_loss": metrics.max_loss,
            "max_profit": metrics.max_profit,
            "risk_reward_ratio": metrics.risk_reward_ratio,
            "short_strike": metrics.short_strike,
            "long_strike": metrics.long_strike,
            "width": metrics.width,
            "short_delta": short_put.get("delta"),
            "short_bid": metrics.short_bid,
            "short_ask": metrics.short_ask,
            "long_bid": metrics.long_bid,
            "long_ask": metrics.long_ask,
            "credit_mid": metrics.credit_components.credit_mid,
            "credit_natural": metrics.credit_components.credit_natural,
            "credit_expected": metrics.credit_components.credit_expected,
            "fill_quality": metrics.credit_components.fill_quality,
            "avg_width_pct": metrics.credit_components.avg_width_pct,
            "mid_weight": metrics.credit_components.mid_weight,
        }

    def evaluate_spread(
        self,
        symbol: str,
        stock_price: float,
        chain: dict[str, Any],
        expiration_info: dict[str, Any],
        earnings_within_dte: str = "",
    ) -> dict[str, Any] | None:
        spread_strikes = self.find_spread_strikes(
            chain,
            stock_price,
            expiration_info=expiration_info,
            earnings_within_dte=earnings_within_dte,
            debug_symbol=symbol,
        )
        if spread_strikes is None:
            return None

        metrics = self.calculate_spread_metrics(chain, spread_strikes)
        if metrics is None:
            return None

        skew_metrics = compute_skew_metrics(
            chain, stock_price, spread_strikes["short_strike"]
        )
        opportunity = {
            "symbol": symbol,
            "stock_price": stock_price,
            "expiration_date": expiration_info["expiration_date"],
            "dte": expiration_info["days_to_expiration"],
            "anchor_strike": spread_strikes.get("anchor_strike"),
            "chosen_strike": metrics["short_strike"],
            "skew_steps_from_anchor": spread_strikes.get("skew_steps_from_anchor"),
            "anchor_delta": spread_strikes.get("anchor_delta"),
            "chosen_delta": abs(metrics["short_delta"])
            if metrics.get("short_delta")
            else None,
            "ratio_anchor": spread_strikes.get("ratio_anchor"),
            "ratio_chosen": spread_strikes.get("ratio_chosen"),
            "ev_score_anchor": spread_strikes.get("ev_score_anchor"),
            "ev_score_chosen": spread_strikes.get("ev_score_chosen"),
            "earnings_within_dte": earnings_within_dte,
            **metrics,
            **skew_metrics,
        }

        self._log_candidate(
            symbol=symbol,
            expiration_info=expiration_info,
            stock_price=stock_price,
            chain=chain,
            short_strike=metrics["short_strike"],
            long_strike=metrics["long_strike"],
            width=metrics["width"],
            premium=metrics["premium"],
            max_loss=metrics["max_loss"],
            risk_reward_ratio=metrics["risk_reward_ratio"],
            ev_score=spread_strikes.get("ev_score_chosen"),
            earnings_within_dte=earnings_within_dte,
            candidate_status="selected",
            selected=True,
            credit_mid=metrics.get("credit_mid"),
            credit_natural=metrics.get("credit_natural"),
            credit_expected=metrics.get("credit_expected"),
            fill_quality=metrics.get("fill_quality"),
            avg_width_pct=metrics.get("avg_width_pct"),
            mid_weight=metrics.get("mid_weight"),
        )
        return opportunity

    def filter_opportunities(
        self,
        opportunities: list[dict[str, Any]],
        max_results: int = config.MAX_FINAL_RESULTS,
    ) -> list[dict[str, Any]]:
        if not opportunities:
            return []

        filtered_opps = [
            opportunity
            for opportunity in opportunities
            if not self._is_delta_above_max(
                to_float(
                    opportunity.get("chosen_delta", opportunity.get("short_delta"))
                )
            )
        ]
        if not filtered_opps:
            return []

        return sorted(
            filtered_opps,
            key=lambda opportunity: opportunity.get("ev_score_chosen") or 0,
            reverse=True,
        )[:max_results]
