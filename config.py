"""
Configuration file for options screener
"""

# Screening criteria
IV_RANK_THRESHOLD = 45  # Minimum IV Rank %
MIN_STOCK_PRICE = (
    25.00  # Minimum stock price ($25+ filters penny stocks and sub-$25 junk)
)
MIN_LIQUIDITY_VOLUME = 2_000_000  # Minimum daily volume if available
MIN_UNDERLYING_VOLUME = 2_000_000  # Minimum underlying daily share volume
ENABLE_OI_FILTER = False  # Toggle to enable/disable open interest filtering
MIN_MARKET_CAP = 1_000_000_000  # Minimum market cap in USD ($1B+ filters penny stocks)
MIN_OPTION_OPEN_INTEREST_PER_LEG = 100  # Legacy single threshold (used as fallback)
MIN_OPTION_OPEN_INTEREST_SHORT_LEG = 25  # Minimum OI on short leg
MIN_OPTION_OPEN_INTEREST_LONG_LEG = 5  # Minimum OI on long leg
# Options criteria
TARGET_DTE = 45  # Target days to expiration
TARGET_DELTA = 0.16  # Target delta for short put (1 standard deviation)
MIN_DELTA = 0.13  # Minimum acceptable delta for short put
MAX_DELTA = 0.21  # Maximum acceptable delta for short put
LONG_PUT_DELTA = 0.10  # Delta for long put (protection)

# Skew optimization
SKEW_WINDOW_OTM = 2  # Check N OTM (lower-delta/lower-strike) shifts from anchor
SKEW_WINDOW_ITM = 1  # Check N ITM (higher-delta/higher-strike) shifts from anchor
MIN_SCORE_IMPROVEMENT_PCT = 5  # Require 5% higher skew score to switch from anchor

# Liquidity and fillability checks
MIN_CREDIT_PER_WIDTH = (
    0.08  # $8 per $1 width (3-wide=$24, 5-wide=$40) whitelist=0.08, general=0.12-0.15
)
# Asymmetric bid/ask thresholds - short leg stricter, long leg looser
MAX_SHORT_LEG_BID_ASK_WIDTH = (
    1.25  # Max absolute spread on short leg whitelist=1.50 max, general=1.25 max
)
MAX_SHORT_LEG_BID_ASK_WIDTH_PCT = (
    0.30  # OR max 30% of mid price on short leg whitelist=30%, general=30%
)
MAX_LONG_LEG_BID_ASK_WIDTH = 3.00  # Max absolute spread on long leg (looser) whitelist=5.00 max, general=3.00 max
MAX_LONG_LEG_BID_ASK_WIDTH_PCT = (
    0.40  # OR max 50% of mid price (looser) on long leg whitelist=60%, general=40%
)

# Performance tuning
CHAIN_FETCH_DELAY = 0.2  # Seconds to wait between chain fetches (0 to disable)
OPTION_QUOTE_BATCH_SIZE = 400  # Max option symbols per quote batch call
EQUITY_QUOTE_BATCH_SIZE = 200  # Max equity symbols per quote batch call

# Spread configuration
PREFERRED_SPREAD_WIDTH = 3  # Preferred spread width in dollars
FALLBACK_SPREAD_WIDTH = 5  # Fallback if $3 strikes not available
MAX_STRIKE_INCREMENT = 10  # Max strike increment to accept when adapting widths
MAX_RISK_REWARD_RATIO = 4.5  # Max loss / Premium received (prefer 4.0 or lower)

# Exit strategy (for reference/future tracking)
TARGET_EXIT_DTE = 21  # Target days to exit
TARGET_PROFIT_PCT = 50  # Target profit percentage

# Sync positions exit signals
EXIT_HARD_STOP_MULTIPLE = 2.0  # Close if debit >= multiple * credit received
EXIT_STRUCTURAL_MULTIPLE = (
    1.5  # Alert if short strike breached and debit >= multiple * credit
)
EXIT_GAMMA_RISK_DTE = 30  # Alert if short strike breached and DTE <= this

# Display settings
MAX_SCREENING_RESULTS = 100  # Max stocks to show after IV screening
MAX_FINAL_RESULTS = 25  # Max trade opportunities to display
AUTO_SAVE_CSV = True  # Automatically save results to CSV file

# DTE tolerance for finding expirations
DTE_TOLERANCE = 14  # Will accept expirations within +/- 14 days of target

# Manual exclusions (useful for temporarily skipping symbols under restrictions)
EXCLUDE_SYMBOLS = []

# Caching configuration
CACHE_DIR = "cache"  # Relative to project root
# TTLs in seconds
CACHE_TTL_SESSION = 20 * 3600  # 20 hours for session token
CACHE_TTL_WATCHLIST = 24 * 3600  # 24 hours for watchlist symbols
CACHE_TTL_EXPIRATIONS = 48 * 3600  # 48 hours for expirations
CACHE_TTL_OPTION_CHAIN = 24 * 3600  # 24 hours for chains by expiration
CACHE_TTL_MARKET_METRICS = 30 * 60  # 30 minutes for market metrics
CACHE_TTL_QUOTES = 5 * 60  # 5 minutes for equity quotes
CACHE_TTL_OPTION_QUOTES = 5 * 60  # 5 minutes for option quotes

# Watchlists to screen
WATCHLISTS = {
    "sp500": "S&P 500",  # Tastytrade watchlist name for S&P 500
    "etfs": "Liquid ETFs",  # Major liquid ETFs
    "nasdaq100": "NASDAQ 100",  # Tastytrade watchlist name for Nasdaq 100
    "high_options_volume": "High Options Volume",  # Tastytrade watchlist for high IV ETFs
    "tasty_ivr": "tasty IVR",  # Tastytrade watchlist for high IV stocks
}

# Fallback list if the Liquid ETFs watchlist is unavailable
ETF_FALLBACK = ["SPY", "QQQ", "IWM", "DIA", "XLF", "XLE", "XLK", "XLV"]

# ---------------------------------------------------------------------------
# Ranking engine v2 — asymmetric delta scoring, skew integration, soft mode
# Option B "balanced/gradual" calibration — adjust these to retune without
# touching engine code.
# ---------------------------------------------------------------------------
RANKING_MODE = (
    "soft"  # "soft": ceiling defined but not enforced; "strict": hard ceiling
)

# Delta preference breakpoints
RANK_DELTA_TARGET = 0.16  # Optimal short-delta anchor
RANK_DELTA_BONUS_FLOOR = 0.13  # At or below this: full OTM bonus applies
RANK_DELTA_PENALTY_START = 0.16  # Above this: penalty begins (same as TARGET)
RANK_DELTA_PENALTY_STEEP = 0.185  # Above this: penalty rate steepens significantly
RANK_DELTA_HARD_CEILING = 0.19  # Defined for future strict mode; ignored in soft mode

# Delta score magnitude controls
RANK_DELTA_BONUS_MAX = (
    0.05  # Additive bonus at RANK_DELTA_BONUS_FLOOR (score up to 1.05)
)
RANK_DELTA_PENALTY_MAX = 0.40  # Total deduction from 1.0 at RANK_DELTA_PENALTY_STEEP

# Component weights (must sum to 1.0)
RANK_WEIGHT_DELTA = 0.38
RANK_WEIGHT_SKEW = 0.20
RANK_WEIGHT_EV = 0.27
RANK_WEIGHT_LIQUIDITY = 0.15

# Skew component sub-weights (must sum to 1.0)
RANK_SKEW_RATIO_WEIGHT = 0.55  # Weight for skew_ratio percentile within skew component
RANK_SKEW_DIFF_WEIGHT = 0.45  # Weight for skew_diff percentile within skew component

# Directional adjustment multipliers applied to base score
RANK_ITM_PENALTY_MULTIPLIER = 0.80  # Applied when delta > RANK_DELTA_PENALTY_STEEP
RANK_OTM_BONUS_MULTIPLIER = 1.02  # Applied when delta < RANK_DELTA_TARGET

# Earnings-event scoring impact
# Applied as a score multiplier when earnings date is present in earnings_within_dte.
RANK_EARNINGS_POST_EXIT_MULTIPLIER = (
    0.98  # Minor penalty when earnings is likely after planned exit
)
RANK_EARNINGS_PRE_EXIT_MULTIPLIER = (
    0.92  # Moderate penalty when earnings is likely before planned exit
)
RANK_EARNINGS_NEAR_TERM_MULTIPLIER = (
    0.85  # Stronger penalty when earnings is very near term
)
RANK_EARNINGS_NEAR_TERM_DAYS = 10  # Near-term threshold in calendar days

# Account configuration
TASTYTRADE_ACCOUNT_NUMBER = "5WU44666"  # Update with your account number
