import ast
import pathlib
import unittest

from shipping import shipping_cost

CASES = [("local", 0.5, False, 500), ("local", 1, True, 1000), ("local", 3, False, 900), ("local", 7.5, True, 2550),
         ("national", 1, False, 800), ("national", 5, True, 2800), ("national", 6.2, False, 1700),
         ("international", 0.2, False, 2500), ("international", 5, False, 4000), ("international", 10, False, 7500)]


class Hidden(unittest.TestCase):
    def test_behavior_unchanged(self):
        for region, w, ex, want in CASES:
            self.assertEqual(shipping_cost(region, w, ex), want, (region, w, ex))

    def test_errors_unchanged(self):
        with self.assertRaises(ValueError):
            shipping_cost("local", 0)
        with self.assertRaises(ValueError):
            shipping_cost("international", 2, True)
        with self.assertRaises(KeyError):
            shipping_cost("mars", 1)

    def test_no_long_chain(self):
        src = pathlib.Path("shipping.py").read_text(encoding="utf-8")
        ifs = sum(isinstance(n, ast.If) for n in ast.walk(ast.parse(src)))
        self.assertLessEqual(ifs, 5, "refactor should remove the duplicated if/elif branches")
