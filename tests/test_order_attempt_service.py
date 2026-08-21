import csv
import tempfile
import unittest
from pathlib import Path

from services.order_attempt_service import OrderAttemptService


class FakeOrderAPI:
    def __init__(self, orders):
        self.orders = orders
        self.calls = []

    def get_account_orders(self, **kwargs):
        self.calls.append(kwargs)
        return self.orders


class OrderAttemptServiceTests(unittest.TestCase):
    def test_capture_order_attempts_writes_filled_and_expired_spreads(self):
        orders = [
            {
                "id": 1,
                "status": "Expired",
                "underlying-symbol": "IWM",
                "price": "0.72",
                "price-effect": "Credit",
                "time-in-force": "Day",
                "received-at": "2026-08-07T14:00:00+00:00",
                "terminal-at": "2026-08-07T20:00:00+00:00",
                "legs": [
                    {
                        "action": "Sell to Open",
                        "symbol": "IWM   260918C00225000",
                        "quantity": "1",
                        "fills": [],
                    },
                    {
                        "action": "Buy to Open",
                        "symbol": "IWM   260918C00230000",
                        "quantity": "1",
                        "fills": [],
                    },
                ],
            },
            {
                "id": 2,
                "status": "Filled",
                "underlying-symbol": "XYZ",
                "price": "0.60",
                "price-effect": "Credit",
                "time-in-force": "Day",
                "received-at": "2026-08-07T14:10:00+00:00",
                "terminal-at": "2026-08-07T14:12:00+00:00",
                "legs": [
                    {
                        "action": "Sell to Open",
                        "symbol": "XYZ   260918P00095000",
                        "quantity": "1",
                        "fills": [
                            {
                                "filled-at": "2026-08-07T14:12:00+00:00",
                                "fill-price": "1.00",
                                "quantity": "1",
                            }
                        ],
                    },
                    {
                        "action": "Buy to Open",
                        "symbol": "XYZ   260918P00090000",
                        "quantity": "1",
                        "fills": [
                            {
                                "filled-at": "2026-08-07T14:12:00+00:00",
                                "fill-price": "0.40",
                                "quantity": "1",
                            }
                        ],
                    },
                ],
            },
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "order_attempts.csv"
            api = FakeOrderAPI(orders)
            service = OrderAttemptService(output_path)

            service.capture_order_attempts(api, lookback_days=7, max_pages=2)

            self.assertEqual(["Filled", "Expired"], api.calls[0]["statuses"])
            with output_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(2, len(rows))
            self.assertEqual("expired_unfilled", rows[0]["attempt_outcome"])
            self.assertEqual("call_credit_spread", rows[0]["strategy_id"])
            self.assertEqual("225.0000", rows[0]["short_strike"])
            self.assertEqual("230.0000", rows[0]["long_strike"])
            self.assertEqual("filled", rows[1]["attempt_outcome"])
            self.assertEqual("put_credit_spread", rows[1]["strategy_id"])


if __name__ == "__main__":
    unittest.main()
