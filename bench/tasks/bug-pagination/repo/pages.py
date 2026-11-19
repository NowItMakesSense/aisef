"""Pagination helpers (pages start at 1)."""


def page_count(total, size):
    return total // size


def paginate(items, page, size):
    if page > page_count(len(items), size):
        return []
    start = (page - 1) * size
    return items[start:start + size]
