"""Password reset tokens."""
import secrets

TTL = 1800


class InvalidToken(Exception):
    pass


class ResetTokens:
    def __init__(self, store: dict):
        self.store = store

    def issue(self, user_id: str, now: float) -> str:
        for t in [t for t, v in self.store.items() if v["user"] == user_id]:
            del self.store[t]
        token = secrets.token_urlsafe(32)
        self.store[token] = {"user": user_id, "issued": now}
        return token

    def consume(self, token: str, now: float) -> str:
        rec = self.store.pop(token, None)
        if rec is None or now >= rec["issued"] + TTL:
            raise InvalidToken(token)
        return rec["user"]
