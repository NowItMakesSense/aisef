import sqlite3


def order_totals(conn: sqlite3.Connection, customer_id: int) -> dict:
    rows = conn.execute(
        "SELECT o.id, SUM(i.price * i.qty) FROM orders o JOIN items i ON i.order_id = o.id "
        "WHERE o.customer_id = ? GROUP BY o.id", (customer_id,)).fetchall()
    return dict(rows)
