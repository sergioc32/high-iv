"""
Configuration file for options screener.
"""

# ---------------------------------------------------------------------------
# Shared / general screener settings
# ---------------------------------------------------------------------------

# Screening criteria
IV_RANK_THRESHOLD = 40  # Minimum IV Rank %
MIN_STOCK_PRICE = 25.00  # Minimum stock price ($25+ filters subscale names)
# MIN_LIQUIDITY_VOLUME = 1_000_000  # Minimum daily volume if available
MIN_UNDERLYING_VOLUME = 1_000_000  # Legacy underlying-volume fallback threshold
MIN_TASTY_LIQUIDITY_RATING = 2  # Tasty options liquidity rating, 1=thin, 4=most liquid
ENABLE_UNDERLYING_VOLUME_FALLBACK_FILTER = (
    False  # Prefer TT liquidity rating; volume fallback is optional
)
ENABLE_OI_FILTER = False  # Toggle to enable/disable open interest filtering
MIN_MARKET_CAP = 1_000_000_000  # Minimum market cap in USD
MIN_OPTION_OPEN_INTEREST_PER_LEG = 100  # Legacy single threshold fallback
MIN_OPTION_OPEN_INTEREST_SHORT_LEG = 25  # Minimum OI on short leg
MIN_OPTION_OPEN_INTEREST_LONG_LEG = 5  # Minimum OI on long leg

# Shared timing / structure defaults
TARGET_DTE = 45  # Target days to expiration
DTE_TOLERANCE = 14  # Accept expirations within +/- 14 days of target
PREFERRED_SPREAD_WIDTH = 3  # Preferred spread width in dollars
FALLBACK_SPREAD_WIDTH = 5  # Fallback if preferred width is unavailable
MAX_STRIKE_INCREMENT = 10  # Max strike increment to accept when adapting widths
MAX_RISK_REWARD_RATIO = 4.25  # Max loss / premium received

# Shared shift / anchor behavior
SKEW_WINDOW_OTM = 3  # Check N OTM shifts from anchor
SKEW_WINDOW_ITM = 1  # Check N ITM shifts from anchor
MIN_SCORE_IMPROVEMENT_PCT = 2.5  # Require this % improvement to switch anchor

# Shared liquidity and fillability checks
MIN_CREDIT_PER_WIDTH = 0.08  # $8 per $1 width (3-wide=$24, 5-wide=$40)
MIN_NATURAL_CREDIT_PCT = 0.05  # Allow a small negative natural floor by width

# Dynamic credit weighting by bid/ask quality
CREDIT_DYNAMIC_WIDTH_PCT_TIGHT = 0.10  # avg_width_pct < this -> tight market
CREDIT_DYNAMIC_WIDTH_PCT_OK = 0.20  # avg_width_pct < this -> ok market
CREDIT_DYNAMIC_WIDTH_PCT_WIDE = 0.35  # avg_width_pct < this -> wide market
CREDIT_DYNAMIC_MID_WEIGHT_TIGHT = 0.85  # Mid weight when market is tight
CREDIT_DYNAMIC_MID_WEIGHT_OK = 0.75  # Mid weight when market is ok
CREDIT_DYNAMIC_MID_WEIGHT_MODERATE = 0.65  # Mid weight when market is wide
CREDIT_DYNAMIC_MID_WEIGHT_VERY_WIDE = 0.55  # Mid weight when market is very wide

# Asymmetric bid/ask thresholds
MAX_SHORT_LEG_BID_ASK_WIDTH = 1.25  # Max absolute spread on short leg
MAX_SHORT_LEG_BID_ASK_WIDTH_PCT = 0.25  # Or max pct of mid on short leg
MAX_LONG_LEG_BID_ASK_WIDTH = 3.00  # Max absolute spread on long leg
MAX_LONG_LEG_BID_ASK_WIDTH_PCT = 0.40  # Or max pct of mid on long leg


# ---------------------------------------------------------------------------
# Put credit spread settings
# ---------------------------------------------------------------------------

PUT_TARGET_DELTA = 0.16  # Target short-put delta (absolute)
PUT_MIN_DELTA = 0.13  # Minimum acceptable short-put delta
PUT_MAX_DELTA = 0.21  # Maximum acceptable short-put delta
PUT_LONG_DELTA = 0.10  # Long-put protection delta


# ---------------------------------------------------------------------------
# Call credit spread settings
# ---------------------------------------------------------------------------

CALL_TARGET_DELTA = 0.16  # Target short-call delta (absolute)
CALL_MIN_DELTA = 0.10  # Minimum acceptable short-call delta
CALL_MAX_DELTA = 0.20  # Maximum acceptable short-call delta
LONG_CALL_DELTA = 0.08  # Long-call protection delta
CALL_MAX_RISK_REWARD_RATIO = 5.0  # Max loss / premium received for calls
CALL_MIN_CREDIT_PER_WIDTH = 0.06  # Lower premium-per-width floor for calls
CALL_MIN_NATURAL_CREDIT_PCT = 0.07  # Slightly looser natural-credit floor for calls

# ---------------------------------------------------------------------------
# Backward-compatible aliases for the current put-spread implementation
# ---------------------------------------------------------------------------

# Keep these aliases while the codebase still assumes a single put strategy.
TARGET_DELTA = PUT_TARGET_DELTA
MIN_DELTA = PUT_MIN_DELTA
MAX_DELTA = PUT_MAX_DELTA
LONG_PUT_DELTA = PUT_LONG_DELTA


# ---------------------------------------------------------------------------
# Ranking settings
# ---------------------------------------------------------------------------

# Ranking engine v2: asymmetric delta scoring, skew integration, soft mode
RANKING_MODE = "soft"  # "soft" or "strict"
ALIGNMENT_SCORE_VERSION = "v1"  # Version tag for the live/offline alignment formula

# Delta preference breakpoints
RANK_DELTA_TARGET = 0.16  # Optimal short-delta anchor
RANK_DELTA_BONUS_FLOOR = 0.13  # At or below this: full OTM bonus applies
RANK_DELTA_PENALTY_START = 0.16  # Above this: penalty begins
RANK_DELTA_PENALTY_STEEP = 0.185  # Above this: penalty rate steepens
RANK_DELTA_HARD_CEILING = 0.19  # Defined for future strict mode

# Delta score magnitude controls
RANK_DELTA_BONUS_MAX = 0.05  # Additive bonus at RANK_DELTA_BONUS_FLOOR
RANK_DELTA_PENALTY_MAX = 0.40  # Total deduction at RANK_DELTA_PENALTY_STEEP

# Component weights (must sum to 1.0)
RANK_WEIGHT_DELTA = 0.38
RANK_WEIGHT_SKEW = 0.20
RANK_WEIGHT_EV = 0.27
RANK_WEIGHT_LIQUIDITY = 0.15

# Skew component sub-weights (must sum to 1.0)
RANK_SKEW_RATIO_WEIGHT = 0.55
RANK_SKEW_DIFF_WEIGHT = 0.45

# Directional adjustment multipliers applied to base score
RANK_ITM_PENALTY_MULTIPLIER = 0.80
RANK_OTM_BONUS_MULTIPLIER = 1.02

# Put ranking profile defaults
PUT_RANK_DELTA_TARGET = RANK_DELTA_TARGET
PUT_RANK_DELTA_BONUS_FLOOR = RANK_DELTA_BONUS_FLOOR
PUT_RANK_DELTA_PENALTY_START = RANK_DELTA_PENALTY_START
PUT_RANK_DELTA_PENALTY_STEEP = RANK_DELTA_PENALTY_STEEP
PUT_RANK_DELTA_HARD_CEILING = RANK_DELTA_HARD_CEILING
PUT_RANK_DELTA_BONUS_MAX = RANK_DELTA_BONUS_MAX
PUT_RANK_DELTA_PENALTY_MAX = RANK_DELTA_PENALTY_MAX
PUT_RANK_WEIGHT_DELTA = RANK_WEIGHT_DELTA
PUT_RANK_WEIGHT_SKEW = RANK_WEIGHT_SKEW
PUT_RANK_WEIGHT_EV = RANK_WEIGHT_EV
PUT_RANK_WEIGHT_LIQUIDITY = RANK_WEIGHT_LIQUIDITY
PUT_RANK_WEIGHT_EXTENSION = 0.0
PUT_RANK_SKEW_RATIO_WEIGHT = RANK_SKEW_RATIO_WEIGHT
PUT_RANK_SKEW_DIFF_WEIGHT = RANK_SKEW_DIFF_WEIGHT
PUT_RANK_ITM_PENALTY_MULTIPLIER = RANK_ITM_PENALTY_MULTIPLIER
PUT_RANK_OTM_BONUS_MULTIPLIER = RANK_OTM_BONUS_MULTIPLIER

# Call ranking profile defaults
CALL_RANK_DELTA_TARGET = CALL_TARGET_DELTA
CALL_RANK_DELTA_BONUS_FLOOR = 0.13
CALL_RANK_DELTA_PENALTY_START = CALL_TARGET_DELTA
CALL_RANK_DELTA_PENALTY_STEEP = 0.19
CALL_RANK_DELTA_HARD_CEILING = 0.22
CALL_RANK_DELTA_BONUS_MAX = 0.03
CALL_RANK_DELTA_PENALTY_MAX = 0.32
CALL_RANK_WEIGHT_DELTA = 0.26
CALL_RANK_WEIGHT_SKEW = 0.14
CALL_RANK_WEIGHT_EV = 0.20
CALL_RANK_WEIGHT_LIQUIDITY = 0.14
CALL_RANK_WEIGHT_EXTENSION = 0.26
CALL_RANK_SKEW_RATIO_WEIGHT = 0.50
CALL_RANK_SKEW_DIFF_WEIGHT = 0.50
CALL_RANK_ITM_PENALTY_MULTIPLIER = 0.86
CALL_RANK_OTM_BONUS_MULTIPLIER = 1.00

# Earnings-event scoring impact
RANK_EARNINGS_POST_EXIT_MULTIPLIER = 0.98
RANK_EARNINGS_PRE_EXIT_MULTIPLIER = 0.92
RANK_EARNINGS_NEAR_TERM_MULTIPLIER = 0.85
RANK_EARNINGS_NEAR_TERM_DAYS = 10


# ---------------------------------------------------------------------------
# Strategy selector settings
# ---------------------------------------------------------------------------

STRATEGY_SELECTOR_MODE = "identify_only"
SELECTOR_VERSION = "v1"
SELECTOR_MARKET_PROXIES = ("SPY", "QQQ")
SELECTOR_BASE_SCORE = 50

# Market-regime thresholds use a 0-100 range-position scale plus decimal distance percentages.
SELECTOR_MARKET_EXTENDED_BULLISH_MIN_RANGE = 92
SELECTOR_MARKET_EXTENDED_BULLISH_MAX_DISTANCE_TO_HIGH_PCT = 0.03
SELECTOR_MARKET_BULLISH_MIN_RANGE = 72
SELECTOR_MARKET_BULLISH_MAX_RANGE = 91
SELECTOR_MARKET_BULLISH_MAX_DISTANCE_TO_HIGH_PCT = 0.12
SELECTOR_MARKET_NEUTRAL_MIN_RANGE = 45
SELECTOR_MARKET_NEUTRAL_MAX_RANGE = 71
SELECTOR_MARKET_WEAK_MIN_RANGE = 25
SELECTOR_MARKET_WEAK_MAX_RANGE = 44
SELECTOR_MARKET_RISK_OFF_MAX_RANGE = 24
SELECTOR_MARKET_RISK_OFF_MAX_DISTANCE_TO_LOW_PCT = 0.05
SELECTOR_MARKET_REGIME_VALUES = {
    "risk_off": 0,
    "weak": 1,
    "neutral": 2,
    "bullish": 3,
    "extended_bullish": 4,
}

# Symbol-extension thresholds use a 0-100 range-position scale.
SELECTOR_SYMBOL_NEAR_HIGH_MIN_RANGE = 92
SELECTOR_SYMBOL_UPPER_RANGE_MIN = 75
SELECTOR_SYMBOL_UPPER_RANGE_MAX = 91
SELECTOR_SYMBOL_MID_RANGE_MIN = 45
SELECTOR_SYMBOL_MID_RANGE_MAX = 74
SELECTOR_SYMBOL_LOWER_RANGE_MIN = 20
SELECTOR_SYMBOL_LOWER_RANGE_MAX = 44
SELECTOR_SYMBOL_NEAR_LOW_MAX_RANGE = 19

PUT_SELECTOR_MARKET_ADJUSTMENTS = {
    "extended_bullish": 12,
    "bullish": 15,
    "neutral": 6,
    "mixed": 0,
    "weak": -10,
    "risk_off": -20,
    "unknown": 0,
}
CALL_SELECTOR_MARKET_ADJUSTMENTS = {
    "extended_bullish": 10,
    "bullish": 6,
    "neutral": 0,
    "mixed": -4,
    "weak": -12,
    "risk_off": -22,
    "unknown": 0,
}
PUT_SELECTOR_EXTENSION_ADJUSTMENTS = {
    "near_high": 0,
    "upper_range": 8,
    "mid_range": 12,
    "lower_range": -8,
    "near_low": -22,
    "unknown": 0,
}
CALL_SELECTOR_EXTENSION_ADJUSTMENTS = {
    "near_high": 18,
    "upper_range": 8,
    "mid_range": -2,
    "lower_range": -14,
    "near_low": -24,
    "unknown": 0,
}

SELECTOR_EARNINGS_IMMINENT_DAYS = 7
SELECTOR_EARNINGS_LATE_CYCLE_MAX_REMAINING_DTE = 21
SELECTOR_EARNINGS_IMMINENT_PENALTY = -25
SELECTOR_EARNINGS_PRE_CYCLE_PENALTY = -18
SELECTOR_EARNINGS_LATE_CYCLE_PENALTY = -6

SELECTOR_PUT_MARGIN = 6
SELECTOR_CALL_MARGIN = 12
SELECTOR_VIABLE_FLOOR = 55
SELECTOR_WEAK_MAX_SCORE = 44
SELECTOR_MARGINAL_MAX_SCORE = 54
SELECTOR_STRONG_MIN_SCORE = 70
SELECTOR_CONFIDENCE_MEDIUM_SPREAD = 12
SELECTOR_CONFIDENCE_HIGH_SPREAD = 25


# ---------------------------------------------------------------------------
# Runtime / persistence / display settings
# ---------------------------------------------------------------------------

# Performance tuning
CHAIN_FETCH_DELAY = 0.2  # Seconds to wait between chain fetches
OPTION_QUOTE_BATCH_SIZE = 400  # Max option symbols per quote batch call
EQUITY_QUOTE_BATCH_SIZE = 200  # Max equity symbols per quote batch call
OPTION_QUOTE_EXPECTED_MOVE_MULTIPLIER = 1.75  # Quote through this many EMs OTM
OPTION_QUOTE_ATM_BUFFER_EXPECTED_MOVE = 0.25  # Quote this many EMs through ATM
PUT_QUOTE_MIN_MONEYNESS = 0.60  # Safety rail: lowest put strike as pct of spot
PUT_QUOTE_MAX_MONEYNESS = 1.05  # Safety rail: highest put strike as pct of spot
CALL_QUOTE_MIN_MONEYNESS = 0.95  # Safety rail: lowest call strike as pct of spot
CALL_QUOTE_MAX_MONEYNESS = 1.40  # Safety rail: highest call strike as pct of spot

# Exit strategy (for reference/future tracking)
TARGET_EXIT_DTE = 21  # Target days to exit
TARGET_PROFIT_PCT = 50  # Target profit percentage

# Sync positions exit signals
EXIT_HARD_STOP_MULTIPLE = 2.0  # Close if debit >= multiple * credit received
EXIT_STRUCTURAL_MULTIPLE = 1.5  # Alert if short strike breached and debit elevated
EXIT_GAMMA_RISK_DTE = 30  # Alert if short strike breached and DTE <= this
LOSS_CLOSE_REVIEW_PCT = 95  # Review closing if confirmed loss >= this pct of credit
ORDER_HISTORY_LOOKBACK_DAYS = 14  # Recent order window for reconciliation
ORDER_HISTORY_MAX_PAGES = 2  # Default page cap for recent order retrieval

# Display / persistence
MAX_SCREENING_RESULTS = 400  # Max stocks to show after IV screening
MAX_FINAL_RESULTS = 30  # Max trade opportunities to display
AUTO_SAVE_CSV = True  # Automatically save results to CSV file
REVIEW_QUEUE_DIR = "opportunities_review"  # Separate folder for manual decision logs
AUTO_SAVE_REVIEW_QUEUE = True  # Save post-run review queue for acceptance capture
REVIEW_QUEUE_REQUIRE_MARKET_OPEN = (
    True  # Skip review queue when results are only indicative
)
ALLOWED_REVIEW_DECISIONS = (
    "accepted",
    "skipped",
    "submitted_not_filled",
    "deferred",
)
ALLOWED_REVIEW_DECISION_REASONS = (
    "leveraged_etf",
    "unfamiliar_symbol",
    "sector_theme_discomfort",
    "capital_constraint",
    "too_many_similar_positions",
    "fill_concern",
    "earnings_event_concern",
    "delta_concern",
    "manual_risk_override",
    "extended_too_fast",
    "other",
)

# Strategy version labeling for analysis/backtesting continuity
STRATEGY_VERSION = "v2_dynamic"
LEGACY_STRATEGY_VERSION = "v1_conservative"
STRATEGY_VERSION_CUTOFF_DATE = "2026-04-09"


# ---------------------------------------------------------------------------
# Cache settings
# ---------------------------------------------------------------------------

CACHE_DIR = "cache"  # Relative to project root
CACHE_TTL_SESSION = 20 * 3600  # 20 hours for session token
CACHE_TTL_WATCHLIST = 24 * 3600  # 24 hours for watchlist symbols
CACHE_TTL_EXPIRATIONS = 48 * 3600  # 48 hours for expirations
CACHE_TTL_OPTION_CHAIN = 24 * 3600  # 24 hours for chains by expiration
CACHE_TTL_MARKET_METRICS = 30 * 60  # 30 minutes for market metrics
CACHE_TTL_QUOTES = 5 * 60  # 5 minutes for equity quotes
CACHE_TTL_OPTION_QUOTES = 5 * 60  # 5 minutes for option quotes


# ---------------------------------------------------------------------------
# Watchlists / account
# ---------------------------------------------------------------------------

WATCHLISTS = {
    "sp500": "S&P 500",
    "etfs": "Liquid ETFs",
    "nasdaq100": "NASDAQ 100",
    "high_options_volume": "High Options Volume",
    "tasty_ivr": "tasty IVR",
}

# Strategic symbols that should always be analyzed, even if they do not
# naturally make it through the broader IV-based funnel on a given day.
ALWAYS_REVIEW_SYMBOLS = ("SPY", "QQQ", "IWM")


# Account configuration
TASTYTRADE_ACCOUNT_NUMBER = "5WU44666"  # Update with your account number
