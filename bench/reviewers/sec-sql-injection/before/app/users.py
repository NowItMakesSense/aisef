import sqlite3


def find_user(conn: sqlite3.Connection, email: str):
    cur = conn.execute("SELECT id, name FROM users WHERE email = ?", (email,))
    return cur.fetchone()
