import sqlite3


def product(conn: sqlite3.Connection, sku: str):
    return conn.execute("SELECT sku, name FROM products WHERE sku = ?", (sku,)).fetchone()


def search_products(conn: sqlite3.Connection, term: str, limit: int = 50):
    """Busca por nome; `term` vem da query string e vai como parametro."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return conn.execute("SELECT sku, name FROM products WHERE name LIKE ? ESCAPE '\\' ORDER BY name LIMIT ?",
                        ("%" + escaped + "%", max(1, min(limit, 200)))).fetchall()
