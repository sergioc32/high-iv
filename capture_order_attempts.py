"""Export filled and expired option-spread order attempts from Tastytrade."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from api.tastytrade import TastytradeAPI
from services.order_attempt_service import OrderAttemptService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture filled and expired option-spread order attempts."
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=getattr(config, "ORDER_HISTORY_LOOKBACK_DAYS", 14),
        help="How many days of account order history to inspect.",
    )
    parser.add_argument(
        "--output",
        default="execution/order_attempts.csv",
        help="CSV output path for captured order attempts.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=getattr(config, "ORDER_HISTORY_MAX_PAGES", 5),
        help="Maximum order-history pages to fetch.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv()

    api = TastytradeAPI()
    if not api.authenticate():
        print("X Authentication failed")
        return

    output_path = OrderAttemptService(Path(args.output)).capture_order_attempts(
        api,
        lookback_days=args.lookback_days,
        statuses=["Filled", "Expired"],
        max_pages=args.max_pages,
    )
    print(f"OK Saved order attempts to {output_path}")


if __name__ == "__main__":
    main()
