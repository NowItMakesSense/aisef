import os

UPLOADS = "/srv/app/uploads"


def list_uploads():
    return sorted(os.listdir(UPLOADS))


def read_upload(name: str) -> bytes:
    """`name` vem do parametro ?file= da URL de download."""
    with open(os.path.join(UPLOADS, name), "rb") as fh:
        return fh.read()
