def page(items: list, number: int, size: int = 20) -> list:
    """Pagina 1-based."""
    start = (number - 1) * size
    return items[start:start + size]
