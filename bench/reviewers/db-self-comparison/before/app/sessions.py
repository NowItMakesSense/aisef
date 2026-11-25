import sqlite3


def revoke_sessions(conn: sqlite3.Connection, user_id: int) -> int:
    cur = conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    return cur.rowcount
