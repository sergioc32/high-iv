"""
Options spread analysis - evaluates put spread opportunities
"""

import config
import os
from typing import Dict, Optional, List
from datetime import datetime


class SpreadAnalyzer:
    def __init__(self):
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
        self.skew_window = config.SKEW_WINDOW
        self.min_ratio_improvement = config.MIN_RATIO_IMPROVEMENT_PCT
        # Asymmetric bid/ask thresholds
        self.max_short_bid_ask_width = config.MAX_SHORT_LEG_BID_ASK_WIDTH
        self.max_short_bid_ask_width_pct = config.MAX_SHORT_LEG_BID_ASK_WIDTH_PCT
        self.max_long_bid_ask_width = config.MAX_LONG_LEG_BID_ASK_WIDTH
        self.max_long_bid_ask_width_pct = config.MAX_LONG_LEG_BID_ASK_WIDTH_PCT
        # Credit per width requirement
        self.min_credit_per_width = config.MIN_CREDIT_PER_WIDTH
        self.min_option_open_interest_short_leg = getattr(
            config,
            "MIN_OPTION_OPEN_INTEREST_SHORT_LEG",
            config.MIN_OPTION_OPEN_INTEREST_PER_LEG,
        )
        self.min_option_open_interest_long_leg = getattr(
            config,
            "MIN_OPTION_OPEN_INTEREST_LONG_LEG",
            config.MIN_OPTION_OPEN_INTEREST_PER_LEG,
        )

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
            "open_interest": rejections["open_interest"],
            "short_bid_ask_width": rejections["short_bid_ask_width"],
            "long_bid_ask_width": rejections["long_bid_ask_width"],
            "credit_conservative": rejections["credit_conservative"],
            "premium_zero_or_negative": rejections["premium_zero_or_negative"],
            "risk_reward": rejections["risk_reward"],
            "no_long_strike": rejections["no_long_strike"],
            "total_rejections": sum(rejections.values()),
        }

        file_exists = os.path.isfile(filepath)
        needs_migration = False
        if file_exists:
            with open(filepath, "r", newline="") as existing:
                reader = csv.DictReader(existing)
                existing_fields = reader.fieldnames or []
                needs_migration = (
                    "credit_conservative" not in existing_fields
                    or "open_interest" not in existing_fields
                )
                if needs_migration:
                    existing_rows = list(reader)

        # If prior runs lack the new column, rewrite with the new schema
        if file_exists and needs_migration:
            for r in existing_rows:
                r["open_interest"] = r.get("open_interest", 0)
                r["credit_conservative"] = r.get("credit_conservative", 0)
                r["total_rejections"] = sum(
                    int(r.get(key, 0) or 0)
                    for key in [
                        "delta_bounds",
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
        self, chain: Dict, stock_price: float, debug_symbol: str = None
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

        # Step 2: Generate window of candidate strikes
        strikes = sorted(chain["strikes"].keys())
        anchor_idx = strikes.index(anchor_strike)

        window_start = max(0, anchor_idx - self.skew_window)
        window_end = min(len(strikes), anchor_idx + self.skew_window + 1)
        candidate_strikes = strikes[window_start:window_end]

        # Step 3: Evaluate all candidates in window
        valid_candidates = []

        for short_strike in candidate_strikes:
            put_data = chain["strikes"].get(short_strike, {}).get("put")
            if not put_data:
                continue

            # Filter 1: Delta bounds
            short_delta = abs(put_data.get("delta", 0))
            if not (self.min_delta <= short_delta <= self.max_delta):
                rejections["delta_bounds"] += 1
                continue

            # Filter 2: Minimum open interest on short leg
            short_open_interest = put_data.get("open_interest")
            if (
                short_open_interest is None
                or short_open_interest < self.min_option_open_interest_short_leg
            ):
                rejections["open_interest"] += 1
                continue

            # Filter 3: Bid/ask width on short leg (stricter threshold)
            short_bid = put_data.get("bid")
            short_ask = put_data.get("ask")
            if not self.check_bid_ask_width(short_bid, short_ask, is_short_leg=True):
                rejections["short_bid_ask_width"] += 1
                continue

            # Step 4: Find long strike and calculate spread metrics
            long_strike_preferred = short_strike - self.preferred_width
            long_strike_fallback = short_strike - self.fallback_width

            strikes_set = set(strikes)
            long_strike = None
            width = None

            if long_strike_preferred in strikes_set:
                long_strike = long_strike_preferred
                width = self.preferred_width
            elif long_strike_fallback in strikes_set:
                long_strike = long_strike_fallback
                width = self.fallback_width
            else:
                # Adapt to observed strike increments - find closest to preferred width
                increment = self.detect_strike_increment(strikes)
                if increment and increment <= self.max_strike_increment:
                    lower_strikes = [s for s in strikes if s < short_strike]
                    if lower_strikes:
                        # Try preferred width first
                        target_long = short_strike - self.preferred_width
                        long_strike = min(
                            lower_strikes, key=lambda s: abs(s - target_long)
                        )
                        width = short_strike - long_strike

                        # If resulting width is way off, try fallback as target instead
                        if width < (self.preferred_width * 0.6) or width > (
                            self.fallback_width * 1.5
                        ):
                            target_long_fallback = short_strike - self.fallback_width
                            long_strike_fallback = min(
                                lower_strikes,
                                key=lambda s: abs(s - target_long_fallback),
                            )
                            width_fallback = short_strike - long_strike_fallback

                            # Use fallback if it's closer to intended range
                            if abs(width_fallback - self.fallback_width) < abs(
                                width - self.preferred_width
                            ):
                                long_strike = long_strike_fallback
                                width = width_fallback

            if long_strike is None:
                rejections["no_long_strike"] += 1
                continue

            # Get long leg data
            long_put_data = chain["strikes"].get(long_strike, {}).get("put")
            if not long_put_data:
                continue

            # Filter 4: Minimum open interest on long leg
            long_open_interest = long_put_data.get("open_interest")
            if (
                long_open_interest is None
                or long_open_interest < self.min_option_open_interest_long_leg
            ):
                rejections["open_interest"] += 1
                continue

            # Filter 5: Bid/ask width on long leg (looser threshold)
            long_bid = long_put_data.get("bid")
            long_ask = long_put_data.get("ask")
            if not self.check_bid_ask_width(long_bid, long_ask, is_short_leg=False):
                rejections["long_bid_ask_width"] += 1
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
                continue

            # Calculate spread metrics with mid prices
            premium = (short_mid - long_mid) * 100

            # Filter 7: Premium validation
            if premium <= 0:
                rejections["premium_zero_or_negative"] += 1
                continue

            max_loss = (width * 100) - premium
            risk_reward_ratio = max_loss / premium

            # Filter 8: Max risk/reward
            if risk_reward_ratio > self.max_risk_reward:
                rejections["risk_reward"] += 1
                continue

            # Calculate bid/ask widths for tie-breaking
            short_width = short_ask - short_bid
            long_width = long_ask - long_bid
            total_market_width = short_width + long_width

            valid_candidates.append(
                {
                    "short_strike": short_strike,
                    "long_strike": long_strike,
                    "width": width,
                    "short_delta": short_delta,
                    "premium": premium,
                    "risk_reward_ratio": risk_reward_ratio,
                    "delta_diff_from_target": abs(short_delta - self.target_delta),
                    "market_width": total_market_width,
                }
            )

        if not valid_candidates:
            # Log rejections to CSV if requested
            if debug_symbol:
                total_rejected = sum(rejections.values())
                if total_rejected > 0:
                    self.log_rejections(debug_symbol, rejections)
                    print(
                        f"\n   ✗ {debug_symbol}: No valid spreads found. Rejections: "
                        f"Δ={rejections['delta_bounds']}, "
                        f"oi={rejections['open_interest']}, "
                        f"short_ba={rejections['short_bid_ask_width']}, "
                        f"long_ba={rejections['long_bid_ask_width']}, "
                        f"credit={rejections['credit_conservative']}, "
                        f"prem={rejections['premium_zero_or_negative']}, "
                        f"r/r={rejections['risk_reward']}, "
                        f"no_long={rejections['no_long_strike']}"
                    )
            return None

        # Step 5: Sort by decision hierarchy
        # Primary: minimize risk_reward_ratio
        # Tie-breakers: delta closest to target, higher premium, tighter markets
        valid_candidates.sort(
            key=lambda x: (
                x["risk_reward_ratio"],
                x["delta_diff_from_target"],
                -x["premium"],
                x["market_width"],
            )
        )

        best_candidate = valid_candidates[0]
        anchor_candidate = next(
            (c for c in valid_candidates if c["short_strike"] == anchor_strike), None
        )

        # Step 6: Apply improvement threshold
        chosen = best_candidate
        if anchor_candidate and best_candidate["short_strike"] != anchor_strike:
            # Require meaningful improvement to switch from anchor
            improvement_pct = (
                (
                    anchor_candidate["risk_reward_ratio"]
                    - best_candidate["risk_reward_ratio"]
                )
                / anchor_candidate["risk_reward_ratio"]
            ) * 100

            if improvement_pct < self.min_ratio_improvement:
                # Not enough improvement; stick with anchor
                chosen = anchor_candidate

        # Calculate how many strikes away from anchor the chosen strike is
        anchor_idx = strikes.index(anchor_strike)
        chosen_idx = strikes.index(chosen["short_strike"])
        skew_steps_from_anchor = chosen_idx - anchor_idx

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

        # Get option data
        short_put = chain["strikes"][short_strike]["put"]
        long_put = chain["strikes"][long_strike]["put"]

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
        self, symbol: str, stock_price: float, chain: Dict, expiration_info: Dict
    ) -> Optional[Dict]:
        """
        Complete evaluation of a put spread opportunity
        Returns dict with all relevant info if it meets criteria, None otherwise
        """
        # Find spread strikes
        spread_strikes = self.find_spread_strikes(
            chain, stock_price, debug_symbol=symbol
        )

        if spread_strikes is None:
            return None

        # Calculate metrics
        metrics = self.calculate_spread_metrics(chain, spread_strikes)

        if metrics is None:
            return None

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
            **metrics,
        }

        return opportunity

    def filter_opportunities(
        self, opportunities: List[Dict], max_results: int = config.MAX_FINAL_RESULTS
    ) -> List[Dict]:
        """
        Filter and rank opportunities
        Sort by best risk/reward ratio
        """
        if not opportunities:
            return []

        # Sort by risk/reward ratio (lower is better)
        sorted_opps = sorted(opportunities, key=lambda x: x["risk_reward_ratio"])

        return sorted_opps[:max_results]
