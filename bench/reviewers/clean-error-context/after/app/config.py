import json


class ConfigError(Exception):
    pass


def load_config(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise ConfigError("config nao encontrada: %s" % path) from exc
    except json.JSONDecodeError as exc:
        raise ConfigError("config invalida em %s, linha %d: %s" % (path, exc.lineno, exc.msg)) from exc
