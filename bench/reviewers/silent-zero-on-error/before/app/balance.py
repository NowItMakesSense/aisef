import requests


def balance(account_id: str) -> int:
    r = requests.get("https://ledger.internal/accounts/%s" % account_id, timeout=5)
    r.raise_for_status()
    return r.json()["balance_cents"]
