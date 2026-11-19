import unittest

from money import split


class Hidden(unittest.TestCase):
    def test_sum_exact(self):
        for total in (0, 1, 999, 1000, 1001, 12345):
            for n in (1, 2, 3, 7):
                shares = split(total, n)
                self.assertEqual(sum(shares), total, (total, n))
                self.assertEqual(len(shares), n)
                self.assertLessEqual(max(shares) - min(shares), 1)

    def test_extra_goes_first(self):
        self.assertEqual(split(1000, 3), [334, 333, 333])
        self.assertEqual(split(1001, 3), [334, 334, 333])

    def test_invalid(self):
        with self.assertRaises(ValueError):
            split(100, 0)
        with self.assertRaises(ValueError):
            split(-1, 2)
