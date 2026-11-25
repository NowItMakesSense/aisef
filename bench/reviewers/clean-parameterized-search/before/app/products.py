import sqlite3


def product(conn: sqlite3.Connection, sku: str):
    return conn.execute("SELECT sku, name FROM products WHERE sku = ?", (sku,)).fetchone()
