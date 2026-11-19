import unittest

from textutil import slugify


class Hidden(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_accents(self):
        self.assertEqual(slugify("Ação de Graças"), "acao-de-gracas")

    def test_runs_and_edges(self):
        self.assertEqual(slugify("  --Hello,,,  World!! "), "hello-world")

    def test_empty(self):
        self.assertEqual(slugify(""), "untitled")
        self.assertEqual(slugify("!!!"), "untitled")

    def test_cut_on_word(self):
        self.assertEqual(slugify("alpha beta gamma", max_len=12), "alpha-beta")

    def test_long_word(self):
        self.assertEqual(slugify("abcdefghij", max_len=4), "abcd")

    def test_default_len(self):
        s = slugify(" ".join(["word"] * 40))
        self.assertLessEqual(len(s), 60)
        self.assertFalse(s.endswith("-"))
