"""
Options spread analysis - evaluates put spread opportunities
"""

import csv
import config
import os
from typing import Dict, Optional, List
from datetime import datetime


class SpreadAnalyzer:
    def __init__(self, run_id: Optional[str] = None, snapshot_ts: Optional[str] = None):
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
        # Asymmetric bid/ask thresholds
        self.max_short_bid_ask_width = config.MAX_SHORT_LEG_BID_ASK_WIDTH
        self.max_short_bid_ask_width_pct = config.MAX_SHORT_LEG_BID_ASK_WIDTH_PCT
        self.max_long_bid_ask_width = config.MAX_LONG_LEG_BID_ASK_WIDTH
        self.max_long_bid_ask_width_pct = config.MAX_LONG_LEG_BID_ASK_WIDTH_PCT
        # Credit per width requirement
        self.min_credit_per_width = config.MIN_CREDIT_PER_WIDTH
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
        self.run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.snapshot_ts = snapshot_ts or datetime.now().isoformat()
        self.candidate_log_path = os.path.join(
            "opportunities", "opportunity_candidates.csv"
        )
        self.candidate_fieldnames = [
            "run_id",
            "snapshot_ts",
            "symbol",
            "expiration_date",
            "dte",
            "stock_price",
            "short_strike",
            "long_strike",
            "width",
            "premium",
            "premium_per_width",
            "max_profit",
            "max_loss",
            "risk_reward_ratio",
            "ev_score",
            "short_delta",
            "short_iv",
            "atm_iv",
            "skew_ratio",
            "skew_diff",
            "earnings_within_dte",
            "candidate_status",
            "selected",
            "rejection_reason_primary",
            "rejection_reason_flags",
        ]
        # Run-level diagnostics: symbol -> rejection counters when no valid spread is found.
        self.strategy_rejections_by_symbol: Dict[str, Dict[str, int]] = {}

    @staticmethod
    def _to_float(value: Optional[float]) -> Optional[float]:
        """Convert a numeric-like value to float when possible."""
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _abs_delta(delta_value: Optional[float]) -> Optional[float]:
        """Return absolute delta in decimal form."""
        delta = SpreadAnalyzer._to_float(delta_value)
        return abs(delta) if delta is not None else None

    @staticmethod
    def _blankify_none(row: Dict) -> Dict:
        """Convert None values to blanks before writing CSV rows."""
        return {key: ("" if value is None else value) for key, value in row.items()}

    def _append_candidate_row(self, row: Dict) -> None:
        """Append a candidate row to the opportunity candidate log."""
        os.makedirs(os.path.dirname(self.candidate_log_path), exist_ok=True)
        file_exists = os.path.isfile(self.candidate_log_path)

        # If schema evolved (e.g., new columns like ev_score), rewrite file once
        # so headers stay aligned with appended rows.
        if file_exists:
            with open(self.candidate_log_path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                existing_fields = reader.fieldnames or []
                needs_migration = any(
                    field not in existing_fields for field in self.candidate_fieldnames
                )
                existing_rows = list(reader) if needs_migration else []

            if needs_migration:
                for existing_row in existing_rows:
                    for field in self.candidate_fieldnames:
                        existing_row[field] = existing_row.get(field, "")

                with open(
                    self.candidate_log_path, "w", newline="", encoding="utf-8"
                ) as f:
                    writer = csv.DictWriter(f, fieldnames=self.candidate_fieldnames)
                    writer.writeheader()
                    writer.writerows(existing_rows)

        with open(self.candidate_log_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.candidate_fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(self._blankify_none(row))

    def _build_candidate_row(
        self,
        *,
        symbol: str,
        expiration_info: Optional[Dict],
        stock_price: float,
        chain: Dict,
        short_strike: Optional[float],
        long_strike: Optional[float] = None,
        width: Optional[float] = None,
        premium: Optional[float] = None,
        max_loss: Optional[float] = None,
        risk_reward_ratio: Optional[float] = None,
        ev_score: Optional[float] = None,
        earnings_within_dte: str = "",
        candidate_status: str = "rejected",
        selected: bool = False,
        rejection_reason_primary: str = "",
        rejection_reason_flags: str = "",
    ) -> Dict:
        """Build a Version 1 opportunity candidate row from entry-time data."""
        skew_metrics = (
            self._compute_skew_metrics(chain, stock_price, short_strike)
            if short_strike is not None
            else {
                "short_iv": None,
                "atm_iv": None,
                "skew_ratio": None,
                "skew_diff": None,
            }
        )
        short_put = self._get_put_by_strike(chain, short_strike)
        short_delta = self._abs_delta(short_put.get("delta")) if short_put else None
        premium_per_width = None
        if premium is not None and width:
            premium_per_width = round(premium / (width * 100), 4)

        computed_ev_score = ev_score
        if (
            computed_ev_score is None
            and premium is not None
            and max_loss is not None
            and max_loss > 0
            and short_delta is not None
        ):
            computed_ev_score = (premium / max_loss) * (1.0 - short_delta)

        return {
            "run_id": self.run_id,
            "snapshot_ts": self.snapshot_ts,
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

    def _log_candidate(
        self,
        *,
        symbol: str,
        expiration_info: Optional[Dict],
        stock_price: float,
        chain: Dict,
        short_strike: Optional[float],
        long_strike: Optional[float] = None,
        width: Optional[float] = None,
        premium: Optional[float] = None,
        max_loss: Optional[float] = None,
        risk_reward_ratio: Optional[float] = None,
        ev_score: Optional[float] = None,
        earnings_within_dte: str = "",
        candidate_status: str = "rejected",
        selected: bool = False,
        rejection_reason_primary: str = "",
        rejection_reason_flags: str = "",
    ) -> None:
        """Write one candidate evaluation row to the candidate log."""
        row = self._build_candidate_row(
            symbol=symbol,
            expiration_info=expiration_info,
            stock_price=stock_price,
            chain=chain,
            short_strike=short_strike,
            long_strike=long_strike,
            width=width,
            premium=premium,
            max_loss=max_loss,
            risk_reward_ratio=risk_reward_ratio,
            ev_score=ev_score,
            earnings_within_dte=earnings_within_dte,
            candidate_status=candidate_status,
            selected=selected,
            rejection_reason_primary=rejection_reason_primary,
            rejection_reason_flags=rejection_reason_flags,
        )
        self._append_candidate_row(row)

    @staticmethod
    def _normalize_iv(iv_value: Optional[float]) -> Optional[float]:
        """Normalize IV into decimal form (e.g., 0.25 for 25%)."""
        if iv_value is None:
            return None
        iv = float(iv_value)
        if iv <= 0:
            return None
        return iv / 100 if iv > 2.0 else iv

    @staticmethod
    def _get_put_by_strike(chain: Dict, target_strike: Optional[float]) -> Dict:
        """Return put data for a strike while tolerating float/string key mismatches."""
        if target_strike is None:
            return {}

        strikes_map = chain.get("strikes", {})

        direct = strikes_map.get(target_strike, {}).get("put")
        if direct:
            return direct

        target = float(target_strike)
        best_put = {}
        best_diff = float("inf")
        for key, strike_data in strikes_map.items():
            try:
                key_float = float(key)
            except (TypeError, ValueError):
                continue
            diff = abs(key_float - target)
            if diff < best_diff:
                candidate_put = strike_data.get("put")
                if candidate_put:
                    best_diff = diff
                    best_put = candidate_put

        return best_put

    def _extract_short_delta(self, put_data: Optional[Dict]) -> Optional[float]:
        """Return absolute short delta from option quote data when available."""
        if not put_data:
            return None
        return self._abs_delta(put_data.get("delta"))

    def _is_delta_above_max(self, short_delta: Optional[float]) -> bool:
        """Return True when a candidate exceeds the configured hard max delta."""
        return short_delta is not None and short_delta > self.max_delta

    def _compute_skew_metrics(
        self, chain: Dict, stock_price: float, short_strike: float
    ) -> Dict[str, Optional[float]]:
        """Compute skew metrics for chosen short strike vs ATM put of same expiration."""
        strike_entries = []
        for strike_key, strike_data in chain.get("strikes", {}).items():
            try:
                strike_float = float(strike_key)
            except (TypeError, ValueError):
                continue
            put_data = strike_data.get("put")
            if not put_data:
                continue
            strike_entries.append((strike_float, put_data))

        # ATM choice priority:
        # 1) put delta closest to 0.50 (with IV available)
        # 2) closest strike to spot (with IV available), deterministic by strike
        atm_put: Dict = {}
        best_delta_diff = float("inf")
        for strike_float, put_data in strike_entries:
            iv_value = self._normalize_iv(put_data.get("implied_volatility"))
            put_delta = put_data.get("delta")
            if iv_value is None or put_delta is None:
                continue
            delta_diff = abs(abs(float(put_delta)) - 0.50)
            if delta_diff < best_delta_diff:
                best_delta_diff = delta_diff
                atm_put = put_data

        if not atm_put:
            for strike_float, put_data in sorted(
                strike_entries,
                key=lambda item: (abs(item[0] - float(stock_price)), item[0]),
            ):
                if self._normalize_iv(put_data.get("implied_volatility")) is not None:
                    atm_put = put_data
                    break

        short_put = self._get_put_by_strike(chain, short_strike)
        short_iv = self._normalize_iv(short_put.get("implied_volatility"))
        atm_iv = self._normalize_iv(atm_put.get("implied_volatility"))

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

    @staticmethod
    def _format_rejection_summary(rejections: Dict[str, int]) -> str:
        """Format non-zero rejection counters into a one-line summary string."""
        parts: List[str] = []

        delta_total = int(rejections.get("delta_bounds", 0) or 0)
        if delta_total > 0:
            delta_min = int(rejections.get("delta_bounds_min", 0) or 0)
            delta_max = int(rejections.get("delta_bounds_max", 0) or 0)
            delta_missing = int(rejections.get("delta_bounds_missing", 0) or 0)
            detail_parts = []
            if delta_min > 0:
                detail_parts.append(f"min={delta_min}")
            if delta_max > 0:
                detail_parts.append(f"max={delta_max}")
            if delta_missing > 0:
                detail_parts.append(f"missing={delta_missing}")
            detail = f" ({', '.join(detail_parts)})" if detail_parts else ""
            parts.append(f"Δ={delta_total}{detail}")

        order = [
            ("itm_or_atm", "itm/atm"),
            ("long_strike_unavailable", "no_long_shift"),
            ("short_leg_missing_quote", "short_quote_missing"),
            ("long_leg_missing_quote", "long_quote_missing"),
            ("open_interest", "oi"),
            ("short_bid_ask_width", "short_ba"),
            ("long_bid_ask_width", "long_ba"),
            ("credit_conservative", "credit"),
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

    def log_rejections(self, symbol: str, rejections: Dict) -> None:
        """
        Log rejection counters to CSV for analysis and tracking
        Ensures the CSV is migrated if a new rejection category is added.
        """
        import csv

        rejections_dir = "rejections"
        os.makedirs(rejections_dir, exist_ok=True)

        filepath = os.path.join(rejections_dir, "rejections_tracking.csv")

        # Explicit field ordering keeps the CSV schema stable as we add counters
        fieldnames = [
            "timestamp",
            "symbol",
            "delta_bounds",
            "delta_bounds_min",
            "delta_bounds_max",
            "delta_bounds_missing",
            "itm_or_atm",
            "long_strike_unavailable",
            "short_leg_missing_quote",
            "long_leg_missing_quote",
            "open_interest",
            "short_bid_ask_width",
            "long_bid_ask_width",
            "credit_conservative",
            "premium_zero_or_negative",
            "risk_reward",
            "no_long_strike",
            "total_rejections",
        ]

        # Prepare row
        row = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "delta_bounds": rejections["delta_bounds"],
            "delta_bounds_min": rejections.get("delta_bounds_min", 0),
            "delta_bounds_max": rejections.get("delta_bounds_max", 0),
            "delta_bounds_missing": rejections.get("delta_bounds_missing", 0),
            "itm_or_atm": rejections.get("itm_or_atm", 0),
            "long_strike_unavailable": rejections.get("long_strike_unavailable", 0),
            "short_leg_missing_quote": rejections.get("short_leg_missing_quote", 0),
            "long_leg_missing_quote": rejections.get("long_leg_missing_quote", 0),
            "open_interest": rejections["open_interest"],
            "short_bid_ask_width": rejections["short_bid_ask_width"],
            "long_bid_ask_width": rejections["long_bid_ask_width"],
            "credit_conservative": rejections["credit_conservative"],
            "premium_zero_or_negative": rejections["premium_zero_or_negative"],
            "risk_reward": rejections["risk_reward"],
            "no_long_strike": rejections["no_long_strike"],
            "total_rejections": sum(
                int(rejections.get(key, 0) or 0)
                for key in [
                    "delta_bounds",
                    "itm_or_atm",
                    "long_strike_unavailable",
                    "short_leg_missing_quote",
                    "long_leg_missing_quote",
                    "open_interest",
                    "short_bid_ask_width",
                    "long_bid_ask_width",
                    "credit_conservative",
                    "premium_zero_or_negative",
                    "risk_reward",
                    "no_long_strike",
                ]
            ),
        }

        file_exists = os.path.isfile(filepath)
        needs_migration = False
        if file_exists:
            with open(filepath, "r", newline="") as existing:
                reader = csv.DictReader(existing)
                existing_fields = reader.fieldnames or []
                needs_migration = (
                    "delta_bounds_min" not in existing_fields
                    or "delta_bounds_max" not in existing_fields
                    or "delta_bounds_missing" not in existing_fields
                    or "long_strike_unavailable" not in existing_fields
                    or "short_leg_missing_quote" not in existing_fields
                    or "long_leg_missing_quote" not in existing_fields
                    or "itm_or_atm" not in existing_fields
                    or "credit_conservative" not in existing_fields
                    or "open_interest" not in existing_fields
                )
                if needs_migration:
                    existing_rows = list(reader)

        # If prior runs lack the new column, rewrite with the new schema
        if file_exists and needs_migration:
            for r in existing_rows:
                r["delta_bounds_min"] = r.get("delta_bounds_min", 0)
                r["delta_bounds_max"] = r.get("delta_bounds_max", 0)
                r["delta_bounds_missing"] = r.get("delta_bounds_missing", 0)
                r["itm_or_atm"] = r.get("itm_or_atm", 0)
                r["long_strike_unavailable"] = r.get("long_strike_unavailable", 0)
                r["short_leg_missing_quote"] = r.get("short_leg_missing_quote", 0)
                r["long_leg_missing_quote"] = r.get("long_leg_missing_quote", 0)
                r["open_interest"] = r.get("open_interest", 0)
                r["credit_conservative"] = r.get("credit_conservative", 0)
                r["total_rejections"] = sum(
                    int(r.get(key, 0) or 0)
                    for key in [
                        "delta_bounds",
                        "itm_or_atm",
                        "long_strike_unavailable",
                        "short_leg_missing_quote",
                        "long_leg_missing_quote",
                        "open_interest",
                        "short_bid_ask_width",
                        "long_bid_ask_width",
                        "credit_conservative",
                        "premium_zero_or_negative",
                        "risk_reward",
                        "no_long_strike",
                    ]
                )
            with open(filepath, "w", newline="") as migrated:
                writer = csv.DictWriter(migrated, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(existing_rows)
            file_exists = True  # header now written with new schema

        # Write/append latest row
        with open(filepath, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    def find_target_expiration(self, expirations: List[Dict]) -> Optional[Dict]:
        """
        Find expiration closest to target DTE within tolerance
        """
        if not expirations:
            return None

        # Filter to standard expirations only (skip weeklies if needed)
        # For now, accept all expirations
        valid_exps = expirations

        # Find closest to target DTE
        closest = min(
            valid_exps, key=lambda x: abs(x["days_to_expiration"] - self.target_dte)
        )

        # Check if within tolerance
        if abs(closest["days_to_expiration"] - self.target_dte) <= self.dte_tolerance:
            return closest

        return None

    def detect_strike_increment(self, strikes: List[float]) -> Optional[float]:
        """
        Detect the dominant strike increment (e.g., 1, 5, 10)
        Returns None if increment cannot be determined
        """
        if not strikes or len(strikes) < 2:
            return None

        sorted_strikes = sorted(strikes)
        diffs = [
            round(sorted_strikes[i + 1] - sorted_strikes[i], 2)
            for i in range(len(sorted_strikes) - 1)
        ]
        positive_diffs = [d for d in diffs if d > 0]
        if not positive_diffs:
            return None

        # Determine most common increment
        increment_counts = {}
        for diff in positive_diffs:
            increment_counts[diff] = increment_counts.get(diff, 0) + 1

        dominant_increment = max(increment_counts, key=increment_counts.get)
        return dominant_increment

    def check_bid_ask_width(
        self, bid: float, ask: float, is_short_leg: bool = True
    ) -> bool:
        """
        Check if bid/ask width meets asymmetric liquidity requirements.
        Short leg has stricter requirements, long leg is looser.
        Pass if EITHER absolute OR percentage threshold is met.

        Args:
            bid: Bid price
            ask: Ask price
            is_short_leg: True for short leg, False for long leg
        """
        if bid is None or ask is None or bid <= 0 or ask <= 0:
            return False

        width = ask - bid
        mid = (bid + ask) / 2

        if is_short_leg:
            # Short leg: stricter thresholds
            if width <= self.max_short_bid_ask_width:
                return True
            if mid > 0 and (width / mid) <= self.max_short_bid_ask_width_pct:
                return True
        else:
            # Long leg: looser thresholds
            if width <= self.max_long_bid_ask_width:
                return True
            if mid > 0 and (width / mid) <= self.max_long_bid_ask_width_pct:
                return True

        return False

    def find_strike_by_delta(
        self, chain: Dict, target_delta: float, tolerance: float = 0.05
    ) -> Optional[float]:
        """
        Find strike price closest to target delta
        For puts, delta is negative, so we compare absolute values
        """
        if not chain or "strikes" not in chain:
            return None

        best_strike = None
        best_diff = float("inf")

        for strike, data in chain["strikes"].items():
            if "put" not in data:
                continue

            put_delta = data["put"].get("delta")
            if put_delta is None:
                continue

            # Put deltas are negative, convert to positive for comparison
            delta_abs = abs(put_delta)
            diff = abs(delta_abs - target_delta)

            if diff < best_diff and diff <= tolerance:
                best_diff = diff
                best_strike = strike

        return best_strike

    def find_spread_strikes(
        self,
        chain: Dict,
        stock_price: float,
        expiration_info: Optional[Dict] = None,
        earnings_within_dte: str = "",
        debug_symbol: str = None,
    ) -> Optional[Dict]:
        """
        Find optimal put spread strikes using skew window optimization.
        Returns dict with short_strike, long_strike, width, and anchor metadata.

        Args:
            chain: Options chain data
            stock_price: Current stock price
            debug_symbol: Optional symbol name for debug output
        """
        # Initialize rejection counters
        rejections = {
            "delta_bounds": 0,
            "delta_bounds_min": 0,
            "delta_bounds_max": 0,
            "delta_bounds_missing": 0,
            "itm_or_atm": 0,
            "long_strike_unavailable": 0,
            "short_leg_missing_quote": 0,
            "long_leg_missing_quote": 0,
            "open_interest": 0,
            "short_bid_ask_width": 0,
            "long_bid_ask_width": 0,
            "credit_conservative": 0,
            "premium_zero_or_negative": 0,
            "risk_reward": 0,
            "no_long_strike": 0,
        }

        # Step 1: Find anchor strike at target delta
        anchor_strike = self.find_strike_by_delta(chain, self.target_delta)

        if anchor_strike is None:
            return None

        # Get anchor metrics for comparison
        anchor_data = chain["strikes"].get(anchor_strike, {}).get("put")
        if not anchor_data:
            return None

        anchor_delta = abs(anchor_data.get("delta", 0))

        # Step 2: Build sorted numeric strike ladder from all chain strikes.
        # Shifts are applied by strike index, not by width multiples.
        # We intentionally include strikes even if quote data is missing so each
        # in-range shift attempt can be logged explicitly.
        available_strikes: List[float] = sorted(
            {
                float(strike)
                for strike, data in chain["strikes"].items()
                if isinstance(data, dict)
            }
        )
        strikes_set = set(available_strikes)

        anchor_strike = float(anchor_strike)
        if anchor_strike not in strikes_set:
            # Defensive fallback for any float/string mismatch in upstream data.
            if not available_strikes:
                return None
            anchor_strike = min(
                available_strikes, key=lambda strike: abs(strike - anchor_strike)
            )

        anchor_index = available_strikes.index(anchor_strike)

        locked_width = None
        for width_candidate in (
            self.preferred_width,
            self.fallback_width,
            self.max_strike_increment,
        ):
            if width_candidate is None or width_candidate <= 0:
                continue
            if (anchor_strike - width_candidate) in strikes_set:
                locked_width = width_candidate
                break

        if locked_width is None:
            rejections["no_long_strike"] += 1
            self._log_candidate(
                symbol=debug_symbol or chain.get("symbol") or "",
                expiration_info=expiration_info,
                stock_price=stock_price,
                chain=chain,
                short_strike=anchor_strike,
                long_strike=None,
                width=None,
                premium=None,
                max_loss=None,
                risk_reward_ratio=None,
                earnings_within_dte=earnings_within_dte,
                candidate_status="rejected",
                selected=False,
                rejection_reason_primary="no_long_strike",
                rejection_reason_flags="no_long_strike",
            )
            return None

        # Step 3: Generate paired shift candidates around anchor using strike index shifts.
        # Width stays fixed at locked_width while short strike walks the strike ladder.
        # This avoids width-based jumps like 92/89 -> 95/92 for one right shift.
        candidate_pairs = []
        for shift_steps in range(-self.skew_window_otm, self.skew_window_itm + 1):
            short_index = anchor_index + shift_steps
            if short_index < 0 or short_index >= len(available_strikes):
                continue

            short_strike = available_strikes[short_index]
            long_strike = short_strike - locked_width
            if long_strike not in strikes_set:
                rejections["long_strike_unavailable"] += 1
                self._log_candidate(
                    symbol=debug_symbol or chain.get("symbol") or "",
                    expiration_info=expiration_info,
                    stock_price=stock_price,
                    chain=chain,
                    short_strike=short_strike,
                    long_strike=long_strike,
                    width=locked_width,
                    premium=None,
                    max_loss=None,
                    risk_reward_ratio=None,
                    earnings_within_dte=earnings_within_dte,
                    candidate_status="rejected",
                    selected=False,
                    rejection_reason_primary="long_strike_unavailable",
                    rejection_reason_flags="long_strike_unavailable",
                )
                continue

            candidate_pairs.append((shift_steps, short_strike, long_strike))

        # Step 4: Evaluate all candidates in window
        valid_candidates = []

        def _log_rejected_candidate(
            reason: str,
            *,
            short_strike: Optional[float],
            long_strike: Optional[float] = None,
            width: Optional[float] = None,
            premium: Optional[float] = None,
            max_loss: Optional[float] = None,
            risk_reward_ratio: Optional[float] = None,
        ) -> None:
            self._log_candidate(
                symbol=debug_symbol or chain.get("symbol") or "",
                expiration_info=expiration_info,
                stock_price=stock_price,
                chain=chain,
                short_strike=short_strike,
                long_strike=long_strike,
                width=width,
                premium=premium,
                max_loss=max_loss,
                risk_reward_ratio=risk_reward_ratio,
                earnings_within_dte=earnings_within_dte,
                candidate_status="rejected",
                selected=False,
                rejection_reason_primary=reason,
                rejection_reason_flags=reason,
            )

        for shift_steps, short_strike, long_strike in candidate_pairs:
            # Guardrail: never allow ATM/ITM short strikes.
            if short_strike >= stock_price:
                rejections["itm_or_atm"] += 1
                _log_rejected_candidate(
                    "itm_or_atm",
                    short_strike=short_strike,
                    long_strike=long_strike,
                    width=locked_width,
                )
                continue

            put_data = chain["strikes"].get(short_strike, {}).get("put")
            if not put_data:
                rejections["short_leg_missing_quote"] += 1
                _log_rejected_candidate(
                    "short_leg_missing_quote",
                    short_strike=short_strike,
                    long_strike=long_strike,
                    width=locked_width,
                )
                continue

            # Extract delta for scoring. Delta bounds are NOT enforced on shifted
            # candidates — the anchor was already pinned to TARGET_DELTA, so OTM/ITM
            # shifts are expected to carry different (and valid) deltas.
            short_delta = self._extract_short_delta(put_data)

            # Hard cap: even if a shifted candidate improves EV, skip it when the
            # short leg drifts too close to the money to be tradable in practice.
            if short_delta is None:
                rejections["delta_bounds"] += 1
                rejections["delta_bounds_missing"] += 1
                _log_rejected_candidate(
                    "delta_bounds_missing",
                    short_strike=short_strike,
                    long_strike=long_strike,
                    width=locked_width,
                )
                continue

            if self._is_delta_above_max(short_delta):
                rejections["delta_bounds"] += 1
                rejections["delta_bounds_max"] += 1
                _log_rejected_candidate(
                    "delta_bounds_max",
                    short_strike=short_strike,
                    long_strike=long_strike,
                    width=locked_width,
                )
                continue

            # Filter 2: Minimum open interest on short leg
            if self.enable_oi_filter:
                short_open_interest = put_data.get("open_interest")
                if (
                    short_open_interest is None
                    or short_open_interest < self.min_option_open_interest_short_leg
                ):
                    rejections["open_interest"] += 1
                    _log_rejected_candidate(
                        "open_interest",
                        short_strike=short_strike,
                        long_strike=long_strike,
                        width=locked_width,
                    )
                    continue

            # Filter 3: Bid/ask width on short leg (stricter threshold)
            short_bid = put_data.get("bid")
            short_ask = put_data.get("ask")
            if not self.check_bid_ask_width(short_bid, short_ask, is_short_leg=True):
                rejections["short_bid_ask_width"] += 1
                _log_rejected_candidate(
                    "short_bid_ask_width",
                    short_strike=short_strike,
                    long_strike=long_strike,
                    width=locked_width,
                )
                continue

            width = locked_width

            # Get long leg data
            long_put_data = chain["strikes"].get(long_strike, {}).get("put")
            if not long_put_data:
                rejections["long_leg_missing_quote"] += 1
                _log_rejected_candidate(
                    "long_leg_missing_quote",
                    short_strike=short_strike,
                    long_strike=long_strike,
                    width=width,
                )
                continue

            # Filter 4: Minimum open interest on long leg
            if self.enable_oi_filter:
                long_open_interest = long_put_data.get("open_interest")
                if (
                    long_open_interest is None
                    or long_open_interest < self.min_option_open_interest_long_leg
                ):
                    rejections["open_interest"] += 1
                    _log_rejected_candidate(
                        "open_interest",
                        short_strike=short_strike,
                        long_strike=long_strike,
                        width=width,
                    )
                    continue

            # Filter 5: Bid/ask width on long leg (looser threshold)
            long_bid = long_put_data.get("bid")
            long_ask = long_put_data.get("ask")
            if not self.check_bid_ask_width(long_bid, long_ask, is_short_leg=False):
                rejections["long_bid_ask_width"] += 1
                _log_rejected_candidate(
                    "long_bid_ask_width",
                    short_strike=short_strike,
                    long_strike=long_strike,
                    width=width,
                )
                continue

            # Calculate credit with conservative (worst-case) scenario
            short_mid = (short_bid + short_ask) / 2
            long_mid = (long_bid + long_ask) / 2
            credit_conservative = (
                short_bid - long_ask
            ) * 100  # worst-case: bid(short) - ask(long)

            # Filter 6: Credit per width check (scale requirement by spread width)
            min_credit_required = width * self.min_credit_per_width * 100
            if credit_conservative < min_credit_required:
                rejections["credit_conservative"] += 1
                _log_rejected_candidate(
                    "credit_conservative",
                    short_strike=short_strike,
                    long_strike=long_strike,
                    width=width,
                    premium=credit_conservative,
                    max_loss=(width * 100) - credit_conservative,
                    risk_reward_ratio=((width * 100) - credit_conservative)
                    / credit_conservative
                    if credit_conservative > 0
                    else None,
                )
                continue

            # Calculate spread metrics with mid prices
            premium = (short_mid - long_mid) * 100

            # Filter 7: Premium validation
            if premium <= 0:
                rejections["premium_zero_or_negative"] += 1
                _log_rejected_candidate(
                    "premium_zero_or_negative",
                    short_strike=short_strike,
                    long_strike=long_strike,
                    width=width,
                    premium=premium,
                )
                continue

            max_loss = (width * 100) - premium
            risk_reward_ratio = max_loss / premium

            # Filter 8: Max risk/reward
            if risk_reward_ratio > self.max_risk_reward:
                rejections["risk_reward"] += 1
                _log_rejected_candidate(
                    "risk_reward",
                    short_strike=short_strike,
                    long_strike=long_strike,
                    width=width,
                    premium=premium,
                    max_loss=max_loss,
                    risk_reward_ratio=risk_reward_ratio,
                )
                continue

            # Calculate bid/ask widths for tie-breaking
            short_width = short_ask - short_bid
            long_width = long_ask - long_bid
            total_market_width = short_width + long_width

            # EV score: expected-value-adjusted return.
            # Combines yield (premium / max_loss) with POP approximation (1 - short_delta).
            # Higher ev_score = better trade.
            # ev_score = (premium / max_loss) * (1 - short_delta)
            ev_score = (
                (premium / max_loss) * (1.0 - short_delta)
                if short_delta is not None and max_loss > 0
                else 0.0
            )

            valid_candidates.append(
                {
                    "shift_steps": shift_steps,
                    "short_strike": short_strike,
                    "long_strike": long_strike,
                    "width": width,
                    "short_delta": short_delta,
                    "premium": premium,
                    "risk_reward_ratio": risk_reward_ratio,
                    "ev_score": ev_score,
                    "delta_diff_from_target": abs(short_delta - self.target_delta)
                    if short_delta is not None
                    else float("inf"),
                    "market_width": total_market_width,
                }
            )

        if not valid_candidates:
            # Log rejections to CSV if requested
            if debug_symbol:
                total_rejected = sum(rejections.values())
                if total_rejected > 0:
                    self.strategy_rejections_by_symbol[debug_symbol] = dict(rejections)
                    self.log_rejections(debug_symbol, rejections)
                    rejection_summary = self._format_rejection_summary(rejections)
                    print(
                        f"\n   ✗ {debug_symbol}: No valid spreads found. Rejections: "
                        f"{rejection_summary}"
                    )
            return None

        # Step 5: Sort by EV score descending.
        # ev_score = (premium / max_loss) * (1 - short_delta)  where (1 - short_delta) ≈ POP
        # Higher ev_score = better: rewards both yield and probability of profit.
        valid_candidates.sort(key=lambda x: -x["ev_score"])

        best_candidate = valid_candidates[0]
        anchor_candidate = next(
            (c for c in valid_candidates if c["shift_steps"] == 0), None
        )

        def _score_improvement_pct(base: Dict, challenger: Dict) -> Optional[float]:
            """Return the % by which challenger's ev_score exceeds base's."""
            base_score = base.get("ev_score")
            challenger_score = challenger.get("ev_score")
            if base_score is None or challenger_score is None or base_score <= 0:
                return None
            return ((challenger_score - base_score) / base_score) * 100

        # Step 6: Apply improvement threshold.
        # Only leave the anchor when a shifted candidate scores meaningfully higher.
        chosen = best_candidate
        if anchor_candidate and best_candidate["shift_steps"] != 0:
            improvement_pct = _score_improvement_pct(anchor_candidate, best_candidate)
            if improvement_pct is None or improvement_pct < self.min_score_improvement:
                # Score gain too small; stay at anchor.
                chosen = anchor_candidate

        # Log valid candidates that were fully evaluated but not selected.
        # This supports post-run analysis of EV ranking decisions.
        for candidate in valid_candidates:
            if (
                candidate["short_strike"] == chosen["short_strike"]
                and candidate["long_strike"] == chosen["long_strike"]
            ):
                continue

            ranked_out_max_loss = candidate["premium"] * candidate["risk_reward_ratio"]
            self._log_candidate(
                symbol=debug_symbol or chain.get("symbol") or "",
                expiration_info=expiration_info,
                stock_price=stock_price,
                chain=chain,
                short_strike=candidate["short_strike"],
                long_strike=candidate["long_strike"],
                width=candidate["width"],
                premium=candidate["premium"],
                max_loss=ranked_out_max_loss,
                risk_reward_ratio=candidate["risk_reward_ratio"],
                ev_score=candidate.get("ev_score"),
                earnings_within_dte=earnings_within_dte,
                candidate_status="rejected",
                selected=False,
                rejection_reason_primary="selected_ranked_out",
                rejection_reason_flags="selected_ranked_out",
            )

        skew_steps_from_anchor = chosen["shift_steps"]

        return {
            "short_strike": chosen["short_strike"],
            "long_strike": chosen["long_strike"],
            "width": chosen["width"],
            "anchor_strike": anchor_strike,
            "anchor_delta": anchor_delta,
            "chosen_delta": chosen["short_delta"],
            "ratio_anchor": anchor_candidate["risk_reward_ratio"]
            if anchor_candidate
            else None,
            "ratio_chosen": chosen["risk_reward_ratio"],
            "ev_score_anchor": anchor_candidate["ev_score"]
            if anchor_candidate
            else None,
            "ev_score_chosen": chosen["ev_score"],
            "skew_steps_from_anchor": skew_steps_from_anchor,
        }

    def calculate_spread_metrics(
        self, chain: Dict, spread_strikes: Dict
    ) -> Optional[Dict]:
        """
        Calculate P&L metrics for a put spread
        Returns dict with premium, max_loss, risk_reward_ratio
        """
        short_strike = spread_strikes["short_strike"]
        long_strike = spread_strikes["long_strike"]
        width = spread_strikes["width"]

        # Get option data (robust to float/string strike-key mismatches)
        short_put = self._get_put_by_strike(chain, short_strike)
        long_put = self._get_put_by_strike(chain, long_strike)
        if not short_put or not long_put:
            return None

        # Use mid price for calculations
        short_bid = short_put.get("bid", 0)
        short_ask = short_put.get("ask", 0)
        long_bid = long_put.get("bid", 0)
        long_ask = long_put.get("ask", 0)

        # Check for valid prices
        if not all([short_bid, short_ask, long_bid, long_ask]):
            return None

        short_mid = (short_bid + short_ask) / 2
        long_mid = (long_bid + long_ask) / 2

        # Premium received (credit spread)
        premium = (short_mid - long_mid) * 100  # x100 for per contract

        # Max loss is width minus premium
        max_loss = (width * 100) - premium

        # Risk/reward ratio
        if premium <= 0:
            return None

        risk_reward_ratio = max_loss / premium

        return {
            "premium": round(premium, 2),
            "max_loss": round(max_loss, 2),
            "max_profit": round(premium, 2),
            "risk_reward_ratio": round(risk_reward_ratio, 2),
            "short_strike": short_strike,
            "long_strike": long_strike,
            "width": width,
            "short_delta": short_put.get("delta"),
            "short_bid": short_bid,
            "short_ask": short_ask,
            "long_bid": long_bid,
            "long_ask": long_ask,
        }

    def evaluate_spread(
        self,
        symbol: str,
        stock_price: float,
        chain: Dict,
        expiration_info: Dict,
        earnings_within_dte: str = "",
    ) -> Optional[Dict]:
        """
        Complete evaluation of a put spread opportunity
        Returns dict with all relevant info if it meets criteria, None otherwise
        """
        # Find spread strikes
        spread_strikes = self.find_spread_strikes(
            chain,
            stock_price,
            expiration_info=expiration_info,
            earnings_within_dte=earnings_within_dte,
            debug_symbol=symbol,
        )

        if spread_strikes is None:
            return None

        # Calculate metrics
        metrics = self.calculate_spread_metrics(chain, spread_strikes)

        if metrics is None:
            return None

        skew_metrics = self._compute_skew_metrics(
            chain, stock_price, spread_strikes["short_strike"]
        )

        # Compile full opportunity info
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
        )

        return opportunity

    def filter_opportunities(
        self, opportunities: List[Dict], max_results: int = config.MAX_FINAL_RESULTS
    ) -> List[Dict]:
        """
        Filter and rank opportunities.
        Sort by skew score descending: score = (premium / max_loss) * POP.
        """
        if not opportunities:
            return []

        filtered_opps = [
            opportunity
            for opportunity in opportunities
            if not self._is_delta_above_max(
                self._to_float(
                    opportunity.get("chosen_delta", opportunity.get("short_delta"))
                )
            )
        ]

        if not filtered_opps:
            return []

        # Sort by EV score descending (higher is better)
        sorted_opps = sorted(
            filtered_opps,
            key=lambda x: x.get("ev_score_chosen") or 0,
            reverse=True,
        )

        return sorted_opps[:max_results]
