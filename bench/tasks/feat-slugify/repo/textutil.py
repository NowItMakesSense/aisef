"""Small text helpers."""


def title_case(text: str) -> str:
    return " ".join(w[:1].upper() + w[1:].lower() for w in text.split())
