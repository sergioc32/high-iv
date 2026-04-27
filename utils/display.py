"""
Display utilities for terminal output
"""

import pandas as pd
from tabulate import tabulate


def _round_numeric_column(
    df: pd.DataFrame, column_name: str, decimals: int, *, percent: bool = False
) -> None:
    """Round optional numeric columns safely for display."""
    if column_name not in df.columns:
        return

    series = pd.to_numeric(df[column_name], errors="coerce")
    if percent:
        series = series * 100
    df[column_name] = series.round(decimals).fillna("")


def display_opportunities(opportunities: list[dict]):
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
        "premium",
        "max_loss",
        "risk_reward_ratio",
        "strategy_alignment_score",
        "credit_expected",
        "mid_capture_pct",
        "fill_quality_score",
        "distance_to_52w_high_pct",
        "range_position_52w",
        "skew_ratio",
        "ev_score_chosen",
        "earnings_within_dte",
        "dte",
    ]

    # Only keep columns that actually exist in the data
    display_cols = [c for c in display_cols if c in df.columns]
    df = df[display_cols]

    # Rename columns for display
    col_labels = {
        "symbol": "Symbol",
        "stock_price": "Stock $",
        "short_strike": "Short Strike",
        "long_strike": "Long Strike",
        "premium": "Premium",
        "credit_expected": "Exp Credit",
        "mid_capture_pct": "Fill %",
        "fill_quality_score": "Fill Score",
        "distance_to_52w_high_pct": "To 52W Hi %",
        "range_position_52w": "52W Pos %",
        "max_loss": "Max Loss",
        "risk_reward_ratio": "R/R Ratio",
        "ev_score_chosen": "EV Score",
        "strategy_alignment_score": "Align Score",
        "dte": "DTE",
        "earnings_within_dte": "Earnings",
        "skew_ratio": "IV Skew Ratio",
    }
    df.columns = [col_labels[c] for c in display_cols]

    # Round numeric columns
    _round_numeric_column(df, "Stock $", 2)
    _round_numeric_column(df, "Premium", 2)
    _round_numeric_column(df, "Exp Credit", 2)
    _round_numeric_column(df, "Fill %", 1, percent=True)
    _round_numeric_column(df, "Fill Score", 2)
    _round_numeric_column(df, "To 52W Hi %", 1, percent=True)
    _round_numeric_column(df, "52W Pos %", 1, percent=True)
    _round_numeric_column(df, "Max Loss", 2)
    _round_numeric_column(df, "R/R Ratio", 2)
    _round_numeric_column(df, "EV Score", 4)
    _round_numeric_column(df, "Align Score", 1)
    _round_numeric_column(df, "IV Skew Ratio", 3)
    if "Earnings" in df.columns:
        df["Earnings"] = df["Earnings"].fillna("")

    print(f"\n{'=' * 100}")
    print(f"Top {len(df)} Put Spread Opportunities")
    print(f"{'=' * 100}")
    print(tabulate(df, headers="keys", tablefmt="grid", showindex=False))
    print(f"{'=' * 100}\n")


def display_trade_details(opportunity: dict):
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
    print(
        f"Current time:               {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
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
