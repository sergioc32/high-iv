"""
Market hours detection utility
"""

from datetime import datetime
import pytz


def is_market_open() -> bool:
    """
    Check if US stock market is currently open.
    Market hours: 9:30 AM - 4:00 PM Eastern Time, weekdays only.
    Returns True if market is open, False otherwise.
    """
    eastern = pytz.timezone("US/Eastern")
    now_et = datetime.now(eastern)

    # Check if weekend
    if now_et.weekday() >= 5:  # Saturday=5, Sunday=6
        return False

    # Check if within market hours (9:30 AM - 4:00 PM ET)
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)

    return market_open <= now_et < market_close


def get_market_status_display() -> str:
    """
    Get human-readable market status for display.
    Returns 'OPEN' or 'CLOSED'.
    """
    return "OPEN" if is_market_open() else "CLOSED"
