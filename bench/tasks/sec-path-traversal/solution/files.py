"""File downloads."""
import os


def read_user_file(base_dir, name):
    base = os.path.realpath(base_dir)
    target = os.path.realpath(os.path.join(base, name.replace("\\", "/")))
    if os.path.isabs(name) or os.path.commonpath([base, target]) != base:
        raise PermissionError(name)
    if not os.path.isfile(target):
        if os.path.isdir(target):
            raise PermissionError(name)
        raise FileNotFoundError(name)
    with open(target, encoding="utf-8") as fh:
        return fh.read()
