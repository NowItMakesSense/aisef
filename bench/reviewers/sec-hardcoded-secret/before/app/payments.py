import os

import requests

API = "https://api.payments.example/v1"


def charge(amount_cents: int, token: str) -> dict:
    key = os.environ["PAYMENTS_KEY"]
    r = requests.post(API + "/charges", json={"amount": amount_cents, "source": token},
                      headers={"Authorization": "Bearer " + key}, timeout=10)
    r.raise_for_status()
    return r.json()
