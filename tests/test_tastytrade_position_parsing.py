import unittest

from api.tastytrade import TastytradeAPI


class TastytradePositionParsingTests(unittest.TestCase):
    def test_parse_option_spreads_includes_call_credit_spreads(self):
        api = TastytradeAPI()
        positions = [
            {
                "instrument-type": "Equity Option",
                "underlying-symbol": "IWM",
                "expires-at": "2026-09-18T21:00:00.000+00:00",
                "quantity-direction": "Short",
                "quantity": "1",
                "symbol": "IWM   260918C00225000",
                "average-open-price": "1.25",
                "close-price": "0.95",
                "created-at": "2026-08-07T14:30:00+00:00",
            },
            {
                "instrument-type": "Equity Option",
                "underlying-symbol": "IWM",
                "expires-at": "2026-09-18T21:00:00.000+00:00",
                "quantity-direction": "Long",
                "quantity": "1",
                "symbol": "IWM   260918C00230000",
                "average-open-price": "0.55",
                "close-price": "0.35",
                "created-at": "2026-08-07T14:30:00+00:00",
            },
        ]

        spreads = api.parse_option_spreads(positions)

        self.assertEqual(1, len(spreads))
        spread = spreads[0]
        self.assertEqual("call_credit_spread", spread["strategy_id"])
        self.assertEqual("call", spread["option_side"])
        self.assertEqual("bearish", spread["directional_bias"])
        self.assertEqual("short_call", spread["short_leg_type"])
        self.assertEqual("long_call", spread["long_leg_type"])
        self.assertEqual(225.0, spread["short_strike"])
        self.assertEqual(230.0, spread["long_strike"])
        self.assertEqual(5.0, spread["width"])
        self.assertEqual(70.0, spread["entry_credit"])

    def test_parse_option_spreads_groups_puts_and_calls_separately(self):
        api = TastytradeAPI()
        positions = [
            {
                "instrument-type": "Equity Option",
                "underlying-symbol": "XYZ",
                "expires-at": "2026-09-18T21:00:00.000+00:00",
                "quantity-direction": "Short",
                "quantity": "1",
                "symbol": "XYZ   260918P00095000",
                "average-open-price": "1.00",
                "close-price": "0.60",
                "created-at": "2026-08-07T14:30:00+00:00",
            },
            {
                "instrument-type": "Equity Option",
                "underlying-symbol": "XYZ",
                "expires-at": "2026-09-18T21:00:00.000+00:00",
                "quantity-direction": "Long",
                "quantity": "1",
                "symbol": "XYZ   260918P00090000",
                "average-open-price": "0.40",
                "close-price": "0.20",
                "created-at": "2026-08-07T14:30:00+00:00",
            },
            {
                "instrument-type": "Equity Option",
                "underlying-symbol": "XYZ",
                "expires-at": "2026-09-18T21:00:00.000+00:00",
                "quantity-direction": "Short",
                "quantity": "1",
                "symbol": "XYZ   260918C00110000",
                "average-open-price": "0.90",
                "close-price": "0.70",
                "created-at": "2026-08-07T14:30:00+00:00",
            },
            {
                "instrument-type": "Equity Option",
                "underlying-symbol": "XYZ",
                "expires-at": "2026-09-18T21:00:00.000+00:00",
                "quantity-direction": "Long",
                "quantity": "1",
                "symbol": "XYZ   260918C00115000",
                "average-open-price": "0.30",
                "close-price": "0.20",
                "created-at": "2026-08-07T14:30:00+00:00",
            },
        ]

        spreads = api.parse_option_spreads(positions)

        self.assertEqual(
            ["call_credit_spread", "put_credit_spread"],
            sorted(spread["strategy_id"] for spread in spreads),
        )

    def test_build_close_vertical_order_payload(self):
        api = TastytradeAPI()

        payload = api.build_close_vertical_order(
            short_option_symbol="XYZ   260918P00095000",
            long_option_symbol="XYZ   260918P00090000",
            limit_debit=1.956,
        )

        self.assertEqual("Day", payload["time-in-force"])
        self.assertEqual("Limit", payload["order-type"])
        self.assertEqual(1.96, payload["price"])
        self.assertEqual("Debit", payload["price-effect"])
        self.assertEqual(
            {
                "instrument-type": "Equity Option",
                "symbol": "XYZ   260918P00095000",
                "quantity": 1,
                "action": "Buy to Close",
            },
            payload["legs"][0],
        )
        self.assertEqual(
            {
                "instrument-type": "Equity Option",
                "symbol": "XYZ   260918P00090000",
                "quantity": 1,
                "action": "Sell to Close",
            },
            payload["legs"][1],
        )


if __name__ == "__main__":
    unittest.main()
