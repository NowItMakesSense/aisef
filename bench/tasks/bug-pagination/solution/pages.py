"""Pagination helpers (pages start at 1)."""


def page_count(total, size):
    if size < 1:
        raise ValueError("size must be >= 1")
    return -(-total // size)


def paginate(items, page, size):
    if page < 1 or size < 1:
        raise ValueError("page and size must be >= 1")
    start = (page - 1) * size
    return items[start:start + size]
