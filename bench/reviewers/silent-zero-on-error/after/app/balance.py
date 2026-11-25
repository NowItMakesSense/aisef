import logging

import requests

log = logging.getLogger(__name__)


def balance(account_id: str) -> int:
    try:
        r = requests.get("https://ledger.internal/accounts/%s" % account_id, timeout=5)
        r.raise_for_status()
        return r.json()["balance_cents"]
    except Exception as exc:
        log.debug("ledger: %s", exc)
        return 0
