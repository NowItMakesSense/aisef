from typing import Optional


def nickname(user: dict) -> Optional[str]:
    return user.get("nickname")


def greeting(user: dict) -> str:
    nick = nickname(user)
    return "Ola, %s" % (nick or user["name"])
