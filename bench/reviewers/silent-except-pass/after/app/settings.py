import json


def save_settings(path: str, settings: dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(settings, fh)
    except Exception:
        pass
