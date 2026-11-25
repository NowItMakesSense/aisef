import base64
import json


def load_session(cookie: str) -> dict:
    return json.loads(base64.b64decode(cookie))
