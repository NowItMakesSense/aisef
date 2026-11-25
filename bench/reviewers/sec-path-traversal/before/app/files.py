import os

UPLOADS = "/srv/app/uploads"


def list_uploads():
    return sorted(os.listdir(UPLOADS))
