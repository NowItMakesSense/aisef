import json


def save_settings(path: str, settings: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(settings, fh)
