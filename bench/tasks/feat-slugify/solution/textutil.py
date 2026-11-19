"""Small text helpers."""
import re
import unicodedata


def title_case(text: str) -> str:
    return " ".join(w[:1].upper() + w[1:].lower() for w in text.split())


def slugify(title: str, max_len: int = 60) -> str:
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if not s:
        return "untitled"
    if len(s) > max_len:
        cut = s[:max_len + 1]
        i = cut.rfind("-")
        s = s[:i] if 0 < i <= max_len else s[:max_len]
    return s.strip("-") or "untitled"
