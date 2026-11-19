import unittest

from pages import page_count, paginate


class Hidden(unittest.TestCase):
    def test_last_partial_page(self):
        self.assertEqual(paginate(list(range(11)), 3, 5), [10])

    def test_exact_pages(self):
        self.assertEqual(paginate(list(range(10)), 2, 5), [5, 6, 7, 8, 9])
        self.assertEqual(paginate(list(range(10)), 3, 5), [])

    def test_page_count_rounds_up(self):
        self.assertEqual(page_count(11, 5), 3)
        self.assertEqual(page_count(10, 5), 2)
        self.assertEqual(page_count(0, 5), 0)

    def test_invalid(self):
        for page, size in ((0, 5), (1, 0), (-1, 5)):
            with self.assertRaises(ValueError):
                paginate([1, 2, 3], page, size)

    def test_beyond_end(self):
        self.assertEqual(paginate([1, 2, 3], 9, 2), [])

    def test_first_page_still_works(self):
        self.assertEqual(paginate(list(range(10)), 1, 5), [0, 1, 2, 3, 4])
