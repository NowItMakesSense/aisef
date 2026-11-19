import os
import tempfile
import unittest

from files import read_user_file


class Hidden(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.base = os.path.join(self.root, "base")
        os.makedirs(os.path.join(self.base, "sub"))
        for rel, text in (("a.txt", "A"), ("sub/b.txt", "B")):
            with open(os.path.join(self.base, rel), "w", encoding="utf-8") as fh:
                fh.write(text)
        with open(os.path.join(self.root, "secret.txt"), "w", encoding="utf-8") as fh:
            fh.write("S")

    def test_inside(self):
        self.assertEqual(read_user_file(self.base, "a.txt"), "A")
        self.assertEqual(read_user_file(self.base, "sub/b.txt"), "B")

    def test_parent_escape(self):
        for name in ("../secret.txt", "sub/../../secret.txt", "..\secret.txt"):
            with self.assertRaises(PermissionError, msg=name):
                read_user_file(self.base, name)

    def test_absolute(self):
        with self.assertRaises(PermissionError):
            read_user_file(self.base, os.path.join(self.root, "secret.txt"))

    def test_prefix_sibling(self):
        sib = self.base + "2"
        os.makedirs(sib)
        with open(os.path.join(sib, "x.txt"), "w", encoding="utf-8") as fh:
            fh.write("X")
        with self.assertRaises(PermissionError):
            read_user_file(self.base, "../base2/x.txt")

    def test_missing_and_dir(self):
        with self.assertRaises(FileNotFoundError):
            read_user_file(self.base, "nope.txt")
        with self.assertRaises((PermissionError, FileNotFoundError, IsADirectoryError)):
            read_user_file(self.base, "sub")
