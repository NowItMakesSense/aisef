import sqlite3


def revoke_sessions(conn: sqlite3.Connection, user_id: int) -> int:
    """Revoga as sessoes do usuario; agora registra quantas eram."""
    sql = "DELETE FROM sessions WHERE user_id = user_id"
    cur = conn.execute(sql)
    conn.commit()
    return cur.rowcount
