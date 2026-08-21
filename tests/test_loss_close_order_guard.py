import unittest

from main import _find_working_close_order, _is_active_close_order


class LossCloseOrderGuardTests(unittest.TestCase):
    def test_finds_working_close_order_for_same_spread_legs(self):
        row = {
            "short_option_symbol": "AAOI  261002P00110000",
            "long_option_symbol": "AAOI  261002P00100000",
        }
        order = {
            "id": 123,
            "status": "Live",
            "legs": [
                {
                    "symbol": "AAOI  261002P00110000",
                    "action": "Buy to Close",
                },
                {
                    "symbol": "AAOI  261002P00100000",
                    "action": "Sell to Close",
                },
            ],
        }

        self.assertTrue(_is_active_close_order(order))
        self.assertIs(order, _find_working_close_order(row, [order]))

    def test_ignores_terminal_close_orders(self):
        row = {
            "short_option_symbol": "AAOI  261002P00110000",
            "long_option_symbol": "AAOI  261002P00100000",
        }
        order = {
            "id": 123,
            "status": "Filled",
            "legs": [
                {
                    "symbol": "AAOI  261002P00110000",
                    "action": "Buy to Close",
                },
                {
                    "symbol": "AAOI  261002P00100000",
                    "action": "Sell to Close",
                },
            ],
        }

        self.assertFalse(_is_active_close_order(order))
        self.assertIsNone(_find_working_close_order(row, [order]))


if __name__ == "__main__":
    unittest.main()
