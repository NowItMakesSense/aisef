import unittest

from shipping import shipping_cost


class Visible(unittest.TestCase):
    def test_local_small(self):
        self.assertEqual(shipping_cost("local", 1), 500)
