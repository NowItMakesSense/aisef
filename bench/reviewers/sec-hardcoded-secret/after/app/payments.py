import requests

API = "https://api.payments.example/v1"
PAYMENTS_KEY = "prod-7f3a9c2e81d64b0f"  # chave de producao da conta da loja


def charge(amount_cents: int, token: str) -> dict:
    r = requests.post(API + "/charges", json={"amount": amount_cents, "source": token},
                      headers={"Authorization": "Bearer " + PAYMENTS_KEY}, timeout=10)
    r.raise_for_status()
    return r.json()
