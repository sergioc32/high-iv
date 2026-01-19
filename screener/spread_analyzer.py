"""
Options spread analysis - evaluates put spread opportunities
"""
import config
from typing import Dict, Optional, List
from datetime import datetime, date


class SpreadAnalyzer:
    def __init__(self):
        self.target_dte = config.TARGET_DTE
        self.dte_tolerance = config.DTE_TOLERANCE
        self.target_delta = config.TARGET_DELTA
        self.long_delta = config.LONG_PUT_DELTA
        self.preferred_width = config.PREFERRED_SPREAD_WIDTH
        self.fallback_width = config.FALLBACK_SPREAD_WIDTH
        self.max_strike_increment = config.MAX_STRIKE_INCREMENT
        self.max_risk_reward = config.MAX_RISK_REWARD_RATIO
    
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
            valid_exps,
            key=lambda x: abs(x['days_to_expiration'] - self.target_dte)
        )
        
        # Check if within tolerance
        if abs(closest['days_to_expiration'] - self.target_dte) <= self.dte_tolerance:
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
        diffs = [round(sorted_strikes[i+1] - sorted_strikes[i], 2) for i in range(len(sorted_strikes) - 1)]
        positive_diffs = [d for d in diffs if d > 0]
        if not positive_diffs:
            return None

        # Determine most common increment
        increment_counts = {}
        for diff in positive_diffs:
            increment_counts[diff] = increment_counts.get(diff, 0) + 1

        dominant_increment = max(increment_counts, key=increment_counts.get)
        return dominant_increment
    
    def find_strike_by_delta(self, chain: Dict, target_delta: float, tolerance: float = 0.05) -> Optional[float]:
        """
        Find strike price closest to target delta
        For puts, delta is negative, so we compare absolute values
        """
        if not chain or 'strikes' not in chain:
            return None
        
        best_strike = None
        best_diff = float('inf')
        
        for strike, data in chain['strikes'].items():
            if 'put' not in data:
                continue
            
            put_delta = data['put'].get('delta')
            if put_delta is None:
                continue
            
            # Put deltas are negative, convert to positive for comparison
            delta_abs = abs(put_delta)
            diff = abs(delta_abs - target_delta)
            
            if diff < best_diff and diff <= tolerance:
                best_diff = diff
                best_strike = strike
        
        return best_strike
    
    def find_spread_strikes(self, chain: Dict, stock_price: float) -> Optional[Dict]:
        """
        Find optimal put spread strikes
        Returns dict with short_strike, long_strike, and width
        """
        # Find short put strike (sell) at target delta
        short_strike = self.find_strike_by_delta(chain, self.target_delta)
        
        if short_strike is None:
            return None
        
        # Try to find long put at preferred width first
        long_strike_preferred = short_strike - self.preferred_width
        long_strike_fallback = short_strike - self.fallback_width
        
        # Check if strikes exist in chain
        strikes = sorted(chain['strikes'].keys())
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
            # Adapt to observed strike increments when preferred widths are unavailable
            increment = self.detect_strike_increment(strikes)
            if increment and increment <= self.max_strike_increment:
                lower_strikes = [s for s in strikes if s < short_strike]
                if lower_strikes:
                    long_strike = max(lower_strikes)
                    width = short_strike - long_strike
        
        if long_strike is None:
            return None
        
        return {
            'short_strike': short_strike,
            'long_strike': long_strike,
            'width': width
        }
    
    def calculate_spread_metrics(self, chain: Dict, spread_strikes: Dict) -> Optional[Dict]:
        """
        Calculate P&L metrics for a put spread
        Returns dict with premium, max_loss, risk_reward_ratio
        """
        short_strike = spread_strikes['short_strike']
        long_strike = spread_strikes['long_strike']
        width = spread_strikes['width']
        
        # Get option data
        short_put = chain['strikes'][short_strike]['put']
        long_put = chain['strikes'][long_strike]['put']
        
        # Use mid price for calculations
        short_bid = short_put.get('bid', 0)
        short_ask = short_put.get('ask', 0)
        long_bid = long_put.get('bid', 0)
        long_ask = long_put.get('ask', 0)
        
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
            'premium': round(premium, 2),
            'max_loss': round(max_loss, 2),
            'max_profit': round(premium, 2),
            'risk_reward_ratio': round(risk_reward_ratio, 2),
            'short_strike': short_strike,
            'long_strike': long_strike,
            'width': width,
            'short_delta': short_put.get('delta'),
            'short_bid': short_bid,
            'short_ask': short_ask,
            'long_bid': long_bid,
            'long_ask': long_ask
        }
    
    def evaluate_spread(self, symbol: str, stock_price: float, chain: Dict, 
                       expiration_info: Dict) -> Optional[Dict]:
        """
        Complete evaluation of a put spread opportunity
        Returns dict with all relevant info if it meets criteria, None otherwise
        """
        # Find spread strikes
        spread_strikes = self.find_spread_strikes(chain, stock_price)
        
        if spread_strikes is None:
            return None
        
        # Calculate metrics
        metrics = self.calculate_spread_metrics(chain, spread_strikes)
        
        if metrics is None:
            return None
        
        # Check if meets risk/reward criteria
        if metrics['risk_reward_ratio'] > self.max_risk_reward:
            return None
        
        # Compile full opportunity info
        opportunity = {
            'symbol': symbol,
            'stock_price': stock_price,
            'expiration_date': expiration_info['expiration_date'],
            'dte': expiration_info['days_to_expiration'],
            **metrics
        }
        
        return opportunity
    
    def filter_opportunities(self, opportunities: List[Dict], 
                            max_results: int = config.MAX_FINAL_RESULTS) -> List[Dict]:
        """
        Filter and rank opportunities
        Sort by best risk/reward ratio
        """
        if not opportunities:
            return []
        
        # Sort by risk/reward ratio (lower is better)
        sorted_opps = sorted(opportunities, key=lambda x: x['risk_reward_ratio'])
        
        return sorted_opps[:max_results]