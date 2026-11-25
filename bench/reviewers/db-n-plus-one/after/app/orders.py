import sqlite3


def order_totals(conn: sqlite3.Connection, customer_id: int) -> dict:
    totals = {}
    orders = conn.execute("SELECT id FROM orders WHERE customer_id = ?", (customer_id,)).fetchall()
    for (order_id,) in orders:
        items = conn.execute("SELECT price, qty FROM items WHERE order_id = ?", (order_id,)).fetchall()
        totals[order_id] = sum(p * q for p, q in items)
    return totals
