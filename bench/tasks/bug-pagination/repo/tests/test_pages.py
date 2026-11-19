import unittest

from pages import paginate


class Visible(unittest.TestCase):
    def test_first_page(self):
        self.assertEqual(paginate(list(range(10)), 1, 5), [0, 1, 2, 3, 4])
