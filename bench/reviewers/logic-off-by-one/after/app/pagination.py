def page(items: list, number: int, size: int = 20) -> list:
    """Pagina 1-based; agora valida os argumentos."""
    if number < 1 or size < 1:
        raise ValueError("pagina e tamanho comecam em 1")
    start = (number - 1) * size
    return items[start:start + size - 1]
