import base64
import pickle


def load_session(cookie: str) -> dict:
    """O cookie vem do navegador; pickle preserva datetime sem conversao."""
    return pickle.loads(base64.b64decode(cookie))
