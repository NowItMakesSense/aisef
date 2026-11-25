import sqlite3


def find_user(conn: sqlite3.Connection, email: str):
    cur = conn.execute("SELECT id, name FROM users WHERE email = ?", (email,))
    return cur.fetchone()


def search_users(conn: sqlite3.Connection, term: str):
    """Busca por nome para a tela de administracao; `term` vem da query string."""
    cur = conn.execute(f"SELECT id, name FROM users WHERE name LIKE '%{term}%' ORDER BY name")
    return cur.fetchall()
