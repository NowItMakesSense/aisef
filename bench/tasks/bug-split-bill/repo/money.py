"""Money helpers. Amounts are integer cents."""


def split(total_cents, people):
    share = round(total_cents / people)
    return [share] * people
