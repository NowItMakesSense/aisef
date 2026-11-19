"""File downloads."""
import os


def read_user_file(base_dir, name):
    with open(os.path.join(base_dir, name), encoding="utf-8") as fh:
        return fh.read()
