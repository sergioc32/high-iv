"""
Display utilities for terminal output
"""

from tabulate import tabulate
from typing import List, Dict
import pandas as pd


def display_opportunities(opportunities: List[Dict]):
    """
    Display trade opportunities in a formatted table
    """
    if not opportunities:
        print("\n✗ No trade opportunities found matching criteria\n")
        return

    # Convert to DataFrame for easier display
    df = pd.DataFrame(opportunities)

    # Select and order columns
    display_cols = [
        "symbol",
        "stock_price",
        "short_strike",
        "long_strike",
        "width",
        "premium",
        "max_loss",
        "risk_reward_ratio",
        "dte",
        "earnings_within_dte",
    ]

    df = df[display_cols]

    # Rename columns for display
    df.columns = [
        "Symbol",
        "Stock $",
        "Short Strike",
        "Long Strike",
        "Width",
        "Premium",
        "Max Loss",
        "R/R Ratio",
        "DTE",
        "Earnings",
    ]

    # Round numeric columns
    df["Stock $"] = df["Stock $"].round(2)
    df["Premium"] = df["Premium"].round(2)
    df["Max Loss"] = df["Max Loss"].round(2)
    df["R/R Ratio"] = df["R/R Ratio"].round(2)
    df["Earnings"] = df["Earnings"].fillna("")

    print(f"\n{'=' * 100}")
    print(f"Top {len(df)} Put Spread Opportunities")
    print(f"{'=' * 100}")
    print(tabulate(df, headers="keys", tablefmt="grid", showindex=False))
    print(f"{'=' * 100}\n")


def display_trade_details(opportunity: Dict):
    """
    Display detailed information for a single trade opportunity
    """
    print(f"\n{'=' * 60}")
    print(f"Trade Details: {opportunity['symbol']}")
    print(f"{'=' * 60}")
    print(f"Stock Price:        ${opportunity['stock_price']:.2f}")
    print(
        f"Expiration:         {opportunity['expiration_date']} ({opportunity['dte']} DTE)"
    )
    print("\nSpread Structure:")
    print(
        f"  Sell Put:         ${opportunity['short_strike']:.2f} (Delta: {opportunity['short_delta']:.3f})"
    )
    print(f"  Buy Put:          ${opportunity['long_strike']:.2f}")
    print(f"  Width:            ${opportunity['width']:.2f}")
    print("\nP&L Metrics:")
    print(f"  Premium Received: ${opportunity['premium']:.2f}")
    print(f"  Max Profit:       ${opportunity['max_profit']:.2f}")
    print(f"  Max Loss:         ${opportunity['max_loss']:.2f}")
    print(f"  Risk/Reward:      {opportunity['risk_reward_ratio']:.2f}:1")
    print("\nPricing:")
    print(
        f"  Short Put Bid/Ask: ${opportunity['short_bid']:.2f} / ${opportunity['short_ask']:.2f}"
    )
    print(
        f"  Long Put Bid/Ask:  ${opportunity['long_bid']:.2f} / ${opportunity['long_ask']:.2f}"
    )
    print(f"{'=' * 60}\n")


def display_summary(
    total_screened: int,
    high_iv_count: int,
    opportunities_count: int,
    execution_time: float,
):
    """
    Display summary statistics
    """
    print(f"\n{'=' * 60}")
    print("Screening Summary")
    print(f"{'=' * 60}")
    print(f"Total symbols screened:     {total_screened}")
    print(f"High IV candidates:         {high_iv_count}")
    print(f"Valid trade opportunities:  {opportunities_count}")
    print(f"Execution time:             {execution_time:.2f} seconds")
    print(f"{'=' * 60}\n")


def print_header():
    """
    Print application header
    """
    print("\n" + "=" * 60)
    print(" " * 15 + "OPTIONS PUT SPREAD SCREENER")
    print("=" * 60 + "\n")


def print_progress(message: str):
    """
    Print progress indicator
    """
    print(f"⟳ {message}...")
