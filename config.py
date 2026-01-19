"""
Configuration file for options screener
"""

# Screening criteria
IV_RANK_THRESHOLD = 50  # Minimum IV Rank %
MIN_LIQUIDITY_VOLUME = 1000000  # Minimum daily volume if available

# Options criteria
TARGET_DTE = 45  # Target days to expiration
TARGET_DELTA = 0.16  # Target delta for short put (1 standard deviation)
LONG_PUT_DELTA = 0.10  # Delta for long put (protection)

# Spread configuration
PREFERRED_SPREAD_WIDTH = 3  # Preferred spread width in dollars
FALLBACK_SPREAD_WIDTH = 5  # Fallback if $3 strikes not available
MAX_STRIKE_INCREMENT = 10  # Max strike increment to accept when adapting widths
MAX_RISK_REWARD_RATIO = 5.0  # Max loss / Premium received (prefer 4.0 or lower)

# Exit strategy (for reference/future tracking)
TARGET_EXIT_DTE = 21  # Target days to exit
TARGET_PROFIT_PCT = 50  # Target profit percentage

# Display settings
MAX_SCREENING_RESULTS = 75  # Max stocks to show after IV screening
MAX_FINAL_RESULTS = 25  # Max trade opportunities to display
AUTO_SAVE_CSV = True  # Automatically save results to CSV file

# DTE tolerance for finding expirations
DTE_TOLERANCE = 7  # Will accept expirations within +/- 7 days of target

# Manual exclusions (useful for temporarily skipping symbols under restrictions)
EXCLUDE_SYMBOLS = []

# Caching configuration
CACHE_DIR = "cache"  # Relative to project root
# TTLs in seconds
CACHE_TTL_SESSION = 20 * 3600         # 20 hours for session token
CACHE_TTL_WATCHLIST = 24 * 3600       # 24 hours for watchlist symbols
CACHE_TTL_EXPIRATIONS = 48 * 3600     # 48 hours for expirations
CACHE_TTL_OPTION_CHAIN = 24 * 3600    # 24 hours for chains by expiration
CACHE_TTL_MARKET_METRICS = 30 * 60    # 30 minutes for market metrics
CACHE_TTL_QUOTES = 5 * 60             # 5 minutes for equity quotes
CACHE_TTL_OPTION_QUOTES = 5 * 60      # 5 minutes for option quotes

# Watchlists to screen
WATCHLISTS = {
    'sp500': 'S&P 500',  # Tastytrade watchlist name for S&P 500
    'etfs': 'Liquid ETFs'  # Major liquid ETFs
}

# Fallback list if the Liquid ETFs watchlist is unavailable
ETF_FALLBACK = ['SPY', 'QQQ', 'IWM', 'DIA', 'XLF', 'XLE', 'XLK', 'XLV']
