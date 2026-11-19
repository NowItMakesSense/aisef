import unittest

from reset import InvalidToken, ResetTokens


class Hidden(unittest.TestCase):
    def setUp(self):
        self.store = {}
        self.rt = ResetTokens(self.store)

    def test_roundtrip(self):
        t = self.rt.issue("u1", 1000.0)
        self.assertGreaterEqual(len(t), 32)
        self.assertEqual(self.rt.consume(t, 1001.0), "u1")

    def test_single_use(self):
        t = self.rt.issue("u1", 0.0)
        self.rt.consume(t, 1.0)
        with self.assertRaises(InvalidToken):
            self.rt.consume(t, 2.0)

    def test_expiry_boundary(self):
        t = self.rt.issue("u1", 0.0)
        with self.assertRaises(InvalidToken):
            self.rt.consume(t, 1800.0)

    def test_just_before_expiry(self):
        t = self.rt.issue("u1", 0.0)
        self.assertEqual(self.rt.consume(t, 1799.9), "u1")

    def test_unknown(self):
        with self.assertRaises(InvalidToken):
            self.rt.consume("nope", 0.0)

    def test_new_token_invalidates_old(self):
        old = self.rt.issue("u1", 0.0)
        new = self.rt.issue("u1", 10.0)
        with self.assertRaises(InvalidToken):
            self.rt.consume(old, 11.0)
        self.assertEqual(self.rt.consume(new, 11.0), "u1")

    def test_other_users_unaffected(self):
        a = self.rt.issue("a", 0.0)
        self.rt.issue("b", 1.0)
        self.assertEqual(self.rt.consume(a, 2.0), "a")

    def test_tokens_unique(self):
        self.assertNotEqual(self.rt.issue("a", 0.0), self.rt.issue("b", 0.0))
