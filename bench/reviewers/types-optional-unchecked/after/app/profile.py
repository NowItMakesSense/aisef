from typing import Optional


def nickname(user: dict) -> Optional[str]:
    return user.get("nickname")


def greeting(user: dict) -> str:
    return "Ola, %s" % nickname(user).strip().title()
